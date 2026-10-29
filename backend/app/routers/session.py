"""会话调试接口：查看/清空当前 session 的记忆内容。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core import auth, session as session_mod

router = APIRouter(prefix="/api/session", tags=["session"])


@router.get("/{session_id}")
def inspect(session_id: str, user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    state = session_mod.get_state(session_id, user["user_id"])
    if state.user_id != user["user_id"]:
        return {"session_id": session_id, "turns": [], "focus_product": None}
    return {
        "session_id": session_id,
        "user_id": state.user_id,
        "turns": list(state.turns),
        "focus_product": {
            "id": state.focus_product_id,
            "name": state.focus_name(),
        }
        if state.focus_product_id
        else None,
        "last_product_ids": state.last_product_ids,
        "last_category": state.last_category,
        "last_budget_max": state.last_budget_max,
    }


@router.delete("/{session_id}")
def clear(session_id: str, user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    session_mod.clear_session(session_id)
    return {"ok": True, "session_id": session_id}
