"""多模态识图：一张图 → 结构化商品特征 → 直接喂给现有 RAG。

几个必须踩准的点：
1. DeepSeek 视觉模型只接受 **user message** 里的图片，提示词必须和图片同一条 content；
2. 返回必须是 JSON，但模型偶尔会带解释文字，所以要用正则兜一层；
3. 识别失败不能把"拍图搜同款"整条链路打断，降级成用户输入的文字关键词继续检索。
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from typing import Any

from app.config import settings
from app.llm import LLMClient, llm

logger = logging.getLogger(__name__)

CATEGORIES = ("手机", "耳机", "笔记本", "平板", "手表")

VISION_PROMPT = """你是电商识图助手。看图片里的商品，为"搜同款"提取特征。
规则：
1. 只描述图片里看得见的特征，看不清就留空，不要猜品牌、型号、价格。
2. category 只能是 手机/耳机/笔记本/平板/手表 之一，判断不了就给 null。
3. form 是形态（头戴式、入耳式、直板、翻盖、轻薄本…），最多 8 字。
4. colors 用常见颜色词；features 最多 4 个；keywords 是搜索用组合词，3-6 个，必须包含品类词。
5. confidence 是 0-1 的小数，拿不准就给低分。
只输出 JSON：{"category":"","colors":[],"form":"","features":[],"keywords":[],"confidence":0.0}"""


class ImageError(ValueError):
    """图片本身不合法（格式、大小），由路由映射成 400。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def sniff_mime(raw: bytes) -> str | None:
    """按文件头判断真实格式——后缀和 MIME 都可能被伪造。"""
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_image(image_base64: str, declared_mime: str | None = None) -> tuple[bytes, str]:
    """base64 → (bytes, 真实 mime)。不合法直接抛 ImageError。"""
    payload = (image_base64 or "").strip()
    if payload.startswith("data:"):
        # data:image/jpeg;base64,xxxx
        header, _, payload = payload.partition(",")
        found = re.search(r"data:([\w/+.-]+);base64", header)
        if found:
            declared_mime = declared_mime or found.group(1)
    if not payload:
        raise ImageError("IMAGE_EMPTY", "没有收到图片数据。")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageError("IMAGE_INVALID", "图片编码不合法，请换一张试试。") from exc

    if len(raw) < settings.image_min_bytes:
        raise ImageError("IMAGE_TOO_SMALL", "这张图太小了，换一张清晰点的。")
    if len(raw) > settings.image_max_bytes:
        raise ImageError(
            "IMAGE_TOO_LARGE",
            f"图片超过 {settings.image_max_bytes // (1024 * 1024)}MB，压缩后再传。",
        )

    mime = sniff_mime(raw)
    if mime is None:
        raise ImageError("IMAGE_TYPE_UNSUPPORTED", "只支持 JPG / PNG / WebP / GIF 图片。")
    return raw, mime


def _client(client=None) -> Any:
    if client is not None:
        return client
    return LLMClient(model=settings.vision_model, timeout=settings.vision_timeout)


def _parse_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _clean_list(value: Any, limit: int = 6) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[,，、/]", value)
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()[:16]
        if text and text not in out:
            out.append(text)
    return out[:limit]


def _normalize(data: dict[str, Any], hint: str) -> dict[str, Any]:
    category = str(data.get("category") or "").strip()
    if category not in CATEGORIES:
        category = ""
    colors = _clean_list(data.get("colors"), 3)
    features = _clean_list(data.get("features"), 4)
    form = str(data.get("form") or "").strip()[:10]
    keywords = _clean_list(data.get("keywords"), 6)

    # keywords 必须能支撑检索：补齐品类/形态/颜色，顺序按"细到粗"
    for token in ([form] if form else []) + colors + features + ([category] if category else []):
        if token and token not in keywords:
            keywords.append(token)
    if category and category not in keywords:
        keywords.append(category)
    keywords = keywords[:6]

    try:
        confidence = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    # 摘要去重：形态词常和 feature 重复（"头戴式"+"头戴式耳机"）
    bits: list[str] = []
    for token in ([colors[0]] if colors else []) + ([form] if form else []) + features[:1] + ([category] if category else []):
        if token and token not in "".join(bits):
            bits.append(token)
    summary = "".join(bits) or (hint or "图片里的商品")
    return {
        "category": category,
        "colors": colors,
        "form": form,
        "features": features,
        "keywords": keywords,
        "confidence": round(confidence, 2),
        "summary": summary,
        "degraded": False,
        "reason": "",
    }


def _fallback(hint: str, reason: str) -> dict[str, Any]:
    tokens = [t for t in re.split(r"[\s,，、/]+", (hint or "").strip()) if t][:6]
    category = next((c for c in CATEGORIES if c in (hint or "")), "")
    if category and category not in tokens:
        tokens.append(category)
    return {
        "category": category,
        "colors": [],
        "form": "",
        "features": [],
        "keywords": tokens,
        "confidence": 0.0,
        "summary": hint.strip() or "图片里的商品",
        "degraded": True,
        "reason": reason,
    }


def describe(raw: bytes, mime: str, hint: str = "", client=None) -> dict[str, Any]:
    """识别图片里的商品特征；任何异常都降级，不抛给上层。"""
    if not settings.vision_enabled:
        return _fallback(hint, "vision_disabled")
    if not settings.deepseek_api_key and client is None:
        return _fallback(hint, "no_api_key")

    b64 = base64.b64encode(raw).decode("ascii")
    prompt = VISION_PROMPT + (f"\n用户补充说明：{hint}" if hint.strip() else "")
    try:
        message = _client(client).complete(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "low"},
                        },
                    ],
                }
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=320,
        )
        data = _parse_json(getattr(message, "content", "") or "")
        if not data:
            return _fallback(hint, "empty_response")
        result = _normalize(data, hint)
        if not result["keywords"]:
            return _fallback(hint, "no_keywords")
        return result
    except Exception as exc:  # noqa: BLE001 - 识图失败必须能继续用文字搜
        logger.warning("视觉识别失败：%s", exc)
        return _fallback(hint, "vision_failed")


def search_query(features: dict[str, Any]) -> str:
    """把特征拼成检索语句；去掉被更长词包含的碎片（"黑色" ⊂ "黑色耳机"）。"""
    tokens = [t for t in features.get("keywords", []) if t]
    kept = [t for t in tokens if not any(t != other and t in other for other in tokens)]
    if features.get("summary") and features["summary"] not in kept:
        kept.append(features["summary"])
    return " ".join(p for p in kept if p) or "商品"


def public_features(features: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": features.get("category") or "",
        "colors": features.get("colors") or [],
        "form": features.get("form") or "",
        "features": features.get("features") or [],
        "keywords": features.get("keywords") or [],
        "confidence": features.get("confidence", 0.0),
        "summary": features.get("summary") or "",
    }
