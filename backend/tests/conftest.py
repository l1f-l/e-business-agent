from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 默认用真实 bge 中文模型验证召回质量；
# 无网络环境可 `TEST_EMBEDDING_PROVIDER=hash pytest`，退化为离线嵌入仍能全绿。
os.environ.setdefault("EMBEDDING_PROVIDER", os.getenv("TEST_EMBEDDING_PROVIDER", "bge"))
# 测试库与开发库隔离，跑 pytest 不会清掉正在演示的购物车/退款
os.environ.setdefault("DB_FILE", "test_shop.db")
os.environ.setdefault("SESSION_BACKEND", "memory")
# 向量库也要隔离：本地 uvicorn 常驻会占着 data/chroma，两个进程同时打开必炸
os.environ.setdefault("CHROMA_DIR", str(BACKEND_DIR / "data" / "chroma_test"))

import pytest  # noqa: E402

from app.core import auth, session  # noqa: E402
from app.tools.db import init_db  # noqa: E402

DEMO_PASSWORD = "shop1234"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: 需要真实 DeepSeek API 的用例（-m live 单独跑）")


@pytest.fixture(scope="session", autouse=True)
def _bootstrap():
    init_db(force=True)
    from app.rag.review_store import get_collection as get_reviews
    from app.rag.store import get_collection

    get_collection()
    get_reviews()
    yield


@pytest.fixture(autouse=True)
def _clean_state():
    init_db(force=True)
    auth.reset_login_failures()
    session.reset_store()
    yield
    session.reset_store()


@pytest.fixture()
def demo_token() -> str:
    from app.core.auth import create_token

    return create_token("u1001")[0]


@pytest.fixture()
def auth_headers(demo_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {demo_token}"}


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
