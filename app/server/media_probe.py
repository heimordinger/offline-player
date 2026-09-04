# -*- coding: utf-8 -*-
"""为 LAN API 探测各游戏下可预览的本地媒体文件。"""
from __future__ import annotations

import os

from app.core.game_registry import GameInfo, get_game
from app.core.game_activate import activate_game

_MEDIA_EXTS = {
    "image": (".jpg", ".jpeg", ".png", ".webp", ".gif"),
    "video": (".mp4", ".webm", ".mov", ".mkv", ".avi"),
}


def _rel_url(root: str, abs_path: str) -> str:
    rel = os.path.relpath(abs_path, root).replace("\\", "/")
    return f"/media/{rel}"


def _scan_dir(
    root: str,
    folder: str,
    limit: int,
    found: list[dict],
) -> None:
    if not os.path.isdir(folder) or len(found) >= limit:
        return
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return
    for name in names:
        if len(found) >= limit:
            break
        low = name.lower()
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            for kind, exts in _MEDIA_EXTS.items():
                if low.endswith(exts):
                    found.append(
                        {
                            "kind": kind,
                            "label": name,
                            "path": os.path.relpath(path, root).replace("\\", "/"),
                            "url": _rel_url(root, path),
                        }
                    )
                    break


def _walk_videos(root: str, folder: str, limit: int, found: list[dict]) -> None:
    if not os.path.isdir(folder) or len(found) >= limit:
        return
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d != ".thumbs"]
        for name in sorted(filenames):
            if len(found) >= limit:
                return
            low = name.lower()
            if not low.endswith(_MEDIA_EXTS["video"]):
                continue
            path = os.path.join(dirpath, name)
            if not os.path.isfile(path):
                continue
            found.append(
                {
                    "kind": "video",
                    "label": os.path.relpath(path, folder).replace("\\", "/"),
                    "path": os.path.relpath(path, root).replace("\\", "/"),
                    "url": _rel_url(root, path),
                }
            )


def find_game_samples(root: str, game_id: str, limit: int = 8) -> list[dict]:
    game = get_game(game_id)
    if game is None:
        return []
    activate_game(game)
    found: list[dict] = []
    paths = game.paths

    _scan_dir(root, paths.episode_dir, limit, found)
    if len(found) < limit:
        _walk_videos(root, paths.custom_videos_dir, limit, found)

    if game.kind == "purchased" and game.library_dir:
        from app.core.purchased_catalog import PurchasedCatalog

        catalog = PurchasedCatalog(game.library_dir, auto_load=True)
        for jid in catalog.json_list[:limit]:
            cover = catalog.scene_preview_path(jid)
            if cover and os.path.isfile(cover):
                found.append(
                    {
                        "kind": "image",
                        "label": jid,
                        "path": os.path.relpath(cover, root).replace("\\", "/"),
                        "url": _rel_url(root, cover),
                    }
                )
            if len(found) >= limit:
                break

    if game.kind == "telegram" and game.export_dir and os.path.isdir(game.export_dir):
        _scan_dir(root, game.export_dir, limit, found)
        _walk_videos(root, game.export_dir, limit, found)

    if len(found) < limit:
        _scan_dir(root, paths.resource_dir, limit, found)
    return found[:limit]
