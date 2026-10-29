"""下载 BAAI/bge-small-zh-v1.5 的 ONNX 版本（约 95MB）。

用法：
    python scripts/fetch_model.py                # 默认走 hf-mirror
    python scripts/fetch_model.py --source hf    # 直连 HuggingFace

下载后 app/rag/embedding.py 会自动优先使用本地 ONNX，不再依赖外网。
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

REPO = "Xenova/bge-small-zh-v1.5"  # transformers.js 的 ONNX 转换版本
SOURCES = {
    "mirror": "https://hf-mirror.com",
    "hf": "https://huggingface.co",
}
FILES = ["config.json", "tokenizer.json", "tokenizer_config.json", "onnx/model.onnx"]

TARGET = Path(__file__).resolve().parent.parent / "data" / "models" / "bge-small-zh-v1.5"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    def hook(blocks: int, block_size: int, total: int) -> None:
        if total <= 0:
            return
        done = min(blocks * block_size, total)
        pct = done / total * 100
        sys.stdout.write(f"\r  {dest.name} {pct:5.1f}% ({done / 1e6:.1f}/{total / 1e6:.1f} MB)")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, tmp, reporthook=hook)
    print()
    tmp.replace(dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=SOURCES, default="mirror")
    args = parser.parse_args()

    base = f"{SOURCES[args.source]}/{REPO}/resolve/main"
    print(f"下载源：{base}\n目标目录：{TARGET}\n")

    for name in FILES:
        dest = TARGET / name
        if dest.exists() and dest.stat().st_size > 1024:
            print(f"  {name} 已存在，跳过")
            continue
        url = f"{base}/{name}"
        print(f"下载 {url}")
        try:
            download(url, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  失败：{exc}")
            print("  换个源试试：python scripts/fetch_model.py --source hf")
            return 1

    print("\n完成。启动服务时会自动使用本地 ONNX 模型。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
