# -*- coding: utf-8 -*-
"""从台本 name 指令统计分类角色名；结果缓存到本地 category_names.json。"""
from __future__ import annotations

import json
import os

from app.core.adv_script import strip_adv_tags, use_chinese_script
from project_paths import active

CACHE_FILENAME = "category_names.json"


def category_names_cache_path() -> str:
    """与 json/ 同级的本地映射文件（每游戏一份）。"""
    return os.path.join(os.path.dirname(active.json_dir), CACHE_FILENAME)


def load_category_name_cache() -> dict[str, str]:
    path = category_names_cache_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(data, dict):
        names = data.get("names") if "names" in data else data
        if isinstance(names, dict):
            return {str(k): str(v) for k, v in names.items()}
    return {}


def save_category_name_cache(mapping: dict[str, str]) -> None:
    path = category_names_cache_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {"version": 1, "names": mapping}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def resolve_script_path(json_id: str) -> str | None:
    """返回本地台本路径（优先中文 _CN.txt），不存在则 None。"""
    json_path = os.path.join(active.json_dir, json_id + ".json")
    if not os.path.isfile(json_path):
        return None
    try:
        with open(json_path, encoding="utf8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    script_name: str | None = None
    for resource in data.get("resource", []):
        fn = resource.get("fileName", "")
        if "text" in fn.lower():
            script_name = fn.replace("\\", "/")
            break
    if not script_name:
        return None
    if use_chinese_script():
        cn_rel = script_name.replace(".txt", "_CN.txt")
        cn_path = os.path.join(active.resource_dir, json_id, cn_rel)
        if os.path.isfile(cn_path):
            return cn_path
    path = os.path.join(active.resource_dir, json_id, script_name)
    return path if os.path.isfile(path) else None


def iter_speaker_names(script_path: str):
    """按台本顺序 yield 首次出现的说话人。"""
    seen: set[str] = set()
    try:
        with open(script_path, encoding="utf8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("name,"):
                    continue
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                raw = strip_adv_tags(parts[1]).strip()
                if raw and raw != "0" and raw not in seen:
                    seen.add(raw)
                    yield raw
    except OSError:
        pass


def _group_jids_by_category(json_list: list[str]) -> dict[str, list[str]]:
    cat_jids: dict[str, list[str]] = {}
    for jid in json_list:
        cat = jid.split("_")[0][:4]
        cat_jids.setdefault(cat, []).append(jid)
    return cat_jids


def _scan_categories(
    categories: list[str],
    cat_jids: dict[str, list[str]],
    on_step=None,
) -> dict[str, str]:
    """仅扫描指定分类；无台本或无角色名时写入空字符串，避免下次重复扫。"""
    names: dict[str, str] = {}
    total = len(categories)
    for i, cat in enumerate(categories):
        seen: set[str] = set()
        ordered: list[str] = []
        for jid in sorted(cat_jids.get(cat, [])):
            path = resolve_script_path(jid)
            if not path:
                continue
            for speaker in iter_speaker_names(path):
                if speaker not in seen:
                    seen.add(speaker)
                    ordered.append(speaker)
        names[cat] = "+".join(ordered) if ordered else ""
        if on_step and (i % 20 == 0 or i == total - 1):
            on_step(i + 1, total, sum(1 for v in names.values() if v))
    return names


def resolve_category_name_map(
    json_list: list[str],
    on_step=None,
) -> tuple[dict[str, str], int, int]:
    """
    读取本地映射，仅对尚未记录的分类扫台本并写回缓存。

    返回 (完整映射, 本次新扫描分类数, 缓存中已有角色名的分类数)。
    """
    cat_jids = _group_jids_by_category(json_list)
    all_cats = set(cat_jids.keys())

    cache = load_category_name_cache()
    cache = {k: v for k, v in cache.items() if k in all_cats}

    missing = sorted(cat for cat in all_cats if cat not in cache)
    if missing:
        scanned = _scan_categories(missing, cat_jids, on_step)
        cache.update(scanned)
        save_category_name_cache(cache)

    titled = sum(1 for cat in all_cats if cache.get(cat))
    return cache, len(missing), titled

