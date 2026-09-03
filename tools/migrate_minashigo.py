# -*- coding: utf-8
"""将 MinashigoViewer Ren'Py 场景迁移为 DeepOneRE 可播放的 JSON + 资源，并写入日文标签。

用法:
  py -3.13 tools/migrate_minashigo.py --viewer "D:\\离线版\\孤儿离线\\MinashigoViewer-1.2-pc\\MinashigoViewer-1.2-pc"
  py -3.13 tools/migrate_minashigo.py --limit 30   # 试跑
  py -3.13 tools/migrate_minashigo.py --apply      # 默认即写入
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.minashigo_ids import (
    CHARACTER_HUB,
    category_for_scene,
    character_card_id_from_scene,
    infer_scene_type_ja,
    infer_scene_type_tag,
    scene_id_from_label,
)
from app.core.minashigo_viewer_index import category_of_scene, parse_viewer_index, save_viewer_index

DEFAULT_VIEWER = os.path.normpath(
    os.path.join(PROJECT_ROOT, "..", "孤儿离线", "MinashigoViewer-1.2-pc", "MinashigoViewer-1.2-pc")
)
GAME_ROOT = os.path.join(PROJECT_ROOT, "games", "orphan_order")
JSON_DIR = os.path.join(GAME_ROOT, "json")
RESOURCE_DIR = os.path.join(GAME_ROOT, "resource")
EPISODE_DIR = os.path.join(GAME_ROOT, "episode")
TAGS_PATH = os.path.join(GAME_ROOT, "scene_tags.json")
CAT_NAMES_PATH = os.path.join(GAME_ROOT, "category_names.json")

XYZ_RE = re.compile(r'^\s*xyz\s+"(.*)"\s*$')
NAME_ASSIGN_RE = re.compile(r'^\s*\$\s*name\s*=\s*"(.*)"\s*$')
SCENE_RE = re.compile(r"^\s*scene\s+(\S+)")
VOICE_RE = re.compile(r"play voice2\s+'([^']+)'")
LABEL_RE = re.compile(r"^label\s+(scene_\w+)\s*:", re.M)


@dataclass
class ParsedScene:
    scene_id: str
    lines: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    speaker_last: str = ""


def parse_character_labels(charscreen: str) -> dict[str, str]:
    if not os.path.isfile(charscreen):
        return {}
    with open(charscreen, encoding="utf-8") as f:
        text = f.read()
    labels: dict[str, str] = {}
    for m in re.finditer(r'screen S(\d+):.*?label\s+"([^"]+)"', text, re.S):
        sid, label = m.group(1), m.group(2).strip()
        if len(sid) >= 7:
            labels[sid[1:7]] = label
    return labels


def escape_msg(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def voice_rel(raw: str) -> str:
    raw = raw.replace("\\", "/").lstrip("/")
    if raw.startswith("audio/voices/"):
        rest = raw[len("audio/voices/") :]
        parts = rest.split("/")
        if len(parts) >= 2:
            folder, fname = parts[0], parts[-1]
            m = re.search(r"(\d{4,6})", folder)
            char4 = m.group(1)[:4] if m else "0000"
            return f"download/adv/voice/character/{char4}/{fname}"
    return f"download/adv/voice/{os.path.basename(raw)}"


def cg_rel(cg_id: str) -> str:
    return f"download/adv/image/cg/{cg_id}.jpg"


def txt_rel(scene_id: str, char_id: str | None) -> str:
    c4 = (char_id or "0000")[:4]
    return f"download/adv/text/character/{c4}/adultr/{scene_id}.txt"


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


def find_cg_file(cg_index: dict[str, str], cg_id: str) -> str | None:
    return cg_index.get(cg_id)


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


def parse_renpy_scene(path: str) -> ParsedScene | None:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = LABEL_RE.search(text)
    if not m:
        return None
    scene_id = scene_id_from_label(m.group(1))
    out = ParsedScene(scene_id=scene_id)
    out.lines.extend(["name,", "bg,color_0_0_0,1,255", "endwait"])
    current_name = ""

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        nm = NAME_ASSIGN_RE.match(line)
        if nm:
            current_name = nm.group(1).strip()
            out.lines.append(f"name,{current_name}")
            out.speaker_last = current_name
            continue
        vm = VOICE_RE.search(line)
        if vm:
            rel = voice_rel(vm.group(1))
            out.lines.append(f"playvoice,1,{rel}")
            out.resources.append(rel)
            continue
        sm = SCENE_RE.match(line)
        if sm:
            target = sm.group(1)
            if target.lower().startswith("black"):
                out.lines.append("bg,color_0_0_0,1,255")
                out.lines.append("endwait")
            elif target.isdigit():
                rel = cg_rel(target)
                out.lines.append(f"bg,{rel}")
                out.lines.append("endwait")
                out.resources.append(rel)
            continue
        xm = XYZ_RE.match(line)
        if xm:
            msg = xm.group(1).encode("utf-8").decode("unicode_escape") if "\\" in xm.group(1) else xm.group(1)
            if current_name:
                out.lines.append(f"name,{current_name}")
            out.lines.append(f'msg,1,"{escape_msg(msg)}"')
            out.lines.append("clickwait")
            continue
    if len(out.lines) <= 3:
        return None
    return out


def build_json_manifest(scene_id: str, resources: list[str], txt_path: str, tags: dict) -> dict:
    seen: set[str] = set()
    entries = []
    for rel in [txt_path, *resources]:
        rel = rel.replace("\\", "/")
        if rel in seen:
            continue
        seen.add(rel)
        entries.append({"fileName": rel, "path": "local", "md5": "local"})
    try:
        sid_num = int(scene_id.split("_")[0]) if scene_id.split("_")[0].isdigit() else scene_id
    except ValueError:
        sid_num = scene_id
    return {
        "storyIds": [sid_num if isinstance(sid_num, int) else scene_id],
        "adult": 1,
        "local_only": True,
        "tags": tags,
        "resource": entries,
    }


def thumb_src(viewer_game: str, scene_id: str) -> str | None:
    thumb_root = os.path.join(viewer_game, "images", "thumb")
    if not os.path.isdir(thumb_root):
        return None
    prefix = scene_id
    if scene_id.isdigit() and len(scene_id) >= 9:
        prefix = scene_id[:-3]
    for name in os.listdir(thumb_root):
        if name.startswith(prefix) and "_360" in name and name.lower().endswith((".jpg", ".png")):
            return os.path.join(thumb_root, name)
    return None


def migrate(
    viewer_path: str,
    *,
    limit: int | None = None,
    link_assets: bool = True,
) -> dict:
    viewer_game = os.path.join(viewer_path, "game")
    scripts_dir = os.path.join(viewer_game, "scripts")
    cg_root = os.path.join(viewer_game, "images", "cg")
    voices_root = os.path.join(viewer_game, "audio", "voices")

    if not os.path.isdir(scripts_dir):
        raise FileNotFoundError(f"未找到 scripts: {scripts_dir}")

    char_labels = parse_character_labels(os.path.join(viewer_game, "characterscreen.rpy"))
    os.makedirs(JSON_DIR, exist_ok=True)
    os.makedirs(RESOURCE_DIR, exist_ok=True)
    os.makedirs(EPISODE_DIR, exist_ok=True)

    print("索引 CG / 语音资源…", flush=True)
    cg_index = build_cg_index(cg_root)
    voice_index = build_voice_index(voices_root)
    print(f"  CG: {len(cg_index)}, 语音: {len(voice_index)}", flush=True)

    scene_tags: dict[str, dict] = {}
    cat_names: dict[str, str] = dict(char_labels)
    stats = {"scenes": 0, "skipped": 0, "missing_cg": 0, "missing_voice": 0}

    files = sorted(f for f in os.listdir(scripts_dir) if f.startswith("scene_") and f.endswith(".rpy"))
    if limit:
        files = files[:limit]

    total = len(files)
    for idx, fname in enumerate(files, 1):
        src_path = os.path.join(scripts_dir, fname)
        parsed = parse_renpy_scene(src_path)
        if not parsed:
            stats["skipped"] += 1
            continue

        scene_id = parsed.scene_id
        char_id = character_card_id_from_scene(scene_id)
        char_ja = char_labels.get(char_id or "", "") if char_id else ""
        type_ja = infer_scene_type_ja(scene_id)
        type_zh = infer_scene_type_tag(scene_id)
        tags = {
            "character_id": char_id or "",
            "character_ja": char_ja,
            "type_ja": type_ja,
            "type_zh": type_zh,
            "labels_ja": [x for x in [char_ja, type_ja] if x],
            "labels_zh": [x for x in [char_ja, type_zh] if x],
            "category": category_for_scene(scene_id),
        }
        scene_tags[scene_id] = tags

        txt_rel_path = txt_rel(scene_id, char_id)
        res_dir = os.path.join(RESOURCE_DIR, scene_id)
        txt_abs = os.path.join(res_dir, txt_rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(txt_abs), exist_ok=True)
        with open(txt_abs, "w", encoding="utf-8") as f:
            f.write("\n".join(parsed.lines) + "\n")

        resolved_resources = [txt_rel_path]
        for rel in parsed.resources:
            if rel.endswith(".jpg"):
                cg_id = os.path.splitext(os.path.basename(rel))[0]
                src = find_cg_file(cg_index, cg_id)
                dst = os.path.join(res_dir, rel.replace("/", os.sep))
                if src and link_assets:
                    if not link_or_copy(src, dst):
                        stats["missing_cg"] += 1
                elif not src:
                    stats["missing_cg"] += 1
                resolved_resources.append(rel)
            elif "voice" in rel:
                fname_v = os.path.basename(rel)
                src_v = voice_index.get(fname_v)
                dst = os.path.join(res_dir, rel.replace("/", os.sep))
                if src_v and link_assets:
                    if not link_or_copy(src_v, dst):
                        stats["missing_voice"] += 1
                elif not src_v:
                    stats["missing_voice"] += 1
                resolved_resources.append(rel)

        manifest = build_json_manifest(scene_id, resolved_resources, txt_rel_path, tags)
        json_path = os.path.join(JSON_DIR, f"{scene_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        thumb = thumb_src(viewer_game, scene_id)
        if thumb:
            ep = os.path.join(EPISODE_DIR, f"{scene_id}.jpg")
            if link_assets:
                link_or_copy(thumb, ep)

        if char_id and char_ja:
            cat_names[char_id] = char_ja

        stats["scenes"] += 1
        if idx % 100 == 0 or idx == total:
            print(f"  进度 {idx}/{total} ({stats['scenes']} 场景)", flush=True)

    with open(TAGS_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "scenes": scene_tags}, f, ensure_ascii=False, indent=2)

    viewer_index = parse_viewer_index(viewer_path)
    save_viewer_index(viewer_index, JSON_DIR)
    for sid in scene_tags:
        scene_tags[sid]["category"] = category_of_scene(sid, viewer_index)
    with open(TAGS_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "scenes": scene_tags}, f, ensure_ascii=False, indent=2)
    with open(CAT_NAMES_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "names": viewer_index["category_names"]}, f, ensure_ascii=False, indent=2)

    stats["categories"] = len({category_of_scene(s, viewer_index) for s in scene_tags})
    return stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="迁移 MinashigoViewer 到 orphan_order 游戏区")
    parser.add_argument("--viewer", default=DEFAULT_VIEWER, help="MinashigoViewer 根目录")
    parser.add_argument("--limit", type=int, default=None, help="仅迁移前 N 个场景（试跑）")
    parser.add_argument("--copy", action="store_true", help="复制而非硬链接（默认硬链接省空间）")
    args = parser.parse_args()

    viewer = os.path.normpath(args.viewer)
    if not os.path.isdir(viewer):
        print(f"Viewer 不存在: {viewer}")
        return 1

    print(f"Viewer: {viewer}")
    print(f"输出: {GAME_ROOT}")
    stats = migrate(viewer, limit=args.limit, link_assets=not args.copy)
    print(f"完成: {stats['scenes']} 场景, {stats.get('categories', 0)} 分类")
    print(f"跳过(空台本): {stats['skipped']}, 缺 CG: {stats['missing_cg']}, 缺语音: {stats['missing_voice']}")
    print(f"标签: {TAGS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
