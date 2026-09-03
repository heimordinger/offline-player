# -*- coding: utf-8 -*-
"""批量生成本地录屏缩略图。"""
import sys

TOOLS_DIR = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
PROJECT_ROOT = __import__("os").path.dirname(TOOLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.custom_thumb import ensure_custom_thumb
from app.core.scene_catalog import SceneCatalog


def main() -> int:
    catalog = SceneCatalog(auto_load=True)
    jobs = catalog.scan_custom_videos()
    ok = fail = 0
    for jid in jobs:
        rel = jid.split(":", 1)[1]
        path = ensure_custom_thumb(catalog._custom_root, rel)
        if path:
            ok += 1
            print(f"OK {rel}")
        else:
            fail += 1
            print(f"FAIL {rel}")
    print(f"完成: 成功 {ok}, 失败 {fail}, 共 {len(jobs)}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
