from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core.intent import BOTH, CHITCHAT, ORDER, PRODUCT, route


class FakeJsonClient:
    def __init__(self, payload: dict | None = None, boom: bool = False) -> None:
        self.payload = payload or {}
        self.boom = boom
        self.calls = 0

    def json_complete(self, system: str, user: str, max_tokens: int = 400) -> dict:
        self.calls += 1
        if self.boom:
            return {}
        return self.payload


@pytest.mark.parametrize(
    "text,expected",
    [
        ("500元以内降噪耳机", PRODUCT),
        ("想买个打游戏不卡的本子", PRODUCT),
        ("预算3000左右的手机", PRODUCT),
        ("查一下订单1001的物流", ORDER),
        ("1004到哪了", ORDER),
        ("订单1001的耳机还有货吗", BOTH),
    ],
)
def test_rule_route(text, expected):
    decision = route(text, client=FakeJsonClient())
    assert decision["intent"] == expected
    assert decision["source"].startswith("rule")


def test_rule_route_skips_llm():
    client = FakeJsonClient({"intent": "chitchat"})
    route("查一下订单1001的物流", client=client)
    assert client.calls == 0, "规则命中时不应该再调模型"


def test_llm_fallback_for_ambiguous_message():
    client = FakeJsonClient({"intent": "chitchat", "confidence": 0.87})
    decision = route("随便看看", client=client)
    assert client.calls == 1
    assert decision["intent"] == CHITCHAT
    assert decision["source"] == "llm"


def test_llm_failure_falls_back_to_product():
    decision = route("随便看看", client=FakeJsonClient(boom=True))
    assert decision["intent"] == PRODUCT
    assert decision["source"] == "fallback"


def test_invalid_intent_from_llm_falls_back():
    decision = route("随便看看", client=FakeJsonClient({"intent": "闲聊", "confidence": 0.9}))
    assert decision["intent"] == PRODUCT


def test_meta_event_shape():
    from app.agents.orchestrator import _router_events

    event, data = _router_events(
        {"intent": PRODUCT, "confidence": 0.883, "source": "rule:slot",
         "slots": {"category": "耳机", "budget_max": 500, "order_ids": []}}
    )
    assert event == "meta"
    assert data["intent"] == PRODUCT
    assert data["confidence"] == 0.88
    json.dumps(data)  # 必须可序列化
