# -*- coding: utf-8 -*-
"""ADV 台本适配器：DeepOne / 孤儿的工作等（SceneCatalog + beats）。"""
from __future__ import annotations

from app.core.adapters.base import (
    CAP_ADV_BEATS,
    CAP_CATALOG,
    CAP_PREPARE_CDN,
    AdapterInfo,
    GameAdapter,
)
from app.core.game_registry import GameInfo


class AdvAdapter:
    info = AdapterInfo(
        kind="adv",
        label="ADV 台本",
        unit="个场景",
        capabilities=frozenset({CAP_CATALOG, CAP_ADV_BEATS, CAP_PREPARE_CDN}),
        description="JSON 台本 + resource/；支持 CDN 补资源与节拍播放",
    )

    def load(self, worker, game: GameInfo, progress_lo: float, progress_hi: float):
        from app.core.startup import load_adv_game

        return load_adv_game(worker, game, progress_lo, progress_hi)


def get_adapter() -> GameAdapter:
    return AdvAdapter()
