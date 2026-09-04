# -*- coding: utf-8 -*-
"""Release 入口：转到同目录 runtime\\python.exe 执行 run_app.py（完整标准库）。"""
from __future__ import annotations

import os
import sys


def _root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _pause() -> None:
    try:
        input("\n按 Enter 退出...")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    root = _root()
    os.chdir(root)
    runtime = os.path.join(root, "runtime", "python.exe")
    script = os.path.join(root, "run_app.py")
    if not os.path.isfile(runtime):
        print(f"找不到嵌入式 Python: {runtime}")
        print("请重新解压完整发布包（需包含 runtime\\ 目录）。")
        _pause()
        return 1
    if not os.path.isfile(script):
        print(f"找不到 run_app.py: {script}")
        _pause()
        return 1
    # 用完整 Python 接管进程，避免 PyInstaller 精简标准库导致 urllib 等缺失
    os.execv(runtime, [runtime, script])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
