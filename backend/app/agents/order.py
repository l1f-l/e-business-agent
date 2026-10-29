"""订单工具链路：Function Calling 抽取订单号 → 执行 query_order → 流式作答。

user_id 一律由服务端注入，工具 schema 里没有这个参数——模型无法越权。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from app import llm as llm_module
from app.core import sse
from app.core.slots import extract_order_ids, extract_slots
from app.llm import llm
from app.tools.orders import query_order

logger = logging.getLogger(__name__)


class ToolSpec:
    """与 OpenAI / DeepSeek 兼容的 tools 定义。"""

    QUERY_ORDER = {
        "type": "function",
        "function": {
            "name": "query_order",
            "description": "根据订单号查询订单状态、金额、承运商与物流轨迹。用户问订单、物流、发货、签收、退款时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，纯数字或字母数字组合，例如 1001。只抽取用户明确提到的订单号。",
                    }
                },
                "required": ["order_id"],
            },
        },
    }

    ALL = [QUERY_ORDER]


SYSTEM_ORDER = """你是「ShopPilot」商城的订单客服。你的回答必须完全基于【订单查询结果】里的事实。

规则：
1. 只讲查询结果里出现的信息，不要编造物流节点、时间或金额。
2. 先一句话给结论（到哪了 / 什么状态），再补 1-2 条最新轨迹和预计送达时间。
3. 用户问的是订单号不存在的情况：诚恳说明没查到，并提示核对订单号。
4. 查询结果里 code=FORBIDDEN 时，只说"该订单不在当前账号下"，绝不能猜测或透露归属人、金额、地址。
5. 语气自然、简短，80-150 字，不要输出 JSON、表格或 Markdown 标题。
6. 不要提"工具调用""函数"这类实现细节。"""


def _system_messages(history: list[dict[str, str]], message: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_ORDER}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})
    return messages


def detect_tool_call(
    message: str,
    history: list[dict[str, str]] | None = None,
    client=None,
) -> dict[str, Any] | None:
    """让模型自己决定是否调用 query_order，并抽取订单号。"""
    client = client or llm
    try:
        msg = client.tool_complete(_system_messages(history or [], message), ToolSpec.ALL, max_tokens=300)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tool_complete failed: %s", exc)
        return None

    for call in getattr(msg, "tool_calls", None) or []:
        name = getattr(getattr(call, "function", None), "name", None)
        if name != "query_order":
            continue
        raw = getattr(call.function, "arguments", "") or "{}"
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("工具参数不是合法 JSON: %s", raw)
            args = {}
        order_id = str(args.get("order_id", "")).strip()
        return {"order_id": order_id, "raw_arguments": raw} if order_id else None
    return None


def public_order(result: dict[str, Any]) -> dict[str, Any]:
    """给前端的订单结构：失败也只给原因码和可查单号，不含他人信息。"""
    if not result.get("ok"):
        return {
            "ok": False,
            "code": result.get("code", "ORDER_NOT_FOUND"),
            "order_id": result.get("order_id"),
            "message": result.get("message"),
            "available_order_ids": result.get("available_order_ids", [])[:6],
        }
    return {
        "ok": True,
        "order_id": result["order_id"],
        "product_id": result.get("product_id"),
        "product_name": result["product_name"],
        "qty": result["qty"],
        "amount": result["amount"],
        "status": result["status"],
        "status_text": result["status_text"],
        "carrier": result.get("carrier"),
        "tracking_no": result.get("tracking_no"),
        "eta": result.get("eta"),
        "latest_event": result.get("latest_event"),
        "events": result.get("events", [])[-4:],
        "refundable": bool(result.get("refundable")),
        "refund": result.get("refund"),
    }


def _tool_protocol_messages(message: str, order_id: str, raw_args: str, result: dict[str, Any]):
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_ORDER}]
    messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_query_order_1",
                    "type": "function",
                    "function": {
                        "name": "query_order",
                        "arguments": raw_args or json.dumps({"order_id": order_id}, ensure_ascii=False),
                    },
                }
            ],
        }
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": "call_query_order_1",
            "content": json.dumps(result, ensure_ascii=False),
        }
    )
    messages.append({"role": "user", "content": message})
    return messages


def fallback_answer(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        if result.get("code") == "FORBIDDEN":
            return "这笔订单不在当前账号下，我这边没法查看。麻烦确认下订单号，或者切到下单选用的账号再查。"
        return f"没查到订单 {result.get('order_id')}，麻烦您核对一下订单号，或者把下单手机号给我，我再帮您找。"
    text = (
        f"订单 {result['order_id']} 目前{result['status_text']}，"
        f"商品是 {result['product_name']} ×{result['qty']}，共 ¥{result['amount']:.2f}。"
    )
    if result.get("latest_event"):
        text += f" 最新进度：{result['latest_event']}。"
    if result.get("eta"):
        text += f" {result['eta']}。"
    return text


def stream_order(
    message: str,
    history: list[dict[str, str]] | None = None,
    client=None,
    forced_order_id: str | None = None,
    user_id: str | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    history = history or []
    client = client or llm
    yield sse.STATUS, {"stage": "routing_tool", "text": "正在识别订单号…"}

    detected = detect_tool_call(message, history, client=client)
    order_id = (forced_order_id or (detected or {}).get("order_id") or "").strip()
    raw_args = (detected or {}).get("raw_arguments", "")

    if not order_id:
        ids = extract_order_ids(message) or extract_slots(message)["order_ids"]
        if ids:
            order_id = ids[0]

    if not order_id:
        yield sse.STATUS, {"stage": "need_more_info", "text": "缺少订单号"}
        for piece in llm_module.iter_sse_text("可以的，请把订单号发我，比如 1001，我帮您查物流进度。"):
            yield sse.DELTA, {"text": piece}
        yield sse.DONE, {"reason": "missing_order_id"}
        return

    yield sse.TOOL_CALL, {"name": "query_order", "args": {"order_id": order_id}}
    result = query_order(order_id, user_id)
    yield sse.TOOL_RESULT, {
        "name": "query_order",
        "ok": bool(result.get("ok")),
        "code": result.get("code"),
        "order": public_order(result),
    }

    produced = ""
    try:
        messages = _tool_protocol_messages(message, order_id, raw_args, result)
        for token in client.stream(messages):
            produced += token
            yield sse.DELTA, {"text": token}
    except Exception as exc:  # noqa: BLE001
        logger.warning("order stream failed: %s", exc)
        if not produced:
            for piece in llm_module.iter_sse_text(fallback_answer(result)):
                yield sse.DELTA, {"text": piece}

    yield sse.DONE, {"reason": "ok" if result.get("ok") else "order_failed", "order_id": order_id}
