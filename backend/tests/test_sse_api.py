"""SSE 接口测试：事件顺序、结构化数据、鉴权与新增的进度/购物车/退款事件。"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.agents.orchestrator as orch
from app.core import auth, sse
from app.main import app


class FakeClient:
    """按工具名决定调不调工具，模拟真实模型的选择行为。"""

    def __init__(self, order_id: str | None = None, add_product: str | None = None,
                 refund_order: str | None = None, text: str = "推荐声浪 Air Pro，499 元，降噪够用。") -> None:
        self.order_id = order_id
        self.add_product = add_product
        self.refund_order = refund_order
        self.text = text
        self.used: set[str] = set()

    def json_complete(self, system: str, user: str, max_tokens: int = 400) -> dict:
        return {"intent": "chitchat", "confidence": 0.9}

    def tool_complete(self, messages, tools, max_tokens: int = 400):
        names = {t["function"]["name"] for t in tools}
        if self.add_product and "add_to_cart" in names and "add_to_cart" not in self.used:
            self.used.add("add_to_cart")
            return self._call("add_to_cart", {"product_id": self.add_product, "quantity": 1})
        if self.refund_order and "request_refund" in names and "request_refund" not in self.used:
            self.used.add("request_refund")
            return self._call("request_refund", {"order_id": self.refund_order})
        if self.order_id and "query_order" in names and "query_order" not in self.used:
            self.used.add("query_order")
            return self._call("query_order", {"order_id": self.order_id})
        return SimpleNamespace(content="", tool_calls=[])

    @staticmethod
    def _call(name: str, args: dict):
        call = SimpleNamespace(
            id=f"call_{name}",
            function=SimpleNamespace(name=name, arguments=json.dumps(args, ensure_ascii=False)),
        )
        return SimpleNamespace(content=None, tool_calls=[call])

    def stream(self, messages, **kwargs):
        for ch in self.text:
            yield ch


def read_stream(client: TestClient, payload: dict, headers: dict) -> list[tuple[str, dict]]:
    with client.stream("POST", "/api/chat/stream", json=payload, headers=headers) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    return sse.parse(body)


def first(events, kind):
    for event, data in events:
        if event == kind:
            return data
    raise AssertionError(f"没有 {kind} 事件：{[e for e, _ in events]}")


def headers_for(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token(user_id)[0]}"}


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


# ---------------- 商品链路 ----------------

def test_product_query_emits_products_then_text(client, auth_headers, monkeypatch):
    monkeypatch.setattr(orch, "llm", FakeClient(text="推荐声浪 Air Pro，499 元，降噪够用。"))
    events = read_stream(client, {"message": "500元以内降噪耳机", "session_id": "test"}, auth_headers)
    kinds = [e for e, _ in events]

    assert kinds[0] == sse.STATUS, "首帧应为状态提示，让用户先看到反馈"
    assert kinds.index(sse.META) < kinds.index(sse.PRODUCTS), "meta 必须先于商品数据"
    assert sse.DELTA in kinds
    assert kinds[-1] == sse.DONE

    meta = first(events, sse.META)
    assert meta["intent"] == "product"
    assert meta["slot"]["category"] == "耳机"
    assert meta["slot"]["budget_max"] == 500

    products = first(events, sse.PRODUCTS)
    top = products["items"][0]
    for key in ("id", "name", "price", "image", "tagline", "highlights", "score"):
        assert key in top
    assert top["id"] == "p03"
    assert all(item["price"] <= 500 for item in products["items"])

    text = "".join(d.get("text", "") for e, d in events if e == sse.DELTA)
    assert "声浪" in text


# ---------------- 订单链路 ----------------

def test_order_query_emits_tool_events(client, auth_headers, monkeypatch):
    monkeypatch.setattr(orch, "llm", FakeClient(order_id="1001", text="订单 1001 已发货，顺丰运输中。"))
    events = read_stream(client, {"message": "查一下订单1001的物流", "session_id": "test"}, auth_headers)
    kinds = [e for e, _ in events]

    assert first(events, sse.META)["intent"] == "order"
    assert kinds.index(sse.TOOL_CALL) < kinds.index(sse.TOOL_RESULT)

    call = first(events, sse.TOOL_CALL)
    assert call["name"] == "query_order"
    assert call["args"] == {"order_id": "1001"}
    assert call["call_id"]

    result = first(events, sse.TOOL_RESULT)
    assert result["ok"] is True
    assert result["order"]["carrier"] == "顺丰速运"
    assert result["order"]["events"]


def test_cross_user_order_is_denied(client, auth_headers, monkeypatch):
    """u1001 查 u1002 的订单：工具层拒绝，且不泄露归属人。"""
    monkeypatch.setattr(orch, "llm", FakeClient(order_id="1003", text="这笔订单不在当前账号下。"))
    events = read_stream(client, {"message": "查一下订单1003的物流", "session_id": "test"}, auth_headers)

    result = first(events, sse.TOOL_RESULT)
    assert result["ok"] is False
    assert result["code"] == "FORBIDDEN"
    assert "周一鸣" not in json.dumps(result, ensure_ascii=False)


# ---------------- 复杂任务：计划 + 工具 + 购物车 ----------------

def test_complex_task_emits_plan_steps_and_cart(client, auth_headers, monkeypatch):
    monkeypatch.setattr(orch, "llm", FakeClient(add_product="p03", text="已经帮你加购了。"))
    events = read_stream(
        client,
        {"message": "帮我买一个500元以内的降噪耳机并加购物车", "session_id": "buy"},
        auth_headers,
    )
    kinds = [e for e, _ in events]

    assert sse.PLAN in kinds, "复杂任务必须先下发计划"
    plan = first(events, sse.PLAN)
    ids = [step["id"] for step in plan["steps"]]
    assert ids == ["think", "retrieve", "add_to_cart", "answer"]

    steps = [(d["id"], d["status"]) for e, d in events if e == sse.STEP]
    assert ("retrieve", "running") in steps
    assert ("retrieve", "done") in steps
    assert ("add_to_cart", "done") in steps
    assert kinds.index(sse.PLAN) < kinds.index(sse.PRODUCTS) < kinds.index(sse.TOOL_CALL)
    assert kinds.index(sse.TOOL_RESULT) < kinds.index(sse.CART)

    cart = first(events, sse.CART)
    assert cart["count"] == 1
    assert cart["total"] == 499.0
    assert first(events, sse.DONE)["cart_count"] == 1


# ---------------- 评论 / 对比 ----------------

def test_review_question_emits_reviews_block(client, auth_headers, monkeypatch):
    monkeypatch.setattr(orch, "llm", FakeClient(text="降噪强，但戴久了耳道胀。"))
    events = read_stream(client, {"message": "500元以内降噪耳机有什么优缺点", "session_id": "rv"}, auth_headers)

    reviews = first(events, sse.REVIEWS)
    assert reviews["summaries"]
    summary = reviews["summaries"][0]
    assert summary["pros"] and summary["cons"]
    assert summary["items"], "必须带至少一条真实评论原文"


def test_compare_emits_two_column_data(client, auth_headers, monkeypatch):
    monkeypatch.setattr(orch, "llm", FakeClient(text="p03 降噪更强，p04 更便宜。"))
    events = read_stream(client, {"message": "对比一下 p03 和 p04", "session_id": "cmp"}, auth_headers)

    data = first(events, sse.COMPARE)
    assert data["left"]["id"] == "p03"
    assert data["right"]["id"] == "p04"
    labels = [row["label"] for row in data["rows"]]
    assert "价格" in labels and "差评要点" in labels
    assert data["verdict"]

    products = first(events, sse.PRODUCTS)
    assert [p["id"] for p in products["items"]] == ["p03", "p04"], "对比场景不应塞入无关商品"


# ---------------- 退款 ----------------

def test_refund_flow_emits_refund_event(client, monkeypatch):
    monkeypatch.setattr(orch, "llm", FakeClient(refund_order="1005", text="退款已提交。"))
    events = read_stream(
        client,
        {"message": "帮我退掉订单1005", "session_id": "rf"},
        headers_for("u1003"),
    )
    refund = first(events, sse.REFUND)
    assert refund["ok"] is True
    assert refund["refund_id"] == "RF-1005"
    assert refund["status"] == "requested"


# ---------------- 鉴权与其它接口 ----------------

def test_chat_requires_token(client):
    assert client.post("/api/chat", json={"message": "你好"}).status_code == 401
    with client.stream("POST", "/api/chat/stream", json={"message": "你好"}) as resp:
        assert resp.status_code == 401


def test_non_stream_endpoint(client, auth_headers, monkeypatch):
    monkeypatch.setattr(orch, "llm", FakeClient(text="推荐声浪 Air Pro。"))
    resp = client.post("/api/chat", json={"message": "500元以内降噪耳机", "session_id": "test"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["products"][0]["id"] == "p03"
    assert data["answer"]
    assert data["intent"] == "product"


def test_products_endpoint(client):
    items = client.get("/api/products").json()["items"]
    assert len(items) == 10
    assert {item["category"] for item in items} == {"手机", "耳机", "笔记本", "平板", "手表"}


def test_product_detail_includes_reviews(client):
    data = client.get("/api/products/p05").json()
    assert data["id"] == "p05"
    assert data["specs"]
    assert data["reviews"]["count"] >= 5
    assert data["reviews"]["cons"]


def test_compare_endpoint(client):
    data = client.get("/api/products/compare?ids=p03,p04").json()
    assert data["ok"] is True
    assert data["left"]["id"] == "p03"
    assert client.get("/api/products/compare?ids=p03").status_code == 400
    assert client.get("/api/products/compare?ids=p03,p99").status_code == 404


def test_health_endpoint(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["products"] == 10
    assert data["reviews"] >= 60
    assert data["embedding"] in {"bge", "hash"}


def test_validation_rejects_empty_message(client, auth_headers):
    assert client.post("/api/chat/stream", json={"message": ""}, headers=auth_headers).status_code == 422
