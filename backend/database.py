"""
数据库连接管理 + 跨引擎查询助手。
默认使用 SQLite（零依赖），支持 DATABASE_URL 切换 PostgreSQL。
"""

import hashlib
import os
import json
import logging

from databases import Database

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./data.db",
)

database = Database(DATABASE_URL)


def _is_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")


# ─── 跨引擎查询辅助 ───

def cast_time(col: str = "time") -> str:
    """日期列转为字符串。SQLite: time, PG: time::text"""
    return col if _is_sqlite() else f"{col}::text"


def cast_json(raw_var: str = ":raw") -> str:
    """JSON 转换。SQLite: :raw, PG: CAST(:raw AS jsonb)"""
    return raw_var if _is_sqlite() else f"CAST({raw_var} AS jsonb)"


def parse_raw(row: dict) -> dict:
    """从数据库行中提取 raw 字段（兼容 JSONB/TEXT）。"""
    raw = row.get("raw", {}) or {}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return raw


def compute_url_hash(url: str) -> str:
    """Python 计算 URL 的 MD5 哈希（替代 SQL 内置 md5）。"""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def url_hash_condition() -> str:
    """URL 去重条件（通过预计算的 Python 哈希值比较）。
    SQLite: url_hash = :url_hash
    PG:     md5(url) = md5(:url)
    """
    if _is_sqlite():
        return "url_hash = :url_hash"
    return "md5(url) = md5(:url)"


def search_condition() -> str:
    """全文搜索条件。SQLite 用 LIKE，PG 用 tsvector。"""
    if _is_sqlite():
        return "(title LIKE :search OR excerpt LIKE :search OR source LIKE :search)"
    return "search_text @@ plainto_tsquery('simple', :search)"


# ─── 建表 ───

async def init_db() -> None:
    """初始化数据库表（幂等）。
    调用方负责 connect/disconnect，本函数不管理连接生命周期。"""
    if _is_sqlite():
        await database.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                type          VARCHAR(16)  NOT NULL,
                cat           VARCHAR(32)  DEFAULT '',
                title         TEXT         NOT NULL,
                excerpt       TEXT         DEFAULT '',
                source        VARCHAR(64)  DEFAULT '',
                url           TEXT         DEFAULT '',
                url_hash      TEXT         UNIQUE,
                time          DATE         NOT NULL DEFAULT (date('now')),
                raw           TEXT         NOT NULL DEFAULT '{}',
                is_new        BOOLEAN      DEFAULT 0,
                is_featured   BOOLEAN      DEFAULT 0,
                is_urgent     BOOLEAN      DEFAULT 0,
                status        VARCHAR(16)  DEFAULT '',
                created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        for idx_col in ("type", "time", "cat", "is_new", "url_hash"):
            await database.execute(
                f"CREATE INDEX IF NOT EXISTS idx_articles_{idx_col} ON articles ({idx_col});"
            )
    else:
        await database.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id            SERIAL PRIMARY KEY,
                type          VARCHAR(16)  NOT NULL,
                cat           VARCHAR(32)  DEFAULT '',
                title         TEXT         NOT NULL,
                excerpt       TEXT         DEFAULT '',
                source        VARCHAR(64)  DEFAULT '',
                url           TEXT         DEFAULT '',
                url_hash      TEXT         DEFAULT '',
                time          DATE         NOT NULL DEFAULT CURRENT_DATE,
                raw           JSONB        NOT NULL DEFAULT '{}',
                is_new        BOOLEAN      DEFAULT false,
                is_featured   BOOLEAN      DEFAULT false,
                is_urgent     BOOLEAN      DEFAULT false,
                status        VARCHAR(16)  DEFAULT '',
                created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
                updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
                search_text   TSVECTOR    GENERATED ALWAYS AS (
                    to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(excerpt,'') || ' ' || coalesce(source,'') || ' ' || coalesce(cat,''))
                ) STORED
            );
        """)
        await database.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_type       ON articles (type);
        """)
        await database.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_time       ON articles (time DESC);
        """)
        await database.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_cat         ON articles (cat);
        """)
        await database.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_is_new      ON articles (is_new) WHERE is_new = true;
        """)
        await database.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_search      ON articles USING GIN (search_text);
        """)
        await database.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_url_hash    ON articles (md5(url));
        """)
        await database.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'articles_url_hash_key'
                ) THEN
                    ALTER TABLE articles ADD CONSTRAINT articles_url_hash_key UNIQUE (md5(url));
                END IF;
            END
            $$;
        """)

    logger.info("Database tables initialized (%s).", "sqlite" if _is_sqlite() else "pg")
