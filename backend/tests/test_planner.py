"""任务规划：步骤要稳定可断言，否则前端进度条会随模型抽风而错乱。"""
from __future__ import annotations

import pytest

from app.core.planner import build_steps, make_plan, resolve_product_refs, show_plan
from app.core.session import SessionState


def _decision(intent: str = "product", **slots) -> dict:
    base = {"category": None, "budget_max": None, "order_ids": []}
    base.update(slots)
    return {"intent": intent, "confidence": 0.9, "source": "rule", "slots": base}


@pytest.fixture()
def session() -> SessionState:
    return SessionState(session_id="t-planner")


@pytest.mark.parametrize(
    "message",
    [
        "500元以内的降噪耳机，帮我加进购物车",
        "把 p03 加入购物车",
        "帮我把它放到车里",
        "这个下单吧",
        "来一个 199 的半入耳",
    ],
)
def test_cart_phrasings_produce_cart_task(message, session):
    plan = make_plan(message, _decision(), session)
    assert "add_to_cart" in plan["tasks"], plan["tasks"]


@pytest.mark.parametrize(
    "message",
    ["购物车里有几件东西", "500元以内降噪耳机", "这个降价了吗"],
)
def test_browsing_cart_is_not_adding(message, session):
    """只是问购物车里有什么，不能触发加购动作。"""
    plan = make_plan(message, _decision(), session)
    assert "add_to_cart" not in plan["tasks"], plan["tasks"]


def test_cart_without_product_first_retrieves(session):
    plan = make_plan("500元以内的降噪耳机，帮我加进购物车", _decision(), session)
    assert plan["tasks"] == ["retrieve", "add_to_cart"]
    assert show_plan(plan["tasks"]) is True


def test_cart_with_named_product_skips_retrieval(session):
    plan = make_plan("把 p03 加入购物车", _decision(), session)
    assert plan["tasks"] == ["add_to_cart"]


def test_compare_locks_two_product_refs(session):
    plan = make_plan("对比一下 p03 和 p04", _decision(), session)
    assert plan["tasks"] == ["retrieve", "compare"]
    assert plan["product_refs"][:2] == ["p03", "p04"]
    assert "compare_ready" in plan["notes"]


def test_compare_falls_back_to_previous_results(session):
    """只说"对比一下"，用上一轮的商品补位。"""
    session.note_results(product_ids=["p03", "p04"])
    plan = make_plan("对比一下这两个", _decision(), session)
    assert plan["tasks"] == ["retrieve", "compare"]
    assert len(plan["product_refs"]) == 2


def test_refund_action_needs_order_id(session):
    plan = make_plan("订单1005帮我退款", _decision(order_ids=["1005"]), session)
    assert plan["tasks"] == ["query_order", "request_refund"]
    assert plan["intent"] == "order"


def test_refund_without_order_id_asks_first(session):
    plan = make_plan("我要退款", _decision(), session)
    assert plan["tasks"] == ["query_order"]
    assert "refund_need_order_id" in plan["notes"]


@pytest.mark.parametrize("message", ["耳机能退吗", "退款流程是怎样的", "退款多久到账"])
def test_refund_policy_question_is_not_an_action(message, session):
    plan = make_plan(message, _decision(order_ids=["1005"]), session)
    assert "request_refund" not in plan["tasks"], plan["tasks"]


def test_review_question_pulls_both_paths(session):
    plan = make_plan("这耳机有什么优缺点", _decision(), session)
    assert plan["tasks"] == ["retrieve", "reviews"]


def test_steps_keep_fixed_order(session):
    plan = make_plan("对比一下 p03 和 p04", _decision(), session)
    ids = [s["id"] for s in plan["steps"]]
    assert ids[0] == "think"
    assert ids[-1] == "answer"
    assert ids.index("retrieve") < ids.index("compare")


def test_single_task_hides_progress_bar(session):
    plan = make_plan("3000以内的轻薄本", _decision(), session)
    assert plan["tasks"] == ["retrieve"]
    assert show_plan(plan["tasks"]) is False


def test_build_steps_only_includes_needed_tasks():
    steps = build_steps(["add_to_cart"])
    assert [s["id"] for s in steps] == ["think", "add_to_cart", "answer"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("p04 怎么样", ["p04"]),
        ("P4 和 p03 比", ["p04", "p03"]),
        ("声浪 Air Pro 多少钱", ["p03"]),
        ("随便看看", []),
    ],
)
def test_resolve_product_refs(text, expected):
    assert resolve_product_refs(text) == expected
