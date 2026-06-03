"""
APScheduler 定时任务：每 2 小时触发一次全量采集。
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import database, url_hash_condition, cast_json, compute_url_hash, _is_sqlite
from collector import collect_all

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _collect_and_persist() -> None:
    """采集 → 写入数据库。"""
    try:
        items = await collect_all()
        new_count = 0
        skipped = 0

        for item in items:
            # URL 去重（Python 计算哈希，避免 SQL md5）
            url_h = compute_url_hash(item.url)
            existing = await database.fetch_one(
                f"SELECT id FROM articles WHERE {url_hash_condition()}",
                {"url_hash": url_h, "url": item.url},
            )
            if existing:
                skipped += 1
                continue

            await database.execute(
                f"""
                INSERT INTO articles
                    (type, cat, title, excerpt, source, url, url_hash, time, raw, is_new, is_featured, is_urgent, status)
                VALUES
                    (:type, :cat, :title, :excerpt, :source, :url, :url_hash, :time,
                     {cast_json()}, :is_new, :is_featured, :is_urgent, :status)
                """,
                {
                    "type": item.type,
                    "cat": item.cat,
                    "title": item.title,
                    "excerpt": item.excerpt,
                    "source": item.source,
                    "url": item.url,
                    "url_hash": url_h,
                    "time": item.time,
                    "raw": "{}",
                    "is_new": item.is_new,
                    "is_featured": item.is_featured,
                    "is_urgent": item.is_urgent,
                    "status": item.status,
                },
            )
            new_count += 1

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
        next_run_time=None,
    )
    scheduler.start()
    logger.info("Scheduler started (interval=2h).")


async def run_collect_once() -> None:
    """手动触发一次采集（用于 /api/collect 接口）。"""
    await _collect_and_persist()
