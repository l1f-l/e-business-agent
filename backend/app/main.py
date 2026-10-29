from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.auth import AuthContextMiddleware
from app.routers.auth import router as auth_router
from app.routers.cart import router as cart_router
from app.routers.catalog import router as catalog_router
from app.routers.chat import router as chat_router
from app.routers.orders import router as orders_router
from app.routers.search import router as search_router
from app.routers.session import router as session_router
from app.tools.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("shoppilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("业务库就绪：%s", settings.db_path)
    if settings.is_dev_secret:
        logger.warning("JWT_SECRET 仍是开发默认值，上线前必须在 .env 里替换")
    try:
        from app.rag.review_store import get_collection as get_reviews
        from app.rag.store import get_collection

        col = get_collection()  # 首次启动会建库 / 加载嵌入模型
        reviews = get_reviews()
        logger.info("知识库就绪：商品 %d 条 / 评论 %d 条", col.count(), reviews.count())
    except Exception as exc:  # noqa: BLE001
        logger.warning("知识库预热失败（请求时会重试）：%s", exc)
    yield


app = FastAPI(title="ShopPilot · 电商 AI 导购与客服 Agent", version="2.0.0", lifespan=lifespan)

app.add_middleware(AuthContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": {"code": "INTERNAL_ERROR", "message": str(exc)}})


for router in (
    auth_router,
    cart_router,
    catalog_router,
    chat_router,
    orders_router,
    search_router,
    session_router,
):
    app.include_router(router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"service": "shoppilot-agent", "version": "2.0.0", "docs": "/docs", "stream": "/api/chat/stream"}


# 单端口部署：前端静态产物存在时，把它挂在最后兜底。
# /api/*、/docs 先注册，因此不会被静态路由抢走；只有没命中的路径才落到静态文件。
_web = settings.web_dist
if _web.is_dir() and (_web / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(_web), html=True), name="web")
    logger.info("已托管前端静态资源：%s", _web)
else:

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "shoppilot-agent", "version": "2.0.0", "docs": "/docs", "stream": "/api/chat/stream"}
