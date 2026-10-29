"""评论向量库：与商品库分开建集合，按 product_id 元数据过滤后再做语义排序。

为什么必须先过滤再排序：
用户问"这耳机有什么优缺点"时，评论库里 10 个商品的评论混在一起，
不做 product_id 过滤会召回别家的差评，生成"客观总结"就变成了张冠李戴。
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.config import settings
from app.rag.embedding import get_embedder
from app.rag.reviews import REVIEWS, public_review, sentiment_of, to_document
from app.rag.store import _client  # 复用同一个 PersistentClient

logger = logging.getLogger(__name__)


def collection_name() -> str:
    return f"reviews_{get_embedder().name}"


@lru_cache(maxsize=2)
def _collection(_name: str):
    client = _client()
    name = collection_name()
    embedder = get_embedder()

    try:
        col = client.get_collection(name=name, embedding_function=None)
        if col.count() == len(REVIEWS) and (col.metadata or {}).get("dim") == embedder.dim:
            return col
        client.delete_collection(name)
    except Exception:  # noqa: BLE001 - 不存在或维度不符都重建
        pass

    col = client.create_collection(
        name=name,
        metadata={"hnsw:space": "cosine", "dim": embedder.dim},
        embedding_function=None,
    )
    docs = [to_document(r) for r in REVIEWS]
    col.add(
        ids=[r["id"] for r in REVIEWS],
        documents=docs,
        embeddings=embedder.encode(docs),
        metadatas=[
            {
                "product_id": r["product_id"],
                "rating": int(r["rating"]),
                "sentiment": sentiment_of(r["rating"]),
                "helpful": int(r.get("helpful", 0)),
            }
            for r in REVIEWS
        ],
    )
    logger.info("评论库已构建：%s（%d 条）", name, col.count())
    return col


def get_collection():
    return _collection(collection_name())


def search(
    query: str,
    product_ids: list[str] | None = None,
    k: int | None = None,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    col = get_collection()
    total = col.count()
    if total == 0:
        return []

    k = k or settings.review_top_k
    min_score = settings.review_min_score if min_score is None else min_score
    where = {"product_id": {"$in": list(product_ids)}} if product_ids else None

    query_vec = get_embedder().encode([query], is_query=True)[0]
    result = col.query(
        query_embeddings=[query_vec],
        n_results=min(k, total),
        where=where,
        include=["metadatas", "distances"],
    )

    hits: list[dict[str, Any]] = []
    from app.rag.reviews import REVIEW_MAP

    for i, rid in enumerate(result["ids"][0]):
        distance = float(result["distances"][0][i])
        score = max(0.0, min(1.0, 1.0 - distance))
        if score < min_score:
            continue
        review = REVIEW_MAP.get(rid)
        if review is None:
            continue
        hits.append(public_review(review, score=score))
    return hits


def count() -> int:
    return get_collection().count()


def reset() -> None:
    name = collection_name()
    _collection.cache_clear()
    try:
        _client().delete_collection(name)
    except Exception:  # noqa: BLE001
        pass
