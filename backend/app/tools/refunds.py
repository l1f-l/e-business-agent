"""退款：只允许「本人 + 已签收」的订单发起，一单一退，状态流转在事务里完成。"""
from __future__ import annotations

from typing import Any

from app.tools.db import connect, now, status_text
from app.tools.orders import normalize_order_id

REFUNDABLE = {"signed"}


def request_refund(order_id: str, user_id: str, reason: str | None = None) -> dict[str, Any]:
    oid = normalize_order_id(order_id)
    if not oid:
        return {"ok": False, "code": "INVALID_ORDER_ID", "message": "请提供要退款的订单号。"}

    with connect() as conn:
        order = conn.execute("SELECT * FROM orders WHERE order_id = ?", (oid,)).fetchone()
        if order is None:
            owned = [
                r["order_id"]
                for r in conn.execute(
                    "SELECT order_id FROM orders WHERE user_id = ? ORDER BY order_id", (user_id,)
                ).fetchall()
            ]
            return {
                "ok": False,
                "code": "ORDER_NOT_FOUND",
                "order_id": oid,
                "message": f"没有找到订单 {oid}，请核对订单号。",
                "available_order_ids": owned[:6],
            }

        if order["user_id"] != user_id:
            return {
                "ok": False,
                "code": "FORBIDDEN",
                "order_id": oid,
                "message": "该订单不在当前账号下，无法发起退款。请切换到下单时使用的账号。",
            }

        existing = conn.execute("SELECT * FROM refunds WHERE order_id = ?", (oid,)).fetchone()
        if existing is not None:
            return {
                "ok": True,
                "code": "REFUND_EXISTS",
                "refund_id": existing["refund_id"],
                "order_id": oid,
                "status": existing["status"],
                "status_text": "退款处理中" if existing["status"] == "requested" else existing["status"],
                "amount": existing["amount"],
                "message": f"订单 {oid} 已经提交过退款（{existing['refund_id']}），请勿重复申请。",
            }

        status = order["status"]
        if status not in REFUNDABLE:
            return {
                "ok": False,
                "code": "NOT_SIGNED",
                "order_id": oid,
                "status": status,
                "status_text": status_text(status),
                "message": f"订单 {oid} 当前状态是「{status_text(status)}」，只有已签收的订单可以申请退款。",
            }

        refund_id = f"RF-{oid}"
        ts = now()
        conn.execute(
            "UPDATE orders SET status = 'refunding', refund_status = 'requested' WHERE order_id = ?",
            (oid,),
        )
        conn.execute(
            "INSERT INTO refunds (refund_id, order_id, user_id, amount, reason, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (refund_id, oid, user_id, float(order["amount"]), (reason or "用户申请退款")[:120], "requested", ts),
        )
        conn.execute(
            "INSERT INTO order_events (order_id, ts, description, location, kind) VALUES (?,?,?,?,?)",
            (oid, ts, "已提交退款申请，等待商家审核", "线上", "refund"),
        )
        conn.commit()

    return {
        "ok": True,
        "code": "REFUND_CREATED",
        "refund_id": refund_id,
        "order_id": oid,
        "status": "requested",
        "status_text": "退款处理中",
        "amount": float(order["amount"]),
        "product_name": order["product_name"],
        "message": f"订单 {oid} 的退款已提交，金额 ¥{float(order['amount']):.2f}，预计 1-3 个工作日原路退回。",
    }


def list_refunds(user_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM refunds WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [
        {
            "refund_id": r["refund_id"],
            "order_id": r["order_id"],
            "amount": r["amount"],
            "status": r["status"],
            "reason": r["reason"],
            "created_at": r["created_at"],
            "status_text": "退款处理中" if r["status"] == "requested" else r["status"],
        }
        for r in rows
    ]
