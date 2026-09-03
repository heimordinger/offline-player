# -*- coding: utf-8
"""从 MinashigoViewer 重建 orphan_order 分类索引与 category_names。"""
from __future__ import annotations

import argparse
import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.minashigo_ids import CHARACTER_HUB, MAIN_STORY, SITUATION_HUB, SKIN_HUB, SIDE_STORY, SUMMON_HUB
from app.core.minashigo_viewer_index import (
    category_of_scene,
    parse_viewer_index,
    save_viewer_index,
    section_cards,
)

DEFAULT_VIEWER = os.path.normpath(
    os.path.join(PROJECT_ROOT, "..", "孤儿离线", "MinashigoViewer-1.2-pc", "MinashigoViewer-1.2-pc")
)
GAME_ROOT = os.path.join(PROJECT_ROOT, "games", "orphan_order")
JSON_DIR = os.path.join(GAME_ROOT, "json")
TAGS_PATH = os.path.join(GAME_ROOT, "scene_tags.json")
CAT_NAMES_PATH = os.path.join(GAME_ROOT, "category_names.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="从 MinashigoViewer 重建分类索引")
    parser.add_argument("--viewer", default=DEFAULT_VIEWER)
    args = parser.parse_args()

    viewer = os.path.normpath(args.viewer)
    if not os.path.isdir(viewer):
        print(f"Viewer 不存在: {viewer}")
        return 1

    index = parse_viewer_index(viewer)
    idx_path = save_viewer_index(index, JSON_DIR)
    print(f"viewer_index: {len(index['scene_category'])} 场景映射 -> {idx_path}")

    with open(CAT_NAMES_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "names": index["category_names"]}, f, ensure_ascii=False, indent=2)
    print(f"category_names: {len(index['category_names'])} 个 -> {CAT_NAMES_PATH}")

    if os.path.isfile(TAGS_PATH):
        with open(TAGS_PATH, encoding="utf-8") as f:
            tags_data = json.load(f)
        scenes = tags_data.get("scenes", {})
        for sid in scenes:
            scenes[sid]["category"] = category_of_scene(sid, index)
        with open(TAGS_PATH, "w", encoding="utf-8") as f:
            json.dump(tags_data, f, ensure_ascii=False, indent=2)
        print(f"scene_tags: 已更新 {len(scenes)} 个场景的 category")

    cats = {}
    if os.path.isdir(JSON_DIR):
        for name in os.listdir(JSON_DIR):
            if name.endswith(".json"):
                sid = name[:-5]
                cat = category_of_scene(sid, index)
                cats[cat] = cats.get(cat, 0) + 1
    card_cats = [k for k in cats if k.isdigit() and len(k) == 6]
    print(
        f"分类统计: 主线 {cats.get('main_story', 0)} · 支线 {cats.get('side_story', 0)} · "
        f"Situation {cats.get('__situation__', 0)} · 卡面 {len(card_cats)}"
    )
    for key in index["category_order"]:
        if key in (MAIN_STORY, SIDE_STORY, SITUATION_HUB) and key in cats:
            label = index["category_names"].get(key, key)
            try:
                print(f"  {label}: {cats[key]}")
            except UnicodeEncodeError:
                print(f"  {key}: {cats[key]}")
        elif key == CHARACTER_HUB:
            cards = [c for c in section_cards(index, CHARACTER_HUB) if c in cats]
            print(f"  Character: {len(cards)} 卡面 · {sum(cats.get(c, 0) for c in cards)} 场景")
        elif key == SUMMON_HUB:
            cards = [c for c in section_cards(index, SUMMON_HUB) if c in cats]
            print(f"  Summon: {len(cards)} 卡面 · {sum(cats.get(c, 0) for c in cards)} 场景")
        elif key == SKIN_HUB:
            cards = [c for c in section_cards(index, SKIN_HUB) if c in cats]
            print(f"  Skin: {len(cards)} 卡面 · {sum(cats.get(c, 0) for c in cards)} 场景")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
