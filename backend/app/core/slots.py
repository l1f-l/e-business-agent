"""槽位抽取：预算、品类、订单号。

这一层是 RAG 质量的关键——纯向量检索给不出"500 元以内"这种硬约束，
必须先把预算/品类抽成结构化过滤条件，再去向量排序。
"""
from __future__ import annotations

import re
from typing import Any

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "耳机": ("耳机", "耳麦", "耳塞", "tws", "降噪豆", "airpods"),
    "手机": ("手机", "智能机", "千元机", "旗舰机"),
    "笔记本": ("笔记本", "笔电", "电脑", "本子", "游戏本", "轻薄本", "上网本"),
    "平板": ("平板", "pad", "ipad"),
    "手表": ("手表", "腕表", "手环", "watch"),
}

ORDER_HINTS = (
    "订单", "单号", "运单", "物流", "快递", "发货", "签收", "到哪", "到哪儿",
    "配送", "退款", "退货", "包裹", "送达", "order",
)

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}


def cn_to_int(text: str) -> int | None:
    """把「5百」「两百」「三千五」「十五」这类口语数字转成整数。"""
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CN_DIGITS:
        return _CN_DIGITS[text]

    for unit, base in (("万", 10000), ("千", 1000), ("百", 100)):
        if unit in text:
            head, _, tail = text.partition(unit)
            head_val = _small_cn(head) if head else 1
            if head_val is None:
                return None
            value = head_val * base
            tail_val = _small_cn(tail) if tail else 0
            if tail_val:
                value += tail_val * (base // 10)
            return value
    return _small_cn(text)


def _small_cn(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if "十" in text:
        head, _, tail = text.partition("十")
        head_val = _CN_DIGITS.get(head, 1) if head else 1
        tail_val = _CN_DIGITS.get(tail, 0) if tail else 0
        return head_val * 10 + tail_val
    total = 0
    for ch in text:
        if ch not in _CN_DIGITS:
            return None
        total = total * 10 + _CN_DIGITS[ch]
    return total


def extract_category(text: str) -> str | None:
    lowered = text.lower()
    best: tuple[int, str] | None = None
    for category, words in CATEGORY_KEYWORDS.items():
        for word in words:
            idx = lowered.find(word)
            if idx >= 0:
                # 关键词越长越具体（"游戏本" 优先于 "本子"）
                cand = (len(word), category)
                if best is None or cand[0] > best[0]:
                    best = cand
    return best[1] if best else None


_CEIL_HINTS = ("以内", "以下", "之内", "封顶", "不超过", "不到", "低于", "不高于",
               "最多", "预算", "左右", "上下")
_FLOOR_HINTS = ("以上", "不低于", "至少")


def extract_budget(text: str) -> dict[str, float | None]:
    """返回 {"min": x, "max": y}，抽不到就是两个 None。"""
    budget: dict[str, float | None] = {"min": None, "max": None}
    cleaned = text.replace("，", ",").replace(" ", "")

    # 区间：500-1000 / 500~1000 / 500到1000
    range_match = re.search(r"(\d{2,6})\s*(?:-|~|到|至)\s*(\d{2,6})\s*(?:元|块)?", cleaned)
    if range_match:
        low, high = sorted((int(range_match.group(1)), int(range_match.group(2))))
        budget["min"], budget["max"] = float(low), float(high)
        return budget

    # 数字 + 单位百/千（含中文数字）：5百、1.5千
    scaled = re.search(r"(\d+(?:\.\d+)?)\s*([百千万])(?:元|块)?", cleaned)
    if scaled:
        factor = {"百": 100, "千": 1000, "万": 10000}[scaled.group(2)]
        value = float(scaled.group(1)) * factor
        if any(h in cleaned for h in _CEIL_HINTS) or "内" in cleaned:
            budget["max"] = value
        elif any(h in cleaned for h in _FLOOR_HINTS):
            budget["min"] = value
        else:
            budget["max"] = value
        return budget

    cn_scaled = re.search(r"([一二两三四五六七八九十]+[百千万])(?:元|块)?", cleaned)
    if cn_scaled:
        value = cn_to_int(cn_scaled.group(1))
        if value:
            budget["max"] = float(value)
            return budget

    # 普通数字 + 上限词
    plain = re.search(r"(\d{2,6})\s*(?:元|块|rmb|¥)?", cleaned)
    if plain:
        value = float(plain.group(1))
        if any(h in cleaned for h in _CEIL_HINTS) or "内" in cleaned:
            budget["max"] = value
        elif any(h in cleaned for h in _FLOOR_HINTS):
            budget["min"] = value
        elif re.search(r"(?:预算|价位|价格)\D{0,3}" + re.escape(plain.group(1)), cleaned):
            budget["max"] = value
    return budget


def extract_order_ids(text: str) -> list[str]:
    """订单号抽取。优先认"订单/单号"后面的号，其次在订单语境里认裸数字。"""
    ids: list[str] = []
    explicit = re.finditer(
        r"(?:订单号?|单号|运单号?|order[\s_]*id)\s*(?:是|为|[:：#])?\s*([A-Za-z]{0,4}[-_]?\d{3,})",
        text,
        re.IGNORECASE,
    )
    for match in explicit:
        ids.append(re.sub(r"[-_\s]", "", match.group(1)).upper())

    if not ids and any(hint in text.lower() for hint in ORDER_HINTS):
        for match in re.finditer(r"(?<![\d.])(\d{4,8})(?![\d.])", text):
            ids.append(match.group(1))

    deduped: list[str] = []
    for oid in ids:
        if oid not in deduped:
            deduped.append(oid)
    return deduped


def extract_slots(text: str) -> dict[str, Any]:
    budget = extract_budget(text)
    return {
        "category": extract_category(text),
        "budget_min": budget["min"],
        "budget_max": budget["max"],
        "order_ids": extract_order_ids(text),
        "has_order_hint": any(hint in text.lower() for hint in ORDER_HINTS),
    }


def build_where(slots: dict[str, Any]) -> dict[str, Any] | None:
    """把槽位转成 Chroma 的 where 过滤（硬约束）。"""
    clauses: list[dict[str, Any]] = []
    if slots.get("category"):
        clauses.append({"category": slots["category"]})
    if slots.get("budget_max") is not None:
        clauses.append({"price": {"$lte": float(slots["budget_max"])}})
    if slots.get("budget_min") is not None:
        clauses.append({"price": {"$gte": float(slots["budget_min"])}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
