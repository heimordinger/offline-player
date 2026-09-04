# -*- coding: utf-8 -*-
"""Ren'Py 包适配器：导入后的数据走 ADV 管道播放。"""
from __future__ import annotations

from app.core.adapters.base import (
    CAP_ADV_BEATS,
    CAP_CATALOG,
    CAP_LOCAL_ONLY,
    CAP_PREPARE_CDN,
    AdapterInfo,
    GameAdapter,
)
from app.core.game_registry import GameInfo


class RenpyAdapter:
    """数据形态与 adv 相同；默认可 CDN 补资源（Minashigo 迁移包请设 local_only）。"""

    info = AdapterInfo(
        kind="renpy",
        label="Ren'Py 离线包",
        unit="个场景",
        capabilities=frozenset(
            {CAP_CATALOG, CAP_ADV_BEATS, CAP_PREPARE_CDN, CAP_LOCAL_ONLY}
        ),
        description="从 Ren'Py 包导入的 JSON/台本，播放逻辑同 ADV",
    )

    def load(self, worker, game: GameInfo, progress_lo: float, progress_hi: float):
        from app.core.startup import load_adv_game

        return load_adv_game(worker, game, progress_lo, progress_hi)


def get_adapter() -> GameAdapter:
    return RenpyAdapter()
