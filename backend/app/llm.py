"""DeepSeek（OpenAI 兼容协议）客户端封装。

所有模型调用都从这里走，方便测试替换与超时/重试统一处理。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Iterator

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.model = model or settings.llm_model
        self._client = OpenAI(
            api_key=api_key or settings.deepseek_api_key,
            base_url=base_url or settings.deepseek_base_url,
            timeout=timeout,
            max_retries=1,
        )

    # ---------- 基础调用 ----------
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 800,
    ):
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message

    def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.6,
        max_tokens: int = 900,
    ) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    # ---------- 便捷方法 ----------
    def json_complete(self, system: str, user: str, *, max_tokens: int = 400) -> dict[str, Any]:
        """强约束 JSON 输出，失败返回空 dict 由调用方降级。"""
        try:
            msg = self.complete(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
            )
            raw = (msg.content or "").strip()
            return json.loads(raw) if raw else {}
        except Exception as exc:  # noqa: BLE001 - 路由失败必须可降级
            logger.warning("json_complete failed: %s", exc)
            return {}

    def tool_complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_tokens: int = 400,
    ):
        return self.complete(messages, tools=tools, temperature=0.0, max_tokens=max_tokens)


llm = LLMClient()


def has_api_key() -> bool:
    return bool(settings.deepseek_api_key)


def iter_sse_text(text: str, size: int = 2) -> Iterable[str]:
    """模型不可用时把整段话切成小片，保证前端仍能看到打字机效果。"""
    for i in range(0, len(text), size):
        yield text[i : i + size]
