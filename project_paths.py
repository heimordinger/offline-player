# -*- coding: utf-8 -*-
"""项目根目录与共享资源路径（legacy / app 共用）。

资源统一放在 data/ 下（不进 Git）。app 侧请通过 `active` 读取当前游戏路径；
切换游戏时调用 `set_active_game_paths`。legacy 默认指向 data/deepone_one。
"""
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
LEGACY_DIR = os.path.join(PROJECT_ROOT, "legacy")
APP_DIR = os.path.join(PROJECT_ROOT, "app")
TOOLS_DIR = os.path.join(PROJECT_ROOT, "tools")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def data_path(*parts):
    return os.path.join(PROJECT_ROOT, *parts)


def content_path(*parts):
    """data/ 下的内容路径。"""
    return os.path.join(DATA_DIR, *parts)


# Deepone One 默认资源（兼容旧常量名）
JSON_DIR = content_path("deepone_one", "json")
RESOURCE_DIR = content_path("deepone_one", "resource")
EPISODE_DIR = content_path("deepone_one", "episode")
CUSTOM_VIDEOS_DIR = content_path("deepone_one", "custom_videos")
SETTINGS_PATH = data_path("settings.json")
GAMES_CONFIG_PATH = data_path("games.json")


class ActivePaths:
    """可变路径上下文：模块持有本对象引用，切换游戏后无需重新 import。"""

    __slots__ = (
        "game_id",
        "json_dir",
        "resource_dir",
        "episode_dir",
        "custom_videos_dir",
    )

    def __init__(self):
        self.game_id = "deepone_one"
        self.json_dir = JSON_DIR
        self.resource_dir = RESOURCE_DIR
        self.episode_dir = EPISODE_DIR
        self.custom_videos_dir = CUSTOM_VIDEOS_DIR


active = ActivePaths()


def set_active_game_paths(
    game_id: str,
    *,
    json_dir: str,
    resource_dir: str,
    episode_dir: str,
    custom_videos_dir: str,
) -> None:
    active.game_id = game_id
    active.json_dir = json_dir
    active.resource_dir = resource_dir
    active.episode_dir = episode_dir
    active.custom_videos_dir = custom_videos_dir


def load_settings():
    import json

    with open(SETTINGS_PATH, encoding="utf8") as f:
        return json.load(f)


def ensure_data_dirs():
    for d in (
        active.resource_dir,
        active.episode_dir,
        active.json_dir,
        active.custom_videos_dir,
    ):
        os.makedirs(d, exist_ok=True)
