"""主动搭配推荐：选品规则、确认话术、落库与一轮内失效。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents import cross_sell, orchestrator
from app.config import settings
from app.core import session as session_mod
from app.core.planner import make_plan
from app.core.session import SessionState, is_confirm, is_reject
from app.tools.cart import add_to_cart, get_cart

USER = {"user_id": "u1002", "display_name": "周一鸣"}


class FakeClient:
    """没有 complete：文案走模板，保证单测不打真接口。"""

    def json_complete(self, *a, **k):
        return {"intent": "product", "confidence": 0.9}

    def tool_complete(self, *a, **k):
        return SimpleNamespace(content="", tool_calls=[])

    def stream(self, messages, **kwargs):
        yield "已经加好了。"


def _cart(*product_ids: str) -> dict:
    items = [{"product_id": pid} for pid in product_ids]
    return {"items": items, "count": len(items), "total": 0}


# ---------------- 选品 ----------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("p01", ["p11", "p12"]),
        ("p03", ["p13", "p14"]),
        ("p06", ["p15", "p16"]),
        ("p09", ["p17"]),
        ("p10", ["p18"]),
    ],
)
def test_pick_follows_main_product_category(source, expected):
    items = cross_sell.pick({"items": []}, source)
    assert [i["id"] for i in items] == expected


def test_pick_skips_accessories_already_in_cart():
    items = cross_sell.pick(_cart("p01", "p11"), "p01")
    assert [i["id"] for i in items] == ["p12"]


def test_pick_returns_empty_for_unknown_product():
    assert cross_sell.pick({"items": []}, "p99") == []
    assert cross_sell.pick({"items": []}, None) == []


def test_pick_all_in_cart_returns_empty():
    assert cross_sell.pick(_cart("p01", "p11", "p12"), "p01") == []


def test_build_uses_template_when_model_unavailable():
    data = cross_sell.build(_cart("p01"), "p01", client=FakeClient())
    assert data is not None
    assert data["product_ids"] == ["p11", "p12"]
    assert "快充头" in data["text"]
    assert data["pending"] == "add_to_cart"
    assert data["source_product_id"] == "p01"


def test_build_returns_none_when_nothing_to_offer():
    assert cross_sell.build(_cart("p01", "p11", "p12"), "p01", client=FakeClient()) is None


def test_build_respects_kill_switch(monkeypatch):
    monkeypatch.setattr(settings, "cross_sell_enabled", False)
    assert cross_sell.build(_cart("p01"), "p01", client=FakeClient()) is None


# ---------------- 确认话术 ----------------

@pytest.mark.parametrize("text", ["好的", "好", "可以", "加上吧", "都加", "行", "嗯嗯", "顺便带上"])
def test_confirm_words(text):
    assert is_confirm(text) is True


@pytest.mark.parametrize("text", ["不用了", "算了", "先不加", "不要", "查一下订单1001的物流", ""])
def test_non_confirm_words(text):
    assert is_confirm(text) is False


@pytest.mark.parametrize("text", ["不用了", "算了", "暂时不要"])
def test_reject_words(text):
    assert is_reject(text) is True


def test_long_sentence_is_not_confirm():
    """用户说了句长话，即使含"可以"也不能当成同意加购。"""
    assert is_confirm("可以帮我看看这个耳机有没有别的颜色吗") is False


# ---------------- 规划与执行 ----------------

def test_plan_executes_pending_suggestion_on_confirm():
    state = SessionState("s")
    state.pending_suggestion = {"product_ids": ["p11", "p12"], "source_product_id": "p01"}
    plan = make_plan("好的", {"intent": "product", "confidence": 0.9, "source": "rule", "slots": {}}, state)
    assert plan["tasks"] == ["add_to_cart"]
    assert plan["pending_ids"] == ["p11", "p12"]
    assert "cross_sell_confirm" in plan["notes"]


def test_plan_ignores_confirm_without_pending():
    state = SessionState("s")
    plan = make_plan("好的", {"intent": "product", "confidence": 0.9, "source": "rule", "slots": {}}, state)
    assert "add_to_cart" not in plan["tasks"]


def test_confirm_consumes_all_accessories():
    from app.agents.tool_loop import stream_tool_turn
    from app.core import sse

    add_to_cart("u1002", "p01", 1)
    ctx: dict = {"results": [], "order": None, "cart": None, "refund": None}
    events = list(
        stream_tool_turn(
            message="好的",
            history=[],
            user=USER,
            tasks=["add_to_cart"],
            candidates=[],
            focus_id=None,
            order_ids=[],
            ctx=ctx,
            client=FakeClient(),
            pending_ids=["p11", "p12"],
        )
    )
    calls = [d for e, d in events if e == sse.TOOL_CALL]
    assert [c["args"]["product_id"] for c in calls] == ["p11", "p12"]
    cart = get_cart("u1002")
    assert cart["count"] == 3
    assert {i["product_id"] for i in cart["items"]} == {"p01", "p11", "p12"}
    # 答应之后不再推荐，避免"推荐→答应→再推荐"的循环
    assert ctx.get("suggestion_seed") is None


def test_orchestrator_emits_suggest_after_cart():
    events = list(
        orchestrator.stream_chat("把 p01 加进购物车", "cs-1", user=USER, client=FakeClient())
    )
    kinds = [e for e, _ in events]
    assert "cart" in kinds and "suggest" in kinds
    suggest = next(d for e, d in events if e == "suggest")
    assert suggest["product_ids"] == ["p11", "p12"]
    assert suggest["items"][0]["name"]

    state = session_mod.get_state("cs-1", "u1002")
    assert state.pending_suggestion["product_ids"] == ["p11", "p12"]


def test_orchestrator_confirm_turn_adds_everything():
    list(orchestrator.stream_chat("把 p01 加进购物车", "cs-2", user=USER, client=FakeClient()))
    events = list(orchestrator.stream_chat("好的", "cs-2", user=USER, client=FakeClient()))
    assert "cart" in [e for e, _ in events]
    cart = get_cart("u1002")
    assert {i["product_id"] for i in cart["items"]} == {"p01", "p11", "p12"}
    state = session_mod.get_state("cs-2", "u1002")
    assert state.pending_suggestion is None


def test_pending_suggestion_expires_next_turn():
    list(orchestrator.stream_chat("把 p01 加进购物车", "cs-3", user=USER, client=FakeClient()))
    assert session_mod.get_state("cs-3", "u1002").pending_suggestion
    list(orchestrator.stream_chat("那它有什么优缺点", "cs-3", user=USER, client=FakeClient()))
    assert session_mod.get_state("cs-3", "u1002").pending_suggestion is None


def test_suggestion_not_repeated_for_same_cart():
    """配件已经在购物车里，就不再推一遍。"""
    add_to_cart("u1002", "p01", 1)
    add_to_cart("u1002", "p11", 1)
    add_to_cart("u1002", "p12", 1)
    events = list(
        orchestrator.stream_chat("再把 p01 加一个", "cs-4", user=USER, client=FakeClient())
    )
    assert "suggest" not in [e for e, _ in events]
