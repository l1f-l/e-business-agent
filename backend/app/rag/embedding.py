"""中文嵌入：BAAI/bge-small-zh-v1.5。

三种加载方式，按可用性依次降级：
1. 本地 ONNX（scripts/fetch_model.py 下载后，最快、无外网依赖）
2. fastembed（会自动从 GCS 拉模型，部分网络环境不可达）
3. 离线哈希嵌入（零依赖兜底，保证程序在任何机器上都能启动）

降级不是"凑合"：前两种走真实语义向量，第三种只保证功能可用。
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from app.config import settings

logger = logging.getLogger(__name__)

# bge 官方建议：短查询加指令前缀，文档不加。只加在 query 侧。
BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
MODEL_DIR = settings.models_dir / "bge-small-zh-v1.5"

_TOKEN_RE = re.compile(r"[a-zA-Z]+|\d+(?:\.\d+)?|[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    """中文字 + 英文词 + 数字，再补一层中文 bigram。"""
    text = text.lower()
    base = _TOKEN_RE.findall(text)
    grams: list[str] = []
    cjk_run: list[str] = []
    for tok in base:
        if len(tok) == 1 and "\u4e00" <= tok <= "\u9fff":
            cjk_run.append(tok)
        else:
            if len(cjk_run) > 1:
                grams.extend(cjk_run[i] + cjk_run[i + 1] for i in range(len(cjk_run) - 1))
            cjk_run = []
            grams.append(tok)
    if len(cjk_run) > 1:
        grams.extend(cjk_run[i] + cjk_run[i + 1] for i in range(len(cjk_run) - 1))
    grams.extend(base)
    return grams


class HashEmbedding:
    """字符 n-gram 特征哈希 + L2 归一化，完全离线、结果可复现。"""

    name = "hash"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokens(text):
            weight = 1.6 if len(tok) >= 2 else 1.0
            if tok.isdigit():
                weight *= 1.2
            digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def encode(self, texts: Sequence[str], is_query: bool = False) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class BgeOnnxEmbedding:
    """本地 ONNX 推理：tokenizers 分词 + CLS pooling + L2 归一化。"""

    name = "bge"

    def __init__(self, model_dir: Path | None = None, max_length: int = 256) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        root = model_dir or MODEL_DIR
        onnx_path = root / "onnx" / "model.onnx"
        if not onnx_path.exists():
            raise FileNotFoundError(f"缺少 ONNX 模型：{onnx_path}")

        self._np = np
        self.dim = settings.embedding_dim
        self._tok = Tokenizer.from_file(str(root / "tokenizer.json"))
        self._tok.enable_truncation(max_length=max_length)
        self._tok.enable_padding(pad_id=0, pad_token="[PAD]")

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.log_severity_level = 3
        self._sess = ort.InferenceSession(
            str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._input_names = {i.name for i in self._sess.get_inputs()}
        logger.info("bge ONNX 就绪：%s", onnx_path)

    def encode(self, texts: Sequence[str], is_query: bool = False) -> list[list[float]]:
        np = self._np
        payload = [BGE_QUERY_PREFIX + t for t in texts] if is_query else list(texts)
        encodings = self._tok.encode_batch(payload)

        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feeds = {"input_ids": input_ids, "attention_mask": attention}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        hidden = self._sess.run(None, feeds)[0]  # (batch, seq, hidden)
        cls = hidden[:, 0, :]
        norm = np.linalg.norm(cls, axis=1, keepdims=True)
        return (cls / np.maximum(norm, 1e-9)).tolist()


class BgeEmbedding:
    """fastembed 版本（自动下载模型，部分网络环境会失败）。"""

    name = "bge"

    def __init__(self) -> None:
        if settings.hf_endpoint:
            os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)

        from fastembed import TextEmbedding

        self.dim = settings.embedding_dim
        self._model = TextEmbedding(
            model_name=settings.bge_model,
            cache_dir=str(settings.models_dir),
            threads=4,
        )
        logger.info("bge fastembed 就绪：%s", settings.bge_model)

    def encode(self, texts: Sequence[str], is_query: bool = False) -> list[list[float]]:
        payload = [BGE_QUERY_PREFIX + t for t in texts] if is_query else list(texts)
        out: list[list[float]] = []
        for vec in self._model.embed(payload, batch_size=8):
            arr = vec.tolist()
            norm = math.sqrt(sum(v * v for v in arr)) or 1.0
            out.append([v / norm for v in arr])
        return out


class Embedder:
    def __init__(self, primary: object, fallback_hash: HashEmbedding) -> None:
        self._primary = primary
        self._hash = fallback_hash
        self.name = getattr(primary, "name", "unknown")
        self.dim = settings.embedding_dim

    def encode(self, texts: Sequence[str], is_query: bool = False) -> list[list[float]]:
        try:
            return self._primary.encode(texts, is_query=is_query)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - 运行期失败也要降级而不是 500
            logger.warning("embedding 推理失败，降级为 hash：%s", exc)
            self._primary = self._hash
            self.name = self._hash.name
            return self._hash.encode(texts, is_query=is_query)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    fallback = HashEmbedding(settings.embedding_dim)
    if settings.embedding_provider.lower() != "bge":
        return Embedder(fallback, fallback)

    # 本地有 ONNX 就只认本地；否则才去联网（避免每次启动卡在下载重试上）
    if (MODEL_DIR / "onnx" / "model.onnx").exists():
        candidates: tuple = (BgeOnnxEmbedding,)
    else:
        candidates = (BgeEmbedding,)

    for factory in candidates:
        try:
            embedder = factory()
            logger.info("使用嵌入后端：%s", type(embedder).__name__)
            return Embedder(embedder, fallback)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s 不可用：%s", factory.__name__, exc)

    logger.warning(
        "bge 不可用，使用离线 hash 嵌入（召回质量会下降）。"
        "可执行 python scripts/fetch_model.py 下载本地模型。"
    )
    return Embedder(fallback, fallback)
