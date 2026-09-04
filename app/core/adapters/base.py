# -*- coding: utf-8 -*-
"""游戏适配器契约：壳统一浏览/播放，各 kind 自管加载与能力声明。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.core.game_registry import GameInfo

# 能力标志（可组合）。新增游戏时在对应 Adapter.capabilities 中声明。
CAP_CATALOG = "catalog"  # 可列出分类 / 场景
CAP_ADV_BEATS = "adv_beats"  # 台本 → 节拍播放
CAP_PREPARE_CDN = "prepare_cdn"  # 可按 JSON 从 CDN 补资源
CAP_LOCAL_ONLY = "local_only"  # 默认不联网
CAP_TELEGRAM = "telegram"  # Telegram 导出图/视频
CAP_PURCHASED = "purchased"  # 自购文件夹浏览
CAP_GALLERY = "gallery"  # 图集/回想（预留）


@dataclass(frozen=True)
class AdapterInfo:
    """对外暴露的适配器元数据（API / UI）。"""

    kind: str
    label: str
    unit: str  # 数量单位：场景 / 组录屏 / 作品
    capabilities: frozenset[str]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "unit": self.unit,
            "capabilities": sorted(self.capabilities),
            "description": self.description,
        }


@runtime_checkable
class GameAdapter(Protocol):
    """每个 games.json 的 kind 对应一个适配器。"""

    info: AdapterInfo

    def load(self, worker, game: GameInfo, progress_lo: float, progress_hi: float):
        """加载目录与缩略图索引，返回 GameLoadResult。"""
        ...
