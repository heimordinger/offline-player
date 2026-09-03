# -*- coding: utf-8
"""从 MinashigoViewer 菜单结构解析场景分类。

Viewer 导航（screens.rpy）：
  Main Story → MainStoryPage1-2（直接 Replay）
  Side Story → SideStoryPage1-5（直接 Replay）
  Character  → CharacterPage1-7（6 位卡面图标 → characterscreen）
  Summon     → SummonPage1-3（6 位卡面图标 → characterscreen）
  Situation  → WeaponSituationPage1-2（直接 Replay）
  Skin       → SkinPage1（6 位卡面图标 → characterscreen）
"""
from __future__ import annotations

import json
import os
import re

from app.core.minashigo_ids import (
    CHARACTER_HUB,
    MAIN_STORY,
    SECTION_LABELS,
    SITUATION_HUB,
    SKIN_HUB,
    SIDE_STORY,
    SUMMON_HUB,
    category_for_scene as fallback_category_for_scene,
)

REPLAY_RE = re.compile(r'Replay\("scene_(\w+)"')
LABEL_RE = re.compile(r'label\s+"([^"]+)"')
CHAR_SCREEN_RE = re.compile(r"(?:^|\n)screen S(\d+):(.*?)(?=\nscreen |\Z)", re.S)
CHAR_ICON_RE = re.compile(r'imagebutton idle "(\d{6})" action Show')


def _card_from_screen(screen_id: str) -> str | None:
    if len(screen_id) >= 7 and screen_id.isdigit():
        return screen_id[1:7]
    return None


def parse_viewer_index(viewer_path: str) -> dict:
    game = os.path.join(viewer_path, "game")
    charscreen = os.path.join(game, "characterscreen.rpy")
    charselect = os.path.join(game, "characterselection.rpy")

    scene_category: dict[str, str] = {}
    card_labels: dict[str, str] = {}
    card_section: dict[str, str] = {}
    section_card_order: dict[str, list[str]] = {
        CHARACTER_HUB: [],
        SUMMON_HUB: [],
        SKIN_HUB: [],
    }

    category_names = dict(SECTION_LABELS)

    if os.path.isfile(charselect):
        text = open(charselect, encoding="utf-8").read()

        for m in re.finditer(
            r"(?:^|\n)screen (MainStory\w+|SideStory\w+):(.*?)(?=\nscreen |\Z)", text, re.S
        ):
            block_name, block = m.group(1), m.group(2)
            target = MAIN_STORY if block_name.startswith("MainStory") else SIDE_STORY
            for sid in REPLAY_RE.findall(block):
                scene_category[sid] = target

        for m in re.finditer(
            r"(?:^|\n)screen WeaponSituationPage\d+:(.*?)(?=\nscreen |\Z)", text, re.S
        ):
            for sid in REPLAY_RE.findall(m.group(1)):
                scene_category[sid] = SITUATION_HUB

        section_page_patterns = (
            (CHARACTER_HUB, "CharacterPage"),
            (SUMMON_HUB, "SummonPage"),
            (SKIN_HUB, "SkinPage"),
        )
        for section, page_prefix in section_page_patterns:
            seen: set[str] = set()
            for m in re.finditer(
                rf"(?:^|\n)screen {page_prefix}\d+:(.*?)(?=\nscreen |\Z)", text, re.S
            ):
                for card_id in CHAR_ICON_RE.findall(m.group(1)):
                    card_section[card_id] = section
                    if card_id not in seen:
                        seen.add(card_id)
                        section_card_order[section].append(card_id)

    if os.path.isfile(charscreen):
        text = open(charscreen, encoding="utf-8").read()
        for m in CHAR_SCREEN_RE.finditer(text):
            screen_id, body = m.group(1), m.group(2)
            card_id = _card_from_screen(screen_id)
            if not card_id:
                continue
            lm = LABEL_RE.search(body)
            if lm:
                card_labels[card_id] = lm.group(1).strip()
            for sid in REPLAY_RE.findall(body):
                scene_category[sid] = card_id
                if card_id not in card_section:
                    series = card_id[0] if card_id else ""
                    if series in ("1", "2"):
                        card_section[card_id] = CHARACTER_HUB
                    elif series in ("3", "4"):
                        card_section[card_id] = SUMMON_HUB
                    elif series == "7":
                        card_section[card_id] = SKIN_HUB

    for card_id, label in card_labels.items():
        category_names[card_id] = label

    return {
        "version": 3,
        "scene_category": scene_category,
        "category_names": category_names,
        "category_order": [
            MAIN_STORY,
            SIDE_STORY,
            CHARACTER_HUB,
            SUMMON_HUB,
            SITUATION_HUB,
            SKIN_HUB,
        ],
        "card_section": card_section,
        "section_card_order": section_card_order,
        "card_labels": card_labels,
    }


def viewer_index_path(json_dir: str | None = None) -> str:
    root = os.path.dirname(json_dir or "")
    return os.path.join(root, "viewer_index.json")


def load_viewer_index(json_dir: str | None = None) -> dict | None:
    path = viewer_index_path(json_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and isinstance(data.get("scene_category"), dict):
        return data
    return None


def save_viewer_index(data: dict, json_dir: str) -> str:
    path = viewer_index_path(json_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def is_section_hub(cat: str) -> bool:
    return cat in (CHARACTER_HUB, SUMMON_HUB, SITUATION_HUB, SKIN_HUB)


def is_card_category(cat: str, index: dict | None = None) -> bool:
    if is_section_hub(cat) or cat in (MAIN_STORY, SIDE_STORY):
        return False
    if index and cat in index.get("card_section", {}):
        return True
    return cat.isdigit() and len(cat) == 6


def category_of_scene(scene_id: str, index: dict | None) -> str:
    if index:
        mapped = index.get("scene_category", {}).get(scene_id)
        if mapped:
            return mapped
    return fallback_category_for_scene(scene_id)


def section_cards(index: dict | None, section: str) -> list[str]:
    if not index:
        return []
    order = list((index.get("section_card_order") or {}).get(section) or [])
    present = set(order)
    card_section = index.get("card_section") or {}
    for card_id, sec in card_section.items():
        if sec == section and card_id not in present:
            order.append(card_id)
            present.add(card_id)
    return order
