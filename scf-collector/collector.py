"""
多源 RSS / 网页采集器。
RSS: feedparser → 标准化
HTML: httpx + BeautifulSoup → 正则提取
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup

from models import ArticleFeed

logger = logging.getLogger(__name__)

# ============================================================
# RSS 数据源定义
# ============================================================

# ---- 内容质量白名单 ----
# 标题必须匹配至少一个关键词，否则丢弃
# 目标用户：北京地区企业高管/创业者 → 关注产业政策、AI/科技趋势、大厂战略
QUALITY_KEYWORDS: list[str] = [
    "AI", "人工智能", "大模型", "GPT", "Claude", "Gemini", "DeepSeek", "ChatGPT",
    "芯片", "半导体", "GPU", "算力",
    "自动驾驶", "无人驾驶", "Robotaxi",
    "低空经济", "无人机", "eVTOL",
    "量子", "量子计算",
    "新能源", "光伏", "储能", "电池", "氢能",
    "机器人", "人形机器人",
    "生物医药", "创新药", "基因",
    "数字经济", "数字化转型",
    "政策", "补贴", "扶持", "申报", "专项资金",
    "中关村", "海淀", "亦庄", "北京",
    "投融资", "融资", "IPO", "上市",
    "字节", "百度", "阿里", "腾讯", "小米", "京东", "华为", "美团",
    "OpenAI", "Google", "微软", "Meta", "NVIDIA", "英伟达",
    "科技", "产业", "创新",
]

RSS_SOURCES: list[dict] = [
    # ------ AI / 产业科技 ------
    {
        "name": "36氪",
        "url": "https://36kr.com/feed",
        "type": "news",
        "cat": "人工智能",
        "max_entries": 10,
    },
    {
        "name": "机器之心",
        "url": "https://www.jiqizhixin.com/rss",
        "type": "news",
        "cat": "人工智能",
        "max_entries": 8,
    },
    {
        "name": "量子位",
        "url": "https://www.qbitai.com/feed",
        "type": "news",
        "cat": "人工智能",
        "max_entries": 8,
    },
    {
        "name": "新华网·科技",
        "url": "http://www.news.cn/tech/rss.xml",
        "type": "news",
        "cat": "政策动态",
        "max_entries": 10,
    },
    # ------ 政务 ------
    {
        "name": "北京市科委",
        "url": "https://kw.beijing.gov.cn/so/s?qt=rss&siteCode=1100000224&tab=all&toolsStatus=1",
        "type": "policy",
        "cat": "市级",
        "max_entries": 5,
    },
]

# ============================================================
# HTML 采集目标（无 RSS 的源）
# ============================================================

HTML_SOURCES: list[dict] = [
    # ── 市级政策 ──
    {
        "name": "首都之窗·政策文件",
        "url": "https://www.beijing.gov.cn/zhengce/zhengcefagui/",
        "type": "policy",
        "cat": "市级",
        "selector": "ul.newsList li, ul.list-box li, div.list-content li",
        "title_sel": "a",
        "date_sel": "span.time, span.date, em",
        "link_prefix": "https://www.beijing.gov.cn",
    },
    {
        "name": "北京市科委·通知公告",
        "url": "https://kw.beijing.gov.cn/zwgk/tzgg/",
        "type": "policy",
        "cat": "市级",
        "selector": "div.news_list li, ul.list li, div.list-content li, div.right_list li",
        "title_sel": "a",
        "date_sel": "span.time, span.date, em",
        "link_prefix": "https://kw.beijing.gov.cn",
    },
    {
        "name": "北京市经信局·政策文件",
        "url": "https://jxj.beijing.gov.cn/zwgk/2024zcwj/",
        "type": "policy",
        "cat": "市级",
        "selector": "div.news_list li, ul.list li, div.list-content li",
        "title_sel": "a",
        "date_sel": "span.time, span.date, em",
        "link_prefix": "https://jxj.beijing.gov.cn",
    },
    # ── 区级政策（海淀） ──
    {
        "name": "海淀区·政策文件",
        "url": "https://zyk.bjhd.gov.cn/zwdt/zcwj/",
        "type": "policy",
        "cat": "海淀区",
        "selector": "div.news_list li, ul.list li, div.list-content li, div.right_list li",
        "title_sel": "a",
        "date_sel": "span.time, span.date, em",
        "link_prefix": "https://zyk.bjhd.gov.cn",
    },
    {
        "name": "海淀区·优化营商环境",
        "url": "https://www.bjhd.gov.cn/ztzx/2023/yhyshj/hdqzc/",
        "type": "policy",
        "cat": "海淀区",
        "selector": "div.news_list li, ul.list li, div.list-content li, div.right_list li",
        "title_sel": "a",
        "date_sel": "span.time, span.date, em",
        "link_prefix": "https://www.bjhd.gov.cn",
    },
    # ── 中关村 ──
    {
        "name": "中关村示范区·新闻",
        "url": "https://www.zhongguancun.com.cn/xwzx/",
        "type": "news",
        "cat": "中关村",
        "selector": "div.news-list li, ul.list li, div.list-content li",
        "title_sel": "a",
        "date_sel": "span.time, span.date, em",
        "link_prefix": "https://www.zhongguancun.com.cn",
    },
    {
        "name": "中关村论坛·动态",
        "url": "https://www.zgcforum.com.cn/news/forum",
        "type": "event",
        "cat": "宣发会议",
        "selector": "div.news-list li, ul.list li, div.list-content li, div.forum-list li",
        "title_sel": "a",
        "date_sel": "span.time, span.date, em",
        "link_prefix": "https://www.zgcforum.com.cn",
    },
    # ── 国家科技政策 ──
    {
        "name": "科技部·政策通知",
        "url": "https://www.ncsti.gov.cn/kjdt/tzgg/",
        "type": "policy",
        "cat": "国家级",
        "selector": "div.news_list li, ul.list li, div.list-content li, div.right_list li",
        "title_sel": "a",
        "date_sel": "span.time, span.date, em",
        "link_prefix": "https://www.ncsti.gov.cn",
    },
]


def _passes_quality_filter(title: str) -> bool:
    """标题关键词白名单：不含科技/产业相关关键词的内容直接丢弃。"""
    title_lower = title.lower()
    for kw in QUALITY_KEYWORDS:
        if kw.lower() in title_lower:
            return True
    return False


def _normalize_date(raw: str) -> Optional[date]:
    """尝试把各种日期字符串转为 date。"""
    if not raw:
        return None
    raw = raw.strip()
    # 2026-06-02
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    # 2026-06-02T...
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T", raw)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    # Mon, 02 Jun 2026
    from email.utils import parsedate_to_datetime as _parsedate
    try:
        return _parsedate(raw).date()
    except Exception:
        pass
    # 2026年6月2日
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    return None


def _strip_html(text: str) -> str:
    return BeautifulSoup(text, "html.parser").get_text().strip()


# ============================================================
# RSS 采集
# ============================================================

async def fetch_rss(source: dict, timeout: int = 15) -> list[ArticleFeed]:
    name = source["name"]
    articles: list[ArticleFeed] = []
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            resp = await cli.get(source["url"], headers={
                "User-Agent": "BeijingTechHub/1.0 (RSS Aggregator)"
            })
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

        today = date.today()
        week_ago = today - timedelta(days=7)

        for entry in feed.entries[: source.get("max_entries", 10)]:
            pub_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                from time import mktime
                pub_date = date.fromtimestamp(mktime(entry.published_parsed))
            if pub_date is None:
                pub_date = _normalize_date(entry.get("published", "") or entry.get("updated", ""))
            if pub_date is None:
                pub_date = today  # fallback
            # 仅保留近 7 天
            if pub_date < week_ago:
                continue

            title = _strip_html(entry.get("title", "") or "")
            link = entry.get("link", "")
            # 质量过滤：标题不含科技/产业关键词则丢弃
            if not _passes_quality_filter(title):
                continue

            summary = _strip_html(entry.get("summary", "") or entry.get("description", "") or "")
            if len(summary) > 120:
                summary = summary[:120] + "..."

            articles.append(ArticleFeed(
                type=source["type"],
                cat=source.get("cat", ""),
                title=title[:200],
                excerpt=summary,
                source=name,
                url=link,
                time=pub_date,
                is_new=(pub_date >= today - timedelta(days=1)),
                raw={"rss_source": name},
            ))
        logger.info("RSS [%s]: %d entries kept", name, len(articles))
    except Exception as exc:
        logger.warning("RSS [%s] failed: %s", name, exc)
    return articles


# ============================================================
# HTML 采集
# ============================================================

async def fetch_html(source: dict, timeout: int = 15) -> list[ArticleFeed]:
    name = source["name"]
    articles: list[ArticleFeed] = []
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            resp = await cli.get(source["url"], headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/130.0.0.0 Safari/537.36"
            })
            # 部分政务网站 GBK 编码
            if resp.encoding and "gb" in resp.encoding.lower():
                resp.encoding = "gbk"
            soup = BeautifulSoup(resp.text, "html.parser")

        today = date.today()
        week_ago = today - timedelta(days=7)
        items = soup.select(source["selector"])[:10]

        for li in items:
            a_tag = li.select_one(source["title_sel"])
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            href = a_tag.get("href", "")
            if href and not href.startswith("http"):
                href = urljoin(source["link_prefix"], href)

            raw_date = ""
            date_el = li.select_one(source["date_sel"])
            if date_el:
                raw_date = date_el.get_text(strip=True)
            pub_date = _normalize_date(raw_date) or today
            if pub_date < week_ago:
                continue
            # 质量过滤：标题不含科技/产业/政策关键词则丢弃
            if not _passes_quality_filter(title):
                continue

            articles.append(ArticleFeed(
                type=source["type"],
                cat=source.get("cat", ""),
                title=title[:200],
                excerpt="",
                source=name,
                url=href,
                time=pub_date,
                is_new=(pub_date >= today - timedelta(days=1)),
                raw={"html_source": name},
            ))
        logger.info("HTML [%s]: %d entries kept", name, len(articles))
    except Exception as exc:
        logger.warning("HTML [%s] failed: %s", name, exc)
    return articles


# ============================================================
# 主入口
# ============================================================

async def collect_all() -> list[ArticleFeed]:
    """并行采集所有数据源，汇总去重。"""
    all_items: list[ArticleFeed] = []

    for src in RSS_SOURCES:
        items = await fetch_rss(src)
        all_items.extend(items)

    for src in HTML_SOURCES:
        items = await fetch_html(src)
        all_items.extend(items)

    # URL 去重（保留最新一条）
    seen: dict[str, ArticleFeed] = {}
    for item in all_items:
        if item.url and item.url in seen:
            if item.time > seen[item.url].time:
                seen[item.url] = item
        elif item.url:
            seen[item.url] = item
        else:
            seen[f"no_url_{item.title[:30]}"] = item

    logger.info("Collected %d items total, %d unique", len(all_items), len(seen))
    return list(seen.values())
