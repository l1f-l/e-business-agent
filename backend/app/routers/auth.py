"""登录 / 注册 / 当前用户。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    user_id: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)  # 强度由 auth 校验，保证返回统一错误码
    display_name: str | None = Field(default=None, max_length=32)


def _issue(user: dict[str, Any]) -> dict[str, Any]:
    token, expires_in = auth.create_token(user["user_id"])
    return {"token": token, "token_type": "bearer", "expires_in": expires_in, "user": user}


@router.post("/login")
def login(req: LoginRequest) -> dict[str, Any]:
    user_id = req.user_id.strip()
    if not auth.check_login_allowed(user_id):
        raise HTTPException(
            status_code=429,
            detail={"code": "TOO_MANY_ATTEMPTS", "message": "尝试次数过多，请 5 分钟后再试"},
        )

    user = auth.authenticate(user_id, req.password)
    if user is None:
        remaining = auth.record_login_failure(user_id)
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_CREDENTIALS", "message": f"账号或密码不正确，还可尝试 {max(remaining, 0)} 次"},
        )

    auth.clear_login_failures(user_id)
    return _issue(user)


@router.post("/register")
def register(req: RegisterRequest) -> dict[str, Any]:
    try:
        user = auth.create_user(req.user_id, req.password, req.display_name)
    except auth.AuthError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    return _issue(user)


@router.get("/me")
def me(user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    return {"user": user}
