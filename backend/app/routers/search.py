"""拍图搜同款：一次同步调用完成"识别 → 检索"，返回结构化特征与商品卡。"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents import guide
from app.config import settings
from app.core import auth, session as session_mod
from app.core.slots import extract_slots
from app.rag import vision

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])

_hits: dict[str, deque[float]] = {}
_lock = threading.Lock()


def _allow(user_id: str) -> bool:
    """识图要花 token，按用户做滑动窗口限流，防止被刷。"""
    limit = max(1, settings.image_search_per_minute)
    now = time.time()
    with _lock:
        bucket = _hits.setdefault(user_id, deque())
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
    return True


def reset_rate_limit() -> None:
    with _lock:
        _hits.clear()


class ImageSearchRequest(BaseModel):
    image_base64: str = Field(..., min_length=32, max_length=16_000_000)
    mime: str = Field(default="image/jpeg", max_length=32)
    session_id: str = Field(default="default", max_length=64)
    hint: str = Field(default="", max_length=200)
    budget_max: float | None = None


@router.post("/image")
def search_by_image(
    req: ImageSearchRequest, user: dict[str, Any] = Depends(auth.current_user)
) -> dict[str, Any]:
    if not _allow(user["user_id"]):
        raise HTTPException(
            status_code=429,
            detail={"code": "TOO_MANY_IMAGES", "message": "识图太频繁了，歇一分钟再试。"},
        )

    started = time.time()
    try:
        raw, mime = vision.decode_image(req.image_base64, req.mime)
    except vision.ImageError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc

    features = vision.describe(raw, mime, req.hint)

    # 品类既是提示词产物，也是 RAG 的硬过滤条件；预算优先用显式传参
    slots = extract_slots(req.hint)
    if features["category"] and not slots.get("category"):
        slots["category"] = features["category"]
    if req.budget_max is not None:
        slots["budget_max"] = float(req.budget_max)

    retrieval = guide.retrieve(vision.search_query(features), slots)
    items = retrieval.get("hits", [])

    # 写进会话，用户接着问"这个多少钱/有别的颜色吗"能指代
    state = session_mod.get_state(req.session_id, user["user_id"])
    if items:
        state.note_results([i["id"] for i in items], slots)
        state.add_turn("user", f"[上传了一张图片] 识别为：{features['summary']}")
        state.add_turn("assistant", f"按图找到 {len(items)} 款相似商品，主推 {items[0]['name']}。")
        session_mod.save_state(state)

    return {
        "ok": True,
        "features": vision.public_features(features),
        "keywords": features["keywords"],
        "products": items,
        "mode": retrieval.get("mode", "vector"),
        "degraded": features["degraded"],
        "reason": features["reason"],
        "elapsed_ms": int((time.time() - started) * 1000),
    }
