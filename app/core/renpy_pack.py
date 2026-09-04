# -*- coding: utf-8 -*-
"""Ren'Py 离线包探测与导入。

支持两种常见形态：
1. deepone_json — game/json + game/resource（剧情 JSON，与本播放器 ADV 一致）
2. minashigo_scripts — game/scripts/scene_*.rpy（需转成 ADV 台本）
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from typing import Any, Literal

PackFlavor = Literal["deepone_json", "minashigo_scripts", "unknown"]


@dataclass(frozen=True)
class RenpyPack:
    root: str  # 含 DeepOne.exe / MinashigoViewer 的根，或直接 game/ 的上一级
    game_dir: str
    flavor: PackFlavor
    json_dir: str | None = None
    resource_dir: str | None = None
    scripts_dir: str | None = None
    json_count: int = 0
    script_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "game_dir": self.game_dir,
            "flavor": self.flavor,
            "json_dir": self.json_dir,
            "resource_dir": self.resource_dir,
            "scripts_dir": self.scripts_dir,
            "json_count": self.json_count,
            "script_count": self.script_count,
        }


def _is_story_json(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return isinstance(data, dict) and "resource" in data and (
            "storyIds" in data or "storyId" in data
        )
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def resolve_game_dir(pack_path: str) -> str:
    """接受包根或 game/ 目录，返回绝对 game 路径。"""
    path = os.path.abspath(pack_path)
    if os.path.basename(path).lower() == "game" and os.path.isdir(path):
        return path
    nested = os.path.join(path, "game")
    if os.path.isdir(nested):
        return nested
    # 解压后多一层目录：pack/DeepOne（renpy）/game
    if os.path.isdir(path):
        for name in os.listdir(path):
            cand = os.path.join(path, name, "game")
            if os.path.isdir(cand):
                return cand
    raise FileNotFoundError(f"未找到 Ren'Py game 目录: {pack_path}")


def detect_pack(pack_path: str) -> RenpyPack:
    game_dir = resolve_game_dir(pack_path)
    root = os.path.dirname(game_dir)
    json_dir = os.path.join(game_dir, "json")
    resource_dir = os.path.join(game_dir, "resource")
    scripts_dir = os.path.join(game_dir, "scripts")

    json_count = 0
    if os.path.isdir(json_dir):
        for name in os.listdir(json_dir):
            if name.lower().endswith(".json") and _is_story_json(os.path.join(json_dir, name)):
                json_count += 1

    script_count = 0
    if os.path.isdir(scripts_dir):
        script_count = sum(
            1
            for n in os.listdir(scripts_dir)
            if n.startswith("scene_") and n.endswith(".rpy")
        )

    if json_count > 0 and os.path.isdir(resource_dir):
        flavor: PackFlavor = "deepone_json"
    elif script_count > 0:
        flavor = "minashigo_scripts"
    else:
        flavor = "unknown"

    return RenpyPack(
        root=root,
        game_dir=game_dir,
        flavor=flavor,
        json_dir=json_dir if os.path.isdir(json_dir) else None,
        resource_dir=resource_dir if os.path.isdir(resource_dir) else None,
        scripts_dir=scripts_dir if os.path.isdir(scripts_dir) else None,
        json_count=json_count,
        script_count=script_count,
    )


def _link_or_copy(src: str, dst: str, *, copy: bool) -> str:
    """返回 'skip' | 'link' | 'copy'。"""
    if os.path.isfile(dst) and os.path.getsize(dst) > 0:
        return "skip"
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    if not copy:
        try:
            os.link(src, dst)
            return "link"
        except OSError:
            pass
    shutil.copy2(src, dst)
    return "copy"


def _mirror_tree(src_root: str, dst_root: str, *, copy: bool) -> dict[str, int]:
    stats = {"files": 0, "linked": 0, "copied": 0, "skipped": 0}
    if not os.path.isdir(src_root):
        return stats
    for dirpath, _dirs, files in os.walk(src_root):
        rel_dir = os.path.relpath(dirpath, src_root)
        for name in files:
            src = os.path.join(dirpath, name)
            if rel_dir in (".", ""):
                dst = os.path.join(dst_root, name)
            else:
                dst = os.path.join(dst_root, rel_dir, name)
            try:
                if not os.path.isfile(src) or os.path.getsize(src) <= 0:
                    continue
            except OSError:
                continue
            action = _link_or_copy(src, dst, copy=copy)
            stats["files"] += 1
            if action == "skip":
                stats["skipped"] += 1
            elif action == "link":
                stats["linked"] += 1
            else:
                stats["copied"] += 1
    return stats


def import_deepone_json_pack(
    pack: RenpyPack,
    dest_root: str,
    *,
    copy: bool = False,
) -> dict[str, Any]:
    """把 deepone_json 包的 json/resource（及可选 episode）镜像到 dest_root。"""
    if pack.flavor != "deepone_json":
        raise ValueError(f"需要 deepone_json 包，当前为 {pack.flavor}")
    assert pack.json_dir and pack.resource_dir

    dest_root = os.path.abspath(dest_root)
    dst_json = os.path.join(dest_root, "json")
    dst_res = os.path.join(dest_root, "resource")
    dst_ep = os.path.join(dest_root, "episode")
    os.makedirs(dst_json, exist_ok=True)
    os.makedirs(dst_res, exist_ok=True)
    os.makedirs(dst_ep, exist_ok=True)

    json_stats = _mirror_tree(pack.json_dir, dst_json, copy=copy)
    res_stats = _mirror_tree(pack.resource_dir, dst_res, copy=copy)

    # 可选：json_play 缩略图 / images
    extra: dict[str, Any] = {}
    for name in ("json_play", "images", "episode"):
        src = os.path.join(pack.game_dir, name)
        if os.path.isdir(src) and name != "episode":
            # json_play 仅作参考，不强制；episode 若存在则镜像
            continue
    ep_src = os.path.join(pack.game_dir, "episode")
    if os.path.isdir(ep_src):
        extra["episode"] = _mirror_tree(ep_src, dst_ep, copy=copy)

    # list.json 若存在，复制到游戏根便于以后做菜单
    list_src = os.path.join(pack.game_dir, "list.json")
    if os.path.isfile(list_src):
        _link_or_copy(list_src, os.path.join(dest_root, "list.json"), copy=True)

    return {
        "flavor": pack.flavor,
        "dest": dest_root,
        "json": json_stats,
        "resource": res_stats,
        **extra,
    }


def games_json_snippet(
    game_id: str,
    name: str,
    dest_root: str,
    *,
    flavor: PackFlavor,
    relative_to: str | None = None,
) -> dict[str, Any]:
    """生成可粘贴进 games.json 的条目。"""
    root = dest_root
    if relative_to:
        try:
            root = os.path.relpath(dest_root, relative_to).replace("\\", "/")
        except ValueError:
            root = dest_root.replace("\\", "/")
    entry: dict[str, Any] = {
        "id": game_id,
        "name": name,
        "description": "Ren'Py 离线包导入" if flavor == "deepone_json" else "Ren'Py 台本迁移",
        "kind": "renpy",
        "local_only": flavor == "minashigo_scripts",
        "enabled": True,
        "root": root,
        "paths": {
            "json": "json",
            "resource": "resource",
            "episode": "episode",
            "custom_videos": "custom_videos",
        },
    }
    if flavor == "minashigo_scripts":
        entry["category_mode"] = "minashigo"
    else:
        entry["category_mode"] = "deepone"
    return entry
