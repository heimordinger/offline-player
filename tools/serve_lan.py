# -*- coding: utf-8 -*-
"""启动局域网互通测试服务（手机浏览器访问）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
_deps = os.path.join(ROOT, "_deps")
if os.path.isdir(_deps) and _deps not in sys.path:
    sys.path.insert(0, _deps)

os.chdir(ROOT)

try:
    import PySide6  # noqa: F401
except ImportError:
    print("缺少 PySide6，手机端加载游戏会失败。")
    print("请执行: pip install PySide6")
    print("或运行 build_release.bat 生成 _deps 后重试。")
    raise SystemExit(1)

from app.server.lan_server import LanServer


def main() -> int:
    port = None
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("用法: serve_lan.py [端口]")
            return 1
    LanServer(port=port).run_blocking()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
