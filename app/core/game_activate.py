# -*- coding: utf-8 -*-
"""切换当前游戏路径（无 Qt 依赖，可供 LAN 服务使用）。"""
from app.core.game_registry import GameInfo
from project_paths import set_active_game_paths


def activate_game(game: GameInfo) -> None:
    game.ensure_dirs()
    set_active_game_paths(
        game.id,
        json_dir=game.paths.json_dir,
        resource_dir=game.paths.resource_dir,
        episode_dir=game.paths.episode_dir,
        custom_videos_dir=game.paths.custom_videos_dir,
    )
