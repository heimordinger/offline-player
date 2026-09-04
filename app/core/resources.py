# -*- coding: utf-8 -*-
"""场景资源清单与下载。"""
import json
import os
import socket
import threading
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FuturesTimeout

from project_paths import active, load_settings

CDN_ADV = "https://tonofura-r-cdn-resource.deepone-online.com/deep_one/download_adv/"
CN_BASE = "https://lisanjin.github.io/DeepOne_translate_CN/"

CHUNK_SIZE = 256 * 1024
USER_AGENT = "DeepOneRE/1.0"
MAX_DOWNLOAD_WORKERS = 16
_path_locks: dict[str, threading.Lock] = {}
_path_locks_guard = threading.Lock()


def iter_resource_entries(json_id: str):
    json_path = os.path.join(active.json_dir, json_id + ".json")
    with open(json_path, encoding="utf8") as f:
        data = json.load(f)
    for r in data.get("resource", []):
        rel = r["fileName"].replace("\\", "/")
        local = os.path.join(active.resource_dir, json_id, rel)
        end = rel.split(".")[-1]
        url = CDN_ADV + r["path"] + "/" + r["md5"] + "." + end
        yield rel, local, url
        if rel.endswith(".txt"):
            cn_rel = rel.replace(".txt", "_CN.txt")
            cn_local = os.path.join(active.resource_dir, json_id, cn_rel)
            cn_url = CN_BASE + rel
            yield cn_rel, cn_local, cn_url


def scene_has_mp4(json_id: str) -> bool:
    """场景资源清单中是否包含 mp4（动态 CG / 视频）。"""
    json_path = os.path.join(active.json_dir, json_id + ".json")
    if not os.path.isfile(json_path):
        return False
    try:
        with open(json_path, encoding="utf8") as f:
            data = json.load(f)
        for r in data.get("resource", []):
            fn = r.get("fileName", "").replace("\\", "/").lower()
            if fn.endswith(".mp4"):
                return True
    except (OSError, json.JSONDecodeError, KeyError):
        return False
    return False


def _timeout_for_url(url: str) -> int:
    low = url.lower()
    if low.endswith(".mp4"):
        return 300
    if "github.io" in low:
        return 45
    if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return 90
    return 60


def _remove_if_exists(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _lock_for_path(local: str) -> threading.Lock:
    key = os.path.normpath(local)
    with _path_locks_guard:
        if key not in _path_locks:
            _path_locks[key] = threading.Lock()
        return _path_locks[key]


def _download_one(url: str, local: str) -> bool:
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return True
    lock = _lock_for_path(local)
    with lock:
        if os.path.exists(local) and os.path.getsize(local) > 0:
            return True
        if os.path.exists(local) and os.path.getsize(local) == 0:
            _remove_if_exists(local)

        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        timeout = _timeout_for_url(url)
        tmp = local + ".part"
        name = os.path.basename(local)

        for attempt in range(3):
            _remove_if_exists(tmp)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    with open(tmp, "wb") as handle:
                        while True:
                            chunk = resp.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            handle.write(chunk)
                if not os.path.exists(tmp) or os.path.getsize(tmp) <= 0:
                    raise OSError("空文件")
                os.replace(tmp, local)
                return True
            except urllib.error.HTTPError as exc:
                # 404/403 再试也没用，立刻放弃，避免准备页卡死重试
                print(f"[下载] 失败 ({attempt + 1}/3) {name}: {exc}")
                _remove_if_exists(tmp)
                if exc.code in (403, 404, 410):
                    return False
            except (urllib.error.URLError, TimeoutError, OSError, socket.timeout) as exc:
                print(f"[下载] 失败 ({attempt + 1}/3) {name}: {exc}")
                _remove_if_exists(tmp)
        return False


def local_resource_path(json_id: str, rel_path: str) -> str | None:
    """仅检查本地是否已有资源，不触发下载。"""
    rel_path = rel_path.replace("\\", "/")
    if rel_path == "color_0_0_0":
        return None
    local = os.path.join(active.resource_dir, json_id, rel_path)
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return local
    return None


def ensure_resource(json_id: str, rel_path: str) -> str | None:
    """确保单个资源存在（播放中按需补下）。"""
    rel_path = rel_path.replace("\\", "/")
    if rel_path == "color_0_0_0":
        return None
    local = os.path.join(active.resource_dir, json_id, rel_path)
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return local
    for rel, path, url in iter_resource_entries(json_id):
        if rel == rel_path:
            if _download_one(url, path):
                return path
            break
    return None


def has_missing_resources(json_id: str) -> bool:
    for _, local, _ in iter_resource_entries(json_id):
        if not (os.path.exists(local) and os.path.getsize(local) > 0):
            return True
    return False


def prepare_script_files(json_id: str) -> bool:
    """确保剧本文本已下载，边下边看时用于尽快进入播放。"""
    from app.core.adv_script import load_adv_commands

    try:
        load_adv_commands(json_id)
        return True
    except FileNotFoundError:
        pass

    for rel, local, url in iter_resource_entries(json_id):
        rel_norm = rel.replace("\\", "/").lower()
        if not rel_norm.endswith(".txt"):
            continue
        if not (os.path.exists(local) and os.path.getsize(local) > 0):
            _download_one(url, local)

    try:
        load_adv_commands(json_id)
        return True
    except FileNotFoundError:
        return False


def count_missing_resources(json_id: str) -> int:
    count = 0
    for _, local, _ in iter_resource_entries(json_id):
        if not (os.path.exists(local) and os.path.getsize(local) > 0):
            count += 1
    return count


def get_missing_resources(json_id: str) -> list[tuple[str, str, str]]:
    missing = []
    for rel, local, url in iter_resource_entries(json_id):
        if not (os.path.exists(local) and os.path.getsize(local) > 0):
            missing.append((rel, url, local))
    return missing


def rels_from_adv_line(line: str) -> list[str]:
    line = line.strip()
    if not line:
        return []
    parts = line.split(",")
    op = parts[0].strip()
    if op == "bg" and len(parts) > 1:
        return [parts[1].strip().replace("\\", "/")]
    if op == "playvoice" and len(parts) > 2:
        return [parts[2].strip().replace("\\", "/")]
    if op == "movie" and len(parts) > 1:
        return [
            p.strip().replace("\\", "/")
            for p in parts[1].split(":")
            if p.strip()
        ]
    return []


def collect_script_resource_rels(
    commands: list[str],
    start_index: int = 0,
) -> list[str]:
    """按台本出现顺序收集资源路径（去重）。"""
    seen: set[str] = set()
    ordered: list[str] = []
    for line in commands[start_index:]:
        for rel in rels_from_adv_line(line):
            if rel and rel not in seen:
                seen.add(rel)
                ordered.append(rel)
    return ordered


def build_download_order(
    json_id: str,
    commands: list[str] | None = None,
    cursor: int = 0,
) -> list[tuple[str, str, str]]:
    """缺失资源下载顺序：剧本文本 → 当前进度后的台本顺序 → json 其余项。"""
    missing = get_missing_resources(json_id)
    if not missing:
        return []
    by_rel = {rel: (rel, url, local) for rel, url, local in missing}
    seen: set[str] = set()
    ordered: list[tuple[str, str, str]] = []

    for rel, url, local in missing:
        if rel.lower().endswith(".txt") and rel not in seen:
            seen.add(rel)
            ordered.append((rel, url, local))

    if commands:
        for rel in collect_script_resource_rels(commands, cursor):
            if rel in by_rel and rel not in seen:
                seen.add(rel)
                ordered.append(by_rel[rel])

    for rel, url, local in missing:
        if rel not in seen:
            ordered.append((rel, url, local))
    return ordered


def _reorder_pending(pending: deque, priority_rels: list[str]) -> None:
    if not pending or not priority_rels:
        return
    items = list(pending)
    by_rel = {rel: item for rel, url, local in items}
    new_items: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for rel in priority_rels:
        rel = rel.replace("\\", "/")
        if rel in by_rel:
            new_items.append(by_rel[rel])
            seen.add(rel)
    for item in items:
        if item[0] not in seen:
            new_items.append(item)
    pending.clear()
    pending.extend(new_items)


def download_scene_resources(
    json_id: str,
    on_progress=None,
    on_item_start=None,
    cancel_check=None,
    ordered_missing: list[tuple[str, str, str]] | None = None,
    priority_callback=None,
) -> tuple[int, int]:
    """下载缺失资源；支持按台本顺序排队，播放中可动态提升优先级。"""
    if ordered_missing is None:
        ordered_missing = get_missing_resources(json_id)
    total = len(ordered_missing)
    if total == 0:
        return 0, 0

    settings_workers = max(1, int(load_settings().get("下载线程数", 8)))
    workers = min(settings_workers, MAX_DOWNLOAD_WORKERS, total)
    done = ok = 0
    pending: deque[tuple[str, str, str]] = deque(ordered_missing)

    def _task(rel: str, url: str, local: str) -> bool:
        if cancel_check and cancel_check():
            return False
        if on_item_start:
            on_item_start(rel)
        return _download_one(url, local)

    pool = ThreadPoolExecutor(max_workers=workers)
    futures: dict = {}
    try:
        while pending or futures:
            if cancel_check and cancel_check():
                print(f"[下载] {json_id}: 用户终止")
                break
            if priority_callback and pending:
                prefs = priority_callback()
                if prefs:
                    _reorder_pending(pending, prefs)
            while len(futures) < workers and pending:
                rel, url, local = pending.popleft()
                fut = pool.submit(_task, rel, url, local)
                futures[fut] = (rel, url, local)
            if not futures:
                break
            done_set, _ = wait(futures.keys(), return_when=FIRST_COMPLETED, timeout=1.0)
            if cancel_check and cancel_check():
                break
            if not done_set:
                continue
            for fut in done_set:
                rel, url, local = futures.pop(fut)
                max_wait = _timeout_for_url(url) + 20
                success = False
                elapsed = 0
                while elapsed < max_wait:
                    if cancel_check and cancel_check():
                        break
                    try:
                        success = bool(fut.result(timeout=0))
                        break
                    except FuturesTimeout:
                        elapsed += 1
                    except Exception as exc:
                        print(f"[下载] 失败 {rel}: {exc}")
                        break
                if cancel_check and cancel_check():
                    break
                done += 1
                if success:
                    ok += 1
                elif os.path.exists(local) and os.path.getsize(local) == 0:
                    _remove_if_exists(local)
                if on_progress:
                    on_progress(done, total, ok)
    finally:
        aborted = bool(cancel_check and cancel_check())
        pool.shutdown(wait=not aborted, cancel_futures=aborted)
    return ok, total
