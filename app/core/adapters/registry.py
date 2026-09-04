# -*- coding: utf-8 -*-
"""按 games.json 的 kind 解析适配器。未知 kind 回退为 adv。"""
from __future__ import annotations

from app.core.adapters.adv import AdvAdapter
from app.core.adapters.base import AdapterInfo, GameAdapter
from app.core.adapters.purchased import PurchasedAdapter
from app.core.adapters.renpy import RenpyAdapter
from app.core.adapters.telegram import TelegramAdapter

_REGISTRY: dict[str, GameAdapter] = {
    "adv": AdvAdapter(),
    "deepone": AdvAdapter(),  # 历史别名
    "renpy": RenpyAdapter(),
    "telegram": TelegramAdapter(),
    "purchased": PurchasedAdapter(),
}


def normalize_kind(kind: str | None) -> str:
    k = (kind or "adv").strip().lower() or "adv"
    if k == "deepone":
        return "adv"
    return k


def get_adapter(kind: str | None) -> GameAdapter:
    k = normalize_kind(kind)
    return _REGISTRY.get(k) or _REGISTRY["adv"]


def list_adapters() -> list[AdapterInfo]:
    seen: set[str] = set()
    out: list[AdapterInfo] = []
    for adapter in _REGISTRY.values():
        if adapter.info.kind in seen:
            continue
        seen.add(adapter.info.kind)
        out.append(adapter.info)
    return out


def adapter_info(kind: str | None) -> AdapterInfo:
    return get_adapter(kind).info
