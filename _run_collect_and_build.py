"""
Run collector locally, merge with static-data.json, build data.json, push to GitHub.
Usage: python _run_collect_and_build.py
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("merge")

HERE = Path(__file__).parent

async def main():
    # 1. Run collector
    logger.info("=" * 50)
    logger.info("[1/4] Running collector...")
    sys.path.insert(0, str(HERE / "scf-collector"))
    from collector import collect_all
    collected = await collect_all()
    logger.info(f"[1/4] Collected {len(collected)} items")

    # 2. Load static-data.json
    logger.info("[2/4] Loading static-data.json...")
    static = json.loads((HERE / "static-data.json").read_text("utf-8"))
    static_items = static.get("items", [])
    logger.info(f"[2/4] Static items: {len(static_items)}")

    # 3. Convert ArticleFeed objects to dicts
    collected_dicts = []
    for item in collected:
        d = {
            "type": item.type,
            "cat": item.cat,
            "title": item.title,
            "excerpt": item.excerpt,
            "source": item.source,
            "url": item.url,
            "time": str(item.time),
            "isNew": item.is_new,
            "isFeatured": item.is_featured,
            "isUrgent": item.is_urgent,
            "status": item.status,
        }
        collected_dicts.append(d)

    # 4. Merge: keep non-news/non-policy from static + all collected
    kept = [s for s in static_items if s.get("type") not in ("news", "policy")]
    merged = kept + collected_dicts

    # 5. Only dedup news/policy by URL (subsidy/corp/event URLs may be shared generic links)
    seen = set()
    deduped = []
    for item in merged:
        key = None
        if item.get("type") in ("news", "policy"):
            key = item.get("url", "") or item.get("title", "")[:50]
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(item)

    updated = str(collected_dicts[0].get("time", "")) if collected_dicts else "2026-06-03"
    output = {
        "updated": updated,
        "count": len(deduped),
        "items": deduped,
        "source": "merged",
    }

    # 4. Write data.json
    data_path = HERE / "data.json"
    data_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    # Stats
    type_counts = {}
    for item in deduped:
        t = item["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    logger.info(f"[3/4] data.json written: {len(deduped)} items")
    for t, c in sorted(type_counts.items()):
        logger.info(f"  {t}: {c}")

    # Today count
    today = "2026-06-03"
    today_items = [i for i in deduped if str(i.get("time", "")).startswith(today)]
    logger.info(f"[4/4] Today's items ({today}): {len(today_items)}")

if __name__ == "__main__":
    asyncio.run(main())
