# -*- coding: utf-8 -*-
"""新版客户端启动器：保留控制台，便于查看日志与报错。"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))


def _setup_paths() -> None:
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    deps = os.path.join(ROOT, "_deps")
    if not os.path.isdir(deps):
        return
    if deps not in sys.path:
        sys.path.insert(0, deps)
    # PySide6 / Shiboken 依赖本地 DLL
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(deps)
        except OSError:
            pass
        for name in ("shiboken6", "PySide6"):
            sub = os.path.join(deps, name)
            if os.path.isdir(sub):
                try:
                    os.add_dll_directory(sub)
                except OSError:
                    pass
                # Qt 插件/DLL 常在 PySide6 子目录
                for child in os.listdir(sub):
                    child_path = os.path.join(sub, child)
                    if os.path.isdir(child_path) and child.lower().startswith("qt"):
                        try:
                            os.add_dll_directory(child_path)
                        except OSError:
                            pass
    extras = [deps]
    for name in ("shiboken6", "PySide6"):
        sub = os.path.join(deps, name)
        if os.path.isdir(sub):
            extras.append(sub)
    os.environ["PATH"] = os.pathsep.join(extras + [os.environ.get("PATH", "")])


_setup_paths()
os.chdir(ROOT)


def _pause_on_error():
    try:
        input("\n按 Enter 退出...")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    local_version = "?"
    try:
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as vf:
            local_version = vf.read().strip() or "?"
    except OSError:
        pass
    print(f"离线播放器 · 新版 (PySide6)  v{local_version}")
    print(f"工作目录: {ROOT}")
    print("-" * 40)
    try:
        from app.core.updater import maybe_update

        if maybe_update(ROOT):
            return 0
    except Exception:
        traceback.print_exc()
    try:
        from app.main import main as run_app
    except ImportError as exc:
        print("启动失败：缺少依赖。")
        if "PySide6" in str(exc) or "Shiboken" in str(exc):
            print("请确认 _deps 目录完整，或重新运行 build_release.bat")
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
