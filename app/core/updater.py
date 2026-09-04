# -*- coding: utf-8 -*-
"""启动时检查 GitHub Releases，可选下载增量更新包（不触碰 data/）。"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from typing import Any

GITHUB_REPO = "heimordinger/offline-player"
UPDATE_ASSET = "offline-player-update.zip"
NETWORK_TIMEOUT = 12
USER_AGENT = "offline-player-updater"

# 更新时绝不覆盖的用户内容
SKIP_TOP_DIRS = frozenset({"data", "tg_library", "runtime", "_deps"})
SKIP_TOP_FILES = frozenset({"settings.json", "OfflinePlayer.exe"})


def read_local_version(root: str) -> str:
    path = os.path.join(root, "VERSION")
    if not os.path.isfile(path):
        return "0.0.0"
    with open(path, encoding="utf-8") as f:
        return f.read().strip() or "0.0.0"


def parse_version(text: str) -> tuple[int, ...]:
    text = text.strip().lstrip("vV")
    m = re.match(r"(\d+(?:\.\d+)*)", text)
    if not m:
        return (0,)
    return tuple(int(p) for p in m.group(1).split("."))


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def _api_get(url: str) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=NETWORK_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def fetch_latest_release() -> dict[str, Any] | None:
    return _api_get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest")


def find_update_asset(release: dict[str, Any]) -> dict[str, Any] | None:
    for asset in release.get("assets") or []:
        if asset.get("name") == UPDATE_ASSET:
            return asset
    return None


def _ask_yes_no(title: str, message: str) -> bool:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox()
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.Yes)
        return box.exec() == QMessageBox.Yes
    except Exception:
        print(message)
        try:
            ans = input("是否更新？[Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return ans in ("", "y", "yes")


def _download(url: str, dest: str) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
            shutil.copyfileobj(resp, out)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _staging_root(extract_dir: str) -> str:
    names = [n for n in os.listdir(extract_dir) if not n.startswith(".")]
    if len(names) == 1:
        only = os.path.join(extract_dir, names[0])
        if os.path.isdir(only):
            return only
    return extract_dir


def _should_skip_relative(rel: str) -> bool:
    rel = rel.replace("\\", "/").lstrip("/")
    if not rel:
        return True
    top = rel.split("/", 1)[0]
    if top in SKIP_TOP_DIRS:
        return True
    if "/" not in rel and rel in SKIP_TOP_FILES:
        return True
    if rel in SKIP_TOP_FILES:
        return True
    return False


def apply_update_zip(zip_path: str, root: str) -> bool:
    root = os.path.abspath(root)
    try:
        with tempfile.TemporaryDirectory(prefix="op_update_") as tmp:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp)
            src_root = _staging_root(tmp)
            for name in os.listdir(src_root):
                rel = name.replace("\\", "/")
                if _should_skip_relative(rel):
                    continue
                src = os.path.join(src_root, name)
                dst = os.path.join(root, name)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
        return True
    except (OSError, zipfile.BadZipFile, shutil.Error):
        return False


def _restart(root: str) -> None:
    if getattr(sys, "frozen", False):
        os.execv(sys.executable, [sys.executable])
    py = sys.executable
    script = os.path.join(root, "run_app.py")
    os.execv(py, [py, script])


def maybe_update(root: str) -> bool:
    """检查并可选应用更新。若已重启进程则不应返回（execv）。"""
    current = read_local_version(root)
    release = fetch_latest_release()
    if not release:
        return False

    tag = str(release.get("tag_name") or release.get("name") or "").strip()
    if not tag or not is_newer(tag, current):
        return False

    asset = find_update_asset(release)
    if not asset:
        print(f"发现新版本 {tag}，但未找到 {UPDATE_ASSET}，跳过自动更新。")
        return False

    url = str(asset.get("browser_download_url") or "")
    if not url:
        return False

    body = str(release.get("body") or "").strip()
    extra = f"\n\n{body[:400]}" if body else ""
    if not _ask_yes_no(
        "发现新版本",
        f"当前版本：{current}\n最新版本：{tag}\n\n是否现在下载并更新？\n（不会修改 data/ 与 settings.json）{extra}",
    ):
        return False

    print(f"正在下载 {UPDATE_ASSET} ...")
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            zip_path = tmp.name
        if not _download(url, zip_path):
            print("下载失败，将继续以当前版本启动。")
            os.remove(zip_path)
            return False
        print("正在应用更新...")
        if not apply_update_zip(zip_path, root):
            print("更新失败，将继续以当前版本启动。")
            os.remove(zip_path)
            return False
        os.remove(zip_path)
    except OSError:
        print("更新过程出错，将继续以当前版本启动。")
        return False

    print("更新完成，正在重启...")
    _restart(root)
    return True
