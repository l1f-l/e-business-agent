"""会话记忆：5 轮对话 + 商品焦点 + 槽位继承，内存/Redis 可切换。

只存"对下一轮有用"的东西：
- turns：最近 5 轮原文，给模型做语气和上下文参考；
- focus_product_id：指代消解的锚点（"那它多少钱"里的"它"）；
- last_category / last_budget_max：追问"还有别的吗"时继承约束。

比把整段历史塞给模型更省 token，也更容易测试。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

from app.config import settings
from app.core.slots import extract_slots
from app.rag.products import PRODUCT_MAP

logger = logging.getLogger(__name__)

PRONOUNS = ("它", "他", "这个", "那个", "这款", "那款", "这台", "那台", "第一个", "上面那个", "刚才那个")
FOLLOWUP_HINTS = ("还有别的", "还有吗", "还有其它", "还有其他", "换一个", "换个", "再便宜", "贵一点", "便宜点")

# 搭配推荐的确认/拒绝话术。"要"这类单字太宽泛，只在 pending 存在且句子很短时才算确认
CONFIRM_WORDS = (
    "好的", "好啊", "好呀", "好", "可以", "行", "嗯", "要", "加上", "都加", "加吧",
    "带上", "顺便", "一起", "都要", "来吧", "麻烦", "那就",
)
REJECT_WORDS = ("不用", "不要", "算了", "先不", "暂时不", "不需要", "不必", "别加")


def is_confirm(text: str) -> bool:
    """用户是不是在答应上一轮的搭配推荐。"""
    clean = (text or "").strip().strip("。，！？!?~ 　")
    if not clean or len(clean) > 14:
        return False
    if any(w in clean for w in REJECT_WORDS):
        return False
    return any(w == clean or w in clean for w in CONFIRM_WORDS)


def is_reject(text: str) -> bool:
    clean = (text or "").strip()
    return any(w in clean for w in REJECT_WORDS)


@dataclass
class SessionState:
    session_id: str
    user_id: str | None = None
    turns: deque[dict[str, str]] = field(
        default_factory=lambda: deque(maxlen=settings.session_max_turns * 2)
    )
    focus_product_id: str | None = None
    last_product_ids: list[str] = field(default_factory=list)
    last_category: str | None = None
    last_budget_max: float | None = None
    # 上一轮的搭配推荐：用户回"好的"时直接消费，不用再问一遍
    pending_suggestion: dict[str, Any] | None = None
    updated_at: float = field(default_factory=time.time)

    # ---------- 序列化（Redis 用） ----------
    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "turns": list(self.turns),
            "focus_product_id": self.focus_product_id,
            "last_product_ids": self.last_product_ids,
            "last_category": self.last_category,
            "last_budget_max": self.last_budget_max,
            "pending_suggestion": self.pending_suggestion,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        state = cls(session_id=data.get("session_id", ""), user_id=data.get("user_id"))
        state.turns = deque(data.get("turns", []), maxlen=settings.session_max_turns * 2)
        state.focus_product_id = data.get("focus_product_id")
        state.last_product_ids = data.get("last_product_ids", [])
        state.last_category = data.get("last_category")
        state.last_budget_max = data.get("last_budget_max")
        state.pending_suggestion = data.get("pending_suggestion")
        state.updated_at = float(data.get("updated_at") or time.time())
        return state

    # ---------- 写入 ----------
    def add_turn(self, role: str, content: str) -> None:
        text = (content or "").strip()
        if not text:
            return
        self.turns.append({"role": role, "content": text})
        self.updated_at = time.time()

    def note_results(self, product_ids: list[str], slots: dict[str, Any] | None = None) -> None:
        """记录本轮命中的商品与约束，供下一轮指代/继承。"""
        if product_ids:
            self.last_product_ids = product_ids[:4]
            self.focus_product_id = product_ids[0]
        slots = slots or {}
        if slots.get("category"):
            self.last_category = slots["category"]
        if slots.get("budget_max") is not None:
            self.last_budget_max = float(slots["budget_max"])
        self.updated_at = time.time()

    def messages(self, limit: int | None = None) -> list[dict[str, str]]:
        turns = list(self.turns)
        if limit:
            turns = turns[-limit:]
        return [{"role": t["role"], "content": t["content"]} for t in turns]

    def focus_name(self) -> str | None:
        product = PRODUCT_MAP.get(self.focus_product_id or "")
        return product["name"] if product else None


class SessionStore(Protocol):
    def load(self, session_id: str, user_id: str | None = None) -> SessionState: ...
    def save(self, state: SessionState) -> None: ...
    def clear(self, session_id: str) -> None: ...


class InMemorySessionStore:
    """带 TTL 与容量上限的进程内存储；单 worker 够用，多 worker 要换 Redis。"""

    def __init__(self) -> None:
        self._data: OrderedDict[str, SessionState] = OrderedDict()
        self._lock = threading.Lock()

    def load(self, session_id: str, user_id: str | None = None) -> SessionState:
        with self._lock:
            state = self._data.get(session_id)
            if state is not None and time.time() - state.updated_at > settings.session_ttl_seconds:
                self._data.pop(session_id, None)
                state = None
            if state is None:
                state = SessionState(session_id=session_id, user_id=user_id)
            self._data[session_id] = state
            self._data.move_to_end(session_id)
            while len(self._data) > settings.session_max_sessions:
                self._data.popitem(last=False)
            return state

    def save(self, state: SessionState) -> None:
        with self._lock:
            self._data[state.session_id] = state
            self._data.move_to_end(state.session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._data.pop(session_id, None)

    def count(self) -> int:
        with self._lock:
            return len(self._data)


class RedisSessionStore:
    """Redis 版：一个 session 一个 JSON，带同样 TTL；多实例部署时用这个。"""

    def __init__(self, url: str | None = None) -> None:
        import redis

        self._redis = redis.Redis.from_url(url or settings.redis_url, decode_responses=True)
        self._redis.ping()  # 起不来就抛，交给 get_store 降级

    def _key(self, session_id: str) -> str:
        return f"{settings.redis_prefix}{session_id}"

    def load(self, session_id: str, user_id: str | None = None) -> SessionState:
        raw = self._redis.get(self._key(session_id))
        if raw:
            return SessionState.from_dict(json.loads(raw))
        return SessionState(session_id=session_id, user_id=user_id)

    def save(self, state: SessionState) -> None:
        self._redis.setex(self._key(state.session_id), settings.session_ttl_seconds, json.dumps(state.to_dict(), ensure_ascii=False))

    def clear(self, session_id: str) -> None:
        self._redis.delete(self._key(session_id))


@lru_cache(maxsize=1)
def get_store() -> SessionStore:
    backend = (settings.session_backend or "memory").lower()
    if backend == "redis":
        try:
            store = RedisSessionStore()
            logger.info("会话存储：Redis（%s）", settings.redis_url)
            return store
        except Exception as exc:  # noqa: BLE001 - Redis 挂了不能影响对话
            logger.warning("Redis 不可用（%s），降级为内存会话", exc)
    return InMemorySessionStore()


def reset_store() -> None:
    """测试用：切环境变量或清干净数据后重建。"""
    get_store.cache_clear()


def get_state(session_id: str, user_id: str | None = None) -> SessionState:
    """同一 session_id 换了用户时，直接丢弃旧上下文——绝不跨账号串记忆。"""
    sids = session_id or "default"
    state = get_store().load(sids, user_id)
    if user_id and state.user_id and state.user_id != user_id:
        state = SessionState(session_id=sids, user_id=user_id)
    if user_id:
        state.user_id = user_id
    return state


def save_state(state: SessionState) -> None:
    get_store().save(state)


def clear_session(session_id: str) -> None:
    get_store().clear(session_id)


# ---------------- 指代消解 ----------------
def resolve(message: str, state: SessionState) -> dict[str, Any]:
    """把"那它多少钱"改写成"声浪 Air Pro 多少钱"，并给出继承后的槽位。

    不改写原文（用户看到的气泡必须是原话），只影响检索 query。
    """
    text = (message or "").strip()
    slots = extract_slots(text)
    lowered = text.lower()

    # "这耳机""这款"也算指代；单独一个"这"太宽泛，用"这 + 已识别品类"来判定
    has_pronoun = any(p in text for p in PRONOUNS) or (
        text.startswith("这") and bool(slots.get("category"))
    )
    wants_alternative = any(h in lowered for h in ("还有别的", "还有吗", "换一个", "换个", "其它", "其他"))
    is_followup = has_pronoun or wants_alternative or any(h in lowered for h in FOLLOWUP_HINTS)
    focus_id = state.focus_product_id if is_followup else None
    focus_name = state.focus_name() if focus_id else None

    query = text
    if focus_name and has_pronoun:
        query = f"{focus_name} {text}"

    category = slots.get("category")
    budget_max = slots.get("budget_max")
    if is_followup:
        category = category or state.last_category
        if budget_max is None:
            budget_max = state.last_budget_max

    merged = dict(slots)
    merged["category"] = category
    merged["budget_max"] = budget_max

    pending = state.pending_suggestion
    confirm = bool(pending) and is_confirm(text)
    reject = bool(pending) and is_reject(text)

    return {
        "query": query,
        "is_followup": is_followup,
        "wants_alternative": wants_alternative,
        "focus_product_id": focus_id,
        "focus_name": focus_name,
        "slots": merged,
        "original_slots": slots,
        "pending": pending,
        "is_confirm": confirm,
        "is_reject": reject,
    }
