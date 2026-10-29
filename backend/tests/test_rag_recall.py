"""RAG 召回测试：不打桩，直接测真实向量检索。

这是本项目最该被测试覆盖的部分——提示词写得好不好很难测，但“500 元以内降噪耳机”
到底召回了什么，是可以精确断言的。
"""
from __future__ import annotations

import pytest

from app.agents.guide import retrieve
from app.core.slots import build_where, extract_slots
from app.rag import store
from app.rag.embedding import get_embedder


def test_knowledge_base_loaded():
    col = store.get_collection()
    assert col.count() == 10


def test_embedding_provider_reported():
    assert get_embedder().name in {"bge", "hash"}


def test_budget_noise_cancelling_earbuds():
    """核心用例：500 元以内降噪耳机 → 必须命中 499 的 Air Pro，且不越预算。"""
    query = "500元以内降噪耳机"
    result = retrieve(query)
    hits = result["hits"]

    assert hits, "应该有召回结果"
    assert hits[0]["id"] == "p03", f"Top1 应为声浪 Air Pro，实际 {hits[0]['name']}"
    assert hits[0]["price"] <= 500
    assert all(h["price"] <= 500 for h in hits), "预算过滤失效，出现了超预算商品"
    assert all(h["category"] == "耳机" for h in hits)
    assert "降噪" in "".join(hits[0]["highlights"]) + hits[0]["tagline"]


def test_budget_is_hard_constraint():
    """预算必须是硬约束，不能靠相似度碰运气。"""
    hits = retrieve("预算3000以内的笔记本")["hits"]
    assert hits
    assert all(h["price"] <= 3000 for h in hits)
    assert "p07" not in [h["id"] for h in hits], "7999 的游戏本不该出现在 3000 预算里"


def test_semantic_match_without_category_word():
    """口语化描述也要能命中品类：『打游戏不卡的本子』→ 游戏本。"""
    hits = retrieve("想买个打游戏不卡的本子")["hits"]
    assert hits
    assert hits[0]["id"] == "p07"
    assert hits[0]["category"] == "笔记本"


def test_relevance_scores_sorted():
    hits = retrieve("想买个降噪耳机")["hits"]
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_irrelevant_query_returns_nothing_or_weak_matches():
    """无关问题不该硬凑商品。"""
    hits = retrieve("今天天气怎么样")["hits"]
    assert len(hits) <= 4


def test_strict_filter_mode():
    result = retrieve("500元以内降噪耳机")
    assert result["mode"] == "strict"
    assert result["slots"]["category"] == "耳机"
    assert result["slots"]["budget_max"] == 500


@pytest.mark.parametrize(
    "query,expect_category",
    [("有没有拍照好的手机", "手机"), ("想买个上网课的平板", "平板"), ("跑步用的手表", "手表")],
)
def test_category_routing(query, expect_category):
    hits = retrieve(query)["hits"]
    assert hits
    assert hits[0]["category"] == expect_category


def test_store_where_builder():
    slots = extract_slots("500元以内降噪耳机")
    assert build_where(slots) == {"$and": [{"category": "耳机"}, {"price": {"$lte": 500.0}}]}


def test_scores_are_populated():
    hits = retrieve("降噪耳机")["hits"]
    assert all("score" in h for h in hits)
    assert all("image" in h for h in hits), "前端卡片需要图片字段"
