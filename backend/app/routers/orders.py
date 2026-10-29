"""订单与退款接口：只暴露当前用户的数据，业务失败用状态码表达。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core import auth
from app.tools.orders import list_orders, query_order
from app.tools.refunds import list_refunds, request_refund

router = APIRouter(prefix="/api/orders", tags=["orders"])

_STATUS = {
    "ORDER_NOT_FOUND": 404,
    "FORBIDDEN": 403,
    "NOT_SIGNED": 409,
    "INVALID_ORDER_ID": 400,
}


class RefundRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=120)


@router.get("")
def orders(user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    return {"items": list_orders(user["user_id"])}


@router.get("/refunds")
def refunds(user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    return {"items": list_refunds(user["user_id"])}


@router.get("/{order_id}")
def order_detail(order_id: str, user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    result = query_order(order_id, user["user_id"])
    if not result.get("ok"):
        # 越权也返回 404，不告诉对方"这单存在但不属于你"
        raise HTTPException(status_code=404, detail={"code": result.get("code"), "message": result.get("message")})
    from app.agents.order import public_order

    return public_order(result)


@router.post("/{order_id}/refund")
def refund(
    order_id: str,
    req: RefundRequest | None = None,
    user: dict[str, Any] = Depends(auth.current_user),
) -> dict[str, Any]:
    result = request_refund(order_id, user["user_id"], (req.reason if req else None))
    if result.get("ok"):
        return result
    raise HTTPException(
        status_code=_STATUS.get(result.get("code", ""), 400),
        detail={"code": result.get("code"), "message": result.get("message")},
    )
