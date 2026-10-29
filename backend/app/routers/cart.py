"""购物车接口：所有读写都限定在当前 token 对应的用户。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core import auth
from app.tools import cart as cart_tool

router = APIRouter(prefix="/api/cart", tags=["cart"])


class AddItemRequest(BaseModel):
    product_id: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(default=1, ge=1, le=99)


class UpdateItemRequest(BaseModel):
    quantity: int = Field(..., ge=0, le=99)


@router.get("")
def get_cart(user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    return cart_tool.get_cart(user["user_id"])


@router.post("/items")
def add_item(req: AddItemRequest, user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    return cart_tool.add_to_cart(user["user_id"], req.product_id, req.quantity)


@router.patch("/items/{product_id}")
def update_item(
    product_id: str, req: UpdateItemRequest, user: dict[str, Any] = Depends(auth.current_user)
) -> dict[str, Any]:
    return cart_tool.set_quantity(user["user_id"], product_id, req.quantity)


@router.delete("/items/{product_id}")
def delete_item(product_id: str, user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    return cart_tool.remove_item(user["user_id"], product_id)


@router.delete("")
def clear(user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    return cart_tool.clear_cart(user["user_id"])
