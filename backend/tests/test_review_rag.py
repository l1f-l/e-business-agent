"""评论 RAG 测试：语料质量、商品过滤、语义命中、聚合可追溯。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.guide import format_reviews
from app.config import settings
from app.core import sse
from app.rag import review_store
from app.rag.products import PRODUCTS
from app.rag.reviews import BY_PRODUCT, REVIEWS, summarize

PRODUCT_IDS = [p["id"] for p in PRODUCTS]


def test_every_product_has_enough_reviews():
    for pid in PRODUCT_IDS:
        reviews = BY_PRODUCT.get(pid, [])
        assert len(reviews) >= 5, f"{pid} 评论太少，无法支撑优缺点总结"
        ratings = [r["rating"] for r in reviews]
        assert any(r >= 4 for r in ratings), f"{pid} 缺少好评"
        assert any(r <= 3 for r in ratings), f"{pid} 缺少差评，优缺点会失真"


def test_review_labels_are_clean():
    for review in REVIEWS:
        assert 1 <= review["rating"] <= 5
        assert review["text"].strip()
        for label in review["pros"] + review["cons"]:
            assert 2 <= len(label) <= 8, f"标签过长会污染聚合：{label}"


def test_collection_holds_all_reviews():
    assert review_store.count() == len(REVIEWS)


def test_search_is_restricted_to_given_products():
    hits = review_store.search("降噪 音质 续航", product_ids=["p03"], k=5)
    assert hits
    assert {h["product_id"] for h in hits} == {"p03"}


@pytest.mark.parametrize(
    "query,product_id,keyword",
    [
        ("戴久了夹耳朵", "p05", "夹"),
        ("地铁里听不清", "p04", "地铁"),
        ("风扇声音大", "p07", "风扇"),
    ],
)
def test_semantic_recall_hits_the_right_review(query, product_id, keyword):
    hits = review_store.search(query, product_ids=[product_id], k=3)
    assert hits, f"没有召回：{query}"
    assert hits[0]["product_id"] == product_id
    assert keyword in hits[0]["text"]


def test_summarize_aggregates_real_labels():
    summary = summarize("p03")
    assert summary["count"] == len(BY_PRODUCT["p03"])
    assert 1 <= summary["rating_avg"] <= 5
    assert summary["pros"], "必须有好评要点"
    assert summary["cons"], "必须有差评要点"
    assert summary["negative"], "必须保留差评原文"
    assert all(item["product_id"] == "p03" for item in summary["items"])


def test_summarize_empty_product():
    summary = summarize("p99")
    assert summary["count"] == 0
    assert summary["pros"] == []


def test_prompt_block_forbids_hallucination():
    block = format_reviews([summarize("p05")])
    assert "不得编造" in block
    assert "声浪 Studio Max" in block
    assert "夹头" in block or "闷热出汗" in block
    assert "★" in block


class _FakeClient:
    def json_complete(self, *a, **k):
        return {"intent": "product", "confidence": 0.9}

    def tool_complete(self, *a, **k):
        return SimpleNamespace(content="", tool_calls=[])

    def stream(self, messages, **kwargs):
        for ch in "它降噪强，但戴久了耳道胀。":
            yield ch


def test_reviews_event_only_covers_retrieved_products():
    from app.agents.orchestrator import stream_chat

    user = {"user_id": "u1001", "display_name": "林一"}
    events = list(stream_chat("500元以内降噪耳机有什么优缺点", "rv1", user=user, client=_FakeClient()))
    products = next(d["items"] for e, d in events if e == sse.PRODUCTS)
    reviews = next(d for e, d in events if e == sse.REVIEWS)

    top_ids = [p["id"] for p in products[:2]]
    assert {s["product_id"] for s in reviews["summaries"]} == set(top_ids)
    assert all(item["product_id"] in top_ids for item in reviews["items"])
    assert reviews["summaries"][0]["pros"]
