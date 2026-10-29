"""购物车：同人同品合并数量，库存校验在服务端做（模型可能算错数字）。"""
from __future__ import annotations

import sqlite3
from typing import Any

from app.rag.products import LOOKUP_MAP
from app.tools.db import connect, now

MAX_QTY = 99


def resolve_product_id(raw: str) -> str | None:
    """模型可能传 id、也可能传商品名，这里统一兜一层。"""
    key = str(raw or "").strip().lower()
    if not key:
        return None
    if key in LOOKUP_MAP:
        return key
    for product in LOOKUP_MAP.values():
        name = product["name"].lower()
        if key == name or key in name or name in key:
            return product["id"]
    return None


def _coerce_qty(value: Any) -> int | None:
    try:
        qty = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    if qty < 1 or qty > MAX_QTY:
        return None
    return qty


def _items(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT product_id, quantity FROM carts WHERE user_id = ? ORDER BY id", (user_id,)
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        product = LOOKUP_MAP.get(row["product_id"])
        if product is None:
            continue
        qty = int(row["quantity"])
        items.append(
            {
                "product_id": product["id"],
                "name": product["name"],
                "price": float(product["price"]),
                "image": product.get("image", ""),
                "category": product["category"],
                "quantity": qty,
                "subtotal": round(float(product["price"]) * qty, 2),
                "stock": int(product["stock"]),
            }
        )
    return items


def cart_snapshot(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": items,
        "count": sum(i["quantity"] for i in items),
        "total": round(sum(i["subtotal"] for i in items), 2),
    }


def get_cart(user_id: str) -> dict[str, Any]:
    with connect() as conn:
        return cart_snapshot(_items(conn, user_id))


def add_to_cart(user_id: str, product_id: str, quantity: Any = 1) -> dict[str, Any]:
    pid = resolve_product_id(product_id)
    if pid is None:
        return {
            "ok": False,
            "code": "PRODUCT_NOT_FOUND",
            "message": f"没有找到商品「{product_id}」，请确认商品编号。",
            "cart": get_cart(user_id),
        }

    qty = _coerce_qty(quantity)
    if qty is None:
        return {
            "ok": False,
            "code": "INVALID_QUANTITY",
            "message": f"数量需要是 1-{MAX_QTY} 之间的整数。",
            "cart": get_cart(user_id),
        }

    product = LOOKUP_MAP[pid]
    stock = int(product["stock"])
    ts = now()
    with connect() as conn:
        row = conn.execute(
            "SELECT quantity FROM carts WHERE user_id = ? AND product_id = ?", (user_id, pid)
        ).fetchone()
        existing = int(row["quantity"]) if row else 0
        if existing + qty > stock:
            snapshot = cart_snapshot(_items(conn, user_id))
            return {
                "ok": False,
                "code": "OUT_OF_STOCK",
                "message": f"{product['name']} 库存只剩 {stock} 件，购物车里已有 {existing} 件。",
                "stock": stock,
                "in_cart": existing,
                "cart": snapshot,
            }

        conn.execute(
            "INSERT INTO carts (user_id, product_id, quantity, created_at, updated_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, product_id) DO UPDATE SET "
            "quantity = MIN(?, quantity + excluded.quantity), updated_at = excluded.updated_at",
            (user_id, pid, qty, ts, ts, MAX_QTY),
        )
        conn.commit()
        snapshot = cart_snapshot(_items(conn, user_id))

    return {
        "ok": True,
        "product_id": pid,
        "product_name": product["name"],
        "price": float(product["price"]),
        "added": qty,
        "quantity": next((i["quantity"] for i in snapshot["items"] if i["product_id"] == pid), qty),
        "message": f"已把 {product['name']} ×{qty} 加入购物车。",
        "cart": snapshot,
    }


def set_quantity(user_id: str, product_id: str, quantity: Any) -> dict[str, Any]:
    pid = resolve_product_id(product_id)
    if pid is None:
        return {"ok": False, "code": "PRODUCT_NOT_FOUND", "message": "商品不存在", "cart": get_cart(user_id)}
    try:
        qty = int(float(str(quantity).strip()))
    except (TypeError, ValueError):
        return {"ok": False, "code": "INVALID_QUANTITY", "message": "数量不合法", "cart": get_cart(user_id)}

    if qty <= 0:
        return remove_item(user_id, pid)
    if qty > MAX_QTY:
        return {"ok": False, "code": "INVALID_QUANTITY", "message": f"单件商品最多 {MAX_QTY} 件", "cart": get_cart(user_id)}
    if qty > int(LOOKUP_MAP[pid]["stock"]):
        return {"ok": False, "code": "OUT_OF_STOCK", "message": "库存不足", "cart": get_cart(user_id)}

    with connect() as conn:
        conn.execute(
            "UPDATE carts SET quantity = ?, updated_at = ? WHERE user_id = ? AND product_id = ?",
            (qty, now(), user_id, pid),
        )
        conn.commit()
        snapshot = cart_snapshot(_items(conn, user_id))
    return {"ok": True, "cart": snapshot, "message": "已更新数量"}


def remove_item(user_id: str, product_id: str) -> dict[str, Any]:
    pid = resolve_product_id(product_id) or str(product_id)
    with connect() as conn:
        conn.execute("DELETE FROM carts WHERE user_id = ? AND product_id = ?", (user_id, pid))
        conn.commit()
        snapshot = cart_snapshot(_items(conn, user_id))
    return {"ok": True, "cart": snapshot, "message": "已从购物车移除"}


def clear_cart(user_id: str) -> dict[str, Any]:
    with connect() as conn:
        conn.execute("DELETE FROM carts WHERE user_id = ?", (user_id,))
        conn.commit()
    return {"ok": True, "cart": cart_snapshot([]), "message": "购物车已清空"}


def cart_summary(cart: dict[str, Any]) -> str:
    if not cart["items"]:
        return "购物车目前是空的。"
    lines = [f"- {i['name']} ×{i['quantity']}（¥{i['price']}）" for i in cart["items"]]
    return "\n".join(lines) + f"\n合计：¥{cart['total']:.2f}，共 {cart['count']} 件"
