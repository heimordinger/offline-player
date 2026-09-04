# -*- coding: utf-8 -*-
"""按最新规则重写 orphan_order 台本并补链背景/CG（不重建标签索引）。

修复：
- scene bgXXXX → 背景图
- scene 纯数字 → CG
- 顺带用正确 UTF-8 重写对白（去掉旧 unicode_escape 乱码）

用法:
  python tools/repair_orphan_scripts.py
  python tools/repair_orphan_scripts.py --limit 20
  python tools/repair_orphan_scripts.py --scene 122040202
"""
from __future__ import annotations

import argparse
import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from app.core.minashigo_ids import character_card_id_from_scene  # noqa: E402
from migrate_minashigo import (  # noqa: E402
    DEFAULT_VIEWER,
    JSON_DIR,
    RESOURCE_DIR,
    build_bg_index,
    build_cg_index,
    build_json_manifest,
    build_voice_index,
    find_image_src,
    link_or_copy,
    parse_renpy_scene,
    txt_rel,
)


def repair(
    viewer_path: str,
    *,
    limit: int | None = None,
    scene_id: str | None = None,
    link_assets: bool = True,
) -> dict:
    viewer_game = os.path.join(viewer_path, "game")
    scripts_dir = os.path.join(viewer_game, "scripts")
    cg_root = os.path.join(viewer_game, "images", "cg")
    bg_root = os.path.join(viewer_game, "images", "bg")
    voices_root = os.path.join(viewer_game, "audio", "voices")

    if not os.path.isdir(scripts_dir):
        raise FileNotFoundError(f"未找到 scripts: {scripts_dir}")

    print("索引资源…", flush=True)
    cg_index = build_cg_index(cg_root)
    bg_index = build_bg_index(bg_root)
    voice_index = build_voice_index(voices_root)
    print(f"  CG {len(cg_index)} / 背景 {len(bg_index)} / 语音 {len(voice_index)}", flush=True)

    files = sorted(f for f in os.listdir(scripts_dir) if f.startswith("scene_") and f.endswith(".rpy"))
    if scene_id:
        want = f"scene_{scene_id}.rpy"
        files = [f for f in files if f == want]
        if not files:
            raise FileNotFoundError(f"未找到场景脚本: {want}")
    if limit:
        files = files[:limit]

    stats = {
        "scenes": 0,
        "skipped": 0,
        "bg_cmds": 0,
        "cg_cmds": 0,
        "missing_image": 0,
        "missing_voice": 0,
    }
    total = len(files)
    for idx, fname in enumerate(files, 1):
        parsed = parse_renpy_scene(os.path.join(scripts_dir, fname))
        if not parsed:
            stats["skipped"] += 1
            continue

        sid = parsed.scene_id
        char_id = character_card_id_from_scene(sid)
        txt_rel_path = txt_rel(sid, char_id)
        res_dir = os.path.join(RESOURCE_DIR, sid)
        txt_abs = os.path.join(res_dir, txt_rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(txt_abs), exist_ok=True)
        with open(txt_abs, "w", encoding="utf-8") as f:
            f.write("\n".join(parsed.lines) + "\n")

        for line in parsed.lines:
            if line.startswith("bg,download/adv/image/bg/"):
                stats["bg_cmds"] += 1
            elif line.startswith("bg,download/adv/image/cg/"):
                stats["cg_cmds"] += 1

        # 保留旧 tags（若有）
        tags: dict = {}
        json_path = os.path.join(JSON_DIR, f"{sid}.json")
        if os.path.isfile(json_path):
            try:
                with open(json_path, encoding="utf-8") as f:
                    old = json.load(f)
                tags = old.get("tags") or {}
            except (OSError, json.JSONDecodeError):
                tags = {}

        resolved = [txt_rel_path]
        for rel in parsed.resources:
            low = rel.lower().replace("\\", "/")
            dst = os.path.join(res_dir, rel.replace("/", os.sep))
            if low.endswith((".jpg", ".jpeg", ".png")):
                src = find_image_src(rel, cg_index=cg_index, bg_index=bg_index)
                if src and link_assets:
                    if not link_or_copy(src, dst):
                        stats["missing_image"] += 1
                elif not src:
                    stats["missing_image"] += 1
                resolved.append(rel)
            elif "voice" in low:
                src_v = voice_index.get(os.path.basename(rel))
                if src_v and link_assets:
                    if not link_or_copy(src_v, dst):
                        stats["missing_voice"] += 1
                elif not src_v:
                    stats["missing_voice"] += 1
                resolved.append(rel)

        manifest = build_json_manifest(sid, resolved, txt_rel_path, tags)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        stats["scenes"] += 1
        if idx % 100 == 0 or idx == total:
            print(f"  进度 {idx}/{total}", flush=True)

    return stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="重写 orphan 台本并补背景/CG")
    parser.add_argument("--viewer", default=DEFAULT_VIEWER)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--scene", default=None, help="只修一个 scene id")
    parser.add_argument("--copy", action="store_true", help="复制而非硬链接")
    args = parser.parse_args()

    viewer = os.path.normpath(args.viewer)
    if not os.path.isdir(viewer):
        print(f"Viewer 不存在: {viewer}")
        return 1

    # link_assets True；--copy 时仍用 link_or_copy（失败会 copy）
    stats = repair(viewer, limit=args.limit, scene_id=args.scene, link_assets=True)
    print("完成:", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
