# -*- coding: utf-8 -*-
"""新版客户端启动器：保留控制台，便于查看日志与报错。"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.chdir(ROOT)


def _pause_on_error():
    try:
        input("\n按 Enter 退出...")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    print("离线播放器 · 新版 (PySide6)")
    print(f"工作目录: {ROOT}")
    print("-" * 40)
    try:
        from app.main import main as run_app
    except ImportError as exc:
        print("启动失败：缺少依赖。")
        if "PySide6" in str(exc):
            print("请先运行: pip install PySide6")
        traceback.print_exc()
        return 1
    try:
        return run_app() or 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        _pause_on_error()
    raise SystemExit(exit_code)
