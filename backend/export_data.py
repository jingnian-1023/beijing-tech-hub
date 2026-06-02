"""
Standalone data exporter: runs collector, outputs data.json to parent directory.
Usage: python export_data.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("export")

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from collector import collect_all


async def main():
    logger.info("Starting data collection...")
    items = await collect_all()
    logger.info("Collected %d items", len(items))

    output = []
    for item in items:
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
        output.append(d)

    out_path = Path(__file__).parent.parent / "data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"updated": str(items[0].time) if items else "", "count": len(output), "items": output}, f, ensure_ascii=False, indent=2)

    logger.info("Exported %d items to %s", len(output), out_path)
    print(f"OK: {len(output)} items written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
