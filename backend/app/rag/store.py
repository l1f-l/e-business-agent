"""Chroma 商品知识库：自己算向量（embedding_function=None），避免 Chroma 版本间的
默认嵌入模型差异，也让离线/在线两种嵌入可以无缝切换。
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.rag.embedding import get_embedder
from app.rag.products import PRODUCTS, PRODUCT_MAP, public, to_document

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client():
    return chromadb.PersistentClient(
        path=str(settings.chroma_dir),
        settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
    )


def collection_name() -> str:
    return f"products_{get_embedder().name}"


@lru_cache(maxsize=4)
def _collection(_name: str):
    client = _client()
    name = collection_name()
    embedder = get_embedder()

    try:
        col = client.get_collection(name=name, embedding_function=None)
        if col.count() == len(PRODUCTS) and (col.metadata or {}).get("dim") == embedder.dim:
            return col
        logger.info("collection %s 需要重建", name)
        client.delete_collection(name)
    except Exception:  # noqa: BLE001 - 不存在或版本不兼容都重建
        pass

    col = client.create_collection(
        name=name,
        metadata={"hnsw:space": "cosine", "dim": embedder.dim, "hnsw:construction_ef": 100},
        embedding_function=None,
    )
    docs = [to_document(p) for p in PRODUCTS]
    vectors = embedder.encode(docs)
    col.add(
        ids=[p["id"] for p in PRODUCTS],
        documents=docs,
        embeddings=vectors,
        metadatas=[
            {
                "name": p["name"],
                "category": p["category"],
                "brand": p["brand"],
                "price": float(p["price"]),
                "stock": int(p["stock"]),
                "tags": "、".join(p["tags"]),
            }
            for p in PRODUCTS
        ],
    )
    logger.info("商品库已构建：%s（%d 条，embedding=%s）", name, col.count(), embedder.name)
    return col


def get_collection():
    return _collection(collection_name())


def search(
    query: str,
    k: int | None = None,
    where: dict[str, Any] | None = None,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    col = get_collection()
    total = col.count()
    if total == 0:
        return []
    k = k or settings.top_k
    min_score = settings.rag_min_score if min_score is None else min_score

    query_vec = get_embedder().encode([query], is_query=True)[0]
    result = col.query(
        query_embeddings=[query_vec],
        n_results=min(k, total),
        where=where or None,
        include=["documents", "metadatas", "distances"],
    )

    hits: list[dict[str, Any]] = []
    for i, pid in enumerate(result["ids"][0]):
        distance = float(result["distances"][0][i])
        score = max(0.0, min(1.0, 1.0 - distance))
        if score < min_score:
            continue
        product = PRODUCT_MAP[pid]
        item = public(product, score=score)
        item["why"] = product["tagline"]
        hits.append(item)
    return hits


def all_products() -> list[dict[str, Any]]:
    return [public(p) for p in PRODUCTS]


def reset() -> None:
    """清空向量集合（改商品数据后调用，或删掉 data/chroma 重启）。"""
    name = collection_name()
    _collection.cache_clear()
    try:
        _client().delete_collection(name)
    except Exception:  # noqa: BLE001
        pass
