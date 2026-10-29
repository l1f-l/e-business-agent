import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # Embedding: "bge" (BAAI/bge-small-zh-v1.5) or "hash" (offline fallback)
    embedding_provider: str = "bge"
    bge_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    embedding_init_timeout: float = 150.0  # fastembed 下载/加载上限，超时自动降级 hash
    hf_endpoint: str = ""  # e.g. https://hf-mirror.com for faster download in CN

    # Retrieval
    top_k: int = 4
    rag_min_score: float = 0.18
    review_top_k: int = 6
    review_min_score: float = 0.05
    max_tool_rounds: int = 3

    # 拍图搜同款（DeepSeek 视觉模型，图片只能放 user message）
    vision_model: str = "deepseek-v4-flash-vision-exp"
    vision_enabled: bool = True
    vision_timeout: float = 25.0
    image_max_bytes: int = 8 * 1024 * 1024
    image_min_bytes: int = 1024
    image_search_per_minute: int = 10

    # 主动搭配推荐
    cross_sell_enabled: bool = True

    # Auth
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    password_min_length: int = 6
    login_max_attempts: int = 5
    login_window_seconds: int = 300

    # Session memory
    session_backend: str = "memory"  # memory | redis
    session_ttl_seconds: int = 1800
    session_max_turns: int = 5
    session_max_sessions: int = 1000
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_prefix: str = "sp:sess:"

    # Server
    cors_origins: str = "http://localhost:3000"
    data_dir: Path = DATA_DIR
    db_file: str = ""  # 留空用 shop.db；测试用 test_shop.db 隔离
    web_dist: Path = BASE_DIR / "web"  # 单端口部署时前端静态产物（next export 的 out/）

    @property
    def chroma_dir(self) -> Path:
        # CHROMA_DIR 让测试用独立目录：dev 服务常驻时会锁住 data/chroma，跑测试必然打架
        override = os.getenv("CHROMA_DIR")
        return Path(override) if override else self.data_dir / "chroma"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def db_path(self) -> Path:
        return self.data_dir / (self.db_file or "shop.db")

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_dev_secret(self) -> bool:
        return self.jwt_secret == DEV_JWT_SECRET


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
