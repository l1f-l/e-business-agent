"""SSE 事件编码：前后端唯一契约（协议 v2）。"""
from __future__ import annotations

import json
from typing import Any

# 事件类型
META = "meta"
PLAN = "plan"
STEP = "step"
STATUS = "status"
PRODUCTS = "products"
REVIEWS = "reviews"
COMPARE = "compare"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
CART = "cart"
REFUND = "refund"
SUGGEST = "suggest"
DELTA = "delta"
DONE = "done"
ERROR = "error"


def encode(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def parse(text: str) -> list[tuple[str, dict]]:
    """测试用：把 SSE 文本流解析成 (event, data) 列表。"""
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if event and data is not None:
            events.append((event, data))
    return events
