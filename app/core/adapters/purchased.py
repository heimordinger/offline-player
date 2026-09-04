# -*- coding: utf-8 -*-
"""自购作品适配器：按文件夹层级浏览。"""
from __future__ import annotations

from app.core.adapters.base import (
    CAP_CATALOG,
    CAP_LOCAL_ONLY,
    CAP_PURCHASED,
    AdapterInfo,
    GameAdapter,
)
from app.core.game_registry import GameInfo


class PurchasedAdapter:
    info = AdapterInfo(
        kind="purchased",
        label="自购库",
        unit="个作品",
        capabilities=frozenset({CAP_CATALOG, CAP_PURCHASED, CAP_LOCAL_ONLY}),
        description="本地文件夹作品库，不走 ADV 台本",
    )

    def load(self, worker, game: GameInfo, progress_lo: float, progress_hi: float):
        from app.core.startup import load_purchased_game

        return load_purchased_game(worker, game, progress_lo, progress_hi)


def get_adapter() -> GameAdapter:
    return PurchasedAdapter()
