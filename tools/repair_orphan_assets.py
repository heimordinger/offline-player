# -*- coding: utf-8 -*-
"""补全 orphan_order 中缺失的 CG/语音/卡面立绘（从 MinashigoViewer 硬链接）。

不重写台本/JSON，只补文件。比全量 migrate 快很多。

用法:
  python tools/repair_orphan_assets.py
  python tools/repair_orphan_assets.py --cards-only
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
GAME_ROOT = os.path.join(PROJECT_ROOT, "data", "orphan_order")
JSON_DIR = os.path.join(GAME_ROOT, "json")
RESOURCE_DIR = os.path.join(GAME_ROOT, "resource")
EPISODE_CARDS = os.path.join(GAME_ROOT, "episode", "cards")
VIEWER_INDEX = os.path.join(GAME_ROOT, "viewer_index.json")
DEFAULT_VIEWER = os.path.normpath(
    os.path.join(PROJECT_ROOT, "..", "孤儿离线", "MinashigoViewer-1.2-pc", "MinashigoViewer-1.2-pc")
)


def build_cg_index(cg_root: str) -> dict[str, str]:
    index: dict[str, str] = {}
    if not os.path.isdir(cg_root):
        return index
    for root, _, files in os.walk(cg_root):
        for fname in files:
            if not fname.lower().endswith(".jpg"):
                continue
            cg_id = os.path.splitext(fname)[0]
            index.setdefault(cg_id, os.path.join(root, fname))
    return index


def build_voice_index(voices_root: str) -> dict[str, str]:
    index: dict[str, str] = {}
    if not os.path.isdir(voices_root):
        return index
    for root, _, fnames in os.walk(voices_root):
        for fname in fnames:
            index.setdefault(fname, os.path.join(root, fname))
    return index


def link_or_copy(src: str, dst: str) -> bool:
    if os.path.isfile(dst) and os.path.getsize(dst) > 0:
        return True
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    try:
        os.link(src, dst)
        return True
    except OSError:
        try:
            shutil.copy2(src, dst)
            return True
        except OSError:
            return False


def collect_card_ids() -> list[str]:
    ids: set[str] = set()
    if os.path.isfile(VIEWER_INDEX):
        try:
            with open(VIEWER_INDEX, encoding="utf-8") as f:
                data = json.load(f)
            for lst in (data.get("section_card_order") or {}).values():
                for cid in lst or []:
                    if isinstance(cid, str) and cid.isdigit() and len(cid) == 6:
                        ids.add(cid)
            for cid in (data.get("card_section") or {}):
                if isinstance(cid, str) and cid.isdigit() and len(cid) == 6:
                    ids.add(cid)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return sorted(ids)


def resolve_stand_src(viewer_game: str, card_id: str) -> str | None:
    """优先 scene stand 立绘，其次选人图标。"""
    icon_root = os.path.join(viewer_game, "images", "icon")
    candidates = [
        os.path.join(icon_root, "scene stand", f"s{card_id}.png"),
        os.path.join(icon_root, "Character", f"{card_id}.png"),
        os.path.join(icon_root, "Summon", f"{card_id}.png"),
    ]
    for src in candidates:
        if os.path.isfile(src) and os.path.getsize(src) > 0:
            return src
    return None


def link_card_faces(viewer_game: str) -> tuple[int, int, int]:
    """把 Viewer 立绘链到 episode/cards/{id}_main.png（仅孤儿）。"""
    card_ids = collect_card_ids()
    if not card_ids:
        print("  未找到卡面 ID（viewer_index.json）", flush=True)
        return 0, 0, 0
    os.makedirs(EPISODE_CARDS, exist_ok=True)
    linked = skipped = missing = 0
    for cid in card_ids:
        dst = os.path.join(EPISODE_CARDS, f"{cid}_main.png")
        if os.path.isfile(dst) and os.path.getsize(dst) > 0:
            skipped += 1
            continue
        src = resolve_stand_src(viewer_game, cid)
        if src and link_or_copy(src, dst):
            linked += 1
        else:
            missing += 1
    print(
        f"  卡面立绘: 新链 {linked} · 已有 {skipped} · 仍缺 {missing} / 共 {len(card_ids)}",
        flush=True,
    )
    return linked, skipped, missing


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="补全 orphan_order 缺失资源")
    parser.add_argument("--viewer", default=DEFAULT_VIEWER)
    parser.add_argument("--cards-only", action="store_true", help="只补卡面立绘")
    args = parser.parse_args()
    viewer = os.path.normpath(args.viewer)
    viewer_game = os.path.join(viewer, "game")
    if not os.path.isdir(viewer_game):
        print(f"Viewer 不存在: {viewer}")
        return 1

    print(f"Viewer: {viewer}")
    print(f"游戏区: {GAME_ROOT}")

    print("链接卡面立绘（scene stand → episode/cards）…", flush=True)
    link_card_faces(viewer_game)
    if args.cards_only:
        print("完成（仅卡面）")
        return 0

    if not os.path.isdir(JSON_DIR):
        print(f"JSON 目录不存在: {JSON_DIR}")
        return 1

    print("索引 CG / 语音…", flush=True)
    cg_index = build_cg_index(os.path.join(viewer_game, "images", "cg"))
    voice_index = build_voice_index(os.path.join(viewer_game, "audio", "voices"))
    print(f"  CG: {len(cg_index)}, 语音: {len(voice_index)}", flush=True)

    json_files = sorted(f for f in os.listdir(JSON_DIR) if f.lower().endswith(".json"))
    linked = missing = skipped = 0
    total = len(json_files)
    for idx, name in enumerate(json_files, 1):
        sid = name[:-5]
        path = os.path.join(JSON_DIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for entry in data.get("resource") or []:
            rel = str(entry.get("fileName") or "").replace("\\", "/")
            if not rel:
                continue
            dst = os.path.join(RESOURCE_DIR, sid, rel.replace("/", os.sep))
            if os.path.isfile(dst) and os.path.getsize(dst) > 0:
                skipped += 1
                continue
            src = None
            low = rel.lower()
            if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
                src = cg_index.get(os.path.splitext(os.path.basename(rel))[0])
            elif "voice" in low or low.endswith((".mp3", ".ogg", ".wav")):
                src = voice_index.get(os.path.basename(rel))
            elif low.endswith(".txt"):
                missing += 1
                continue
            if src and link_or_copy(src, dst):
                linked += 1
            else:
                missing += 1
        if idx % 200 == 0 or idx == total:
            print(
                f"  进度 {idx}/{total} · 新链 {linked} · 已有 {skipped} · 仍缺 {missing}",
                flush=True,
            )

    print(f"完成: 新链接/复制 {linked}, 已存在跳过 {skipped}, 仍缺 {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
