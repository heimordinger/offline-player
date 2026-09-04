# -*- coding: utf-8 -*-
"""预览图下载（与 legacy 逻辑一致，路径走 project_paths）。"""
import hashlib
import json
import os
import socket
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from project_paths import active, load_settings

CDN_GAME = "https://tonofura-r-cdn-resource.deepone-online.com/deep_one/download_game_hd/"
CDN_ADV = "https://tonofura-r-cdn-resource.deepone-online.com/deep_one/download_adv/"
PREVIEW_EXTS = (".png", ".jpg", ".jpeg", ".webp")
USER_AGENT = "DeepOneRE/1.0"
CARD_FAIL_LIST = "_no_main.json"
CARD_MIN_BYTES = 2048
CARD_FETCH_TIMEOUT = 12
_card_fail_lock = threading.Lock()


def story_id(jid: str) -> str:
    return str(jid).split("_")[0]


def get_md5(text: str) -> str:
    return hashlib.md5(("47cd76e43f74bbc2e1baaf194d07e1fa" + text).encode()).hexdigest()


def get_real_path(md5: str) -> str:
    e = i = a = n = ""
    if md5[0] in "cdef":
        e, i, a, n = md5[6:8] + "/", md5[2:4] + "/", md5[4:6] + "/", md5[0:2] + "/"
    elif md5[0] in "89ab":
        e, i, a, n = md5[4:6] + "/", md5[0:2] + "/", md5[6:8] + "/", md5[2:4] + "/"
    elif "4" <= md5[0] <= "7":
        e, i, a = md5[2:4] + "/", md5[6:8] + "/", md5[0:2] + "/"
    elif "0" <= md5[0] <= "3":
        e, i = md5[0:2] + "/", md5[4:6] + "/"
    return e + i + a + n


def get_url(file_name: str) -> str:
    md5 = get_md5(file_name)
    path = get_real_path(md5)
    file_end = "." + file_name.split(".")[-1]
    if ".atlas.txt" in file_name:
        file_end = ".atlas.txt"
    return CDN_GAME + path + md5 + file_end


def card_id_from_story(story_id: str) -> str:
    from app.core.deepone_ids import card_id_from_story as _card_id

    return _card_id(story_id)


def deepone_category_of(story_id: str) -> str:
    from app.core.deepone_ids import deepone_category_of as _cat

    return _cat(story_id)


def cards_dir() -> str:
    return os.path.join(active.episode_dir, "cards")


def _card_fail_path() -> str:
    return os.path.join(cards_dir(), CARD_FAIL_LIST)


def _salvage_card_fail_ids(raw: str) -> set[str]:
    import re

    return {m for m in re.findall(r'"(\d{6})"', raw) if m != "000000"}


def _write_card_fail_ids(fails: set[str]) -> None:
    os.makedirs(cards_dir(), exist_ok=True)
    tmp = _card_fail_path() + ".tmp"
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(sorted(fails), f, ensure_ascii=False)
    os.replace(tmp, _card_fail_path())


def load_card_fail_ids() -> set[str]:
    path = _card_fail_path()
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, encoding="utf8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {str(x) for x in data if str(x).isdigit()}
    except (OSError, json.JSONDecodeError):
        try:
            with open(path, encoding="utf8") as f:
                salvaged = _salvage_card_fail_ids(f.read())
            if salvaged:
                print(
                    f"[卡面] _no_main.json 已损坏，已恢复 {len(salvaged)} 条无卡面记录"
                )
                _write_card_fail_ids(salvaged)
                return salvaged
        except OSError:
            pass
    return set()


def mark_card_face_missing(card_id: str) -> None:
    with _card_fail_lock:
        fails = load_card_fail_ids()
        if card_id in fails:
            return
        fails.add(card_id)
        _write_card_fail_ids(fails)


def mark_card_faces_missing_bulk(card_ids: list[str]) -> None:
    with _card_fail_lock:
        fails = load_card_fail_ids()
        added = 0
        for card_id in card_ids:
            if card_id not in fails:
                fails.add(card_id)
                added += 1
        if added:
            _write_card_fail_ids(fails)


def is_card_face_known_missing(card_id: str) -> bool:
    return card_id in load_card_fail_ids()


def card_face_local(card_id: str) -> str | None:
    path = os.path.join(cards_dir(), card_id + "_main.png")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    return None


def fetch_http_once(url: str, filename: str, timeout: int = CARD_FETCH_TIMEOUT) -> bool:
    """单次 HTTP 拉取，用于卡面等已知可能 404 的资源。"""
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        return True
    if os.path.exists(filename):
        try:
            os.remove(filename)
        except OSError:
            pass
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    tmp = filename + ".part"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < CARD_MIN_BYTES:
            return False
        with open(tmp, "wb") as handle:
            handle.write(data)
        os.replace(tmp, filename)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, socket.timeout) as exc:
        if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 404):
            pass
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def fetch_card_face(
    card_id: str,
    quiet: bool = False,
    skip_if_marked: bool = True,
) -> str | None:
    cached = card_face_local(card_id)
    if cached:
        return cached
    if skip_if_marked and is_card_face_known_missing(card_id):
        return None
    logical = f"character/{card_id}/image/main.png"
    os.makedirs(cards_dir(), exist_ok=True)
    local = os.path.join(cards_dir(), card_id + "_main.png")
    url = get_url(logical)
    if fetch_http_once(url, local):
        return local
    mark_card_face_missing(card_id)
    if not quiet:
        print(f"[卡面] 无资源或下载失败: {card_id}")
    return None


def first_local_adv_image(jid: str) -> str | None:
    res_dir = os.path.join(active.resource_dir, jid)
    if not os.path.isdir(res_dir):
        return None
    candidates: list[str] = []
    for root, _, files in os.walk(res_dir):
        rp = root.replace("\\", "/")
        if "/adv/image/" not in rp:
            continue
        for name in files:
            low = name.lower()
            if low.endswith(PREVIEW_EXTS):
                candidates.append(os.path.join(root, name))
    if not candidates:
        return None
    return sorted(candidates)[0]


def episode_preview_local(story_id: str) -> str | None:
    for ext in PREVIEW_EXTS:
        path = os.path.join(active.episode_dir, story_id + ext)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None


def fetch_file(url: str, filename: str, quiet: bool = False) -> bool:
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        return True
    if os.path.exists(filename):
        try:
            os.remove(filename)
        except OSError:
            pass
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    for attempt in range(3):
        if not quiet and attempt == 0:
            print(f"补下: {filename}")
        if fetch_http_once(url, filename, timeout=45):
            if not quiet:
                print(f"完成: {filename}")
            return True
    if not quiet:
        print(f"下载失败: {filename}")
    return False


def first_cg_url_for_story(story_id: str) -> tuple[str | None, str | None]:
    if not os.path.isdir(active.json_dir):
        return None, None
    names = []
    primary = story_id + ".json"
    if os.path.exists(os.path.join(active.json_dir, primary)):
        names.append(primary)
    for name in sorted(os.listdir(active.json_dir)):
        if name == primary or not name.endswith(".json"):
            continue
        if name.startswith(story_id + "_"):
            names.append(name)
    for name in names:
        try:
            with open(os.path.join(active.json_dir, name), encoding="utf8") as f:
                data = json.load(f)
        except Exception:
            continue
        for r in data.get("resource", []):
            fn = r.get("fileName", "").replace("\\", "/")
            low = fn.lower()
            if "/image/" in low and low.endswith(PREVIEW_EXTS):
                end = fn.split(".")[-1]
                url = CDN_ADV + r["path"] + "/" + r["md5"] + "." + end
                return url, end
    return None, None


def fetch_episode_preview(story_id: str, quiet: bool = False) -> bool:
    if episode_preview_local(story_id):
        return True
    os.makedirs(active.episode_dir, exist_ok=True)
    local_png = os.path.join(active.episode_dir, story_id + ".png")
    episode_name = "gallery/episode/" + story_id + ".png"
    if fetch_file(get_url(episode_name), local_png, quiet=quiet):
        return True
    url, ext = first_cg_url_for_story(story_id)
    if url and ext:
        return fetch_file(
            url, os.path.join(active.episode_dir, story_id + "." + ext), quiet=quiet
        )
    return False


def collect_missing_card_ids(
    json_list: list[str],
    on_step=None,
) -> list[str]:
    """收集缺本地缓存的角色卡面 ID（storyId 前 6 位去重）。"""
    missing: list[str] = []
    seen: set[str] = set()
    total = len(json_list)
    for i, jid in enumerate(json_list):
        card_id = card_id_from_story(story_id(jid))
        if not card_id:
            continue
        if card_id in seen:
            continue
        seen.add(card_id)
        if card_face_local(card_id):
            continue
        if is_card_face_known_missing(card_id):
            continue
        missing.append(card_id)
        if on_step and (i % 200 == 0 or i == total - 1):
            on_step(i + 1, total, card_id)
    return missing


def download_card_faces(
    card_ids: list[str],
    on_progress,
    progress_start: float = 0.25,
    progress_end: float = 0.92,
) -> tuple[int, int]:
    """多线程下载角色卡面 main.png。"""
    total = len(card_ids)
    if total <= 0:
        return 0, 0

    workers = max(1, int(load_settings().get("下载线程数", 8)))
    done = ok = 0
    lock = threading.Lock()
    failed_ids: list[str] = []

    def on_one(success: bool, card_id: str):
        nonlocal done, ok
        with lock:
            done += 1
            if success:
                ok += 1
            else:
                failed_ids.append(card_id)
            cur_done, cur_ok = done, ok
        status = "OK" if success else "FAIL"
        print(f"[卡面 {cur_done}/{total}] {status} {card_id}（成功 {cur_ok}）")
        prog = progress_start + (progress_end - progress_start) * (cur_done / total)
        on_progress(cur_done, total, cur_ok, prog)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_card_face, card_id, True, True): card_id
            for card_id in card_ids
        }
        for fut in as_completed(futures):
            card_id = futures[fut]
            try:
                success = bool(fut.result())
            except Exception:
                success = False
            on_one(success, card_id)
    if failed_ids:
        mark_card_faces_missing_bulk(failed_ids)
    return ok, total


def collect_missing_preview_ids(
    json_list: list[str],
    on_step=None,
) -> list[str]:
    """收集缺预览的 storyId；on_step(done, total, sid) 用于加载界面。"""
    missing = []
    seen = set()
    total = len(json_list)
    for i, jid in enumerate(json_list):
        sid = story_id(jid)
        if sid in seen:
            continue
        seen.add(sid)
        if not episode_preview_local(sid):
            missing.append(sid)
        if on_step and (i % 200 == 0 or i == total - 1):
            on_step(i + 1, total, sid)
    return missing


def download_previews(
    story_ids: list[str],
    on_progress,
    progress_start: float = 0.25,
    progress_end: float = 0.92,
) -> tuple[int, int]:
    """多线程下载预览；on_progress(done, total, ok)。控制台同步输出进度。"""
    total = len(story_ids)
    if total <= 0:
        return 0, 0

    workers = max(1, int(load_settings().get("下载线程数", 8)))
    done = ok = 0
    lock = threading.Lock()

    def on_one(success: bool, sid: str):
        nonlocal done, ok
        with lock:
            done += 1
            if success:
                ok += 1
            cur_done, cur_ok = done, ok
        status = "OK" if success else "FAIL"
        print(f"[预览 {cur_done}/{total}] {status} {sid}（成功 {cur_ok}）")
        prog = progress_start + (progress_end - progress_start) * (cur_done / total)
        on_progress(cur_done, total, cur_ok, prog)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_episode_preview, sid, True): sid for sid in story_ids}
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                success = bool(fut.result())
            except Exception:
                success = False
            on_one(success, sid)
    return ok, total
