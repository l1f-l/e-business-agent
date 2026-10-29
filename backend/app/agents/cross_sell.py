"""主动搭配推荐：加购成功后顺手问一句，用户点头就一起下单。

两条原则：
1. 选品靠规则——品类决定配件池，已加购的排除，避免模型把不搭的东西硬塞；
2. 文案靠模型——一句话要像人说的，模型挂了就用模板，绝不因为文案失败而卡住主流程。
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.llm import llm
from app.rag.products import accessories_for, product_by_id, public

logger = logging.getLogger(__name__)

MAX_ITEMS = 2


def pick(cart: dict[str, Any], source_product_id: str | None) -> list[dict[str, Any]]:
    """按主商品品类挑配件，跳过购物车里已经有的。"""
    product = product_by_id(source_product_id or "")
    if product is None:
        return []
    in_cart = {item["product_id"] for item in cart.get("items", [])}
    picked = [a for a in accessories_for(product.get("category")) if a["id"] not in in_cart]
    return [public(a) for a in picked[:MAX_ITEMS]]


def _fallback_text(source_name: str, items: list[dict[str, Any]]) -> str:
    if len(items) >= 2:
        return f"{source_name} 到手就能用，要不要顺便配上 {items[0]['name']} 和 {items[1]['name']}？"
    if items:
        return f"{source_name} 要不要顺便带一个 {items[0]['name']}？"
    return ""


def _llm_text(source_name: str, items: list[dict[str, Any]], client=None) -> str:
    """让模型说一句人话；任何异常都返回空串，交给模板兜底。"""
    names = "、".join(f"{i['name']}（¥{i['price']}）" for i in items)
    prompt = (
        f"用户刚把「{source_name}」加入购物车。商城想顺势推荐：{names}。\n"
        "请用一句不超过 34 字的中文口语问他要不要顺便带上，语气自然、别像广告，"
        "不要提工具、不要说“亲”、不要罗列卖点。"
        + ("两件都要问，用“和”连起来，不要说“或者”。" if len(items) >= 2 else "")
        + "只输出这句话。"
    )
    try:
        if client is not None:
            # 测试或降级场景传入的假客户端没有 complete，直接用模板，绝不偷偷打真接口
            if not hasattr(client, "complete"):
                return ""
            active = client
        else:
            active = llm
        message = active.complete(
            [
                {"role": "system", "content": "你是电商导购，说话简短、具体、不油腻。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=64,
        )
        text = (getattr(message, "content", "") or "").strip().strip('"“”')
        return text if 0 < len(text) <= 60 else ""
    except Exception as exc:  # noqa: BLE001 - 文案失败不能影响下单
        logger.warning("搭配推荐文案生成失败：%s", exc)
        return ""


def build(
    cart: dict[str, Any],
    source_product_id: str | None,
    *,
    items: list[dict[str, Any]] | None = None,
    client=None,
) -> dict[str, Any] | None:
    """产出 suggest 事件的数据；没有可推荐的就返回 None。"""
    if not settings.cross_sell_enabled:
        return None
    product = product_by_id(source_product_id or "")
    if product is None:
        return None
    picked = items if items is not None else pick(cart, source_product_id)
    if not picked:
        return None
    text = _llm_text(product["name"], picked, client) or _fallback_text(product["name"], picked)
    if not text:
        return None
    return {
        "text": text,
        "source_product_id": product["id"],
        "source_product_name": product["name"],
        "items": picked,
        "product_ids": [i["id"] for i in picked],
        "pending": "add_to_cart",
    }
