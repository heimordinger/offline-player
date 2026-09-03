# -*- coding: utf-8 -*-
from dataclasses import dataclass


@dataclass
class ThumbEntry:
    key: str
    title: str
    subtitle: str = ""
    image_path: str | None = None
    hover_image_path: str | None = None
    badge: str = ""
    missing_count: int = 0
