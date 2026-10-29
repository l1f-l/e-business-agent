"""对话编排：意图路由 → 任务计划 → 双路检索 / 工具循环 → 统一 SSE 事件流。

事件顺序是契约：meta → (plan) → step(think) → products → reviews → compare
→ tool_call/tool_result → cart/refund → delta → done。
前端按事件到达顺序往消息里追加 block，所以这里不能"先算完再一次性发"。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Iterator

from app import llm as llm_module
from app.agents import compare as compare_agent
from app.agents import cross_sell, guide, tool_loop
from app.core import planner, session as session_mod, sse
from app.core.intent import BOTH, CHITCHAT, ORDER, route
from app.llm import llm
from app.rag.products import PRODUCT_MAP, public as product_public
from app.tools.orders import order_summary

logger = logging.getLogger(__name__)

SYSTEM_CHAT = (
    "你是「ShopPilot」商城的导购助手。用中文口语自然回应，简短友好（60 字以内）。"
    "如果对方想买东西，主动问一句预算和用途。不要提自己是 AI 模型。"
)

DEFAULT_USER = {"user_id": "u1001", "display_name": "林一"}

Event = tuple[str, dict[str, Any]]


def _step(step_id: str, status: str, detail: str | None = None) -> Event:
    payload: dict[str, Any] = {"id": step_id, "status": status}
    if detail:
        payload["detail"] = detail
    return sse.STEP, payload


def _router_events(decision: dict[str, Any], focus: dict[str, Any] | None = None) -> Event:
    slots = decision.get("slots") or {}
    return sse.META, {
        "intent": decision["intent"],
        "confidence": round(float(decision.get("confidence", 0.5)), 2),
        "source": decision.get("source", "rule"),
        "tasks": decision.get("tasks", []),
        "focus_product": focus,
        "slot": {
            "category": slots.get("category"),
            "budget_max": slots.get("budget_max"),
            "order_ids": slots.get("order_ids", []),
        },
    }


def _stream_chitchat(message: str, history: list[dict[str, str]], client) -> Iterator[Event]:
    messages = [{"role": "system", "content": SYSTEM_CHAT}]
    messages.extend(history[-4:])
    messages.append({"role": "user", "content": message})
    try:
        for token in client.stream(messages, max_tokens=160):
            yield sse.DELTA, {"text": token}
    except Exception as exc:  # noqa: BLE001
        logger.warning("chitchat stream failed: %s", exc)
        yield sse.DELTA, {"text": "我在的。想找什么商品？说个预算和用途，我给你挑几款。"}


def _reorder_focus(items: list[dict[str, Any]], focus_id: str | None) -> list[dict[str, Any]]:
    """指代追问时把焦点商品顶到第一位，避免"它多少钱"答成别的型号。"""
    if not focus_id:
        return items
    head = next((i for i in items if i["id"] == focus_id), None)
    if head is None and focus_id in PRODUCT_MAP:
        head = product_public(PRODUCT_MAP[focus_id])
    if head is None:
        return items
    return [head] + [i for i in items if i["id"] != focus_id]


def _format_compare(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return ""
    lines = [f"【对比数据】{result['left']['name']} vs {result['right']['name']}（{result['verdict']}）"]
    for row in result["rows"]:
        lines.append(f"- {row['label']}：左={row['left']}；右={row['right']}")
    return "\n".join(lines)


def stream_chat(
    message: str,
    session_id: str = "default",
    user: dict[str, Any] | None = None,
    client=None,
    decision: dict[str, Any] | None = None,
) -> Iterator[Event]:
    client = client or llm
    user = user or DEFAULT_USER
    message = (message or "").strip()
    state = session_mod.get_state(session_id, user.get("user_id"))

    if not message:
        yield sse.META, {"intent": CHITCHAT, "confidence": 1.0, "source": "empty", "tasks": []}
        yield sse.DELTA, {"text": "想找点什么？说个预算和用途就行。"}
        yield sse.DONE, {"reason": "empty"}
        return

    yield sse.STATUS, {"stage": "routing", "text": "正在理解你的问题…"}
    base = decision or route(message, client=client)

    resolved = session_mod.resolve(message, state)
    merged_slots = resolved["slots"]
    base = {**base, "slots": merged_slots}
    focus_id = resolved["focus_product_id"]
    plan = planner.make_plan(message, base, state, focus_product_id=focus_id)
    pending_ids = list(plan.get("pending_ids") or [])
    # 上一轮的推荐只在一轮内有效：用户没接话就过期，避免几轮之后突然"好的"也触发
    if state.pending_suggestion and not pending_ids:
        state.pending_suggestion = None

    # 闲聊不进计划，直接回
    if plan["intent"] == CHITCHAT or (not plan["tasks"] and base.get("intent") == CHITCHAT):
        yield _router_events(plan)
        yield sse.STATUS, {"stage": "chat", "text": "正在回复…"}
        parts: list[str] = []
        for event, data in _stream_chitchat(message, state.messages(), client):
            if event == sse.DELTA:
                parts.append(str(data.get("text", "")))
            yield event, data
        state.add_turn("user", message)
        state.add_turn("assistant", "".join(parts))
        session_mod.save_state(state)
        yield sse.DONE, {"intent": CHITCHAT, "chars": len("".join(parts))}
        return

    focus_payload = None
    if focus_id and focus_id in PRODUCT_MAP:
        focus_payload = {"id": focus_id, "name": PRODUCT_MAP[focus_id]["name"]}
    yield _router_events(plan, focus_payload)

    plan_id = uuid.uuid4().hex[:8]
    if planner.show_plan(plan["tasks"]):
        yield sse.PLAN, {"plan_id": plan_id, "steps": plan["steps"], "show": True}
        yield _step("think", "running")
        yield _step("think", "done", "已识别为" + _intent_label(plan["intent"]))

    tasks = plan["tasks"]
    items: list[dict[str, Any]] = []
    review_block = ""
    compare_block = ""
    produced: list[str] = []

    # ---------- 1. 商品检索 ----------
    if "retrieve" in tasks:
        yield _step("retrieve", "running")
        locked = plan["product_refs"][:2] if "compare" in tasks and len(plan["product_refs"]) >= 2 else []
        if locked:
            # 对比场景用户已经点名型号，不需要再向量召回，避免把无关商品塞进卡片
            items = [product_public(PRODUCT_MAP[pid]) for pid in locked if pid in PRODUCT_MAP]
            retrieval = {"mode": "explicit", "hits": items}
            yield sse.PRODUCTS, {"items": items, "mode": "explicit", "slot": {}}
            yield _step("retrieve", "done", f"已锁定 {'、'.join(locked)}")
        else:
            retrieval = guide.retrieve(resolved["query"], merged_slots)
            items = retrieval["hits"]
            if resolved.get("wants_alternative") and focus_id:
                items = [i for i in items if i["id"] != focus_id] or items
            elif resolved["is_followup"]:
                items = _reorder_focus(items, focus_id)
            if not items and focus_id and focus_id in PRODUCT_MAP:
                items = [product_public(PRODUCT_MAP[focus_id])]
                retrieval["mode"] = "focus"
            yield sse.PRODUCTS, {
                "items": items,
                "mode": retrieval["mode"],
                "slot": {
                    "category": merged_slots.get("category"),
                    "budget_max": merged_slots.get("budget_max"),
                },
            }
            detail = f"命中 {len(items)} 款" + (f"，{items[0]['name']} ¥{items[0]['price']} 起" if items else "")
            yield _step("retrieve", "done", detail)
    elif plan["product_refs"]:
        items = [product_public(PRODUCT_MAP[pid]) for pid in plan["product_refs"][:3] if pid in PRODUCT_MAP]
        if items:
            yield sse.PRODUCTS, {"items": items, "mode": "explicit"}

    # ---------- 2. 评论召回 ----------
    if "reviews" in tasks:
        yield _step("reviews", "running")
        ids = [i["id"] for i in items[:2]] or ([focus_id] if focus_id else [])
        reviewed = guide.retrieve_reviews(resolved["query"], ids)
        summaries = reviewed["summaries"]
        for summary in summaries:
            product = PRODUCT_MAP.get(summary["product_id"])
            summary["product_name"] = product["name"] if product else summary["product_id"]
        yield sse.REVIEWS, {"items": reviewed["items"], "summaries": summaries}
        review_block = guide.format_reviews(summaries)
        yield _step("reviews", "done", f"{len(reviewed['items'])} 条相关评论")

    # ---------- 3. 商品对比 ----------
    if "compare" in tasks:
        yield _step("compare", "running")
        ids = plan["product_refs"] or [i["id"] for i in items[:2]]
        if len(ids) >= 2:
            result = compare_agent.compare(ids[0], ids[1])
            if result.get("ok"):
                yield sse.COMPARE, result
                compare_block = _format_compare(result)
                yield _step("compare", "done", result["verdict"])
            else:
                yield _step("compare", "failed", result.get("message", "对比失败"))
        else:
            yield _step("compare", "failed", "需要两款商品")
            for piece in llm_module.iter_sse_text(
                "想对比哪两款？告诉我型号就行，比如「对比一下 p03 和 p04」。"
            ):
                yield sse.DELTA, {"text": piece}
            state.add_turn("user", message)
            state.add_turn("assistant", "想对比哪两款？")
            session_mod.save_state(state)
            yield sse.DONE, {"intent": plan["intent"], "reason": "compare_need_targets"}
            return

    # ---------- 4. 工具循环 ----------
    tool_tasks = [t for t in ("query_order", "add_to_cart", "request_refund") if t in tasks]
    ctx: dict[str, Any] = {"results": [], "order": None, "cart": None, "refund": None}

    if "request_refund" in tasks and not merged_slots.get("order_ids"):
        ask = "可以的，请把要退款的订单号发我，我先帮你核对是否符合退款条件。"
        for piece in llm_module.iter_sse_text(ask):
            yield sse.DELTA, {"text": piece}
        produced.append(ask)
    elif tool_tasks:
        for task in tool_tasks:
            yield _step(task, "running")
        for event, data in tool_loop.stream_tool_turn(
            message=message,
            history=state.messages(),
            user=user,
            tasks=tasks,
            candidates=items,
            focus_id=focus_id,
            order_ids=merged_slots.get("order_ids") or [],
            ctx=ctx,
            client=client,
            pending_ids=pending_ids,
        ):
            if event == sse.DELTA:
                produced.append(str(data.get("text", "")))
            yield event, data

        for task in tool_tasks:
            results = [r for r in ctx["results"] if r["name"] == task]
            if not results:
                yield _step(task, "skipped")
            elif all(r["ok"] for r in results):
                yield _step(task, "done", _tool_detail(task, ctx))
            else:
                yield _step(task, "failed", _tool_detail(task, ctx))

    # ---------- 5. 生成文字 ----------
    if tool_tasks:
        if any(ctx.get(k) for k in ("order", "cart", "refund")):
            yield _step("answer", "done", "已整理结果")
    elif "retrieve" in tasks and not produced:
        yield _step("answer", "running")
        messages = guide.build_messages(
            message,
            items,
            state.messages(),
            review_block=review_block,
            compare_block=compare_block,
            focus_name=resolved["focus_name"],
        )
        try:
            for token in client.stream(messages):
                produced.append(token)
                yield sse.DELTA, {"text": token}
        except Exception as exc:  # noqa: BLE001
            logger.warning("guide stream failed: %s", exc)
        if not produced:
            for piece in llm_module.iter_sse_text(guide.fallback_answer(message, items)):
                yield sse.DELTA, {"text": piece}
                produced.append(piece)
        yield _step("answer", "done")

    # 兜底：任何路径都没说话，也要给一句
    if not produced:
        for piece in llm_module.iter_sse_text("我在的，想找什么商品？说个预算和用途，我帮你挑。"):
            yield sse.DELTA, {"text": piece}
        produced.append("我在的")

    answer = "".join(produced)

    # ---------- 6. 主动搭配推荐 ----------
    # 放在回答之后生成：文案要调一次模型，不能让用户等第一个字。
    suggestion = None
    seed = ctx.get("suggestion_seed")
    if seed:
        suggestion = cross_sell.build(
            seed["cart"], seed["source_product_id"], items=seed["items"], client=client
        )
    if suggestion:
        yield sse.SUGGEST, suggestion
        state.pending_suggestion = {
            "product_ids": suggestion["product_ids"],
            "source_product_id": suggestion["source_product_id"],
            "text": suggestion["text"],
        }
    elif pending_ids:
        state.pending_suggestion = None

    state.add_turn("user", message)
    state.add_turn("assistant", answer)
    state.note_results([i["id"] for i in items], merged_slots)
    session_mod.save_state(state)

    raw_order = ctx.get("order_raw") or {}
    orders = order_summary(raw_order) if raw_order.get("ok") else ""
    yield sse.DONE, {
        "intent": plan["intent"],
        "plan_id": plan_id,
        "chars": len(answer),
        "product_ids": [i["id"] for i in items],
        "cart_count": (ctx.get("cart") or {}).get("count", 0),
        "refund_id": (ctx.get("refund") or {}).get("refund_id"),
        "suggest_ids": (suggestion or {}).get("product_ids", []),
        "order": orders,
    }


def _intent_label(intent: str) -> str:
    return {
        "product": "商品咨询",
        "order": "订单售后",
        "both": "订单 + 商品",
        "chitchat": "闲聊",
    }.get(intent, intent)


def _tool_detail(task: str, ctx: dict[str, Any]) -> str:
    if task == "query_order" and ctx.get("order"):
        order = ctx["order"]
        return order.get("status_text") if order.get("ok") else order.get("code", "查询失败")
    if task == "add_to_cart" and ctx.get("cart"):
        return f"共 {ctx['cart']['count']} 件 · ¥{ctx['cart']['total']:.2f}"
    if task == "request_refund" and ctx.get("refund"):
        refund = ctx["refund"]
        return refund.get("status_text") or refund.get("message") or "已提交"
    return ""
