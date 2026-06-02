"""
Pydantic 数据模型 —— 与前端 ALL_DATA 结构一一对应。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ArticleBase(BaseModel):
    """数据库写入 / API 输出共用字段。"""

    type: str = ""
    cat: str = ""
    title: str
    excerpt: str = ""
    source: str = ""
    url: str = ""
    time: date = Field(default_factory=date.today)
    raw: dict[str, Any] = Field(default_factory=dict)
    is_new: bool = False
    is_featured: bool = False
    is_urgent: bool = False
    status: str = ""


class ArticleOut(ArticleBase):
    """API 响应用模型 —— 追加 id / raw 展开 / 时间戳。"""

    id: int
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)
    created_at: datetime
    updated_at: datetime

    # ---- 映射字段：从 raw 展开到顶层 ----
    @property
    def month(self) -> str | None:
        return self.raw.get("month")

    @property
    def day(self) -> int | None:
        return self.raw.get("day")

    @property
    def year(self) -> int | None:
        return self.raw.get("year")

    @property
    def name(self) -> str | None:
        return self.raw.get("name")

    @property
    def detail(self) -> str | None:
        return self.raw.get("detail")

    @property
    def tags(self) -> list[str]:
        return self.raw.get("tags", [])

    @property
    def status_text(self) -> str | None:
        return self.raw.get("statusText")

    @property
    def location(self) -> str | None:
        return self.raw.get("location")

    @property
    def organizer(self) -> str | None:
        return self.raw.get("organizer")

    @property
    def host(self) -> str | None:
        return self.raw.get("host")

    @property
    def deadline(self) -> str | None:
        return self.raw.get("deadline")

    @property
    def amount(self) -> str | None:
        return self.raw.get("amount")

    @property
    def conditions(self) -> list[str]:
        return self.raw.get("conditions", [])

    @property
    def process(self) -> list[str]:
        return self.raw.get("process", [])

    @property
    def contact(self) -> str | None:
        return self.raw.get("contact")


class ArticleFeed(ArticleBase):
    """采集器内部使用 —— 允许 id 可选。"""

    id: int | None = None


class ArticlesResponse(BaseModel):
    """GET /api/news 响应体。"""

    count: int
    updated: datetime
    items: list[dict[str, Any]]


class CollectReport(BaseModel):
    """采集报告。"""

    new_count: int
    skipped: int
    errors: list[str]
    sources_checked: int
