"""商品目录：列表 / 详情 / 对比，只读，允许匿名访问。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.agents import compare as compare_agent
from app.rag import review_store, store
from app.rag.products import PRODUCTS, public
from app.rag.reviews import summarize

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/products")
def products() -> dict[str, Any]:
    return {"items": store.all_products()}


@router.get("/products/compare")
def compare(ids: str = Query(..., description="两个商品 id，逗号分隔，例如 p03,p04")) -> dict[str, Any]:
    parts = [p.strip() for p in ids.split(",") if p.strip()]
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IDS", "message": "需要恰好两个商品 id"})
    result = compare_agent.compare(parts[0], parts[1])
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail={"code": result.get("code"), "message": result.get("message")})
    return result


@router.get("/products/{product_id}")
def product_detail(product_id: str) -> dict[str, Any]:
    product = next((p for p in PRODUCTS if p["id"] == product_id.lower()), None)
    if product is None:
        raise HTTPException(status_code=404, detail={"code": "PRODUCT_NOT_FOUND", "message": "商品不存在"})
    return {
        **public(product),
        "specs": product.get("specs", {}),
        "selling_point": product.get("selling_point"),
        "audience": product.get("audience"),
        "tags": product.get("tags", []),
        "reviews": summarize(product["id"]),
    }


@router.get("/health")
def health() -> dict[str, Any]:
    from app.rag.embedding import get_embedder

    embedder = get_embedder()
    return {
        "status": "ok",
        "embedding": embedder.name,
        "products": store.get_collection().count(),
        "reviews": review_store.count(),
    }
