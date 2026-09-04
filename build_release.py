# -*- coding: utf-8 -*-
"""准备发布目录：嵌入式 Python + _deps + 程序文件 + zip。"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.join(ROOT, "release", "offline-player")
ZIP_OUT = os.path.join(ROOT, "release", "offline-player-win64.zip")
CACHE = os.path.join(ROOT, "release", "cache")
LOG = os.path.join(ROOT, "release", "build_release.log")

# 与本机 py -3.13 接近即可
EMBED_VER = "3.13.3"
EMBED_URL = (
    f"https://www.python.org/ftp/python/{EMBED_VER}/python-{EMBED_VER}-embed-amd64.zip"
)


def log(msg: str) -> None:
    print(msg, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def run(cmd: list[str]) -> None:
    log("> " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def try_rmtree(path: str) -> None:
    if not os.path.isdir(path):
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:
        log(f"[警告] 无法删除 {path}: {exc}")


def ensure_embed() -> str:
    os.makedirs(CACHE, exist_ok=True)
    zip_path = os.path.join(CACHE, f"python-{EMBED_VER}-embed-amd64.zip")
    if not os.path.isfile(zip_path):
        log(f"[1/6] 下载嵌入式 Python {EMBED_VER} ...")
        urllib.request.urlretrieve(EMBED_URL, zip_path)
    else:
        log(f"[1/6] 使用缓存: {zip_path}")
    return zip_path


def patch_pth(runtime_dir: str) -> None:
    for name in os.listdir(runtime_dir):
        if name.endswith("._pth"):
            path = os.path.join(runtime_dir, name)
            text = open(path, encoding="utf-8").read()
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            # 保留 zip 与当前目录，加入父目录与 _deps，启用 site
            keep = [ln for ln in lines if ln.endswith(".zip") or ln == "."]
            if ".." not in keep:
                keep.append("..")
            if r"..\_deps" not in keep and "../_deps" not in keep:
                keep.append(r"..\_deps")
            keep = [ln for ln in keep if not ln.startswith("#") and ln != "import site"]
            keep.append("import site")
            open(path, "w", encoding="utf-8").write("\n".join(keep) + "\n")
            log(f"patched {name}")
            return
    raise FileNotFoundError("embed package missing ._pth")


def build_launcher_exe(icon: str, dist_dir: str, work_dir: str) -> str:
    log("[2/6] 构建 OfflinePlayer.exe（仅跳转到 runtime\\python.exe）...")
    try_rmtree(work_dir)
    try_rmtree(dist_dir)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        "OfflinePlayer",
        "--distpath",
        dist_dir,
        "--workpath",
        work_dir,
        "--specpath",
        work_dir,
        os.path.join(ROOT, "launcher.py"),
    ]
    if icon and os.path.isfile(icon):
        cmd.extend(["--icon", icon])
    run(cmd)
    exe = os.path.join(dist_dir, "OfflinePlayer.exe")
    if not os.path.isfile(exe):
        raise FileNotFoundError(exe)
    return exe


def main() -> int:
    os.chdir(ROOT)
    if os.path.isfile(LOG):
        os.remove(LOG)
    log("=== OfflinePlayer Release Build ===")

    icon = os.path.join(ROOT, "assets", "icon.ico")
    if not os.path.isfile(icon):
        src = r"D:\做着玩\icon.ico"
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(icon), exist_ok=True)
            shutil.copy2(src, icon)
    if not os.path.isfile(icon):
        icon = os.path.join(ROOT, "legacy", "assets", "furau.ico")

    run([sys.executable, "-m", "pip", "install", "-q", "pyinstaller"])

    try_rmtree(STAGE)
    if os.path.isfile(ZIP_OUT):
        os.remove(ZIP_OUT)
    os.makedirs(STAGE, exist_ok=True)

    embed_zip = ensure_embed()
    runtime = os.path.join(STAGE, "runtime")
    os.makedirs(runtime, exist_ok=True)
    with zipfile.ZipFile(embed_zip) as zf:
        zf.extractall(runtime)
    patch_pth(runtime)

    exe = build_launcher_exe(
        icon,
        os.path.join(ROOT, "dist_release"),
        os.path.join(ROOT, "build_release"),
    )

    log("[3/6] 安装 PySide6 到 _deps ...")
    deps = os.path.join(STAGE, "_deps")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "-r",
            "requirements-client.txt",
            "--target",
            deps,
            "--upgrade",
            "--no-warn-script-location",
        ]
    )

    log("[4/6] 复制程序文件 ...")
    shutil.copy2(exe, os.path.join(STAGE, "OfflinePlayer.exe"))
    for name in (
        "VERSION",
        "run_app.py",
        "project_paths.py",
        "games.json",
        "settings.example.json",
    ):
        shutil.copy2(os.path.join(ROOT, name), os.path.join(STAGE, name))
    shutil.copytree(os.path.join(ROOT, "app"), os.path.join(STAGE, "app"), dirs_exist_ok=True)
    data_dir = os.path.join(STAGE, "data")
    os.makedirs(data_dir, exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "data", "README.md"), os.path.join(data_dir, "README.md"))
    shutil.copytree(
        os.path.join(ROOT, "legacy", "assets"),
        os.path.join(STAGE, "legacy", "assets"),
        dirs_exist_ok=True,
    )
    if os.path.isfile(icon):
        assets = os.path.join(STAGE, "assets")
        os.makedirs(assets, exist_ok=True)
        shutil.copy2(icon, os.path.join(assets, "icon.ico"))
    readme = os.path.join(ROOT, "release", "README.txt")
    if os.path.isfile(readme):
        shutil.copy2(readme, os.path.join(STAGE, "README.txt"))

    log("[5/6] 打包 zip ...")
    if os.path.isfile(ZIP_OUT):
        os.remove(ZIP_OUT)
    with zipfile.ZipFile(ZIP_OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _, files in os.walk(STAGE):
            for fn in files:
                full = os.path.join(dirpath, fn)
                arc = os.path.relpath(full, os.path.join(ROOT, "release"))
                zf.write(full, arc.replace("\\", "/"))

    log("[6/6] 清理临时目录 ...")
    try_rmtree(os.path.join(ROOT, "build_release"))
    try_rmtree(os.path.join(ROOT, "dist_release"))

    exe_size = os.path.getsize(os.path.join(STAGE, "OfflinePlayer.exe"))
    zip_size = os.path.getsize(ZIP_OUT)
    log(f"OK: {ZIP_OUT}")
    log(f"exe: {exe_size} bytes  zip: {zip_size} bytes")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"FAILED: {exc}")
        raise
