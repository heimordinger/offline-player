# -*- coding: utf-8
"""Minashigo（孤儿的工作）场景 ID 与分类解析。"""
from __future__ import annotations

MAIN_STORY_PREFIX = "21"
SIDE_PREFIX = "ev"
SITUATION_PREFIX = "191"

MAIN_STORY = "main_story"
SIDE_STORY = "side_story"
CHARACTER_HUB = "__character__"
SUMMON_HUB = "__summon__"
SITUATION_HUB = "__situation__"
SKIN_HUB = "__skin__"

SECTION_HUBS = (CHARACTER_HUB, SUMMON_HUB, SITUATION_HUB, SKIN_HUB)

SECTION_LABELS = {
    MAIN_STORY: "メインストーリー",
    SIDE_STORY: "サイドストーリー",
    CHARACTER_HUB: "Character",
    SUMMON_HUB: "Summon",
    SITUATION_HUB: "Situation",
    SKIN_HUB: "Skin",
}


def scene_id_from_label(label: str) -> str:
    if label.startswith("scene_"):
        return label[6:]
    return label


def character_card_id_from_scene(scene_id: str) -> str | None:
    """9 位场景 ID 内嵌的 6 位角色卡 ID（如 120010101 → 200101）。"""
    base = scene_id.split("_")[0]
    if base.isdigit() and len(base) >= 7 and base[0] in "1234567":
        return base[1:7]
    return None


def category_for_scene(scene_id: str) -> str:
    base = scene_id.split("_")[0]
    if base.startswith(MAIN_STORY_PREFIX):
        return MAIN_STORY
    if base.lower().startswith(SIDE_PREFIX):
        return SIDE_STORY
    if base.startswith(SITUATION_PREFIX):
        return SITUATION_HUB
    cid = character_card_id_from_scene(scene_id)
    if cid:
        return cid
    return base[:8] or "misc"


def infer_scene_type_ja(scene_id: str) -> str:
    if scene_id.startswith(MAIN_STORY_PREFIX):
        return "メインストーリー"
    if scene_id.lower().startswith(SIDE_PREFIX):
        return "サイドストーリー"
    base = scene_id.split("_")[0]
    if base.startswith(SITUATION_PREFIX):
        return "Situation"
    if character_card_id_from_scene(scene_id):
        tail = base[-3:]
        if tail in ("101", "102", "201", "202", "301", "302"):
            return "キャラクターストーリー"
        return "Hシーン"
    return "シーン"


def infer_scene_type_tag(scene_id: str) -> str:
    ja = infer_scene_type_ja(scene_id)
    mapping = {
        "メインストーリー": "主线",
        "サイドストーリー": "支线",
        "Situation": "武器情景",
        "キャラクターストーリー": "角色故事",
        "Hシーン": "H",
    }
    return mapping.get(ja, "场景")
