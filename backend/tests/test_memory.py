"""会话记忆测试：5 轮窗口、指代消解、槽位继承、跨用户隔离。"""
from __future__ import annotations

import time
from types import SimpleNamespace

from app.config import settings
from app.core import session as session_mod
from app.core.session import SessionState, resolve


class FakeClient:
    def json_complete(self, *a, **k):
        return {"intent": "product", "confidence": 0.9}

    def tool_complete(self, *a, **k):
        return SimpleNamespace(content="", tool_calls=[])

    def stream(self, messages, **kwargs):
        for ch in "推荐声浪 Air Pro。":
            yield ch


def test_history_keeps_only_five_turns():
    state = SessionState("s")
    for i in range(6):
        state.add_turn("user", f"问题{i}")
        state.add_turn("assistant", f"回答{i}")
    assert len(state.turns) == settings.session_max_turns * 2
    assert state.turns[0]["content"] == "问题1"
    assert state.turns[-1]["content"] == "回答5"


def test_pronoun_is_rewritten_to_product_name():
    state = SessionState("s", focus_product_id="p03")
    resolved = resolve("那它多少钱", state)
    assert resolved["is_followup"] is True
    assert resolved["focus_name"] == "声浪 Air Pro"
    assert "声浪 Air Pro" in resolved["query"]


def test_followup_inherits_category_and_budget():
    state = SessionState("s", last_category="耳机", last_budget_max=500.0, focus_product_id="p03")
    resolved = resolve("还有别的吗", state)
    assert resolved["slots"]["category"] == "耳机"
    assert resolved["slots"]["budget_max"] == 500.0
    assert resolved["wants_alternative"] is True


def test_new_budget_overrides_inherited_budget():
    state = SessionState("s", last_category="耳机", last_budget_max=500.0, focus_product_id="p03")
    resolved = resolve("那 1000 以内的呢", state)
    assert resolved["slots"]["budget_max"] == 1000.0


def test_independent_question_does_not_inherit():
    state = SessionState("s", last_category="耳机", last_budget_max=500.0, focus_product_id="p03")
    resolved = resolve("3000 以内的笔记本推荐一下", state)
    assert resolved["slots"]["category"] == "笔记本"
    assert resolved["focus_product_id"] is None


def test_session_is_isolated_between_users():
    state = session_mod.get_state("shared", "u1001")
    state.add_turn("user", "我的私密问题")
    state.note_results(["p03"])
    session_mod.save_state(state)

    other = session_mod.get_state("shared", "u1003")
    assert list(other.turns) == []
    assert other.focus_product_id is None


def test_expired_session_is_dropped(monkeypatch):
    state = session_mod.get_state("ttl", "u1001")
    state.add_turn("user", "旧对话")
    state.updated_at = time.time() - settings.session_ttl_seconds - 5
    session_mod.save_state(state)

    fresh = session_mod.get_state("ttl", "u1001")
    assert list(fresh.turns) == []


def test_redis_backend_falls_back_to_memory(monkeypatch):
    monkeypatch.setattr(settings, "session_backend", "redis")
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:6399/0")
    session_mod.reset_store()
    try:
        store = session_mod.get_store()
        assert store.__class__.__name__ == "InMemorySessionStore"
    finally:
        session_mod.reset_store()


def test_multi_turn_focus_in_orchestrator():
    from app.agents.orchestrator import stream_chat
    from app.core import sse

    session_mod.clear_session("m1")
    user = {"user_id": "u1001", "display_name": "林一"}

    first = list(stream_chat("有降噪耳机吗", "m1", user=user, client=FakeClient()))
    top = next(d["items"] for e, d in first if e == sse.PRODUCTS)[0]["id"]
    assert top

    second = list(stream_chat("那它多少钱", "m1", user=user, client=FakeClient()))
    meta = dict(second)[sse.META]
    assert meta["focus_product"]["id"] == top
    assert next(d["items"] for e, d in second if e == sse.PRODUCTS)[0]["id"] == top

    state = session_mod.get_state("m1", "u1001")
    assert state.focus_product_id == top
    assert len(state.turns) == 4
