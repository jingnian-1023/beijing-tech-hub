"""
PostgreSQL 数据库连接管理。
支持 DATABASE_URL 环境变量，默认使用 Supabase/Railway 提供的 PG。
"""

import os
import logging

from databases import Database

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:101900@localhost:5432/beijing_tech_hub",
)

database = Database(DATABASE_URL)


async def init_db() -> None:
    """初始化数据库表（幂等）。"""
    await database.connect()
    await database.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id            SERIAL PRIMARY KEY,
            type          VARCHAR(16)  NOT NULL,
            cat           VARCHAR(32)  DEFAULT '',
            title         TEXT         NOT NULL,
            excerpt       TEXT         DEFAULT '',
            source        VARCHAR(64)  DEFAULT '',
            url           TEXT         DEFAULT '',
            time          DATE         NOT NULL DEFAULT CURRENT_DATE,
            raw           JSONB        NOT NULL DEFAULT '{}',
            is_new        BOOLEAN      DEFAULT false,
            is_featured   BOOLEAN      DEFAULT false,
            is_urgent     BOOLEAN      DEFAULT false,
            status        VARCHAR(16)  DEFAULT '',
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            -- 全文搜索向量（中文用 pg_jieba 或 simple）
            search_text   TSVECTOR    GENERATED ALWAYS AS (
                to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(excerpt,'') || ' ' || coalesce(source,'') || ' ' || coalesce(cat,''))
            ) STORED
        );

        CREATE INDEX IF NOT EXISTS idx_articles_type      ON articles (type);
        CREATE INDEX IF NOT EXISTS idx_articles_time       ON articles (time DESC);
        CREATE INDEX IF NOT EXISTS idx_articles_cat        ON articles (cat);
        CREATE INDEX IF NOT EXISTS idx_articles_is_new     ON articles (is_new) WHERE is_new = true;
        CREATE INDEX IF NOT EXISTS idx_articles_is_featured ON articles (is_featured) WHERE is_featured = true;
        CREATE INDEX IF NOT EXISTS idx_articles_search     ON articles USING GIN (search_text);
        CREATE INDEX IF NOT EXISTS idx_articles_url_hash   ON articles (md5(url));
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
    await database.disconnect()
    logger.info("Database tables initialized.")
