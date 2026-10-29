"""鉴权测试：签发、过期、篡改、限流、跨用户隔离。"""
from __future__ import annotations

import time

import jwt
import pytest

from app.config import settings
from app.core import auth


def login(client, user_id="u1001", password="shop1234"):
    return client.post("/api/auth/login", json={"user_id": user_id, "password": password})


def test_demo_user_can_login(client):
    resp = login(client)
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"]
    assert data["token_type"] == "bearer"
    assert data["user"]["display_name"] == "林一"
    assert "password_hash" not in data["user"]


def test_wrong_password_rejected(client):
    resp = login(client, password="wrong-pass")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_unknown_user_uses_same_error(client):
    resp = login(client, user_id="nobody", password="whatever")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_register_then_login(client):
    resp = client.post("/api/auth/register", json={"user_id": "alice", "password": "hello123", "display_name": "Alice"})
    assert resp.status_code == 200
    assert resp.json()["user"]["user_id"] == "alice"
    assert login(client, "alice", "hello123").status_code == 200


def test_register_rejects_duplicate_and_weak_password(client):
    dup = client.post("/api/auth/register", json={"user_id": "u1002", "password": "hello123"})
    assert dup.status_code == 400
    assert dup.json()["detail"]["code"] == "USER_EXISTS"

    weak = client.post("/api/auth/register", json={"user_id": "bob", "password": "123"})
    assert weak.status_code == 400
    assert weak.json()["detail"]["code"] == "WEAK_PASSWORD"

    bad_id = client.post("/api/auth/register", json={"user_id": "a b", "password": "hello123"})
    assert bad_id.status_code == 400


def test_me_requires_token(client, auth_headers):
    assert client.get("/api/auth/me").status_code == 401
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["user"]["user_id"] == "u1001"


@pytest.mark.parametrize("token", ["", "not-a-jwt", "Bearer x"])
def test_garbage_token_rejected(client, token):
    headers = {"Authorization": token} if token else {}
    assert client.get("/api/cart", headers=headers).status_code == 401


def test_expired_token_rejected():
    expired = jwt.encode(
        {"sub": "u1001", "exp": int(time.time()) - 10, "iat": int(time.time()) - 100},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(auth.AuthError) as exc:
        auth.decode_token(expired)
    assert exc.value.code == "TOKEN_EXPIRED"


def test_token_signed_with_other_secret_rejected():
    forged = jwt.encode({"sub": "u1001", "exp": int(time.time()) + 600}, "other-secret", algorithm="HS256")
    with pytest.raises(auth.AuthError) as exc:
        auth.decode_token(forged)
    assert exc.value.code == "TOKEN_INVALID"


def test_login_throttled_after_repeated_failures(client):
    for _ in range(settings.login_max_attempts):
        assert login(client, password="bad-pass").status_code == 401
    resp = login(client, password="shop1234")
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "TOO_MANY_ATTEMPTS"


def test_cart_is_isolated_between_users(client):
    t1 = login(client, "u1001").json()["token"]
    t3 = login(client, "u1003").json()["token"]
    h1 = {"Authorization": f"Bearer {t1}"}
    h3 = {"Authorization": f"Bearer {t3}"}

    client.post("/api/cart/items", json={"product_id": "p03", "quantity": 1}, headers=h1)
    assert client.get("/api/cart", headers=h3).json()["count"] == 0
    assert client.get("/api/cart", headers=h1).json()["count"] == 1
