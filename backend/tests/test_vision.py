"""拍图搜同款：图片校验、视觉封装降级、识图检索落库。"""
from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from app.config import settings
from app.core import session as session_mod
from app.rag import vision
from app.routers import search as search_router


def _jpeg(size: tuple[int, int] = (320, 240), color=(24, 24, 24)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG", quality=88)
    return buf.getvalue()


@pytest.fixture()
def jpeg_bytes() -> bytes:
    return _jpeg()


@pytest.fixture(autouse=True)
def _reset_limits():
    search_router.reset_rate_limit()
    yield
    search_router.reset_rate_limit()


class VisionOK:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {
            "category": "耳机",
            "colors": ["黑色"],
            "form": "头戴式",
            "features": ["主动降噪", "可折叠"],
            "keywords": ["黑色耳机", "头戴式"],
            "confidence": 0.86,
        }

    def complete(self, *args, **kwargs):
        return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))


class VisionBoom:
    def complete(self, *args, **kwargs):
        raise RuntimeError("upstream timeout")


# ---------------- 解码与校验 ----------------

def test_decode_accepts_data_url_and_sniffs_mime(jpeg_bytes):
    payload = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()
    raw, mime = vision.decode_image(payload, "image/jpeg")
    assert mime == "image/jpeg"
    assert raw == jpeg_bytes


def test_decode_trusts_content_over_declared_mime(jpeg_bytes):
    """后缀写 png，实际是 jpeg：按真实内容走。"""
    raw, mime = vision.decode_image(base64.b64encode(jpeg_bytes).decode(), "image/png")
    assert mime == "image/jpeg"
    assert raw


def test_decode_rejects_non_image():
    payload = base64.b64encode(b"not an image at all" * 120).decode()
    with pytest.raises(vision.ImageError) as exc:
        vision.decode_image(payload)
    assert exc.value.code == "IMAGE_TYPE_UNSUPPORTED"


def test_decode_rejects_broken_base64():
    with pytest.raises(vision.ImageError) as exc:
        vision.decode_image("!!!!not-base64!!!!")
    assert exc.value.code == "IMAGE_INVALID"


def test_decode_rejects_tiny_image():
    payload = base64.b64encode(_jpeg((8, 8))).decode()
    with pytest.raises(vision.ImageError) as exc:
        vision.decode_image(payload)
    assert exc.value.code == "IMAGE_TOO_SMALL"


def test_decode_rejects_oversize(jpeg_bytes, monkeypatch):
    monkeypatch.setattr(settings, "image_max_bytes", 100)
    with pytest.raises(vision.ImageError) as exc:
        vision.decode_image(base64.b64encode(jpeg_bytes).decode())
    assert exc.value.code == "IMAGE_TOO_LARGE"


def test_sniff_mime_recognises_formats():
    assert vision.sniff_mime(b"\xff\xd8\xff\xe0" + b"0" * 20) == "image/jpeg"
    assert vision.sniff_mime(b"\x89PNG\r\n\x1a\n" + b"0" * 20) == "image/png"
    assert vision.sniff_mime(b"GIF89a" + b"0" * 20) == "image/gif"
    assert vision.sniff_mime(b"RIFF" + b"0" * 4 + b"WEBP" + b"0" * 12) == "image/webp"
    assert vision.sniff_mime(b"plain text") is None


# ---------------- 特征抽取 ----------------

def test_describe_returns_structured_features(jpeg_bytes):
    features = vision.describe(jpeg_bytes, "image/jpeg", "", client=VisionOK())
    assert features["degraded"] is False
    assert features["category"] == "耳机"
    assert features["colors"] == ["黑色"]
    assert features["form"] == "头戴式"
    assert features["confidence"] == 0.86
    assert "耳机" in features["keywords"]
    assert features["summary"].startswith("黑色头戴式")


def test_describe_appends_category_when_model_omits_it(jpeg_bytes):
    payload = {"category": "手机", "colors": [], "form": "", "features": [], "keywords": ["旗舰", "拍照"], "confidence": 0.7}
    features = vision.describe(jpeg_bytes, "image/jpeg", "", client=VisionOK(payload))
    assert features["keywords"][-1] == "手机"


def test_describe_falls_back_when_model_fails(jpeg_bytes):
    features = vision.describe(jpeg_bytes, "image/jpeg", "降噪耳机", client=VisionBoom())
    assert features["degraded"] is True
    assert features["reason"] == "vision_failed"
    assert features["category"] == "耳机"
    assert "降噪耳机" in features["keywords"]


def test_describe_falls_back_without_api_key(jpeg_bytes, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    features = vision.describe(jpeg_bytes, "image/jpeg", "平板")
    assert features["degraded"] is True
    assert features["reason"] == "no_api_key"


def test_describe_falls_back_when_disabled(jpeg_bytes, monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    features = vision.describe(jpeg_bytes, "image/jpeg", "手表")
    assert features["degraded"] is True
    assert features["category"] == "手表"


def test_describe_falls_back_on_empty_response(jpeg_bytes):
    class Empty:
        def complete(self, *a, **k):
            return SimpleNamespace(content="")

    assert vision.describe(jpeg_bytes, "image/jpeg", "耳机", client=Empty())["reason"] == "empty_response"


def test_parse_json_tolerates_chatter():
    raw = '好的，结果如下：{"category":"手机","keywords":["手机"]} 希望有帮助'
    assert vision._parse_json(raw)["category"] == "手机"


def test_search_query_dedupes_fragments():
    query = vision.search_query({"keywords": ["黑色耳机", "黑色", "耳机", "降噪"], "summary": ""})
    assert query == "黑色耳机 降噪"


# ---------------- 接口 ----------------

def _post_image(client, headers, payload: str, **extra):
    body = {"image_base64": payload, "mime": "image/jpeg", **extra}
    return client.post("/api/search/image", json=body, headers=headers)


def test_image_search_requires_auth(client):
    body = {"image_base64": base64.b64encode(_jpeg()).decode(), "mime": "image/jpeg"}
    assert client.post("/api/search/image", json=body).status_code == 401


def test_image_search_returns_similar_products(client, auth_headers, monkeypatch):
    monkeypatch.setattr(vision, "describe", lambda *a, **k: vision._normalize(VisionOK().payload, ""))
    res = _post_image(client, auth_headers, base64.b64encode(_jpeg()).decode(), hint="500以内")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["features"]["category"] == "耳机"
    assert data["products"][0]["id"] == "p03"
    assert data["degraded"] is False
    assert data["elapsed_ms"] >= 0


def test_image_search_writes_session_focus(client, auth_headers, monkeypatch):
    monkeypatch.setattr(vision, "describe", lambda *a, **k: vision._normalize(VisionOK().payload, ""))
    _post_image(client, auth_headers, base64.b64encode(_jpeg()).decode(), session_id="img-1", hint="500以内")
    state = session_mod.get_state("img-1", "u1001")
    assert state.focus_product_id == "p03"
    assert state.last_category == "耳机"


def test_image_search_rejects_bad_image(client, auth_headers):
    res = _post_image(client, auth_headers, "a" * 64)
    assert res.status_code == 400
    assert res.json()["detail"]["code"] in {"IMAGE_INVALID", "IMAGE_TYPE_UNSUPPORTED", "IMAGE_TOO_SMALL"}


def test_image_search_rejects_short_payload(client, auth_headers):
    res = _post_image(client, auth_headers, "abc")
    assert res.status_code == 422


def test_image_search_rate_limited(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "image_search_per_minute", 2)
    monkeypatch.setattr(vision, "describe", lambda *a, **k: vision._normalize(VisionOK().payload, ""))
    payload = base64.b64encode(_jpeg()).decode()
    assert _post_image(client, auth_headers, payload).status_code == 200
    assert _post_image(client, auth_headers, payload).status_code == 200
    blocked = _post_image(client, auth_headers, payload)
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "TOO_MANY_IMAGES"


def test_degraded_search_still_returns_products(client, auth_headers, monkeypatch):
    """识图挂了也要能用文字找出来，而不是让整条链路 500。"""
    monkeypatch.setattr(
        vision,
        "describe",
        lambda raw, mime, hint="", client=None: vision._fallback(hint, "vision_failed"),
    )
    res = _post_image(client, auth_headers, base64.b64encode(_jpeg()).decode(), hint="降噪耳机")
    assert res.status_code == 200
    data = res.json()
    assert data["degraded"] is True
    assert data["reason"] == "vision_failed"
    assert data["products"], "降级后仍应返回候选商品"


@pytest.mark.live
@pytest.mark.skipif(not settings.deepseek_api_key, reason="需要 DEEPSEEK_API_KEY")
def test_live_vision_recognises_headphone(jpeg_bytes):
    features = vision.describe(jpeg_bytes, "image/jpeg", "头戴式降噪耳机")
    assert features["keywords"]
