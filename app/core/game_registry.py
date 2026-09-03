# -*- coding: utf-8 -*-
"""游戏注册表：读取 games.json，解析各游戏资源路径。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from project_paths import PROJECT_ROOT, data_path

GAMES_CONFIG_PATH = data_path("games.json")


@dataclass(frozen=True)
class GamePaths:
    json_dir: str
    resource_dir: str
    episode_dir: str
    custom_videos_dir: str


@dataclass(frozen=True)
class GameInfo:
    id: str
    name: str
    description: str
    enabled: bool
    cover: str | None
    root: str
    paths: GamePaths
    kind: str = "adv"
    export_dir: str | None = None
    catalog_file: str | None = None
    root_tags: tuple[str, ...] = ()
    category_mode: str = "deepone"
    local_only: bool = False
    library_dir: str | None = None

    def ensure_dirs(self) -> None:
        if self.kind == "purchased":
            if self.library_dir:
                os.makedirs(self.library_dir, exist_ok=True)
            return
        for d in (
            self.paths.json_dir,
            self.paths.resource_dir,
            self.paths.episode_dir,
            self.paths.custom_videos_dir,
        ):
            os.makedirs(d, exist_ok=True)


def _resolve(root: str, rel: str) -> str:
    if os.path.isabs(rel):
        return os.path.normpath(rel)
    base = PROJECT_ROOT if root in ("", ".", "./") else os.path.join(PROJECT_ROOT, root)
    return os.path.normpath(os.path.join(base, rel))


def _parse_game(raw: dict) -> GameInfo | None:
    gid = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not gid or not name:
        return None
    root = str(raw.get("root") or ".").strip() or "."
    path_map = raw.get("paths") or {}
    paths = GamePaths(
        json_dir=_resolve(root, str(path_map.get("json") or "json")),
        resource_dir=_resolve(root, str(path_map.get("resource") or "resource")),
        episode_dir=_resolve(root, str(path_map.get("episode") or "episode")),
        custom_videos_dir=_resolve(
            root, str(path_map.get("custom_videos") or "custom_videos")
        ),
    )
    cover_raw = str(raw.get("cover") or "").strip()
    cover = None
    if cover_raw:
        cover = cover_raw if os.path.isabs(cover_raw) else data_path(cover_raw)
        if not os.path.isfile(cover):
            cover = None
    kind = str(raw.get("kind") or "adv").strip().lower() or "adv"
    export_dir = str(raw.get("export_dir") or "").strip() or None
    if export_dir and not os.path.isabs(export_dir):
        export_dir = _resolve(root, export_dir) if export_dir.startswith("games/") else data_path(export_dir)
    catalog_file = str(raw.get("catalog_file") or "catalog.json").strip() or "catalog.json"
    if not os.path.isabs(catalog_file):
        catalog_file = _resolve(root, catalog_file)
    root_tags_raw = raw.get("root_tags") or []
    root_tags = tuple(str(t).strip() for t in root_tags_raw if str(t).strip())
    category_mode = str(raw.get("category_mode") or "deepone").strip().lower() or "deepone"
    local_only = bool(raw.get("local_only", False))
    library_dir = str(raw.get("library_dir") or "").strip() or None
    if kind == "purchased" and not library_dir:
        library_dir = PROJECT_ROOT if root in ("", ".", "./") else _resolve(".", root)
    elif library_dir and not os.path.isabs(library_dir):
        library_dir = _resolve(root, library_dir)
    return GameInfo(
        id=gid,
        name=name,
        description=str(raw.get("description") or "").strip(),
        enabled=bool(raw.get("enabled", True)),
        cover=cover,
        root=root,
        paths=paths,
        kind=kind,
        export_dir=export_dir,
        catalog_file=catalog_file,
        root_tags=root_tags,
        category_mode=category_mode,
        local_only=local_only,
        library_dir=library_dir,
    )


def load_games(include_disabled: bool = False) -> list[GameInfo]:
    if not os.path.isfile(GAMES_CONFIG_PATH):
        return [_default_deepone()]
    with open(GAMES_CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    games: list[GameInfo] = []
    for raw in data.get("games") or []:
        if not isinstance(raw, dict):
            continue
        info = _parse_game(raw)
        if info is None:
            continue
        if info.enabled or include_disabled:
            games.append(info)
    return games or [_default_deepone()]


def get_game(game_id: str) -> GameInfo | None:
    for g in load_games(include_disabled=True):
        if g.id == game_id:
            return g
    return None


def _default_deepone() -> GameInfo:
    return GameInfo(
        id="deepone_one",
        name="Deepone One",
        description="Deep One 离线 ADV / 录屏",
        enabled=True,
        cover=None,
        root=".",
        paths=GamePaths(
            json_dir=data_path("json"),
            resource_dir=data_path("resource"),
            episode_dir=data_path("episode"),
            custom_videos_dir=data_path("custom_videos"),
        ),
    )


def quick_scene_count(game: GameInfo) -> int:
    if game.kind == "telegram":
        if game.catalog_file and os.path.isfile(game.catalog_file):
            try:
                import json

                with open(game.catalog_file, encoding="utf-8") as f:
                    data = json.load(f)
                return int(data.get("group_count") or len(data.get("groups") or []))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        return 0
    if game.kind == "purchased":
        lib = game.library_dir
        if not lib or not os.path.isdir(lib):
            return 0
        count = 0
        try:
            for author in os.listdir(lib):
                author_path = os.path.join(lib, author)
                if not os.path.isdir(author_path) or author.startswith("."):
                    continue
                count += sum(
                    1
                    for w in os.listdir(author_path)
                    if os.path.isdir(os.path.join(author_path, w)) and not w.startswith(".")
                )
        except OSError:
            return 0
        return count
    root = game.paths.json_dir
    if not os.path.isdir(root):
        return 0
    return sum(1 for n in os.listdir(root) if n.lower().endswith(".json"))
