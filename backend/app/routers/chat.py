from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents import orchestrator
from app.core import auth, sse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="default", max_length=64)


class ChatResponse(BaseModel):
    answer: str
    intent: str
    products: list[dict[str, Any]] = []
    order: dict[str, Any] | None = None
    cart: dict[str, Any] | None = None
    refund: dict[str, Any] | None = None


def _collect(events) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    products: list[dict[str, Any]] = []
    order = None
    cart = None
    refund = None
    text: list[str] = []
    for event, data in events:
        if event == sse.PRODUCTS:
            products = data.get("items", [])
        elif event == sse.TOOL_RESULT and data.get("order"):
            order = data["order"]
        elif event == sse.CART:
            cart = data
        elif event == sse.REFUND:
            refund = data
        elif event == sse.DELTA:
            text.append(data.get("text", ""))
    return products, "".join(text), order, cart, refund


@router.post("/chat/stream")
def chat_stream(req: ChatRequest, user: dict[str, Any] = Depends(auth.current_user)) -> StreamingResponse:
    """SSE：meta / plan / step / products / reviews / compare / tool_* / cart / refund / delta / done。"""

    def event_stream():
        try:
            for event, data in orchestrator.stream_chat(req.message, req.session_id, user=user):
                yield sse.encode(event, data)
        except Exception as exc:  # noqa: BLE001 - 流里抛错必须变成 error 事件，不能断连
            logger.exception("stream crashed")
            yield sse.encode(sse.ERROR, {"code": "internal_error", "message": str(exc)})
            yield sse.encode(sse.DONE, {"reason": "error"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat", response_model=ChatResponse)
def chat_once(req: ChatRequest, user: dict[str, Any] = Depends(auth.current_user)) -> ChatResponse:
    """非流式版本：调试、脚本、pytest 都更方便。"""
    products, answer, order, cart, refund = _collect(
        orchestrator.stream_chat(req.message, req.session_id, user=user)
    )
    intent = "product" if products and not order else ("order" if order else "chitchat")
    return ChatResponse(answer=answer, intent=intent, products=products, order=order, cart=cart, refund=refund)
