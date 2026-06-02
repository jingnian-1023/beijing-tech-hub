"""
种子脚本：从 index.html 的 ALL_DATA 数组导入 PostgreSQL。
运行: python backend/seed_from_html.py
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import asyncio
from datetime import date
from database import database, init_db


async def seed():
    html_path = os.path.join(os.path.dirname(__file__), "..", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 const ALL_DATA = [...];
    m = re.search(r"const ALL_DATA\s*=\s*(\[.*?\]);", content, re.DOTALL)
    if not m:
        print("ERROR: Unable to find ALL_DATA in index.html")
        return

    raw_json = m.group(1)
    # JS object → Python dict（简单替换）
    raw_json = re.sub(r"//.*?\n", "\n", raw_json)  # 去单行注释
    raw_json = re.sub(r"/\*.*?\*/", "", raw_json, flags=re.DOTALL)  # 去多行注释
    raw_json = re.sub(r",\s*\]", "]", raw_json)  # trailing comma in arrays
    raw_json = re.sub(r",\s*\}", "}", raw_json)  # trailing comma in objects

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        print("Trying demjson3 or manual fix...")
        # fallback: use eval (controlled environment)
        import ast
        # Convert JS-like to Python-safe
        safe = re.sub(r"(\w+):", r"'\1':", raw_json)
        safe = safe.replace("'", '"')
        data = json.loads(safe)

    await database.connect()
    await init_db()

    # 清空现有数据
    await database.execute("DELETE FROM articles")

    inserted = 0
    for item in data:
        raw_fields = {}
        # 提取 non-standard 字段到 raw
        std_fields = {"id", "type", "cat", "isNew", "isFeatured", "isUrgent",
                      "title", "excerpt", "source", "time", "url", "status"}
        for k, v in item.items():
            if k not in std_fields:
                raw_fields[k] = v

        time_str = item.get("time", "2026-06-01")
        try:
            pub_date = date.fromisoformat(time_str)
        except ValueError:
            pub_date = date.today()

        await database.execute(
            """
            INSERT INTO articles
                (type, cat, title, excerpt, source, url, time, raw, is_new, is_featured, is_urgent, status)
            VALUES
                (:type, :cat, :title, :excerpt, :source, :url, :time::date,
                 CAST(:raw AS jsonb), :is_new, :is_featured, :is_urgent, :status)
            ON CONFLICT (md5(url)) DO NOTHING
            """,
            {
                "type": item.get("type", ""),
                "cat": item.get("cat", ""),
                "title": item.get("title", ""),
                "excerpt": item.get("excerpt", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "time": time_str,
                "raw": json.dumps(raw_fields, ensure_ascii=False),
                "is_new": item.get("isNew", False),
                "is_featured": item.get("isFeatured", False),
                "is_urgent": item.get("isUrgent", False),
                "status": item.get("status", ""),
            },
        )
        inserted += 1

    await database.disconnect()
    print(f"Seeded {inserted} articles from ALL_DATA")


if __name__ == "__main__":
    asyncio.run(seed())
