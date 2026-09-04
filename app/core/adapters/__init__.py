# -*- coding: utf-8 -*-
"""多游戏适配器：统一壳 + 按 kind 扩展。

已实现：adv / renpy / telegram / purchased
后续可加：gallery（图集回想）等。
"""
from app.core.adapters.base import (
    CAP_ADV_BEATS,
    CAP_CATALOG,
    CAP_GALLERY,
    CAP_LOCAL_ONLY,
    CAP_PREPARE_CDN,
    CAP_PURCHASED,
    CAP_TELEGRAM,
    AdapterInfo,
    GameAdapter,
)
from app.core.adapters.registry import adapter_info, get_adapter, list_adapters, normalize_kind

__all__ = [
    "CAP_ADV_BEATS",
    "CAP_CATALOG",
    "CAP_GALLERY",
    "CAP_LOCAL_ONLY",
    "CAP_PREPARE_CDN",
    "CAP_PURCHASED",
    "CAP_TELEGRAM",
    "AdapterInfo",
    "GameAdapter",
    "adapter_info",
    "get_adapter",
    "list_adapters",
    "normalize_kind",
]
