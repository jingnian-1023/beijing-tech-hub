"""
京科枢 · 云端后端服务
FastAPI + PostgreSQL + APScheduler
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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import database, init_db
from models import ArticlesResponse
from collector import collect_all
from scheduler import start_scheduler, _collect_and_persist

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ============================================================
# 生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    await init_db()
    # 首次启动立即采集一次
    try:
        await _collect_and_persist()
    except Exception as exc:
        logger.warning("Initial collection failed: %s", exc)
    start_scheduler()
    yield
    await database.disconnect()


app = FastAPI(title="京科枢 API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# API 路由
# ============================================================

@app.get("/api/news", response_model=ArticlesResponse)
async def get_news(
    type: Optional[str] = Query(None, description="policy | news | corp | subsidy | event"),
    cat: Optional[str] = Query(None, description="分类标签"),
    search: Optional[str] = Query(None, description="全文搜索关键词"),
    is_new: Optional[bool] = Query(None, description="仅今日新条目"),
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
        conditions.append(
            "search_text @@ plainto_tsquery('simple', :search)"
        )
        params["search"] = search

    where = " AND ".join(conditions)
    rows = await database.fetch_all(
        f"""
        SELECT id, type, cat, title, excerpt, source, url, time::text AS time,
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
        # 把 raw JSONB 展开到顶层（兼容前端 ALL_DATA 扁平结构）
        raw_data = d.pop("raw", {}) or {}
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)
        d.update(raw_data)
        items.append(d)

    return ArticlesResponse(
        count=count_row["cnt"] if count_row else 0,
        updated=datetime.now(timezone.utc),
        items=items,
    )


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
    try:
        await _collect_and_persist()
        return {"status": "ok", "message": "Collection completed"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================================
# 静态文件（前端 SPA）
# ============================================================

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".")
if os.path.isdir(STATIC_DIR):
    @app.get("/")
    async def serve_index():
        idx = os.path.join(STATIC_DIR, "index.html")
        return FileResponse(idx) if os.path.isfile(idx) else {"status": "API only"}


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
