# -*- coding: utf-8 -*-
"""自购库：按真实文件夹层级浏览；叶子目录（含图 / video / omake）为作品。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from app.core.scene_catalog import LATEST_CATEGORY

BUY_ID_PREFIX = "__buy__:"
BUY_DIR_PREFIX = "__buy_dir__:"
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_DIR_NAMES = ("video", "视频")
INDEX_NAME = ".purchased_index.json"
INDEX_VERSION = 2


def is_purchased_work(jid: str) -> bool:
    return isinstance(jid, str) and jid.startswith(BUY_ID_PREFIX)


def is_purchased_dir(key: str) -> bool:
    return isinstance(key, str) and key.startswith(BUY_DIR_PREFIX)


def purchased_work_key(jid: str) -> str:
    return jid[len(BUY_ID_PREFIX) :]


def purchased_dir_path(key: str) -> str:
    return key[len(BUY_DIR_PREFIX) :].replace("\\", "/").strip("/")


def make_purchased_id(rel_key: str) -> str:
    return f"{BUY_ID_PREFIX}{rel_key.replace(chr(92), '/')}"


def make_purchased_dir_id(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/").strip("/")
    return f"{BUY_DIR_PREFIX}{rel}"


def folder_rel_from_category(cat: str) -> str:
    if is_purchased_dir(cat):
        return purchased_dir_path(cat)
    return (cat or "").replace("\\", "/").strip("/")


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return -1.0


def _to_rel(library_dir: str, path: str | None) -> str | None:
    if not path:
        return None
    try:
        return os.path.relpath(path, library_dir).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def _to_abs(library_dir: str, rel: str | None) -> str | None:
    if not rel:
        return None
    if os.path.isabs(rel):
        return os.path.normpath(rel)
    return os.path.normpath(os.path.join(library_dir, rel.replace("/", os.sep)))


def _list_abs(library_dir: str, rels: list | None) -> list[str]:
    out = []
    for rel in rels or []:
        path = _to_abs(library_dir, rel)
        if path:
            out.append(path)
    return out


def _find_subdir(parent: str, names: tuple[str, ...] | list[str]) -> str | None:
    if not os.path.isdir(parent):
        return None
    want = {n.lower() for n in names}
    try:
        for name in os.listdir(parent):
            if name.lower() in want:
                path = os.path.join(parent, name)
                if os.path.isdir(path):
                    return path
    except OSError:
        return None
    return None


def resolve_content_dir(work_path: str) -> str:
    """处理「作品/作品/video」这种多包一层的目录。"""
    if not os.path.isdir(work_path):
        return work_path
    if _find_subdir(work_path, VIDEO_DIR_NAMES):
        return work_path
    nested = os.path.join(work_path, os.path.basename(work_path))
    if os.path.isdir(nested):
        return resolve_content_dir(nested)
    try:
        for name in os.listdir(work_path):
            sub = os.path.join(work_path, name)
            if os.path.isdir(sub) and _find_subdir(sub, VIDEO_DIR_NAMES):
                return sub
    except OSError:
        pass
    return work_path


def find_cover(content_dir: str) -> str | None:
    for name in ("0.jpg", "0.png", "cover.jpg", "cover.png", "preview.jpg"):
        path = os.path.join(content_dir, name)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
    try:
        names = sorted(
            (
                n
                for n in os.listdir(content_dir)
                if n.lower().endswith(IMAGE_EXTS) and os.path.isfile(os.path.join(content_dir, n))
            ),
            key=_natural_key,
        )
    except OSError:
        return None
    for name in names:
        path = os.path.join(content_dir, name)
        try:
            if os.path.getsize(path) > 0:
                return path
        except OSError:
            continue
    return None


def list_videos(content_dir: str) -> list[str]:
    video_dir = _find_subdir(content_dir, VIDEO_DIR_NAMES)
    root = video_dir if video_dir else content_dir
    if not os.path.isdir(root):
        return []
    try:
        names = [
            n
            for n in os.listdir(root)
            if n.lower().endswith(VIDEO_EXTS) and os.path.isfile(os.path.join(root, n))
        ]
    except OSError:
        return []
    names.sort(key=_natural_key)
    return [os.path.join(root, n) for n in names]


def list_pages(content_dir: str) -> list[str]:
    """主线图片：内容根目录下的图片，不含 video/omake 子目录。"""
    if not os.path.isdir(content_dir):
        return []
    try:
        names = [
            n
            for n in os.listdir(content_dir)
            if n.lower().endswith(IMAGE_EXTS) and os.path.isfile(os.path.join(content_dir, n))
        ]
    except OSError:
        return []
    names.sort(key=_natural_key)
    return [os.path.join(content_dir, n) for n in names]


def list_omake(content_dir: str) -> list[str]:
    """特典图片：omake/ 目录（大小写不敏感）。"""
    omake_dir = _find_subdir(content_dir, ("omake",))
    if not omake_dir:
        return []
    try:
        names = [
            n
            for n in os.listdir(omake_dir)
            if n.lower().endswith(IMAGE_EXTS) and os.path.isfile(os.path.join(omake_dir, n))
        ]
    except OSError:
        return []
    names.sort(key=_natural_key)
    return [os.path.join(omake_dir, n) for n in names]


def looks_like_work(path: str) -> bool:
    """叶子作品：解析后的内容目录含图片 / 视频 / 特典。"""
    if not os.path.isdir(path):
        return False
    content = resolve_content_dir(path)
    if list_pages(content) or list_omake(content) or list_videos(content):
        return True
    return bool(_find_subdir(content, VIDEO_DIR_NAMES) or _find_subdir(content, ("omake",)))


def work_stamp(work_path: str, content_dir: str) -> dict:
    """轻量指纹：只 stat 目录，不遍历成百上千张图。"""
    video_dir = _find_subdir(content_dir, VIDEO_DIR_NAMES)
    omake_dir = _find_subdir(content_dir, ("omake",))
    return {
        "work_mtime": _mtime(work_path),
        "content_mtime": _mtime(content_dir),
        "video_mtime": _mtime(video_dir) if video_dir else -1.0,
        "omake_mtime": _mtime(omake_dir) if omake_dir else -1.0,
    }


def index_path_for(library_dir: str) -> str:
    return os.path.join(library_dir, INDEX_NAME)


def load_index(library_dir: str) -> dict | None:
    path = index_path_for(library_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("version") != INDEX_VERSION:
        return None
    return data


@dataclass
class PurchasedWork:
    rel_key: str
    author: str
    title: str
    work_path: str
    content_dir: str
    cover: str | None = None
    pages: list[str] = field(default_factory=list)
    omake: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.rel_key

    @property
    def jid(self) -> str:
        return make_purchased_id(self.rel_key)


def save_index(library_dir: str, works: dict[str, PurchasedWork]) -> str:
    payload = {
        "version": INDEX_VERSION,
        "library_dir": os.path.normpath(library_dir),
        "works": {},
    }
    for key, work in works.items():
        content = work.content_dir
        payload["works"][key] = {
            "author": work.author,
            "title": work.title,
            "work_path": _to_rel(library_dir, work.work_path),
            "content_dir": _to_rel(library_dir, content),
            "cover": _to_rel(library_dir, work.cover),
            "pages": [_to_rel(library_dir, p) for p in work.pages],
            "omake": [_to_rel(library_dir, p) for p in work.omake],
            "videos": [_to_rel(library_dir, p) for p in work.videos],
            "stamp": work_stamp(work.work_path, content),
            "counts": {
                "pages": len(work.pages),
                "omake": len(work.omake),
                "videos": len(work.videos),
            },
        }
    path = index_path_for(library_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=0)
    os.replace(tmp, path)
    return path


def scan_work(rel_key: str, work_path: str) -> PurchasedWork:
    content = resolve_content_dir(work_path)
    pages = list_pages(content)
    omake = list_omake(content)
    videos = list_videos(content)
    cover = find_cover(content) or (pages[0] if pages else None)
    parts = rel_key.replace("\\", "/").split("/")
    title = parts[-1]
    author = "/".join(parts[:-1]) if len(parts) > 1 else ""
    return PurchasedWork(
        rel_key=rel_key.replace("\\", "/"),
        author=author,
        title=title,
        work_path=work_path,
        content_dir=content,
        cover=cover,
        pages=pages,
        omake=omake,
        videos=videos,
    )


def work_from_cache(library_dir: str, key: str, entry: dict) -> PurchasedWork | None:
    work_path = _to_abs(library_dir, entry.get("work_path"))
    content_dir = _to_abs(library_dir, entry.get("content_dir"))
    if not work_path or not content_dir:
        return None
    if not os.path.isdir(work_path) or not os.path.isdir(content_dir):
        return None
    stamp = entry.get("stamp") or {}
    if stamp != work_stamp(work_path, content_dir):
        return None
    parts = key.replace("\\", "/").split("/")
    title = entry.get("title") or parts[-1]
    author = entry.get("author")
    if author is None:
        author = "/".join(parts[:-1]) if len(parts) > 1 else ""
    return PurchasedWork(
        rel_key=key.replace("\\", "/"),
        author=author,
        title=title,
        work_path=work_path,
        content_dir=content_dir,
        cover=_to_abs(library_dir, entry.get("cover")),
        pages=_list_abs(library_dir, entry.get("pages")),
        omake=_list_abs(library_dir, entry.get("omake")),
        videos=_list_abs(library_dir, entry.get("videos")),
    )


class PurchasedCatalog:
    catalog_kind = "purchased"

    def __init__(self, library_dir: str, auto_load: bool = True):
        self._library_dir = os.path.normpath(library_dir)
        self._works: dict[str, PurchasedWork] = {}
        self._root_folders: list[str] = []
        self._work_ids: list[str] = []
        self._latest_limit = 24
        self._category_icon_cache: dict[str, str | None] = {}
        self._custom_root = ""
        self._last_reload_stats: dict[str, int] = {
            "cached": 0,
            "scanned": 0,
            "total": 0,
            "wrote_index": 0,
        }
        if auto_load:
            self.reload()

    def apply_settings(self):
        from project_paths import load_settings

        settings = load_settings()
        self._latest_limit = max(1, int(settings.get("最新显示数量", 24)))

    @property
    def library_dir(self) -> str:
        return self._library_dir

    @property
    def json_list(self) -> list[str]:
        return list(self._work_ids)

    @property
    def last_reload_stats(self) -> dict[str, int]:
        return dict(self._last_reload_stats)

    def _abs(self, rel: str) -> str:
        rel = (rel or "").replace("\\", "/").strip("/")
        if not rel:
            return self._library_dir
        return os.path.normpath(os.path.join(self._library_dir, rel.replace("/", os.sep)))

    def _has_works_under(self, rel: str) -> bool:
        rel = (rel or "").replace("\\", "/").strip("/")
        if not rel:
            return bool(self._works)
        prefix = rel + "/"
        return any(k == rel or k.startswith(prefix) for k in self._works)

    def reload(self, force_rescan: bool = False) -> dict[str, int]:
        self.apply_settings()
        works: dict[str, PurchasedWork] = {}
        cached = 0
        scanned = 0
        dirty = False

        if not os.path.isdir(self._library_dir):
            self._works = {}
            self._root_folders = []
            self._work_ids = []
            self._last_reload_stats = {
                "cached": 0,
                "scanned": 0,
                "total": 0,
                "wrote_index": 0,
            }
            return self.last_reload_stats

        index = None if force_rescan else load_index(self._library_dir)
        cached_works = (index or {}).get("works") or {}
        if not isinstance(cached_works, dict):
            cached_works = {}

        def walk(rel: str) -> None:
            nonlocal cached, scanned, dirty
            abs_dir = self._abs(rel)
            try:
                names = sorted(os.listdir(abs_dir), key=_natural_key)
            except OSError:
                return
            for name in names:
                if name.startswith("."):
                    continue
                path = os.path.join(abs_dir, name)
                if not os.path.isdir(path):
                    continue
                child_rel = f"{rel}/{name}" if rel else name
                child_rel = child_rel.replace("\\", "/")
                if looks_like_work(path):
                    item = None
                    if not force_rescan and child_rel in cached_works:
                        item = work_from_cache(
                            self._library_dir, child_rel, cached_works[child_rel] or {}
                        )
                    if item is not None:
                        cached += 1
                    else:
                        item = scan_work(child_rel, path)
                        scanned += 1
                        dirty = True
                    works[item.key] = item
                else:
                    walk(child_rel)

        walk("")

        if set(cached_works.keys()) != set(works.keys()):
            dirty = True

        self._works = works
        self._work_ids = [make_purchased_id(k) for k in sorted(works, key=_natural_key)]

        root_folders: list[str] = []
        try:
            for name in sorted(os.listdir(self._library_dir), key=_natural_key):
                if name.startswith("."):
                    continue
                path = os.path.join(self._library_dir, name)
                if not os.path.isdir(path):
                    continue
                if name in works or any(
                    k.startswith(name + "/") for k in works
                ):
                    root_folders.append(name)
        except OSError:
            pass
        self._root_folders = root_folders

        wrote = 0
        if dirty or index is None:
            try:
                save_index(self._library_dir, works)
                wrote = 1
            except OSError:
                wrote = 0

        self._last_reload_stats = {
            "cached": cached,
            "scanned": scanned,
            "total": len(works),
            "wrote_index": wrote,
        }
        return self.last_reload_stats

    def list_folder(self, rel: str) -> list[str]:
        """当前文件夹下一层：子文件夹 + 作品（顺序：文件夹在前，自然排序）。"""
        rel = (rel or "").replace("\\", "/").strip("/")
        abs_dir = self._abs(rel)
        if not os.path.isdir(abs_dir):
            return []
        dirs: list[str] = []
        works: list[str] = []
        try:
            names = sorted(os.listdir(abs_dir), key=_natural_key)
        except OSError:
            return []
        for name in names:
            if name.startswith("."):
                continue
            path = os.path.join(abs_dir, name)
            if not os.path.isdir(path):
                continue
            child_rel = f"{rel}/{name}" if rel else name
            child_rel = child_rel.replace("\\", "/")
            if child_rel in self._works:
                works.append(make_purchased_id(child_rel))
            elif self._has_works_under(child_rel):
                dirs.append(make_purchased_dir_id(child_rel))
        return dirs + works

    def parent_browse_key(self, cat: str) -> str | None:
        """返回上一级浏览键；顶层文件夹返回 None（回主页）。"""
        if cat == LATEST_CATEGORY:
            return None
        rel = folder_rel_from_category(cat)
        if not rel or "/" not in rel:
            return None
        parent = rel.rsplit("/", 1)[0]
        if "/" in parent:
            return make_purchased_dir_id(parent)
        return parent

    def browse_title(self, cat: str) -> str:
        if cat == LATEST_CATEGORY:
            return "最新更新"
        rel = folder_rel_from_category(cat)
        return rel.replace("/", " / ") if rel else "自购"

    def folder_preview(self, rel: str) -> str | None:
        for item in self.list_folder(rel):
            if is_purchased_work(item):
                thumb = self.scene_preview_path(item)
                if thumb:
                    return thumb
            elif is_purchased_dir(item):
                thumb = self.folder_preview(purchased_dir_path(item))
                if thumb:
                    return thumb
        return None

    def get_work(self, jid: str) -> PurchasedWork | None:
        key = purchased_work_key(jid) if is_purchased_work(jid) else jid
        return self._works.get(key.replace("\\", "/"))

    def work_page_paths(self, jid: str) -> list[str]:
        work = self.get_work(jid)
        return list(work.pages) if work else []

    def work_video_paths(self, jid: str) -> list[str]:
        work = self.get_work(jid)
        return list(work.videos) if work else []

    def group_video_paths(self, jid: str) -> list[str]:
        return self.work_video_paths(jid)

    def group_missing_count(self, jid: str) -> int:
        return 0

    def group_photo_path(self, jid: str) -> str | None:
        work = self.get_work(jid)
        return work.cover if work else None

    def categories(self) -> list[str]:
        return [LATEST_CATEGORY] + list(self._root_folders)

    def list_by_category(self, cat: str) -> list[str]:
        if cat == LATEST_CATEGORY:
            return self.recent_work_list()
        if is_purchased_dir(cat) or cat in self._root_folders or self._has_works_under(
            folder_rel_from_category(cat)
        ):
            return self.list_folder(folder_rel_from_category(cat))
        return []

    def recent_work_list(self, limit: int | None = None) -> list[str]:
        limit = self._latest_limit if limit is None else max(1, limit)
        scored: list[tuple[float, str]] = []
        for jid in self._work_ids:
            work = self.get_work(jid)
            if not work:
                continue
            try:
                ts = os.path.getmtime(work.work_path)
            except OSError:
                ts = 0.0
            scored.append((ts, jid))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [jid for _, jid in scored[:limit]]

    def category_display_name(self, cat: str) -> str:
        if cat == LATEST_CATEGORY:
            return cat
        rel = folder_rel_from_category(cat)
        return rel.rsplit("/", 1)[-1] if rel else cat

    def category_icon(self, cat: str) -> str | None:
        if cat in self._category_icon_cache:
            return self._category_icon_cache[cat]
        if cat == LATEST_CATEGORY:
            for jid in self.list_by_category(cat):
                thumb = self.scene_preview_path(jid)
                if thumb:
                    return thumb
            return None
        return self.folder_preview(folder_rel_from_category(cat))

    def category_caption(self, cat: str) -> str:
        if cat == LATEST_CATEGORY:
            return f"{self._latest_limit} 个最近更新"
        items = self.list_by_category(cat)
        n_dirs = sum(1 for i in items if is_purchased_dir(i))
        n_works = sum(1 for i in items if is_purchased_work(i))
        if n_dirs and n_works:
            return f"{n_dirs} 个文件夹 · {n_works} 个作品"
        if n_dirs:
            return f"{n_dirs} 个文件夹"
        return f"{n_works} 个作品"

    def scene_preview_path(self, jid: str) -> str | None:
        if is_purchased_dir(jid):
            return self.folder_preview(purchased_dir_path(jid))
        return self.group_photo_path(jid)

    def scene_list_thumb_paths(self, jid: str, card_cache=None) -> tuple[str | None, str | None]:
        thumb = self.scene_preview_path(jid)
        return thumb, thumb

    def scene_card_face_path(self, jid: str, card_cache=None) -> str | None:
        return self.scene_preview_path(jid)

    def scene_cg_preview_path(self, jid: str) -> str | None:
        return self.scene_preview_path(jid)

    def scene_card_title(self, jid: str, show_date: bool = False) -> str:
        if is_purchased_dir(jid):
            rel = purchased_dir_path(jid)
            return rel.rsplit("/", 1)[-1] if rel else "文件夹"
        work = self.get_work(jid)
        if not work:
            return purchased_work_key(jid).rsplit("/", 1)[-1]
        title = work.title
        return title if len(title) <= 20 else title[:18] + "…"

    def scene_card_subtitle(self, jid: str, show_date: bool = False) -> str:
        if is_purchased_dir(jid):
            items = self.list_folder(purchased_dir_path(jid))
            n_dirs = sum(1 for i in items if is_purchased_dir(i))
            n_works = sum(1 for i in items if is_purchased_work(i))
            if n_dirs and n_works:
                return f"{n_dirs} 文件夹 · {n_works} 作品"
            if n_dirs:
                return f"{n_dirs} 个文件夹"
            return f"{n_works} 个作品"
        work = self.get_work(jid)
        if not work:
            return ""
        if show_date:
            return work.author.replace("/", " / ") if work.author else ""
        return ""

    def scene_label(self, jid: str) -> str:
        if is_purchased_dir(jid):
            return purchased_dir_path(jid).replace("/", " / ")
        work = self.get_work(jid)
        if not work:
            return purchased_work_key(jid).replace("/", " / ")
        if work.author:
            return f"{work.author.replace('/', ' / ')} · {work.title}"
        return work.title

    def scene_subtitle(self, jid: str, show_date: bool = False) -> str:
        return self.scene_card_subtitle(jid, show_date)

    def get_update_time(self, jid: str) -> float:
        work = self.get_work(jid)
        if not work:
            return 0.0
        try:
            return os.path.getmtime(work.work_path)
        except OSError:
            return 0.0

    def category_preview_path(self, jids: list[str]) -> str | None:
        for jid in jids:
            thumb = self.scene_preview_path(jid)
            if thumb:
                return thumb
        return None

    def set_category_icon_cache(self, cache: dict[str, str | None]):
        self._category_icon_cache = cache

    def set_category_name_cache(self, cache: dict[str, str]):
        pass

    def set_category_counts(self, counts: dict[str, int]):
        pass

    def build_category_icon_map(self) -> dict[str, str | None]:
        icons = {}
        for cat in self.categories():
            icons[cat] = self.category_icon(cat)
        self._category_icon_cache = icons
        return icons
