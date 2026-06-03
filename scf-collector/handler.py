"""
腾讯云 SCF 云函数入口
定时触发：采集数据 + 推 data.json 到 GitHub
"""

import asyncio
import base64
import json
import logging
import os

import httpx

logger = logging.getLogger("scf-collector")
logger.setLevel(logging.INFO)


def main_handler(event, context):
    """SCF 入口。event 来自定时触发器。"""
    logger.info("SCF triggered: event=%s", json.dumps(event, ensure_ascii=False)[:200])
    result = asyncio.run(_run())
    logger.info("SCF result: %s", json.dumps(result, ensure_ascii=False))
    return result


async def _run() -> dict:
    """主流程：采集 → 格式化 → 推 GitHub。"""
    # ── 1. 运行采集器 ──
    from collector import collect_all

    logger.info("[1/3] Starting collection...")
    try:
        items = await collect_all()
    except Exception as e:
        logger.error("Collection failed: %s", e)
        return {"status": "error", "message": f"Collection failed: {e}"}

    if not items:
        logger.warning("[1/3] No items collected, skipping push")
        return {"status": "ok", "message": "No items collected, nothing to push"}

    logger.info("[1/3] Collected %d items", len(items))

    # ── 2. 格式化为 data.json ──
    output = []
    for item in items:
        output.append(
            {
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
        )

    data = {
        "updated": str(items[0].time) if items else "",
        "count": len(output),
        "items": output,
        "source": "tencent-scf",
    }
    json_str = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    logger.info("[2/3] Formatted %d items to JSON (%.1f KB)", len(output), len(json_str) / 1024)

    # ── 3. 拉取 static-data.json 并合并 ──
    repo = os.environ.get(
        "GITHUB_REPO", "jingnian-1023/beijing-tech-hub"
    )
    token = os.environ.get("GITHUB_TOKEN", "")

    if not token:
        logger.error("GITHUB_TOKEN environment variable not set")
        return {"status": "error", "message": "GITHUB_TOKEN not set"}

    merged = await _merge_with_static(output, token, repo)
    if merged:
        logger.info("[3/4] Merged with static-data.json: %d total items", len(merged))
        output = merged
    else:
        logger.warning("[3/4] static-data.json fetch failed, using collected data only")

    json_str = json.dumps({
        "updated": str(items[0].time if items else ""),
        "count": len(output),
        "items": output,
        "source": "merged",
    }, ensure_ascii=False, indent=2) + "\n"
    logger.info("[3/4] Final JSON: %d items (%.1f KB)", len(output), len(json_str) / 1024)

    # ── 4. 推送到 GitHub ──
    push_ok = await _push_data_json(json_str, token, repo)
    if push_ok:
        logger.info("[4/4] Successfully pushed data.json to GitHub")
        return {
            "status": "ok",
            "count": len(output),
            "updated": output[0]["time"] if output else "",
            "pushed": True,
        }
    else:
        return {
            "status": "partial",
            "count": len(output),
            "updated": output[0]["time"] if output else "",
            "pushed": False,
            "message": "Collection OK but GitHub push failed",
        }


async def _merge_with_static(collected: list, token: str, repo: str) -> list | None:
    """拉取 static-data.json，合并采集的 news/policy 进去后返回完整列表。"""
    url = f"https://api.github.com/repos/{repo}/contents/static-data.json"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("static-data.json fetch: HTTP %d", resp.status_code)
                return None
            body = resp.json()
            import base64
            raw = base64.b64decode(body["content"]).decode("utf-8")
            static = json.loads(raw)
        except Exception as e:
            logger.warning("static-data.json parse failed: %s", e)
            return None

    static_items = static.get("items", [])
    # 保留 static 中不是 news/policy 的条目（corp/subsidy/event）
    kept = [s for s in static_items if s.get("type") not in ("news", "policy")]

    # collected 中的 news/policy 替换 static 中的
    merged = kept + collected

    # 去重
    seen = set()
    deduped = []
    for item in merged:
        key = item.get("url", "") or item.get("title", "")[:50]
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    logger.info("Merge: kept=%d static + %d collected = %d deduped",
                len(kept), len(collected), len(deduped))
    return deduped


async def _push_data_json(content: str, token: str, repo: str) -> bool:
    """通过 GitHub Contents API 更新 data.json。"""
    path = "data.json"  # 仓库根目录
    url = f"https://api.github.com/repos/{repo}/contents/{path}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # 先获取现有文件 SHA（更新需要）
        sha = None
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                sha = resp.json().get("sha")
                logger.info("Existing data.json found, SHA=%s", sha[:7] if sha else "?")
            elif resp.status_code == 404:
                logger.info("data.json does not exist yet, will create")
            else:
                logger.warning("Unexpected status checking file: %d", resp.status_code)
        except Exception as e:
            logger.warning("Failed to check existing file: %s", e)

        # 推新内容
        body = {
            "message": "scf: auto-update data.json",
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if sha:
            body["sha"] = sha

        try:
            resp = await client.put(url, headers=headers, json=body)
            if resp.status_code in (200, 201):
                logger.info("GitHub push OK: %d", resp.status_code)
                return True
            else:
                logger.error("GitHub push failed: HTTP %d %s", resp.status_code, resp.text[:200])
                return False
        except Exception as e:
            logger.error("GitHub push error: %s", e)
            return False
