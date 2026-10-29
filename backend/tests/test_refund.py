"""退款测试：本人 + 已签收才能退，一单一退，越权一律拒绝。"""
from __future__ import annotations

import pytest

from app.tools.orders import query_order
from app.tools.refunds import list_refunds, request_refund


def test_owner_can_refund_signed_order():
    result = request_refund("1005", "u1003", "尺寸不合适")
    assert result["ok"] is True
    assert result["refund_id"] == "RF-1005"
    assert result["amount"] == 4599.0
    assert result["status"] == "requested"

    order = query_order("1005", "u1003")
    assert order["status"] == "refunding"
    assert order["status_text"] == "退款处理中"
    assert order["refund"]["refund_id"] == "RF-1005"
    assert order["events"][-1]["kind"] == "refund"


def test_refund_is_idempotent():
    request_refund("1005", "u1003")
    again = request_refund("1005", "u1003")
    assert again["ok"] is True
    assert again["code"] == "REFUND_EXISTS"
    assert again["refund_id"] == "RF-1005"
    assert len(list_refunds("u1003")) == 1


def test_cannot_refund_other_users_order():
    result = request_refund("1005", "u1001")
    assert result["ok"] is False
    assert result["code"] == "FORBIDDEN"
    assert "金额" not in result["message"]


def test_cannot_refund_unsigned_order():
    result = request_refund("1001", "u1001")
    assert result["ok"] is False
    assert result["code"] == "NOT_SIGNED"
    assert result["status"] == "shipped"


def test_cannot_refund_cancelled_order():
    result = request_refund("1006", "u1004")
    assert result["ok"] is False
    assert result["code"] == "NOT_SIGNED"


def test_refund_unknown_order():
    result = request_refund("9999", "u1001")
    assert result["ok"] is False
    assert result["code"] == "ORDER_NOT_FOUND"
    assert "1001" in result["available_order_ids"]


def test_query_order_hides_other_users_orders():
    result = query_order("1003", "u1001")
    assert result["ok"] is False
    assert result["code"] == "FORBIDDEN"
    assert "周一鸣" not in str(result)
    assert result["available_order_ids"] == ["1001", "1002"]


def login(client, user_id):
    token = client.post("/api/auth/login", json={"user_id": user_id, "password": "shop1234"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_order_api_only_returns_own_orders(client):
    items = client.get("/api/orders", headers=login(client, "u1001")).json()["items"]
    assert [o["order_id"] for o in items] == ["1001", "1002"]


def test_order_detail_404_for_other_users_order(client):
    assert client.get("/api/orders/1003", headers=login(client, "u1001")).status_code == 404
    assert client.get("/api/orders/1001", headers=login(client, "u1001")).status_code == 200


def test_refund_endpoint_status_codes(client):
    assert client.post("/api/orders/1005/refund", headers=login(client, "u1001")).status_code == 403
    assert client.post("/api/orders/1001/refund", headers=login(client, "u1001")).status_code == 409
    ok = client.post("/api/orders/1005/refund", json={"reason": "不喜欢"}, headers=login(client, "u1003"))
    assert ok.status_code == 200
    assert ok.json()["refund_id"] == "RF-1005"
