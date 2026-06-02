"""
APScheduler 定时任务：每 2 小时触发一次全量采集。
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import database
from models import ArticleFeed
from collector import collect_all

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _collect_and_persist() -> None:
    """采集 → 写入数据库。"""
    try:
        items = await collect_all()
        new_count = 0
        skipped = 0

        await database.connect()
        for item in items:
            # 检查是否已存在（URL 去重）
            existing = await database.fetch_one(
                "SELECT id FROM articles WHERE md5(url) = md5(:url)",
                {"url": item.url},
            )
            if existing:
                skipped += 1
                continue

            await database.execute(
                """
                INSERT INTO articles
                    (type, cat, title, excerpt, source, url, time, raw, is_new, is_featured, is_urgent, status)
                VALUES
                    (:type, :cat, :title, :excerpt, :source, :url, :time,
                     CAST(:raw AS jsonb), :is_new, :is_featured, :is_urgent, :status)
                """,
                {
                    "type": item.type,
                    "cat": item.cat,
                    "title": item.title,
                    "excerpt": item.excerpt,
                    "source": item.source,
                    "url": item.url,
                    "time": item.time,
                    "raw": "{}",
                    "is_new": item.is_new,
                    "is_featured": item.is_featured,
                    "is_urgent": item.is_urgent,
                    "status": item.status,
                },
            )
            new_count += 1

        await database.disconnect()
        logger.info("Collect job done: %d new, %d skipped", new_count, skipped)
    except Exception as exc:
        logger.exception("Collect job failed: %s", exc)


def start_scheduler() -> None:
    """启动 APScheduler（每 2 小时触发）。"""
    scheduler.add_job(
        _collect_and_persist,
        "interval",
        hours=2,
        id="collect_job",
        replace_existing=True,
        next_run_time=None,  # 启动后先等第一个间隔
    )
    scheduler.start()
    logger.info("Scheduler started (interval=2h).")


async def run_collect_once() -> None:
    """手动触发一次采集（用于 /api/collect 接口）。"""
    await _collect_and_persist()
