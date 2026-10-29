"""任务规划：把一句话拆成可展示、可执行的步骤。

为什么不直接让模型 ReAct：
进度条要稳定（用户看到"正在检索→正在加购"），测试要可断言（步骤数量固定），
所以"有哪些步"由规则决定，"参数填什么"才交给模型。
"""
from __future__ import annotations

import re
from typing import Any

from app.core.session import SessionState, is_confirm
from app.rag.products import LOOKUP_MAP

REFUND_WORDS = ("退款", "退货", "退掉", "退钱", "申请退")
REFUND_ACTION_HINTS = ("帮我退", "给我退", "我要退", "退掉", "申请退款", "退了吧", "直接退", "办理退款")
REFUND_POLICY_HINTS = ("能退吗", "可以退吗", "能不能退", "怎么退", "退款政策", "退款流程", "多久到账", "退多少")

CART_HINTS = (
    "加购", "加入购物车", "加进购物车", "加到购物车", "放购物车", "放进购物车",
    "塞进购物车", "装进购物车",
    "买下", "拍了", "拍下", "下单", "来一个", "来一台", "来一只", "帮我买",
)
# "加 / 放 / 塞 / 装 / 添"+近处出现"购物车"也算加购，覆盖"帮我加进购物车""放车里"
# 这类词表穷举不完的说法；反过来"购物车里有什么"因为动词不在购物车附近，不会误判
_CART_RE = re.compile(
    r"(加|放|塞|装|添|丢|扔)[^，。！？,.!?]{0,4}?(购物车|车里)"
    r"|(购物车|车里)[^，。！？,.!?]{0,3}?(加|放|塞|装|添)"
)
COMPARE_HINTS = ("对比", "比较", "区别", "差别", "哪个更", "选哪个", "二选一")
REVIEW_HINTS = (
    "评价", "评论", "口碑", "优缺点", "优点", "缺点", "差评", "好评",
    "值不值", "值得买", "怎么样", "好不好", "翻车", "踩坑",
)

ACTION_TASKS = {"add_to_cart", "request_refund", "compare"}

STEP_LABELS = {
    "think": "理解需求",
    "retrieve": "检索商品库",
    "reviews": "检索用户评价",
    "compare": "生成对比",
    "query_order": "核对订单归属",
    "add_to_cart": "加入购物车",
    "request_refund": "提交退款申请",
    "answer": "生成回复",
}


def resolve_product_refs(text: str) -> list[str]:
    """从文本里认出商品引用：支持 p03、"P3"、以及商品全名。"""
    lowered = (text or "").lower()
    found: list[tuple[int, str]] = []
    for match in re.finditer(r"p0?(\d{1,2})", lowered):
        pid = f"p{int(match.group(1)):02d}"
        if pid in LOOKUP_MAP:
            found.append((match.start(), pid))
    for product in LOOKUP_MAP.values():
        idx = lowered.find(product["name"].lower())
        if idx >= 0:
            found.append((idx, product["id"]))
    found.sort()
    ordered: list[str] = []
    for _, pid in found:
        if pid not in ordered:
            ordered.append(pid)
    return ordered


def _is_refund_action(text: str) -> bool:
    if not any(w in text for w in REFUND_WORDS):
        return False
    if any(h in text for h in REFUND_POLICY_HINTS):
        return False
    if any(h in text for h in REFUND_ACTION_HINTS):
        return True
    # "订单 1005 退款" 这种省略动词的说法，只要带订单号且不是疑问句就当执行
    return not any(q in text for q in ("吗", "?", "？", "怎么", "能否"))


def build_steps(tasks: list[str]) -> list[dict[str, str]]:
    order = ["think", "retrieve", "reviews", "compare", "query_order", "add_to_cart", "request_refund", "answer"]
    steps = []
    for key in order:
        if key == "think" or key == "answer" or key in tasks:
            steps.append({"id": key, "label": STEP_LABELS[key], "status": "pending"})
    return steps


def make_plan(
    message: str,
    decision: dict[str, Any],
    session: SessionState,
    *,
    focus_product_id: str | None = None,
) -> dict[str, Any]:
    """在意图路由之上再识别"动作"，产出任务清单与展示步骤。"""
    text = (message or "").strip()
    lowered = text.lower()
    slots = dict(decision.get("slots") or {})
    order_ids = slots.get("order_ids") or []
    refs = resolve_product_refs(text)

    tasks: list[str] = []
    notes: list[str] = []

    wants_refund = any(w in text for w in REFUND_WORDS)
    wants_refund_action = _is_refund_action(text)
    wants_cart = any(h in lowered for h in CART_HINTS) or bool(_CART_RE.search(lowered))
    wants_compare = any(h in lowered for h in COMPARE_HINTS)
    wants_reviews = any(h in lowered for h in REVIEW_HINTS)

    # 上一轮问过"要不要顺便带个配件"，用户回"好的"：直接执行，不再确认一次
    pending = session.pending_suggestion if isinstance(session.pending_suggestion, dict) else None
    confirm = bool(pending and pending.get("product_ids")) and is_confirm(text)
    if confirm:
        tasks = ["add_to_cart"]
        notes.append("cross_sell_confirm")

    if wants_compare:
        targets = list(refs)
        if len(targets) < 2 and focus_product_id and focus_product_id not in targets:
            targets.append(focus_product_id)
        if len(targets) < 2 and session.last_product_ids:
            for pid in session.last_product_ids:
                if pid not in targets:
                    targets.append(pid)
        if len(targets) >= 2:
            tasks.extend(["retrieve", "compare"])
            refs = targets[:2]
            notes.append("compare_ready")
        else:
            tasks.extend(["retrieve", "compare"])
            notes.append("compare_need_targets")

    if wants_refund:
        tasks.append("query_order")
        if wants_refund_action and order_ids:
            tasks.append("request_refund")
        elif not order_ids:
            notes.append("refund_need_order_id")

    if not tasks:
        if wants_cart:
            if refs and refs[0] in LOOKUP_MAP:
                tasks.append("add_to_cart")
            else:
                tasks.extend(["retrieve", "add_to_cart"])
        elif wants_reviews:
            tasks.append("retrieve")
            tasks.append("reviews")
        elif decision.get("intent") == "order":
            tasks.append("query_order")
        elif decision.get("intent") == "both":
            if order_ids:
                tasks.append("query_order")
            tasks.append("retrieve")
        elif decision.get("intent") in {"product", "both"}:
            tasks.append("retrieve")

    if wants_reviews and "reviews" not in tasks:
        if "retrieve" not in tasks and not wants_refund:
            tasks.insert(0, "retrieve")
        tasks.append("reviews")

    if wants_cart and "add_to_cart" not in tasks:
        tasks.append("add_to_cart")
        if not refs:
            tasks.insert(0, "retrieve")

    # 去重但保序
    deduped: list[str] = []
    for task in tasks:
        if task not in deduped:
            deduped.append(task)
    tasks = deduped

    intent = decision.get("intent", "product")
    if wants_refund and "request_refund" in tasks:
        intent = "order"
    elif "add_to_cart" in tasks or "compare" in tasks:
        intent = "product" if intent != "order" else "both"

    return {
        "intent": intent,
        "confidence": decision.get("confidence", 0.6),
        "source": decision.get("source", "rule"),
        "tasks": tasks,
        "steps": build_steps(tasks),
        "slots": slots,
        "product_refs": refs,
        "focus_product_id": focus_product_id,
        "pending_ids": list(pending.get("product_ids") or []) if confirm else [],
        "notes": notes,
    }


def show_plan(tasks: list[str]) -> bool:
    """单步任务不画进度条，避免"检索→回答"也弹一串动画。"""
    return len(tasks) >= 2
