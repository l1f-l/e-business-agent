"""订单查询：所有入口都必须带 user_id，跨用户一律拒绝。

为什么把 user_id 做成必传的内部参数、而不是工具 schema 的一部分：
模型看不到也填不了这个字段，用户就算在对话里自称别人，也改不了实际过滤条件。
"""
from __future__ import annotations

from typing import Any

from app.tools.db import connect, public_row, status_text


def _fetch_events(conn, order_id: str) -> list[dict[str, Any]]:
    return [
        {"time": e["ts"], "description": e["description"], "location": e["location"], "kind": e["kind"]}
        for e in conn.execute(
            "SELECT ts, description, location, kind FROM order_events WHERE order_id = ? ORDER BY ts",
            (order_id,),
        ).fetchall()
    ]


def _available_ids(conn, user_id: str | None) -> list[str]:
    if user_id:
        rows = conn.execute(
            "SELECT order_id FROM orders WHERE user_id = ? ORDER BY order_id", (user_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT order_id FROM orders ORDER BY order_id").fetchall()
    return [r["order_id"] for r in rows]


def normalize_order_id(order_id: str) -> str:
    normalized = str(order_id or "").strip().upper()
    normalized = normalized.removeprefix("ORDER").removeprefix("ORD").strip("-").strip()
    return normalized


def query_order(order_id: str, user_id: str | None = None) -> dict[str, Any]:
    """查询订单：成功返回订单 + 轨迹；失败返回 ok=False 与原因码。

    user_id 为空表示内部调用（脚本/测试），HTTP 入口永远会传真实用户。
    """
    normalized = normalize_order_id(order_id)

    with connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (normalized,)).fetchone()
        if row is None:
            return {
                "ok": False,
                "code": "ORDER_NOT_FOUND",
                "order_id": normalized,
                "message": f"没有找到订单 {normalized}，请核对订单号后重试。",
                "available_order_ids": _available_ids(conn, user_id)[:6],
            }

        # 越权：不区分"不存在"和"不属于你"以外的信息，绝不透露归属人/金额/地址
        if user_id and row["user_id"] and row["user_id"] != user_id:
            return {
                "ok": False,
                "code": "FORBIDDEN",
                "order_id": normalized,
                "message": "该订单不在当前账号下。请确认订单号，或切换到下单时使用的账号。",
                "available_order_ids": _available_ids(conn, user_id)[:6],
            }

        events = _fetch_events(conn, normalized)
        refund = conn.execute(
            "SELECT refund_id, status, created_at FROM refunds WHERE order_id = ?", (normalized,)
        ).fetchone()

    status = row["status"]
    latest = events[-1]["description"] if events else status_text(status)
    result = {
        "ok": True,
        "order_id": row["order_id"],
        "product_id": row["product_id"],
        "product_name": row["product_name"],
        "qty": row["qty"],
        "amount": row["amount"],
        "status": status,
        "status_text": status_text(status),
        "created_at": row["created_at"],
        "carrier": row["carrier"],
        "tracking_no": row["tracking_no"],
        "address": row["address"],
        "eta": row["eta"],
        "refundable": status == "signed" and refund is None,
        "latest_event": latest,
        "events": events[-4:],
    }
    if refund:
        result["refund"] = {"refund_id": refund["refund_id"], "status": refund["status"]}
    result["customer"] = row["customer"]
    return result


def order_summary(result: dict[str, Any]) -> str:
    """给模型看的紧凑文本，别把原始 JSON 全塞进 prompt。"""
    if not result.get("ok"):
        return result.get("message", "订单查询失败")
    lines = [
        f"订单号：{result['order_id']}（归属：{result.get('customer', '当前用户')}）",
        f"商品：{result['product_name']} ×{result['qty']}",
        f"金额：¥{result['amount']:.2f}",
        f"状态：{result['status_text']}",
        f"下单时间：{result['created_at']}",
    ]
    if result.get("carrier"):
        lines.append(f"承运商：{result['carrier']}（运单号 {result.get('tracking_no')}）")
    if result.get("eta"):
        lines.append(f"预计送达：{result['eta']}")
    if result.get("refund"):
        lines.append(f"退款单：{result['refund']['refund_id']}，进度 {result['refund']['status']}")
    elif result.get("refundable"):
        lines.append("可退款：是（已签收，未申请过退款）")
    if result.get("events"):
        lines.append("物流轨迹：")
        lines.extend(f"  - {e['time']} {e['description']}" for e in result["events"][-4:])
    return "\n".join(lines)


def list_orders(user_id: str | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM orders WHERE user_id = ? ORDER BY order_id", (user_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM orders ORDER BY order_id").fetchall()
    return [
        {
            "order_id": r["order_id"],
            "product_name": r["product_name"],
            "amount": r["amount"],
            "status": r["status"],
            "status_text": status_text(r["status"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_order_row(order_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (normalize_order_id(order_id),)).fetchone()
    return public_row(row) if row else None
