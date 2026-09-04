# -*- coding: utf-8 -*-
"""Telegram 录屏适配器。"""
from __future__ import annotations

from app.core.adapters.base import (
    CAP_CATALOG,
    CAP_LOCAL_ONLY,
    CAP_TELEGRAM,
    AdapterInfo,
    GameAdapter,
)
from app.core.game_registry import GameInfo


class TelegramAdapter:
    info = AdapterInfo(
        kind="telegram",
        label="Telegram 录屏",
        unit="组录屏",
        capabilities=frozenset({CAP_CATALOG, CAP_TELEGRAM, CAP_LOCAL_ONLY}),
        description="ChatExport 图/视频，按 #标签分类",
    )

    def load(self, worker, game: GameInfo, progress_lo: float, progress_hi: float):
        from app.core.startup import load_telegram_game

        return load_telegram_game(worker, game, progress_lo, progress_hi)


def get_adapter() -> GameAdapter:
    return TelegramAdapter()
