# -*- coding: utf-8 -*-
"""导入 Ren'Py 离线包到 data/，并打印 games.json 片段。

用法:
  py -3.13 tools/import_renpy_pack.py --pack "D:\\path\\to\\DeepOne（renpy）"
  py -3.13 tools/import_renpy_pack.py --pack "..." --game-id deepone_renpy --apply
  py -3.13 tools/import_renpy_pack.py --pack "..." --detect-only
  py -3.13 tools/import_renpy_pack.py --pack "MinashigoViewer-..." --apply
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

from app.core.renpy_pack import (  # noqa: E402
    detect_pack,
    games_json_snippet,
    import_deepone_json_pack,
)


def _utf8_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _upsert_games_json(entry: dict) -> str:
    path = os.path.join(PROJECT_ROOT, "games.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"games": []}
    games = data.setdefault("games", [])
    gid = entry["id"]
    for i, g in enumerate(games):
        if g.get("id") == gid:
            games[i] = {**g, **entry}
            break
    else:
        games.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def main() -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(description="导入 Ren'Py 离线包")
    parser.add_argument("--pack", required=True, help="Ren'Py 包根目录或 game/ 目录")
    parser.add_argument("--game-id", default="", help="写入 games.json 的 id（默认由目录名生成）")
    parser.add_argument("--name", default="", help="显示名称")
    parser.add_argument(
        "--out",
        default="",
        help="导入目标目录（默认 data/<game-id>）",
    )
    parser.add_argument("--copy", action="store_true", help="复制文件（默认硬链接）")
    parser.add_argument("--detect-only", action="store_true", help="只探测包类型")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="导入并写入/更新 games.json（默认只打印计划）",
    )
    parser.add_argument(
        "--mount",
        action="store_true",
        help="不复制：games.json 直接指向包内 game/（仅 deepone_json）",
    )
    args = parser.parse_args()

    pack_path = os.path.abspath(args.pack)
    try:
        info = detect_pack(pack_path)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    print("探测结果:")
    print(json.dumps(info.to_dict(), ensure_ascii=False, indent=2))

    if info.flavor == "unknown":
        print("无法识别：需要 game/json+resource（DeepOne 系）或 game/scripts/scene_*.rpy（孤儿系）")
        return 2

    if args.detect_only:
        return 0

    base_name = os.path.basename(info.root.rstrip("\\/")) or "renpy_pack"
    game_id = (args.game_id or base_name).strip()
    game_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in game_id).strip("_") or "renpy_pack"
    name = args.name.strip() or base_name

    if info.flavor == "minashigo_scripts":
        out = args.out.strip() or os.path.join(PROJECT_ROOT, "data", game_id)
        print(f"\n将调用 Minashigo 迁移 → {out}")
        if not args.apply:
            snippet = games_json_snippet(
                game_id, name, out, flavor=info.flavor, relative_to=PROJECT_ROOT
            )
            print("预览 games.json 条目:")
            print(json.dumps(snippet, ensure_ascii=False, indent=2))
            print("\n加 --apply 执行迁移并写入 games.json")
            return 0

        # 复用现有迁移脚本
        sys.path.insert(0, TOOLS_DIR)
        import migrate_minashigo as mm

        mm.GAME_ROOT = out
        mm.JSON_DIR = os.path.join(out, "json")
        mm.RESOURCE_DIR = os.path.join(out, "resource")
        mm.EPISODE_DIR = os.path.join(out, "episode")
        mm.TAGS_PATH = os.path.join(out, "scene_tags.json")
        mm.CAT_NAMES_PATH = os.path.join(out, "category_names.json")
        stats = mm.migrate(info.root, link_assets=not args.copy)
        print("迁移完成:", stats)
        snippet = games_json_snippet(
            game_id, name, out, flavor=info.flavor, relative_to=PROJECT_ROOT
        )
        path = _upsert_games_json(snippet)
        print(f"已更新 {path}")
        return 0

    # deepone_json
    if args.mount:
        dest = info.game_dir
        print(f"\n挂载模式：直接使用 {dest}")
        snippet = games_json_snippet(
            game_id, name, dest, flavor=info.flavor, relative_to=PROJECT_ROOT
        )
        # root 若在项目外，用绝对路径更稳
        if os.path.isabs(dest) and not dest.startswith(PROJECT_ROOT):
            snippet["root"] = dest.replace("\\", "/")
        if not args.apply:
            print(json.dumps(snippet, ensure_ascii=False, indent=2))
            print("\n加 --apply 写入 games.json（不复制文件）")
            return 0
        path = _upsert_games_json(snippet)
        print(f"已更新 {path}")
        return 0

    out = args.out.strip() or os.path.join(PROJECT_ROOT, "data", game_id)
    print(f"\n导入目标: {out} ({'复制' if args.copy else '硬链接'})")
    if not args.apply:
        snippet = games_json_snippet(
            game_id, name, out, flavor=info.flavor, relative_to=PROJECT_ROOT
        )
        print("预览 games.json 条目:")
        print(json.dumps(snippet, ensure_ascii=False, indent=2))
        print("\n加 --apply 执行导入并写入 games.json；或 --mount --apply 直接挂载包内路径")
        return 0

    stats = import_deepone_json_pack(info, out, copy=args.copy)
    print("导入完成:", json.dumps(stats, ensure_ascii=False, indent=2))
    snippet = games_json_snippet(
        game_id, name, out, flavor=info.flavor, relative_to=PROJECT_ROOT
    )
    path = _upsert_games_json(snippet)
    print(f"已更新 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
