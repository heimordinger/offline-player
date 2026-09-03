# -*- coding: utf-8 -*-
"""从台本导出 SillyTavern 角色卡 / 世界书（按分类角色）。

用法:
  py -3 tools/export_sillytavern.py --mode both
  py -3 tools/export_sillytavern.py --mode card --category 1029
  py -3 tools/export_sillytavern.py --game deepone_one --out sillytavern_export
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from project_paths import active, set_active_game_paths
from app.core.category_names import (
    category_names_cache_path,
    load_category_name_cache,
    resolve_script_path,
)
from app.core.game_registry import get_game, load_games
from app.core.script_dialogue import (
    build_mes_example,
    format_dialogue_block,
    parse_script_dialogue,
    pick_primary_name,
    speaker_matches,
    split_aliases,
)
from app.core.tavern_card_png import find_category_avatar, write_tavern_png_card


def _safe_filename(text: str) -> str:
    text = re.sub(r"[<>:\"/\\|?*]", "_", text)
    text = text.replace("・", "_").replace("·", "_")
    return text[:80] or "unknown"


def _activate_game(game_id: str) -> None:
    game = get_game(game_id)
    if game is None:
        raise SystemExit(f"未找到游戏: {game_id}")
    game.ensure_dirs()
    set_active_game_paths(
        game.id,
        json_dir=game.paths.json_dir,
        resource_dir=game.paths.resource_dir,
        episode_dir=game.paths.episode_dir,
        custom_videos_dir=game.paths.custom_videos_dir,
    )


def _group_jids(json_dir: str) -> dict[str, list[str]]:
    cat_jids: dict[str, list[str]] = {}
    if not os.path.isdir(json_dir):
        return cat_jids
    for name in os.listdir(json_dir):
        if not name.lower().endswith(".json"):
            continue
        jid = name[:-5]
        cat = jid.split("_")[0][:4]
        cat_jids.setdefault(cat, []).append(jid)
    for cat in cat_jids:
        cat_jids[cat].sort()
    return cat_jids


def _load_scene_dialogues(jids: list[str]) -> dict[str, list[dict]]:
    scenes: dict[str, list[dict]] = {}
    for jid in jids:
        path = resolve_script_path(jid)
        if not path:
            continue
        with open(path, encoding="utf-8") as f:
            scenes[jid] = parse_script_dialogue(f.readlines())
    return scenes


def _narration_summary(dialogues: list[dict], max_lines: int = 12) -> str:
    lines = [d["text"] for d in dialogues if d["narration"]]
    if not lines:
        return ""
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append("…")
    return "\n".join(lines)


def _char_lines(dialogues: list[dict], aliases: list[str], max_lines: int = 20) -> list[str]:
    out: list[str] = []
    for d in dialogues:
        if not d["narration"] and speaker_matches(d["speaker"], aliases):
            out.append(d["text"])
            if len(out) >= max_lines:
                break
    return out


def _first_char_line(dialogues: list[dict], aliases: list[str]) -> str:
    for d in dialogues:
        if not d["narration"] and speaker_matches(d["speaker"], aliases):
            return d["text"]
    for d in dialogues:
        if d["text"]:
            return d["text"]
    return ""


def _make_character_book(
    book_name: str,
    scenes: dict[str, list[dict]],
    aliases: list[str],
    primary: str,
) -> dict:
    entries: list[dict] = []
    order = 0
    for jid, dialogues in sorted(scenes.items()):
        if not dialogues:
            continue
        content = format_dialogue_block(dialogues, max_lines=80)
        if len(content) > 4000:
            content = content[:4000] + "\n…（台本过长已截断）"
        keys = [jid, jid.split("_")[0]]
        for alias in aliases[:3]:
            if alias and alias != primary:
                keys.append(alias)
        entries.append(
            {
                "keys": keys[:8],
                "content": content,
                "enabled": True,
                "insertion_order": order,
                "case_sensitive": False,
                "selective": False,
                "secondary_keys": [],
                "constant": False,
                "position": "before_char",
                "comment": jid,
                "extensions": {},
            }
        )
        order += 10
    return {
        "name": book_name,
        "description": f"由 DeepOneRE 台本导出 · {len(entries)} 个场景",
        "scan_depth": 50,
        "token_budget": 2048,
        "recursive_scanning": False,
        "extensions": {},
        "entries": entries,
    }


def _make_character_card(
    primary: str,
    aliases: list[str],
    scenes: dict[str, list[dict]],
    category: str,
    game_name: str,
) -> dict:
    all_dialogues: list[dict] = []
    for jid in sorted(scenes.keys()):
        all_dialogues.extend(scenes[jid])

    char_lines = _char_lines(all_dialogues, aliases, max_lines=30)
    narration = _narration_summary(all_dialogues, max_lines=15)
    first_line = _first_char_line(all_dialogues, aliases)

    description_parts = [
        f"{{{{char}}}} 出自 {game_name}（分类 {category}）。",
        f"别名：{'、'.join(aliases)}" if len(aliases) > 1 else "",
    ]
    if narration:
        description_parts.append("【剧情摘要】\n" + narration)
    if char_lines:
        description_parts.append(
            "【台词风格参考】\n" + "\n".join(f"- {t}" for t in char_lines[:12])
        )
    description = "\n\n".join(p for p in description_parts if p)

    personality = (
        f"{{{{char}}}} 说话方式与原作 ADV 台本一致，保留语气、口癖与情绪节奏。"
        f"涉及 {'、'.join(aliases[:4])} 相关剧情时保持人设。"
    )

    scenario = (
        f"{{{{user}}}} 与 {{{{char}}}} 对话。背景可参考 Deep One 原作设定；"
        f"分类编号 {category}，共 {len(scenes)} 个已解析场景台本。"
    )

    first_mes = first_line or "「……」"
    if not first_mes.startswith("「") and not first_mes.startswith('"'):
        first_mes = f"「{first_mes}」"

    mes_example = build_mes_example(all_dialogues, aliases, max_blocks=4)
    book = _make_character_book(f"{primary} · 台本", scenes, aliases, primary)

    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": primary,
            "description": description,
            "personality": personality,
            "scenario": scenario,
            "first_mes": first_mes,
            "mes_example": mes_example,
            "creator_notes": (
                "由 DeepOneRE tools/export_sillytavern.py 从本地台本自动生成。"
                "可在 SillyTavern 中导入 JSON 或嵌入 character_book 作为角色世界书。"
            ),
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": ["DeepOne", game_name, category],
            "creator": "DeepOneRE",
            "character_version": "1.0",
            "extensions": {},
            "character_book": book,
        },
    }


def _make_standalone_worldbook(
    book_name: str,
    scenes: dict[str, list[dict]],
    aliases: list[str],
    primary: str,
    category: str,
) -> dict:
    book = _make_character_book(book_name, scenes, aliases, primary)
    book["description"] = (
        f"DeepOne 分类 {category} · 角色 {primary} · {len(scenes)} 个场景台本"
    )
    return book


def _filter_dialogues_for_alias(
    dialogues: list[dict], alias: str, include_narration: bool = True
) -> list[dict]:
    aliases = [alias]
    out: list[dict] = []
    for d in dialogues:
        if d["narration"]:
            if include_narration:
                out.append(d)
        elif speaker_matches(d["speaker"], aliases):
            out.append(d)
    return out


def _filter_scenes_for_alias(
    scenes: dict[str, list[dict]], alias: str
) -> dict[str, list[dict]]:
    filtered: dict[str, list[dict]] = {}
    for jid, dialogues in scenes.items():
        chunk = _filter_dialogues_for_alias(dialogues, alias)
        if chunk:
            filtered[jid] = chunk
    return filtered


def export_sillytavern(
    game_id: str,
    out_dir: str,
    mode: str,
    categories: list[str] | None,
    per_name: bool = False,
    with_png: bool = True,
    avatar_path: str | None = None,
) -> int:
    _activate_game(game_id)
    game = get_game(game_id)
    if game is None:
        return 0

    name_map = load_category_name_cache()
    if not name_map and os.path.isfile(category_names_cache_path()):
        name_map = load_category_name_cache()

    cat_jids = _group_jids(active.json_dir)
    if categories:
        cat_jids = {c: cat_jids[c] for c in categories if c in cat_jids}

    cards_dir = os.path.join(out_dir, "cards")
    books_dir = os.path.join(out_dir, "worldbooks")
    if mode in ("card", "both"):
        os.makedirs(cards_dir, exist_ok=True)
    if mode in ("worldbook", "both"):
        os.makedirs(books_dir, exist_ok=True)

    exported = 0
    for cat in sorted(cat_jids.keys()):
        title_field = name_map.get(cat, "").strip()
        if not title_field:
            print(f"[跳过] {cat}：无角色名映射（category_names.json）")
            continue

        scenes = _load_scene_dialogues(cat_jids[cat])
        if not scenes:
            print(f"[跳过] {cat}：无本地台本（需先下载 resource 中文本）")
            continue

        primary = pick_primary_name(title_field)
        aliases = split_aliases(title_field)
        targets = aliases if per_name else [primary]

        for name in targets:
            work_scenes = (
                _filter_scenes_for_alias(scenes, name) if per_name else scenes
            )
            if not work_scenes:
                print(f"[跳过] {cat}/{name}：无匹配台词")
                continue
            name_aliases = [name]
            safe = _safe_filename(f"{cat}_{name}")

            if mode in ("card", "both"):
                card = _make_character_card(
                    name, name_aliases, work_scenes, cat, game.name
                )
                card_path = os.path.join(cards_dir, f"{safe}.json")
                with open(card_path, "w", encoding="utf-8") as f:
                    json.dump(card, f, ensure_ascii=False, indent=2)
                print(f"[角色卡] {card_path}（{len(work_scenes)} 场景）")
                exported += 1

                if with_png:
                    avatar = avatar_path or find_category_avatar(cat_jids[cat])
                    if avatar:
                        png_path = os.path.join(cards_dir, f"{safe}.png")
                        if write_tavern_png_card(card, avatar, png_path):
                            print(f"[头像卡] {png_path}（预览图 {os.path.basename(avatar)}）")
                            exported += 1
                        else:
                            print(f"[头像卡] 跳过 {cat}/{name}：PNG 写入失败")
                    else:
                        print(f"[头像卡] 跳过 {cat}/{name}：无角色卡面或预览图")

            if mode in ("worldbook", "both"):
                book = _make_standalone_worldbook(
                    f"{name} · DeepOne {cat}",
                    work_scenes,
                    name_aliases,
                    name,
                    cat,
                )
                book_path = os.path.join(books_dir, f"{safe}.json")
                with open(book_path, "w", encoding="utf-8") as f:
                    json.dump(book, f, ensure_ascii=False, indent=2)
                print(f"[世界书] {book_path}（{len(book['entries'])} 条）")
                exported += 1

    return exported


def main() -> int:
    parser = argparse.ArgumentParser(description="从台本导出 SillyTavern 角色卡/世界书")
    parser.add_argument(
        "--game",
        default="deepone_one",
        help="games.json 中的游戏 id（默认 deepone_one）",
    )
    parser.add_argument(
        "--mode",
        choices=("card", "worldbook", "both"),
        default="both",
        help="导出角色卡、独立世界书或两者",
    )
    parser.add_argument(
        "--category",
        action="append",
        help="仅导出指定分类（四位编号，可多次指定）",
    )
    parser.add_argument(
        "--per-name",
        action="store_true",
        help="按 category_names 中 + 分隔的每个名字各导出一张（多角色分类）",
    )
    parser.add_argument(
        "--no-png",
        action="store_true",
        help="不生成带头像的 PNG 卡（仅 JSON）",
    )
    parser.add_argument(
        "--avatar",
        help="指定头像图片路径（覆盖自动选取的角色卡面）",
    )
    parser.add_argument(
        "--out",
        default=os.path.join(PROJECT_ROOT, "sillytavern_export"),
        help="输出目录（默认项目根 sillytavern_export）",
    )
    args = parser.parse_args()

    games = load_games()
    print(f"游戏: {args.game} · 模式: {args.mode} · 输出: {args.out}")
    if not games:
        print("games.json 为空")
        return 1

    count = export_sillytavern(
        args.game,
        args.out,
        args.mode,
        args.category,
        per_name=args.per_name,
        with_png=not args.no_png,
        avatar_path=args.avatar,
    )
    if count == 0:
        print("未导出任何文件。请确认 category_names.json 与本地台本 resource。")
        return 1
    print(f"完成，共 {count} 个文件。")
    print(
        "导入 SillyTavern：优先导入 cards/*.png（含头像）；"
        "或 JSON + 在 ST 里手动点头像上传"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
