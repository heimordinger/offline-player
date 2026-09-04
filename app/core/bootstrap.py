# -*- coding: utf-8 -*-
"""Release 运行环境：路径、_deps、Windows DLL 搜索路径。"""
from __future__ import annotations

import os
import sys
import traceback


def bootstrap(root: str) -> None:
    root = os.path.abspath(root)
    deps = os.path.join(root, "_deps")
    for path in (deps, root):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    os.chdir(root)
    if sys.platform == "win32":
        add_dll = getattr(os, "add_dll_directory", None)
        if add_dll:
            for sub in ("PySide6", "shiboken6", ""):
                folder = os.path.join(deps, sub) if sub else deps
                if os.path.isdir(folder):
                    try:
                        add_dll(folder)
                    except OSError:
                        pass


def log_startup_error(root: str, exc: BaseException) -> str:
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, "startup_error.log")
    with open(path, "w", encoding="utf-8") as f:
        f.write(traceback.format_exc())
        f.write("\n")
    return path
