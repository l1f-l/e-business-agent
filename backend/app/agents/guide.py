"""RAG 导购链路：槽位 → 硬过滤 → 向量召回 → 双路上下文 → 流式生成。"""
from __future__ import annotations

import logging
from typing import Any, Iterator

from app import llm as llm_module
from app.config import settings
from app.core import sse
from app.core.slots import build_where, extract_slots
from app.llm import llm
from app.rag import review_store, store
from app.rag.products import PRODUCT_MAP
from app.rag.reviews import summarize

logger = logging.getLogger(__name__)

SYSTEM_GUIDE = """你是「ShopPilot」商城的资深导购。语气自然、口语化，像一个懂行的朋友，不要客服腔。

规则：
1. 只能基于【商品资料】和【真实用户评论】里出现的事实作答，绝对不允许编造不存在的型号、参数、价格或评价。
2. 优先推荐 1-3 款最匹配的：先用一句话给结论，再说"为什么适合你"，最后点一个真实的注意点。
3. 用户有预算或品类硬约束时必须尊重，绝不能推荐超预算的商品。
4. 只有【真实用户评论】里明确提到的优缺点才能说。归纳优缺点时用"有用户提到…""比较集中的吐槽是…"的口吻，不要把个别评论说成普遍结论。
5. 如果用户意图不明确（没说预算、没说用途、没说是自用还是送人），先用一句话给出大致方向，然后主动追问最关键的那一个信息，例如"你预算大概多少？"。
6. 用户用"它/这个/那款"指代时，结合对话历史判断指的是哪款，直接说型号名，不要反问"您说的是哪款"。
7. 不要重复用户原话，不要用 Markdown 标题，不要列参数表，长度控制在 120-220 字。
8. 价格用 ¥ 表示，口语化即可，不要说"根据资料"这类机器话。
9. 用户用商品编号（如 p03）提问时，直接对应【商品资料】/【对比数据】里的型号，不要说不认识这个编号，也不要再反问"是哪款"。
10. 本轮已经给出明确推荐或对比结论时，不要再追问预算；只有确实缺少关键信息（用途、预算）时才问一个最关键的问题。"""


def retrieve(query: str, slots: dict[str, Any] | None = None, k: int | None = None) -> dict[str, Any]:
    """三级检索：硬约束 → 圈内按相似度 → 放开过滤。

    预算/品类是硬约束，先圈定候选集；如果圈内没有过阈值的，
    就在圈内按相似度取最优（min_score=0），而不是直接回空。
    """
    slots = slots or extract_slots(query)
    k = k or settings.top_k

    where = build_where(slots)
    hits = store.search(query, k=k, where=where)
    mode = "strict"

    if not hits and where is not None:
        hits = store.search(query, k=k, where=where, min_score=0.0)
        mode = "relaxed_score"

    if not hits and where is not None:
        budget_where = None
        if slots.get("budget_max") is not None:
            budget_where = {"price": {"$lte": float(slots["budget_max"])}}
        hits = store.search(query, k=k, where=budget_where, min_score=0.0)
        mode = "relaxed_category"

    if not hits:
        hits = store.search(query, k=k, where=None, min_score=0.0)
        mode = "relaxed_all"

    return {"hits": hits, "slots": slots, "mode": mode}


def retrieve_reviews(
    query: str,
    product_ids: list[str],
    k: int | None = None,
) -> dict[str, Any]:
    """评论召回：先按商品过滤，再做语义排序；同时给出商品级口碑聚合。"""
    ids = [pid for pid in product_ids if pid in PRODUCT_MAP][:2]
    if not ids:
        return {"items": [], "summaries": [], "product_ids": []}

    items = review_store.search(query, product_ids=ids, k=k)
    by_product: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_product.setdefault(item["product_id"], []).append(item)

    summaries = [summarize(pid, by_product.get(pid)) for pid in ids]
    return {"items": items, "summaries": summaries, "product_ids": ids}


def format_context(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "【商品资料】(空)"
    lines = ["【商品资料】"]
    for idx, item in enumerate(hits, start=1):
        lines.append(
            f"{idx}. {item['name']}（{item['category']}）¥{item['price']}｜"
            f"卖点：{'；'.join(item['highlights'])}｜{item['tagline']}"
        )
    return "\n".join(lines)


def format_reviews(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return ""
    lines = ["【真实用户评论（只能据此归纳，不得编造）】"]
    for summary in summaries:
        product = PRODUCT_MAP.get(summary["product_id"])
        if product is None or summary["count"] == 0:
            continue
        lines.append(
            f"■ {product['name']}｜均分 {summary['rating_avg']}（{summary['count']} 条评论）"
        )
        if summary["pros"]:
            lines.append("  好评要点：" + "、".join(f"{p['label']}({p['count']})" for p in summary["pros"]))
        if summary["cons"]:
            lines.append("  差评要点：" + "、".join(f"{c['label']}({c['count']})" for c in summary["cons"]))
        lines.append("  代表评论：")
        for item in summary["items"][:4]:
            lines.append(f"   - ★{item['rating']} {item['text']}（{item['author']}）")
    return "\n".join(lines) if len(lines) > 1 else ""


def build_messages(
    message: str,
    hits: list[dict[str, Any]],
    history: list[dict[str, str]],
    review_block: str = "",
    compare_block: str = "",
    focus_name: str | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_GUIDE}]
    messages.extend(history)
    parts = [format_context(hits)]
    if review_block:
        parts.append(review_block)
    if compare_block:
        parts.append(compare_block)
    if focus_name:
        parts.append(f"【本轮指代】用户说的「它/这个」最可能指：{focus_name}")
    parts.append(f"用户问题：{message}\n\n请基于以上资料直接回答。")
    messages.append({"role": "user", "content": "\n\n".join(parts)})
    return messages


def fallback_answer(message: str, hits: list[dict[str, Any]]) -> str:
    """模型不可用时的规则兜底，保证 demo 不会白屏。"""
    if not hits:
        return "抱歉，商品库里暂时没有匹配的商品。可以说说预算和用途，我再帮你找找。"
    top = hits[0]
    others = "、".join(f"{h['name']}（¥{h['price']}）" for h in hits[1:3])
    tail = f" 另外 {others} 也可以看看。" if others else ""
    return f"最推荐 {top['name']}，¥{top['price']}。{top['tagline']}。{tail}"


def stream_guide(
    message: str,
    history: list[dict[str, str]],
    slots: dict[str, Any] | None = None,
    client=None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """轻量版导购（不含评价双路），保留给脚本与回归测试用。"""
    client = client or llm
    yield sse.STATUS, {"stage": "searching", "text": "正在检索商品库…"}

    result = retrieve(message, slots)
    hits = result["hits"]

    yield sse.PRODUCTS, {
        "items": hits,
        "mode": result["mode"],
        "slot": {
            "category": result["slots"].get("category"),
            "budget_max": result["slots"].get("budget_max"),
        },
    }

    if not hits:
        for piece in llm_module.iter_sse_text(fallback_answer(message, hits)):
            yield sse.DELTA, {"text": piece}
        yield sse.DONE, {"reason": "no_product"}
        return

    messages = build_messages(message, hits, history)
    produced = ""
    try:
        for token in client.stream(messages):
            produced += token
            yield sse.DELTA, {"text": token}
    except Exception as exc:  # noqa: BLE001
        logger.error("guide stream failed: %s", exc)
        if not produced:
            for piece in llm_module.iter_sse_text(fallback_answer(message, hits)):
                yield sse.DELTA, {"text": piece}

    yield sse.DONE, {
        "reason": "ok",
        "product_ids": [h["id"] for h in hits],
        "chars": len(produced),
    }
