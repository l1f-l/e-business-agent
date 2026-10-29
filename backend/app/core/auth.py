"""JWT 鉴权、密码哈希、登录限流。

设计要点：
1. token 只放 user_id（sub），不放角色/昵称——避免改了昵称还要等 token 过期；
2. 工具层的 user_id 一律从 token 解出来再注入，模型没有任何途径指定别人的 id；
3. 登录失败按 user_id 计数（内存滑动窗口），5 次 / 5 分钟，防止弱口令爆破。
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any

import bcrypt
import jwt
from fastapi import HTTPException, Request
from starlette.datastructures import Headers

from app.config import settings
from app.tools.db import DEMO_PASSWORD_HASH, connect, now

MAX_PASSWORD_BYTES = 72  # bcrypt 的硬上限，超长直接截断而不是抛错


class AuthError(Exception):
    def __init__(self, code: str, message: str = "登录状态无效") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------- 密码 ----------------
def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8")[:MAX_PASSWORD_BYTES], bcrypt.gensalt(rounds=10)).decode()


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8")[:MAX_PASSWORD_BYTES], hashed.encode())
    except (ValueError, TypeError):
        return False


# ---------------- JWT ----------------
def create_token(user_id: str) -> tuple[str, int]:
    expires_in = settings.jwt_expire_minutes * 60
    payload = {
        "sub": user_id,
        "typ": "access",
        "jti": uuid.uuid4().hex[:12],
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("TOKEN_EXPIRED", "登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("TOKEN_INVALID", "登录状态无效，请重新登录") from exc
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        raise AuthError("TOKEN_INVALID", "登录状态无效，请重新登录")
    return user_id


# ---------------- 用户 ----------------
def public_user(row: Any) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "display_name": row["display_name"],
        "created_at": row["created_at"],
    }


def get_user(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return public_user(row) | {"password_hash": row["password_hash"]}


def create_user(user_id: str, password: str, display_name: str | None = None) -> dict[str, Any]:
    user_id = (user_id or "").strip()
    if not (3 <= len(user_id) <= 32) or not all(c.isalnum() or c in "_-" for c in user_id):
        raise AuthError("INVALID_USER_ID", "user_id 需为 3-32 位字母、数字、下划线或短横线")
    if len(password or "") < settings.password_min_length:
        raise AuthError("WEAK_PASSWORD", f"密码至少 {settings.password_min_length} 位")

    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if exists:
            raise AuthError("USER_EXISTS", "该 user_id 已被注册，请直接登录")
        conn.execute(
            "INSERT INTO users (user_id, display_name, password_hash, created_at) VALUES (?,?,?,?)",
            (user_id, (display_name or user_id).strip()[:32], hash_password(password), now()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return public_user(row)


def authenticate(user_id: str, password: str) -> dict[str, Any] | None:
    """恒定开销：用户不存在也跑一次哈希校验，避免用时间差探测账号是否存在。"""
    user = get_user((user_id or "").strip())
    if user is None:
        verify_password(password or "", DEMO_PASSWORD_HASH)
        return None
    if not verify_password(password or "", user["password_hash"]):
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}


# ---------------- 登录限流 ----------------
_LOCK = threading.Lock()
_FAILS: dict[str, deque[float]] = {}


def _prune(bucket: deque[float]) -> None:
    deadline = time.time() - settings.login_window_seconds
    while bucket and bucket[0] < deadline:
        bucket.popleft()


def check_login_allowed(user_id: str) -> bool:
    with _LOCK:
        bucket = _FAILS.get(user_id)
        if not bucket:
            return True
        _prune(bucket)
        return len(bucket) < settings.login_max_attempts


def record_login_failure(user_id: str) -> int:
    with _LOCK:
        bucket = _FAILS.setdefault(user_id, deque(maxlen=32))
        _prune(bucket)
        bucket.append(time.time())
        return settings.login_max_attempts - len(bucket)


def clear_login_failures(user_id: str) -> None:
    with _LOCK:
        _FAILS.pop(user_id, None)


def reset_login_failures() -> None:
    with _LOCK:
        _FAILS.clear()


# ---------------- 中间件与依赖 ----------------
class AuthContextMiddleware:
    """纯 ASGI 中间件：只解析、不拦截（拦截交给依赖），避免给 SSE 加缓冲。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        # 优先读 X-Auth-Token：部分托管平台的网关会覆写 Authorization（塞自己的 token），
        # 直接读 Authorization 会拿到别人的东西，全部解成 TOKEN_INVALID。
        raw = headers.get("x-auth-token") or headers.get("authorization", "")
        user_id: str | None = None
        auth_error: str | None = None
        if raw.lower().startswith("bearer "):
            raw = raw[7:]
        raw = raw.strip()
        if raw:
            try:
                user_id = decode_token(raw)
            except AuthError as exc:
                auth_error = exc.code

        state = scope.setdefault("state", {})
        state["user_id"] = user_id
        state["auth_error"] = auth_error
        await self.app(scope, receive, send)


def current_user(request: Request) -> dict[str, Any]:
    """FastAPI 依赖：没有有效 token 直接 401（在开流之前返回 JSON）。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        code = getattr(request.state, "auth_error", None) or "UNAUTHORIZED"
        message = "请先登录" if code == "UNAUTHORIZED" else "登录已失效，请重新登录"
        raise HTTPException(status_code=401, detail={"code": code, "message": message})
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={"code": "USER_NOT_FOUND", "message": "账号不存在"})
    return {k: v for k, v in user.items() if k != "password_hash"}
