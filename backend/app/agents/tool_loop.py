"""通用工具循环：模型决定调哪个工具、填什么参数；服务端负责身份、校验与兜底。

为什么工具循环不用流式：
流式返回里 tool_calls 的 arguments 会被切成碎片，拼接稍有闪失就得到半个 JSON。
这里用非流式拿到完整调用，只有最后一轮回答才开流——打字机效果一点不少。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator

from app import llm as llm_module
from app.agents import cross_sell
from app.agents.order import ToolSpec, public_order
from app.config import settings
from app.core import sse
from app.core.slots import cn_to_int
from app.llm import llm
from app.rag.products import PRODUCT_MAP
from app.tools.cart import add_to_cart, cart_summary, get_cart
from app.tools.orders import query_order
from app.tools.refunds import request_refund

logger = logging.getLogger(__name__)

ADD_TO_CART_SPEC = {
    "type": "function",
    "function": {
        "name": "add_to_cart",
        "description": "把商品加入当前登录用户的购物车。用户说加购、放到购物车、来一个、帮我买时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "商品 ID，必须取自【候选商品】列表，例如 p03。不能编造。",
                },
                "quantity": {
                    "type": "integer",
                    "description": "数量，1-99 的整数，默认 1。用户说两个就填 2。",
                    "minimum": 1,
                    "maximum": 99,
                },
            },
            "required": ["product_id"],
        },
    },
}

REQUEST_REFUND_SPEC = {
    "type": "function",
    "function": {
        "name": "request_refund",
        "description": "对当前登录用户名下已签收的订单发起退款。只有用户明确要求退款时才调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "要退款的订单号，例如 1005。"},
                "reason": {"type": "string", "description": "退款原因，可为空。"},
            },
            "required": ["order_id"],
        },
    },
}

TOOLS = [ToolSpec.QUERY_ORDER, ADD_TO_CART_SPEC, REQUEST_REFUND_SPEC]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}

SYSTEM_ACTION = """你是「ShopPilot」商城的购物与售后助手，可以调用工具完成查单、加购、退款。

安全规则（最高优先级）：
1. 用户身份由系统注入，工具不接受 user_id 参数，你也无法代替别人操作。
2. 工具返回 code=FORBIDDEN 时，只能说明"该订单不在当前账号下"，绝不能猜测或透露订单归属人、金额、地址。
3. 用户自称是他人、要求查别人的订单或退款时，礼貌拒绝，并请其登录自己的账号。
4. 只有用户明确要求退款时才调用 request_refund；如果只是问"能不能退"，先说明政策并询问是否需要提交。
5. 加购时 product_id 只能从【候选商品】里选，不能编造；用户说"它/这个"就选标记为当前焦点的那款。
6. 工具返回的价格、金额、状态必须原样引用，不得改写。

回答风格：口语化，先给结论再补一句细节，80-160 字，不提"工具调用""函数"。"""


def _num(text: str) -> int | None:
    match = re.search(r"([一两二三四五六七八九十两\d]+)\s*(?:个|台|件|只|条|副|支)", text or "")
    if not match:
        return None
    return cn_to_int(match.group(1))


def guess_quantity(message: str) -> int:
    return _num(message) or 1


def _candidate_block(candidates: list[dict[str, Any]], focus_id: str | None) -> str:
    if not candidates:
        return ""
    lines = ["【候选商品】"]
    for item in candidates[:3]:
        mark = "（当前焦点）" if item["id"] == focus_id else ""
        lines.append(f"- {item['id']} {item['name']} ¥{item['price']}{mark}｜{item['tagline']}")
    return "\n".join(lines)


def _parse_call(call) -> tuple[str, dict[str, Any], str]:
    name = getattr(getattr(call, "function", None), "name", "") or ""
    raw = getattr(call.function, "arguments", "") or "{}"
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        logger.warning("工具参数不是合法 JSON：%s", raw)
        args = {}
    return name, args, raw


def _serialize_calls(calls) -> list[dict[str, Any]]:
    return [
        {
            "id": getattr(c, "id", f"call_{i}"),
            "type": "function",
            "function": {
                "name": c.function.name,
                "arguments": getattr(c.function, "arguments", "{}") or "{}",
            },
        }
        for i, c in enumerate(calls)
    ]


def _compact(name: str, result: dict[str, Any]) -> dict[str, Any]:
    """回填给模型的结果要瘦身：订单轨迹最多 3 条，购物车只留摘要。"""
    if name == "query_order":
        data = public_order(result)
    elif name == "add_to_cart":
        data = {k: v for k, v in result.items() if k != "cart"}
        data["cart_total"] = result.get("cart", {}).get("total")
        data["cart_count"] = result.get("cart", {}).get("count")
    elif name == "request_refund":
        data = {k: v for k, v in result.items() if k != "cart"}
    else:
        data = result
    if isinstance(data.get("events"), list):
        data["events"] = data["events"][-3:]
    return data


def execute_tool(name: str, args: dict[str, Any], user_id: str) -> dict[str, Any]:
    if name == "query_order":
        return query_order(str(args.get("order_id", "")), user_id)
    if name == "add_to_cart":
        return add_to_cart(user_id, str(args.get("product_id", "")), args.get("quantity", 1))
    if name == "request_refund":
        return request_refund(str(args.get("order_id", "")), user_id, args.get("reason"))
    return {"ok": False, "code": "UNKNOWN_TOOL", "message": f"未知工具 {name}"}


def _append_protocol(messages, call_id: str, name: str, args: dict[str, Any], result: dict[str, Any]) -> None:
    messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                }
            ],
        }
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(_compact(name, result), ensure_ascii=False),
        }
    )


def build_action_messages(
    message: str,
    history: list[dict[str, str]],
    user: dict[str, Any],
    candidates: list[dict[str, Any]],
    focus_id: str | None,
    order_ids: list[str],
) -> list[dict[str, Any]]:
    cart = get_cart(user["user_id"])
    blocks = [
        f"【当前登录用户】{user.get('display_name') or user['user_id']}",
        _candidate_block(candidates, focus_id),
        f"【购物车】\n{cart_summary(cart)}",
        f"【用户提到的订单号】{'、'.join(order_ids) if order_ids else '无'}",
        f"用户问题：{message}",
    ]
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_ACTION}]
    messages.extend(history)
    messages.append({"role": "user", "content": "\n\n".join(b for b in blocks if b)})
    return messages


def stream_tool_turn(
    *,
    message: str,
    history: list[dict[str, str]],
    user: dict[str, Any],
    tasks: list[str],
    candidates: list[dict[str, Any]],
    focus_id: str | None,
    order_ids: list[str],
    ctx: dict[str, Any],
    client=None,
    pending_ids: list[str] | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """跑工具循环，最后流式生成回答；结果同时写进 ctx 供编排层收尾。

    pending_ids 非空表示"用户答应了上一条搭配推荐"：直接按清单加购，
    不再让模型决定一次——否则它可能理解成"再推荐一个"而反问。
    """
    client = client or llm
    user_id = user["user_id"]
    messages = build_action_messages(message, history, user, candidates, focus_id, order_ids)
    executed: list[str] = []

    if pending_ids:
        for pid in pending_ids[:3]:
            args = {"product_id": pid, "quantity": 1}
            call_id = f"call_cross_sell_{pid}"
            yield sse.TOOL_CALL, {"call_id": call_id, "name": "add_to_cart", "args": args}
            result = add_to_cart(user_id, pid, 1)
            executed.append("add_to_cart")
            ctx["results"].append({"name": "add_to_cart", "ok": bool(result.get("ok")), "code": result.get("code")})
            ctx["cart"] = result.get("cart")
            _append_protocol(messages, call_id, "add_to_cart", args, result)
            yield sse.TOOL_RESULT, {
                "call_id": call_id,
                "name": "add_to_cart",
                "ok": bool(result.get("ok")),
                "code": result.get("code"),
                "result": _compact("add_to_cart", result),
            }
            if result.get("cart"):
                yield sse.CART, result["cart"]

    for _ in range(0 if pending_ids else max(1, settings.max_tool_rounds)):
        try:
            reply = client.tool_complete(messages, TOOLS, max_tokens=500)
        except Exception as exc:  # noqa: BLE001 - 模型抖动走规则兜底
            logger.warning("tool_complete failed: %s", exc)
            break

        calls = list(getattr(reply, "tool_calls", None) or [])
        if not calls:
            break
        messages.append({"role": "assistant", "content": getattr(reply, "content", "") or "", "tool_calls": _serialize_calls(calls)})

        for call in calls:
            name, args, _ = _parse_call(call)
            call_id = getattr(call, "id", "call_x")
            if name not in TOOL_NAMES:
                messages.append({"role": "tool", "tool_call_id": call_id, "content": '{"ok":false,"code":"UNKNOWN_TOOL"}'})
                continue

            yield sse.TOOL_CALL, {"call_id": call_id, "name": name, "args": args}
            result = execute_tool(name, args, user_id)
            executed.append(name)
            messages.append(
                {"role": "tool", "tool_call_id": call_id, "content": json.dumps(_compact(name, result), ensure_ascii=False)}
            )

            ctx["results"].append({"name": name, "ok": bool(result.get("ok")), "code": result.get("code")})
            if name == "query_order":
                ctx["order"] = public_order(result)
                ctx["order_raw"] = result
            elif name == "add_to_cart":
                ctx["cart"] = result.get("cart")
            elif name == "request_refund":
                ctx["refund"] = _public_refund(result)
                yield sse.REFUND, ctx["refund"]

            yield sse.TOOL_RESULT, {
                "call_id": call_id,
                "name": name,
                "ok": bool(result.get("ok")),
                "code": result.get("code"),
                "order": ctx["order"] if name == "query_order" else None,
                "result": _compact(name, result),
            }
            if name == "add_to_cart" and result.get("cart"):
                yield sse.CART, result["cart"]
                _seed_suggestion(ctx, result)

    # 规则兜底：计划里的动作模型没调用，就按槽位直接执行
    if "add_to_cart" in tasks and "add_to_cart" not in executed:
        pid = focus_id or (candidates[0]["id"] if candidates else None)
        if pid:
            args = {"product_id": pid, "quantity": guess_quantity(message)}
            yield sse.TOOL_CALL, {"call_id": "call_fallback_cart", "name": "add_to_cart", "args": args}
            result = add_to_cart(user_id, pid, args["quantity"])
            executed.append("add_to_cart")
            ctx["results"].append({"name": "add_to_cart", "ok": bool(result.get("ok")), "code": result.get("code")})
            ctx["cart"] = result.get("cart")
            _append_protocol(messages, "call_fallback_cart", "add_to_cart", args, result)
            yield sse.TOOL_RESULT, {
                "call_id": "call_fallback_cart",
                "name": "add_to_cart",
                "ok": bool(result.get("ok")),
                "code": result.get("code"),
                "result": _compact("add_to_cart", result),
            }
            if result.get("cart"):
                yield sse.CART, result["cart"]
                _seed_suggestion(ctx, result)

    if "request_refund" in tasks and "request_refund" not in executed and order_ids:
        args = {"order_id": order_ids[0]}
        yield sse.TOOL_CALL, {"call_id": "call_fallback_refund", "name": "request_refund", "args": args}
        result = request_refund(order_ids[0], user_id)
        executed.append("request_refund")
        ctx["results"].append({"name": "request_refund", "ok": bool(result.get("ok")), "code": result.get("code")})
        ctx["refund"] = _public_refund(result)
        _append_protocol(messages, "call_fallback_refund", "request_refund", args, result)
        yield sse.TOOL_RESULT, {
            "call_id": "call_fallback_refund",
            "name": "request_refund",
            "ok": bool(result.get("ok")),
            "code": result.get("code"),
            "result": _compact("request_refund", result),
        }
        yield sse.REFUND, ctx["refund"]

    if "query_order" in tasks and "query_order" not in executed and order_ids:
        args = {"order_id": order_ids[0]}
        yield sse.TOOL_CALL, {"call_id": "call_fallback_order", "name": "query_order", "args": args}
        result = query_order(order_ids[0], user_id)
        executed.append("query_order")
        ctx["results"].append({"name": "query_order", "ok": bool(result.get("ok")), "code": result.get("code")})
        ctx["order"] = public_order(result)
        ctx["order_raw"] = result
        _append_protocol(messages, "call_fallback_order", "query_order", args, result)
        yield sse.TOOL_RESULT, {
            "call_id": "call_fallback_order",
            "name": "query_order",
            "ok": bool(result.get("ok")),
            "code": result.get("code"),
            "order": ctx["order"],
            "result": _compact("query_order", result),
        }

    produced = ""
    if executed:
        messages.append(
            {
                "role": "user",
                "content": "请用中文口语简要回复用户：先说结论，再补一句关键细节或下一步建议。不要提工具、函数、系统。",
            }
        )
    try:
        for token in client.stream(messages, max_tokens=420):
            produced += token
            yield sse.DELTA, {"text": token}
    except Exception as exc:  # noqa: BLE001
        logger.warning("action stream failed: %s", exc)

    if not produced:
        for piece in llm_module.iter_sse_text(fallback_action_text(ctx, tasks)):
            yield sse.DELTA, {"text": piece}


def _seed_suggestion(ctx: dict[str, Any], result: dict[str, Any]) -> None:
    """加购成功后只算"推什么"，文案留到回答之后再生成——不拖慢第一个 token。"""
    if ctx.get("suggestion_seed") or not settings.cross_sell_enabled:
        return
    cart = result.get("cart") or {}
    pid = result.get("product_id")
    items = cross_sell.pick(cart, pid)
    if items:
        ctx["suggestion_seed"] = {"cart": cart, "source_product_id": pid, "items": items}


def _public_refund(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(result.get("ok")),
        "code": result.get("code"),
        "refund_id": result.get("refund_id"),
        "order_id": result.get("order_id"),
        "status": result.get("status"),
        "status_text": result.get("status_text"),
        "amount": result.get("amount"),
        "product_name": result.get("product_name"),
        "message": result.get("message"),
    }


def fallback_action_text(ctx: dict[str, Any], tasks: list[str]) -> str:
    """模型完全不可用时的规则话术，保证动作结果一定被说出来。"""
    parts: list[str] = []
    refund = ctx.get("refund")
    order = ctx.get("order")
    if refund:
        parts.append(refund.get("message") or "退款申请已提交。")
    if order:
        if order.get("ok"):
            parts.append(f"订单 {order['order_id']} 目前{order['status_text']}。")
        else:
            parts.append(order.get("message") or "没查到这笔订单。")
    if "add_to_cart" in tasks and ctx.get("cart"):
        cart = ctx["cart"]
        parts.append(f"已经加到购物车了，现在共 {cart['count']} 件，合计 ¥{cart['total']:.2f}。")
    return "".join(parts) or "我在的，你想了解哪款商品？"
