# -*- coding: utf-8 -*-
"""从 ChatExport 构建孤儿的工作 catalog.json。"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.core.telegram_export_parser import build_catalog_from_export, save_catalog


def main() -> int:
    export_dir = os.path.join(ROOT, "ChatExport_2026-08-25")
    out_path = os.path.join(ROOT, "games", "orphan_recordings", "catalog.json")
    if not os.path.isdir(export_dir):
        print(f"导出目录不存在: {export_dir}")
        return 1
    data = build_catalog_from_export(
        export_dir, ROOT, root_tags=["孤儿的工作", "孤子的工作"]
    )
    save_catalog(data, out_path)
    print(f"已写入 {out_path}")
    print(f"  媒体组: {data.get('group_count', 0)}")
    print(f"  角色标签: {len(data.get('by_tag') or {})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
