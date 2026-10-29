"""意图识别路由：规则优先，模型兜底。

为什么不是全交给大模型：
1. "查一下订单 1001 的物流" 这种句式规则 100% 命中，省一次 800ms 的模型调用；
2. 模型 JSON 输出偶尔会漂，规则层是稳定底线。
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.slots import extract_slots
from app.llm import llm

logger = logging.getLogger(__name__)

PRODUCT = "product"
ORDER = "order"
BOTH = "both"
CHITCHAT = "chitchat"

PRODUCT_HINTS = (
    "推荐", "想买", "买什么", "选购", "哪个好", "哪款", "对比", "区别", "怎么样",
    "多少钱", "价格", "有没有", "适合", "降噪", "续航", "拍照", "性能", "轻",
    "便宜", "性价比", "屏幕", "打游戏", "办公", "上网课", "送人", "礼物",
)
CHITCHAT_HINTS = ("你好", "在吗", "谢谢", "再见", "你是谁", "能做什么", "hello", "hi")

_ROUTER_SYSTEM = """你是电商客服的意图分类器。把用户消息分到下列之一：
- product：咨询/推荐商品、比较商品、问价格配置等购物需求
- order：查询订单状态、物流进度、发货、退款进度
- both：同时问订单又问了商品
- chitchat：打招呼、闲聊、与购物无关
只输出 JSON：{"intent":"product|order|both|chitchat","confidence":0到1的小数}
不要输出解释。"""


def rule_route(text: str, slots: dict[str, Any] | None = None) -> dict[str, Any] | None:
    slots = slots or extract_slots(text)
    lowered = text.lower()

    has_order = slots["has_order_hint"]
    has_ids = bool(slots["order_ids"])
    has_product = bool(slots["category"]) or slots["budget_max"] is not None or slots["budget_min"] is not None
    product_hit = any(hint in lowered for hint in PRODUCT_HINTS)

    if has_order and has_ids:
        intent = BOTH if has_product or product_hit else ORDER
        return {"intent": intent, "confidence": 0.96, "source": "rule:order_id", "slots": slots}
    if has_order:
        return {"intent": ORDER, "confidence": 0.82, "source": "rule:order_hint", "slots": slots}
    if has_product:
        return {"intent": PRODUCT, "confidence": 0.88, "source": "rule:slot", "slots": slots}
    if product_hit:
        return {"intent": PRODUCT, "confidence": 0.8, "source": "rule:keyword", "slots": slots}
    if any(text.strip().lower().startswith(h) for h in CHITCHAT_HINTS) and len(text) <= 12:
        return {"intent": CHITCHAT, "confidence": 0.7, "source": "rule:chitchat", "slots": slots}
    return None


def route(text: str, client=None) -> dict[str, Any]:
    slots = extract_slots(text)
    ruled = rule_route(text, slots)
    if ruled:
        return ruled

    client = client or llm
    result = client.json_complete(_ROUTER_SYSTEM, text, max_tokens=80)
    intent = str(result.get("intent") or "").strip().lower()
    if intent not in {PRODUCT, ORDER, BOTH, CHITCHAT}:
        intent = PRODUCT  # 兜底走导购：宁可多推荐，也不要冷场
        confidence = 0.4
        source = "fallback"
    else:
        try:
            confidence = float(result.get("confidence", 0.6))
        except (TypeError, ValueError):
            confidence = 0.6
        source = "llm"

    return {"intent": intent, "confidence": confidence, "source": source, "slots": slots}
