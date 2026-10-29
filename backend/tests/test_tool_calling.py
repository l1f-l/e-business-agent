"""Function Calling 测试：订单号抽取 + 三个工具的协议、执行与权限。

分两层：
1. 离线层（默认跑）：正则槽位、FakeClient 验证 tool_calls 解析、工具执行与事件流；
2. live 层（-m live 单独跑）：真实调用 DeepSeek，验证口语里的订单号能被正确抽出。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents.order import detect_tool_call, stream_order
from app.agents.tool_loop import TOOLS, execute_tool, stream_tool_turn
from app.config import settings
from app.core import sse
from app.core.slots import extract_order_ids
from app.tools.orders import query_order


class FakeClient:
    """模拟 DeepSeek 的 tool_calls 返回。"""

    def __init__(self, order_id: str | None = "1001", tool_name: str = "query_order",
                 raw_arguments: str | None = None, text: str = "订单 1001 正在运输中。") -> None:
        self.order_id = order_id
        self.tool_name = tool_name
        self.raw_arguments = raw_arguments
        self.text = text
        self.captured: dict = {}

    def tool_complete(self, messages, tools, max_tokens: int = 400):
        self.captured = {"messages": messages, "tools": tools}
        if self.order_id is None:
            return SimpleNamespace(content="你好呀", tool_calls=[])
        arguments = self.raw_arguments if self.raw_arguments is not None else json.dumps(
            {"order_id": self.order_id}
        )
        call = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name=self.tool_name, arguments=arguments),
        )
        return SimpleNamespace(content=None, tool_calls=[call])

    def stream(self, messages, **kwargs):
        for ch in self.text:
            yield ch


class SeqClient:
    """按顺序吐出预设的工具调用，用完后返回纯文本。"""

    def __init__(self, calls: list[tuple[str, dict]], text: str = "已经帮你处理好了。") -> None:
        self.calls = list(calls)
        self.text = text
        self.messages_seen: list[list] = []

    def tool_complete(self, messages, tools, max_tokens: int = 400):
        self.messages_seen.append(messages)
        if not self.calls:
            return SimpleNamespace(content="", tool_calls=[])
        name, args = self.calls.pop(0)
        call = SimpleNamespace(
            id=f"call_{len(self.messages_seen)}",
            function=SimpleNamespace(name=name, arguments=json.dumps(args, ensure_ascii=False)),
        )
        return SimpleNamespace(content="", tool_calls=[call])

    def stream(self, messages, **kwargs):
        for ch in self.text:
            yield ch


USER_LINYI = {"user_id": "u1001", "display_name": "林一"}
USER_SUQING = {"user_id": "u1003", "display_name": "苏晴"}


def run_tools(message, calls, user=USER_LINYI, tasks=None):
    ctx: dict = {"results": [], "order": None, "cart": None, "refund": None}
    client = SeqClient(calls)
    events = list(
        stream_tool_turn(
            message=message,
            history=[],
            user=user,
            tasks=tasks or [],
            candidates=[],
            focus_id=None,
            order_ids=[],
            ctx=ctx,
            client=client,
        )
    )
    return events, ctx, client


# ---------------- 离线：槽位层 ----------------

@pytest.mark.parametrize(
    "message",
    [
        "查一下订单1001的物流",
        "订单 1001 到哪了",
        "帮我看看单号 1001 的快递",
        "1001 发货了吗",
        "订单号：1001",
    ],
)
def test_order_id_regex_before_llm(message):
    assert extract_order_ids(message) == ["1001"]


# ---------------- 离线：工具协议 ----------------

def test_detect_tool_call_extracts_order_id():
    result = detect_tool_call("查一下订单1001的物流", client=FakeClient())
    assert result is not None
    assert result["order_id"] == "1001"
    assert json.loads(result["raw_arguments"]) == {"order_id": "1001"}


def test_tool_schemas_never_expose_user_id():
    """身份必须由服务端注入，schema 里出现 user_id 就等于把越权入口交给模型。"""
    names = set()
    for tool in TOOLS:
        fn = tool["function"]
        names.add(fn["name"])
        assert "user_id" not in fn["parameters"]["properties"]
        assert "user_id" not in json.dumps(fn["parameters"], ensure_ascii=False)
    assert names == {"query_order", "add_to_cart", "request_refund"}


def test_model_declines_tool_when_no_order():
    assert detect_tool_call("这个耳机多少钱", client=FakeClient(order_id=None)) is None


def test_unknown_tool_name_is_ignored():
    assert detect_tool_call("订单1001", client=FakeClient(tool_name="refund_order")) is None


def test_malformed_arguments_do_not_crash():
    assert detect_tool_call("订单1001", client=FakeClient(raw_arguments="{oops")) is None


def test_empty_order_id_is_ignored():
    assert detect_tool_call("订单1001", client=FakeClient(raw_arguments='{"order_id":"  "}')) is None


# ---------------- 离线：工具执行 ----------------

def test_query_order_found():
    result = query_order("1001", "u1001")
    assert result["ok"] is True
    assert result["status"] == "shipped"
    assert result["carrier"] == "顺丰速运"
    assert result["refundable"] is False


def test_query_order_not_found():
    result = query_order("9999", "u1001")
    assert result["ok"] is False
    assert result["code"] == "ORDER_NOT_FOUND"
    assert "1001" in result["available_order_ids"]


def test_query_order_normalizes_input():
    assert query_order(" 1001 ", "u1001")["ok"] is True
    assert query_order("ORD-1001", "u1001")["ok"] is True


def test_add_to_cart_tool_writes_current_user():
    result = execute_tool("add_to_cart", {"product_id": "p03", "quantity": 2}, "u1001")
    assert result["ok"] is True
    assert result["cart"]["count"] == 2
    assert result["cart"]["items"][0]["product_id"] == "p03"


def test_refund_tool_rejects_other_users_order():
    result = execute_tool("request_refund", {"order_id": "1005"}, "u1001")
    assert result["ok"] is False
    assert result["code"] == "FORBIDDEN"


# ---------------- 离线：事件流 ----------------

def test_stream_order_emits_tool_events():
    client = FakeClient(order_id="1001")
    events = list(stream_order("查一下订单1001的物流", [], client=client, user_id="u1001"))

    kinds = [e for e, _ in events]
    assert sse.TOOL_CALL in kinds
    assert sse.TOOL_RESULT in kinds
    assert kinds[0] == sse.STATUS
    assert kinds[-1] == sse.DONE

    tool_call = dict(events)[sse.TOOL_CALL]
    assert tool_call["args"] == {"order_id": "1001"}

    tool_result = dict(events)[sse.TOOL_RESULT]
    assert tool_result["ok"] is True
    assert tool_result["order"]["status_text"] == "已发货，运输中"


def test_stream_order_falls_back_to_regex_when_model_skips_tool():
    events = list(stream_order("1001到哪了", [], client=FakeClient(order_id=None), user_id="u1001"))
    assert sse.TOOL_CALL in [e for e, _ in events]
    assert dict(events)[sse.TOOL_CALL]["args"] == {"order_id": "1001"}


def test_stream_order_asks_for_id_when_missing():
    events = list(stream_order("我的快递怎么还没到", [], client=FakeClient(order_id=None), user_id="u1001"))
    assert sse.TOOL_CALL not in [e for e, _ in events]
    assert dict(events)[sse.DONE]["reason"] == "missing_order_id"


def test_stream_order_not_found_still_answers():
    events = list(stream_order("查一下订单9999", [], client=FakeClient(order_id="9999"), user_id="u1001"))
    assert dict(events)[sse.TOOL_RESULT]["ok"] is False


def test_tool_loop_emits_cart_event_after_add():
    events, ctx, _ = run_tools(
        "把 p03 加购物车",
        [("add_to_cart", {"product_id": "p03", "quantity": 1})],
        tasks=["add_to_cart"],
    )
    kinds = [e for e, _ in events]
    assert sse.TOOL_CALL in kinds
    assert sse.CART in kinds
    assert kinds.index(sse.TOOL_CALL) < kinds.index(sse.CART)
    cart = dict(events)[sse.CART]
    assert cart["count"] == 1
    assert ctx["cart"]["total"] == 499.0


def test_tool_loop_emits_refund_event():
    events, ctx, _ = run_tools(
        "帮我退掉订单1005",
        [("request_refund", {"order_id": "1005"})],
        user=USER_SUQING,
        tasks=["query_order", "request_refund"],
    )
    refund = dict(events)[sse.REFUND]
    assert refund["ok"] is True
    assert refund["refund_id"] == "RF-1005"
    assert ctx["refund"]["status"] == "requested"


def test_fallback_executes_action_when_model_does_not_call_tool():
    """模型只聊天不动手时，规则兜底仍要把商品加进去。"""
    ctx: dict = {"results": [], "order": None, "cart": None, "refund": None}
    client = SeqClient([], text="好的。")
    events = list(
        stream_tool_turn(
            message="帮我买一个降噪耳机",
            history=[],
            user=USER_LINYI,
            tasks=["add_to_cart"],
            candidates=[{"id": "p03", "name": "声浪 Air Pro", "price": 499, "tagline": "降噪"}],
            focus_id="p03",
            order_ids=[],
            ctx=ctx,
            client=client,
        )
    )
    assert sse.CART in [e for e, _ in events]
    assert ctx["cart"]["count"] == 1


# ---------------- live：真实模型抽取订单号 ----------------

@pytest.mark.live
@pytest.mark.skipif(not settings.deepseek_api_key, reason="需要 DEEPSEEK_API_KEY")
@pytest.mark.parametrize(
    "message,expected_id",
    [
        ("查一下订单1001的物流", "1001"),
        ("订单1004到哪了", "1004"),
        ("我上周买的那个订单1003签收了吗", "1003"),
    ],
)
def test_live_llm_extracts_order_id(message, expected_id):
    from app.llm import llm

    result = detect_tool_call(message, [], client=llm)
    assert result is not None, f"模型没有调用 query_order：{message}"
    assert result["order_id"] == expected_id
