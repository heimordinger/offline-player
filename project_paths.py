# -*- coding: utf-8 -*-
"""项目根目录与共享资源路径（legacy / app 共用）。

资源统一放在 data/ 下（不进 Git）。app 侧请通过 `active` 读取当前游戏路径；
切换游戏时调用 `set_active_game_paths`。legacy 默认指向 data/deepone_one。

打包为 exe 时：PROJECT_ROOT 为 exe 所在目录（放 games.json / data/）；
内嵌资源从 PyInstaller 的 _MEIPASS/legacy 读取。
"""
import os
import shutil
import sys


def _resolve_project_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.dirname(__file__))


def _resolve_legacy_dir(root: str) -> str:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        bundled = os.path.join(meipass, "legacy")
        if os.path.isdir(bundled):
            return bundled
    return os.path.join(root, "legacy")


PROJECT_ROOT = _resolve_project_root()
LEGACY_DIR = _resolve_legacy_dir(PROJECT_ROOT)
APP_DIR = os.path.join(PROJECT_ROOT, "app")
TOOLS_DIR = os.path.join(PROJECT_ROOT, "tools")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
APP_ICON_PATH = os.path.join(ASSETS_DIR, "icon.ico")
# 主图标源文件（本机）；发版用 assets/icon.ico，缺省时从此处复制
APP_ICON_SOURCE = r"D:\做着玩\icon.ico"


def resolve_app_icon() -> str | None:
    if os.path.isfile(APP_ICON_PATH):
        return APP_ICON_PATH
    if os.path.isfile(APP_ICON_SOURCE):
        return APP_ICON_SOURCE
    return None


def ensure_app_icon() -> str | None:
    """保证 assets/icon.ico 存在；返回可用图标路径。"""
    if os.path.isfile(APP_ICON_PATH):
        return APP_ICON_PATH
    if os.path.isfile(APP_ICON_SOURCE):
        os.makedirs(ASSETS_DIR, exist_ok=True)
        shutil.copy2(APP_ICON_SOURCE, APP_ICON_PATH)
        return APP_ICON_PATH
    return None


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

    if not os.path.isfile(SETTINGS_PATH):
        example = os.path.join(PROJECT_ROOT, "settings.example.json")
        if os.path.isfile(example):
            shutil.copyfile(example, SETTINGS_PATH)
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
