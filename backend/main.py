"""
京科枢 FastAPI 主应用 —— 同时服务前端 + API。
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from database import (
    database,
    init_db,
    cast_time,
    parse_raw,
    search_condition,
    _is_sqlite,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── 生命周期 ──

async def _init_and_collect():
    """延迟导入采集器，避免启动时循环依赖导致崩溃。"""
    from scheduler import _collect_and_persist, start_scheduler
    await database.connect()
    await init_db()
    try:
        await _collect_and_persist()
    except Exception as exc:
        logger.warning("Initial collection failed: %s", exc)
    start_scheduler()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _init_and_collect()
    yield
    await database.disconnect()


app = FastAPI(title="京科枢 API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API 路由 ──

@app.get("/api/news")
async def get_news(
    type: Optional[str] = Query(None, description="policy | news | corp | subsidy | event"),
    cat: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    is_new: Optional[bool] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """获取新闻/政策/补贴/会议数据。"""
    conditions = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if type:
        conditions.append("type = :type")
        params["type"] = type
    if cat:
        conditions.append("cat = :cat")
        params["cat"] = cat
    if is_new:
        conditions.append("is_new = true")
    if search:
        conditions.append(search_condition())
        params["search"] = f"%{search}%" if _is_sqlite() else search

    where = " AND ".join(conditions)
    tcol = cast_time("time")
    rows = await database.fetch_all(
        f"""
        SELECT id, type, cat, title, excerpt, source, url, {tcol} AS time,
               raw, is_new, is_featured, is_urgent, status, created_at, updated_at
        FROM articles
        WHERE {where}
        ORDER BY time DESC, id DESC
        LIMIT :limit OFFSET :offset
        """,
        params,
    )

    count_row = await database.fetch_one(
        f"SELECT count(*) as cnt FROM articles WHERE {where}",
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )

    items: list[dict] = []
    for row in rows:
        d = dict(row)
        raw_data = parse_raw(d)
        d.pop("raw", None)
        d.update(raw_data)
        # 布尔值归一化（SQLite 返回 0/1）
        for k in ("is_new", "is_featured", "is_urgent"):
            d[k] = bool(d.get(k))
        # 时间戳序列化
        for k in ("created_at", "updated_at"):
            if hasattr(d.get(k), "isoformat"):
                d[k] = d[k].isoformat()
        items.append(d)

    return {
        "count": count_row["cnt"] if count_row else 0,
        "updated": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


@app.get("/api/stats")
async def get_stats():
    """各类目文章数统计。"""
    rows = await database.fetch_all(
        "SELECT type, count(*) as cnt FROM articles GROUP BY type"
    )
    stats: dict[str, int] = {r["type"]: r["cnt"] for r in rows}
    stats["total"] = sum(stats.values())

    today = date.today()
    today_row = await database.fetch_one(
        "SELECT count(*) as cnt FROM articles WHERE time = :today",
        {"today": today},
    )
    stats["today"] = today_row["cnt"] if today_row else 0
    return stats


@app.post("/api/collect")
async def trigger_collect():
    """手动触发一次采集任务。"""
    from scheduler import run_collect_once

    try:
        await run_collect_once()
        return {"status": "ok", "message": "Collection completed"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── 静态文件（前端 SPA） ──

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".")
@app.get("/")
async def serve_index():
    idx = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(idx):
        return FileResponse(idx)
    return {"status": "API only", "static_dir": STATIC_DIR}


@app.get("/data.json")
async def serve_data():
    """采集器定时快照（SCF 云函数→GitHub→Railway 静态服务）。"""
    dj = os.path.join(STATIC_DIR, "data.json")
    if os.path.isfile(dj):
        return FileResponse(dj, media_type="application/json")
    return {"count": 0, "items": [], "source": "none", "note": "data.json not found"}


# ── 入口 ──

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
