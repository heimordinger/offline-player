# -*- coding: utf-8 -*-
"""按文件名快速清理 json/ 中的重复副本（_N 后缀、括号 (N) 等）。

规则：
- 同一 story 基址下，优先保留 10010204.json（无后缀）
- 否则保留后缀数字最小的（_1 优先于 _3；(1) 视为后缀 1）
- 其余副本移入 json/.dedupe_backup/

默认预览；加 --apply 执行。
"""
import argparse
import os
import re
import shutil
import sys
import time

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from project_paths import JSON_DIR

BACKUP_DIR = os.path.join(JSON_DIR, ".dedupe_backup")
PAREN_TAIL_RE = re.compile(r"\s*\(\d+\)$", re.I)


def parse_json_name(filename: str) -> tuple[str, int] | None:
    """解析为 (story基址, 后缀编号)。无后缀为 0。"""
    if not filename.lower().endswith(".json"):
        return None
    stem = filename[:-5]

    m = re.match(r"^(\d+)_(\d+)$", stem, re.I)
    if m:
        return m.group(1), int(m.group(2))

    m = re.match(r"^(\d+)$", stem, re.I)
    if m:
        return m.group(1), 0

    # 10010204 (1) 或 10010204(1)
    m = re.match(r"^(\d+)\s*\((\d+)\)$", stem, re.I)
    if m:
        return m.group(1), int(m.group(2))

    # 其它含括号的乱名：尝试去掉 (N) 后看能否得到数字 id
    if "(" in stem:
        stripped = PAREN_TAIL_RE.sub("", stem).strip()
        m = re.match(r"^(\d+)$", stripped, re.I)
        if m:
            paren = re.search(r"\((\d+)\)\s*$", stem, re.I)
            n = int(paren.group(1)) if paren else 1
            return m.group(1), n

    return None


def scan_groups() -> dict[str, list[tuple[int, str]]]:
    groups: dict[str, list[tuple[int, str]]] = {}
    skipped = 0
    for name in os.listdir(JSON_DIR):
        if name.startswith(".") or not name.lower().endswith(".json"):
            continue
        parsed = parse_json_name(name)
        if not parsed:
            skipped += 1
            continue
        base, suffix = parsed
        groups.setdefault(base, []).append((suffix, name))
    return groups, skipped


def plan_by_filename(groups: dict[str, list[tuple[int, str]]]) -> list[tuple[str, str, str]]:
    plan: list[tuple[str, str, str]] = []
    for base, items in sorted(groups.items()):
        if len(items) <= 1:
            continue
        items = sorted(items, key=lambda x: (x[0], x[1]))
        if any(suf == 0 for suf, _ in items):
            keep = next(name for suf, name in items if suf == 0)
        else:
            keep = items[0][1]
        for _suf, name in items:
            if name != keep:
                plan.append((base, keep, name))
    return plan


def plan_paren_junk(groups: dict[str, list[tuple[int, str]]]) -> list[str]:
    """删除无法归组、但文件名含 (数字) 的 json（若同基址已有规范文件）。"""
    canonical_bases = set(groups.keys())
    remove: list[str] = []
    for name in os.listdir(JSON_DIR):
        if name.startswith(".") or not name.lower().endswith(".json"):
            continue
        if "(" not in name:
            continue
        if parse_json_name(name):
            continue  # 已在主流程处理
        stripped = PAREN_TAIL_RE.sub("", name[:-5]).strip()
        m = re.match(r"^(\d+)", stripped)
        if m and m.group(1) in canonical_bases:
            remove.append(name)
    return remove


def main() -> int:
    parser = argparse.ArgumentParser(description="按文件名快速清理 json 重复副本")
    parser.add_argument("--apply", action="store_true", help="执行移动")
    args = parser.parse_args()

    if not os.path.isdir(JSON_DIR):
        print(f"未找到目录: {JSON_DIR}")
        return 1

    groups, skipped = scan_groups()
    total = sum(len(v) for v in groups.values()) + skipped
    multi = sum(1 for v in groups.values() if len(v) > 1)

    plan = plan_by_filename(groups)
    extra_paren = plan_paren_junk(groups)
    seen = {r for _, _, r in plan}
    for name in extra_paren:
        if name not in seen:
            plan.append(("?", "（已有规范名）", name))

    print(f"json 文件: {total}（未识别命名: {skipped}）")
    print(f"有多个副本的 story: {multi}")
    print(f"将移除副本: {len(plan)} 个（含 _N 与括号命名）")
    if not plan:
        print("无需清理。")
        return 0

    print(f"清理后约剩: {total - len(plan)} 个")
    for base, keep, remove in plan[:12]:
        print(f"  保留 {keep}，移除 {remove}")
    if len(plan) > 12:
        print(f"  … 共 {len(plan)} 个")

    if not args.apply:
        print("\n预览模式。执行请加: --apply")
        return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest_root = os.path.join(BACKUP_DIR, stamp)
    os.makedirs(dest_root, exist_ok=True)
    moved = 0
    for _base, _keep, remove in plan:
        src = os.path.join(JSON_DIR, remove)
        if not os.path.isfile(src):
            continue
        shutil.move(src, os.path.join(dest_root, remove))
        moved += 1

    remain = len(
        [n for n in os.listdir(JSON_DIR) if n.lower().endswith(".json") and not n.startswith(".")]
    )
    print(f"\n已移动 {moved} 个到:\n  {dest_root}")
    print(f"当前 json 数量: {remain}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())
