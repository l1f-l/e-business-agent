"""商品对比：把两款商品摊成同一组行，前端直接两列渲染。

行结构固定为 {label, left, right, highlight}，前端不需要知道商品字段。
highlight 用来标"这一行谁更占优"：price 越低越好，rating 越高越好。
"""
from __future__ import annotations

from typing import Any

from app.rag.products import PRODUCT_MAP, public
from app.rag.reviews import summarize


def _spec_rows(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    keys: list[str] = []
    for product in (left, right):
        for key in (product.get("specs") or {}):
            if key not in keys:
                keys.append(key)
    rows = []
    for key in keys:
        rows.append(
            {
                "label": key,
                "left": (left.get("specs") or {}).get(key) or "—",
                "right": (right.get("specs") or {}).get(key) or "—",
                "highlight": None,
            }
        )
    return rows


def _dot(items: list[dict[str, Any]]) -> str:
    return "、".join(f"{i['label']}（{i['count']}）" for i in items[:3]) or "—"


def compare(left_id: str, right_id: str) -> dict[str, Any]:
    left = PRODUCT_MAP.get(left_id)
    right = PRODUCT_MAP.get(right_id)
    if left is None or right is None:
        missing = left_id if left is None else right_id
        return {"ok": False, "code": "PRODUCT_NOT_FOUND", "message": f"没有找到商品 {missing}"}
    if left_id == right_id:
        return {"ok": False, "code": "SAME_PRODUCT", "message": "两款是同一件商品，换个型号再比吧。"}

    ls, rs = summarize(left_id), summarize(right_id)
    rows: list[dict[str, Any]] = [
        {
            "label": "价格",
            "left": f"¥{left['price']}",
            "right": f"¥{right['price']}",
            "highlight": "left" if left["price"] < right["price"] else ("right" if right["price"] < left["price"] else None),
        },
        {
            "label": "评分",
            "left": f"{left.get('rating', '-')} 分",
            "right": f"{right.get('rating', '-')} 分",
            "highlight": "left" if (left.get("rating") or 0) > (right.get("rating") or 0) else ("right" if (right.get("rating") or 0) > (left.get("rating") or 0) else None),
        },
        {
            "label": "用户口碑",
            "left": f"{ls['rating_avg']} 分 / {ls['count']} 条",
            "right": f"{rs['rating_avg']} 分 / {rs['count']} 条",
            "highlight": None,
        },
        {"label": "好评要点", "left": _dot(ls["pros"]), "right": _dot(rs["pros"]), "highlight": None},
        {"label": "差评要点", "left": _dot(ls["cons"]), "right": _dot(rs["cons"]), "highlight": None},
    ]
    rows.extend(_spec_rows(left, right))

    return {
        "ok": True,
        "left": public(left),
        "right": public(right),
        "rows": rows,
        "verdict": _verdict(left, right),
    }


def _verdict(left: dict[str, Any], right: dict[str, Any]) -> str:
    cheaper = left if left["price"] <= right["price"] else right
    other = right if cheaper is left else left
    gap = abs(left["price"] - right["price"])
    return f"{cheaper['name']} 便宜 ¥{gap:g}" if gap else f"{cheaper['name']} 与 {other['name']} 同价"
