"""购物车测试：累加、库存、数量边界、用户隔离。"""
from __future__ import annotations

import pytest

from app.tools import cart as cart_tool


MEMBERS = {"u1001": "shop1234", "u1002": "shop1234"}


def token(client, user_id: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"user_id": user_id, "password": "shop1234"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_add_returns_full_snapshot():
    result = cart_tool.add_to_cart("u1001", "p03", 1)
    assert result["ok"] is True
    assert result["cart"]["count"] == 1
    assert result["cart"]["total"] == 499.0
    assert result["cart"]["items"][0]["name"] == "声浪 Air Pro"
    assert result["quantity"] == 1


def test_same_product_accumulates():
    cart_tool.add_to_cart("u1001", "p03", 1)
    result = cart_tool.add_to_cart("u1001", "p03", 2)
    assert result["quantity"] == 3
    assert result["cart"]["count"] == 3
    assert len(result["cart"]["items"]) == 1


def test_accepts_product_name_as_reference():
    result = cart_tool.add_to_cart("u1001", "声浪 Air Pro", 1)
    assert result["ok"] is True
    assert result["product_id"] == "p03"


def test_unknown_product_rejected():
    result = cart_tool.add_to_cart("u1001", "p99", 1)
    assert result["ok"] is False
    assert result["code"] == "PRODUCT_NOT_FOUND"


@pytest.mark.parametrize("qty", [0, -1, 100, "abc"])
def test_invalid_quantity_rejected(qty):
    result = cart_tool.add_to_cart("u1001", "p03", qty)
    assert result["ok"] is False
    assert result["code"] == "INVALID_QUANTITY"


def test_stock_limit_enforced():
    result = cart_tool.add_to_cart("u1001", "p07", 99)
    assert result["ok"] is False
    assert result["code"] == "OUT_OF_STOCK"
    assert result["stock"] == 15


def test_set_quantity_zero_removes_item():
    cart_tool.add_to_cart("u1001", "p03", 2)
    result = cart_tool.set_quantity("u1001", "p03", 0)
    assert result["ok"] is True
    assert result["cart"]["count"] == 0


def test_remove_and_clear():
    cart_tool.add_to_cart("u1001", "p03", 1)
    cart_tool.add_to_cart("u1001", "p04", 2)
    removed = cart_tool.remove_item("u1001", "p03")
    assert removed["cart"]["count"] == 2
    cleared = cart_tool.clear_cart("u1001")
    assert cleared["cart"] == {"items": [], "count": 0, "total": 0}


def test_other_users_cart_is_invisible():
    cart_tool.add_to_cart("u1002", "p03", 4)
    assert cart_tool.get_cart("u1001")["count"] == 0
    assert cart_tool.get_cart("u1002")["count"] == 4


def test_cart_api_requires_auth(client):
    assert client.get("/api/cart").status_code == 401
    assert client.post("/api/cart/items", json={"product_id": "p03"}).status_code == 401


def test_cart_api_roundtrip(client):
    headers = token(client, "u1001")
    added = client.post("/api/cart/items", json={"product_id": "p03", "quantity": 2}, headers=headers).json()
    assert added["cart"]["count"] == 2

    patched = client.patch("/api/cart/items/p03", json={"quantity": 5}, headers=headers).json()
    assert patched["cart"]["count"] == 5

    deleted = client.delete("/api/cart/items/p03", headers=headers).json()
    assert deleted["cart"]["count"] == 0
