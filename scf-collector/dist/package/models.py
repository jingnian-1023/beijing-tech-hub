"""
纯 Python dataclass 数据模型 —— 避免 pydantic 的 Rust 二进制依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ArticleFeed:
    """采集器输出模型。"""

    type: str = ""
    cat: str = ""
    title: str = ""
    excerpt: str = ""
    source: str = ""
    url: str = ""
    time: date = field(default_factory=date.today)
    raw: dict[str, Any] = field(default_factory=dict)
    is_new: bool = False
    is_featured: bool = False
    is_urgent: bool = False
    status: str = ""
    id: int | None = None
