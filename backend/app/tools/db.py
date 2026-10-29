"""SQLite 数据层：连接、建表、迁移、种子数据。

所有业务表（用户 / 订单 / 购物车 / 退款）都在这里定义，工具层只写业务逻辑。
连接按需创建、短事务、WAL 模式，避免长连接把库锁住。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from app.config import settings

# demo 账号统一密码：shop1234（bcrypt 成本 10，预生成避免启动时算哈希）
DEMO_PASSWORD = "shop1234"
DEMO_PASSWORD_HASH = "$2b$10$avEwf9/eps2fP6N0nB/kR.aJGc7kw79Xk2WetEehPGeDZ9BeXx0Au"

_STATUS_TEXT = {
    "paid": "已付款，等待发货",
    "shipped": "已发货，运输中",
    "delivering": "派送中",
    "signed": "已签收",
    "refunding": "退款处理中",
    "refunded": "已退款",
    "cancelled": "已取消",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL DEFAULT '',
    customer      TEXT NOT NULL,
    product_id    TEXT NOT NULL,
    product_name  TEXT NOT NULL,
    qty           INTEGER NOT NULL,
    amount        REAL NOT NULL,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    carrier       TEXT,
    tracking_no   TEXT,
    address       TEXT,
    eta           TEXT,
    refund_status TEXT
);

CREATE TABLE IF NOT EXISTS order_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT NOT NULL,
    ts          TEXT NOT NULL,
    description TEXT NOT NULL,
    location    TEXT,
    kind        TEXT NOT NULL DEFAULT 'logistics'
);
CREATE INDEX IF NOT EXISTS idx_events_order ON order_events(order_id);

CREATE TABLE IF NOT EXISTS carts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 99),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, product_id)
);
CREATE INDEX IF NOT EXISTS idx_carts_user ON carts(user_id);

CREATE TABLE IF NOT EXISTS refunds (
    refund_id  TEXT PRIMARY KEY,
    order_id   TEXT NOT NULL UNIQUE,
    user_id    TEXT NOT NULL,
    amount     REAL NOT NULL,
    reason     TEXT,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refunds_user ON refunds(user_id);
"""

# (user_id, display_name, order_ids)
_USERS = [
    ("u1001", "林一", ["1001", "1002"]),
    ("u1002", "周一鸣", ["1003"]),
    ("u1003", "苏晴", ["1004", "1005"]),
    ("u1004", "陈默", ["1006"]),
]

# (order_id, customer, product_id, product_name, qty, amount, status, created_at,
#  carrier, tracking_no, address, eta)
_ORDERS = [
    ("1001", "林一", "p03", "声浪 Air Pro", 1, 499.0, "shipped",
     "2026-10-16 10:22", "顺丰速运", "SF1234567890", "广东省深圳市南山区科技园 12 栋", "预计 10-20 送达"),
    ("1002", "林一", "p07", "极光 Game 16", 1, 7999.0, "paid",
     "2026-10-18 21:05", "待分配", None, "广东省深圳市南山区科技园 12 栋", "预计 10-21 发货"),
    ("1003", "周一鸣", "p02", "星火 Note 12", 2, 2598.0, "signed",
     "2026-10-09 14:40", "京东物流", "JD9988776655", "北京市海淀区中关村大街 5 号", None),
    ("1004", "苏晴", "p05", "声浪 Studio Max", 1, 899.0, "delivering",
     "2026-10-15 09:12", "中通快递", "ZT5566778899", "上海市浦东新区张江路 88 号", "今日 18:00 前送达"),
    ("1005", "苏晴", "p06", "极光 Book 14", 1, 4599.0, "signed",
     "2026-09-28 11:30", "顺丰速运", "SF6677889900", "上海市浦东新区张江路 88 号", None),
    ("1006", "陈默", "p09", "掌阅 Pad 11", 1, 1899.0, "cancelled",
     "2026-10-11 19:45", "未发货", None, "杭州市西湖区文三路 200 号", None),
]

_EVENTS = {
    "1001": [
        ("2026-10-16 10:25", "商家已接单，正在拣货", "深圳"),
        ("2026-10-16 18:02", "包裹已揽收", "深圳南山集散点"),
        ("2026-10-17 08:40", "运输中，已到达广州转运中心", "广州"),
        ("2026-10-18 23:10", "运输中，已到达深圳南山营业点", "深圳南山"),
    ],
    "1002": [("2026-10-18 21:06", "订单已付款，等待商家发货", "深圳")],
    "1003": [
        ("2026-10-09 15:10", "已揽收", "北京"),
        ("2026-10-10 07:30", "派送中", "北京海淀"),
        ("2026-10-10 12:15", "已签收，签收人：本人", "北京海淀"),
    ],
    "1004": [
        ("2026-10-15 10:00", "已揽收", "上海"),
        ("2026-10-18 06:50", "到达上海浦东网点", "上海浦东"),
        ("2026-10-19 08:20", "快递员正在派送，请注意查收", "上海浦东"),
    ],
    "1005": [
        ("2026-09-28 12:00", "已揽收", "上海"),
        ("2026-09-29 16:20", "已签收，签收人：前台", "上海浦东"),
    ],
    "1006": [("2026-10-12 09:00", "订单已取消，退款 3 个工作日内原路退回", "—")],
}

_ORDER_OWNER = {order_id: uid for uid, _, ids in _USERS for order_id in ids}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(conn: sqlite3.Connection) -> None:
    """老库平滑升级：orders 加 user_id/refund_status，order_events 加 kind。"""
    cols = _columns(conn, "orders")
    if "user_id" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
    if "refund_status" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN refund_status TEXT")
    if "kind" not in _columns(conn, "order_events"):
        conn.execute("ALTER TABLE order_events ADD COLUMN kind TEXT NOT NULL DEFAULT 'logistics'")

    # 回填归属：老库里 user_id 是空的，按种子映射补上
    for order_id, user_id in _ORDER_OWNER.items():
        conn.execute(
            "UPDATE orders SET user_id = ? WHERE order_id = ? AND (user_id IS NULL OR user_id = '')",
            (user_id, order_id),
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")


def init_db(force: bool = False) -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)

        if force:
            for table in ("refunds", "carts", "order_events", "orders", "users"):
                conn.execute(f"DELETE FROM {table}")

        has_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if not has_users:
            conn.executemany(
                "INSERT INTO users (user_id, display_name, password_hash, created_at) "
                "VALUES (?,?,?,?)",
                [(uid, name, DEMO_PASSWORD_HASH, now()) for uid, name, _ in _USERS],
            )

        has_orders = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
        if has_orders:
            conn.commit()
            return

        conn.executemany(
            "INSERT INTO orders (order_id, user_id, customer, product_id, product_name, qty, amount, "
            "status, created_at, carrier, tracking_no, address, eta) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(o[0], _ORDER_OWNER.get(o[0], ""), *o[1:]) for o in _ORDERS],
        )
        rows = [
            (order_id, ts, desc, loc, "logistics")
            for order_id, events in _EVENTS.items()
            for ts, desc, loc in events
        ]
        conn.executemany(
            "INSERT INTO order_events (order_id, ts, description, location, kind) VALUES (?,?,?,?,?)",
            rows,
        )
        conn.commit()


def status_text(status: str) -> str:
    return _STATUS_TEXT.get(status, status)


def public_row(row: sqlite3.Row | dict[str, Any], *, with_events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """订单行 → 前端/模型共用的结构。"""
    data = dict(row)
    data.pop("user_id", None)  # 绝不外泄归属人字段以外的内部键
    data["status_text"] = status_text(data.get("status", ""))
    data.pop("customer", None)
    if with_events is not None:
        data["events"] = with_events
    return data
