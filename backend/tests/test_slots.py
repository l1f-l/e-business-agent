from __future__ import annotations

import pytest

from app.core.slots import build_where, cn_to_int, extract_budget, extract_category, extract_order_ids, extract_slots


@pytest.mark.parametrize(
    "text,expected",
    [("5百", 500), ("两百", 200), ("三千", 3000), ("十五", 15), ("一千五", 1500), ("500", 500)],
)
def test_cn_to_int(text, expected):
    assert cn_to_int(text) == expected


@pytest.mark.parametrize(
    "text,expected_max",
    [
        ("500元以内降噪耳机", 500),
        ("预算3000的笔记本", 3000),
        ("三千左右的手机", 3000),
        ("不超过 8000 的游戏本", 8000),
        ("1千以下的耳机", 1000),
    ],
)
def test_budget_ceiling(text, expected_max):
    assert extract_budget(text)["max"] == expected_max


def test_budget_range():
    budget = extract_budget("2000-3000 元的手机")
    assert budget["min"] == 2000
    assert budget["max"] == 3000


def test_order_id_is_not_budget():
    """订单号不能被误当成预算。"""
    slots = extract_slots("查一下订单1001的物流")
    assert slots["budget_max"] is None
    assert slots["order_ids"] == ["1001"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("500元以内降噪耳机", "耳机"),
        ("想买个游戏本", "笔记本"),
        ("有没有平板推荐", "平板"),
        ("送女朋友的手表", "手表"),
        ("千元机有什么好选择", "手机"),
    ],
)
def test_category(text, expected):
    assert extract_category(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("查一下订单1001的物流", ["1001"]),
        ("订单号：1002", ["1002"]),
        ("1004到哪了", ["1004"]),
        ("帮我看看订单 1005 的快递", ["1005"]),
        ("order 1003 status", ["1003"]),
        ("订单号 ORD-1002 什么时候发货", ["ORD1002"]),
    ],
)
def test_order_id_extraction(text, expected):
    assert extract_order_ids(text) == expected


def test_no_order_id_without_context():
    assert extract_order_ids("这个耳机多少钱") == []


def test_build_where_strict():
    where = build_where({"category": "耳机", "budget_max": 500})
    assert where == {"$and": [{"category": "耳机"}, {"price": {"$lte": 500.0}}]}
    assert build_where({"category": None, "budget_max": None}) is None
