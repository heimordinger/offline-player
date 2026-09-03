# -*- coding: utf-8 -*-
"""孤儿的工作 · Telegram 录屏目录（按 #标签 / joined 媒体组）。"""
from __future__ import annotations

import os
import time
from typing import Any

from app.core.scene_catalog import LATEST_CATEGORY, format_scene_date
from app.core.telegram_export_parser import (
    build_catalog_from_export,
    catalog_needs_refresh,
    load_catalog,
    resolve_export_dir,
    save_catalog,
)
from project_paths import PROJECT_ROOT

TG_ID_PREFIX = "__tg__:"
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi")


def is_telegram_group(jid: str) -> bool:
    return isinstance(jid, str) and jid.startswith(TG_ID_PREFIX)


def telegram_group_key(jid: str) -> str:
    return jid[len(TG_ID_PREFIX) :]


def make_telegram_id(group_key: str) -> str:
    return TG_ID_PREFIX + group_key


class TelegramCatalog:
    catalog_kind = "telegram"

    def __init__(
        self,
        export_dir: str,
        catalog_path: str,
        root_tags: list[str] | None = None,
        auto_load: bool = True,
    ):
        self._export_dir = export_dir
        self._catalog_path = catalog_path
        self._root_tags = list(root_tags or ["孤儿的工作"])
        self._export_abs = resolve_export_dir(export_dir, PROJECT_ROOT)
        self._data: dict[str, Any] = {}
        self._groups: dict[str, dict] = {}
        self._by_tag: dict[str, list[str]] = {}
        self._group_ids: list[str] = []
        self._latest_limit = 24
        self._category_icon_cache: dict[str, str | None] = {}
        if auto_load:
            self.reload()

    def apply_settings(self):
        from project_paths import load_settings

        settings = load_settings()
        self._latest_limit = max(1, int(settings.get("最新显示数量", 24)))

    @property
    def export_abs(self) -> str:
        return self._export_abs

    @property
    def json_list(self) -> list[str]:
        return list(self._group_ids)

    def reload(self) -> None:
        self.apply_settings()
        if catalog_needs_refresh(self._catalog_path, self._export_dir, PROJECT_ROOT):
            data = build_catalog_from_export(
                self._export_dir, PROJECT_ROOT, self._root_tags
            )
            save_catalog(data, self._catalog_path)
            self._data = data
        elif os.path.isfile(self._catalog_path):
            self._data = load_catalog(self._catalog_path)
        else:
            self._data = build_catalog_from_export(
                self._export_dir, PROJECT_ROOT, self._root_tags
            )
            if self._data.get("groups"):
                save_catalog(self._data, self._catalog_path)

        self._groups = {g["group_key"]: g for g in self._data.get("groups") or []}
        self._by_tag = dict(self._data.get("by_tag") or {})
        self._group_ids = [
            make_telegram_id(k) for k in sorted(self._groups, key=self._sort_key)
        ]

    @staticmethod
    def _sort_key(group_key: str) -> tuple:
        if group_key.startswith("m") and group_key[1:].isdigit():
            return (0, int(group_key[1:]))
        return (1, group_key)

    def get_group(self, jid: str) -> dict | None:
        key = telegram_group_key(jid) if is_telegram_group(jid) else jid
        return self._groups.get(key)

    def abs_media_path(self, rel_path: str) -> str:
        rel = rel_path.replace("\\", "/").lstrip("/")
        return os.path.normpath(os.path.join(self._export_abs, rel))

    def group_photo_path(self, jid: str) -> str | None:
        g = self.get_group(jid)
        if not g:
            return None
        for f in g.get("files") or []:
            if f.get("kind") == "photo" and f.get("exists"):
                return self.abs_media_path(f["path"])
        return None

    def group_video_paths(self, jid: str) -> list[str]:
        g = self.get_group(jid)
        if not g:
            return []
        out = []
        for f in g.get("files") or []:
            if f.get("kind") != "video":
                continue
            if not f.get("exists"):
                continue
            path = self.abs_media_path(f["path"])
            if os.path.isfile(path):
                out.append(path)
        return out

    def group_missing_count(self, jid: str) -> int:
        g = self.get_group(jid)
        if not g:
            return 0
        return sum(1 for f in g.get("files") or [] if not f.get("exists"))

    def categories(self) -> list[str]:
        tags = sorted(self._by_tag.keys())
        return [LATEST_CATEGORY] + tags

    def list_by_category(self, cat: str) -> list[str]:
        if cat == LATEST_CATEGORY:
            return self.recent_group_list()
        keys = self._by_tag.get(cat, [])
        return [make_telegram_id(k) for k in keys]

    def recent_group_list(self, limit: int | None = None) -> list[str]:
        limit = self._latest_limit if limit is None else max(1, limit)
        scored: list[tuple[float, str]] = []
        for gid in self._group_ids:
            g = self.get_group(gid)
            if not g:
                continue
            ts = self._parse_date(g.get("date") or "")
            scored.append((ts, gid))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [gid for _, gid in scored[:limit]]

    @staticmethod
    def _parse_date(date_str: str) -> float:
        if not date_str:
            return 0.0
        for fmt in ("%d.%m.%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return time.mktime(time.strptime(date_str.strip(), fmt))
            except ValueError:
                continue
        return 0.0

    def category_display_name(self, cat: str) -> str:
        return cat

    def category_icon(self, cat: str) -> str | None:
        if cat in self._category_icon_cache:
            return self._category_icon_cache[cat]
        for jid in self.list_by_category(cat):
            photo = self.group_photo_path(jid)
            if photo:
                return photo
            for path in self.group_video_paths(jid):
                thumb = path + "_thumb.jpg"
                if os.path.isfile(thumb):
                    return thumb
        return None

    def category_caption(self, cat: str) -> str:
        if cat == LATEST_CATEGORY:
            return f"{self._latest_limit} 个最近更新"
        return f"{len(self.list_by_category(cat))} 组录屏"

    def scene_preview_path(self, jid: str) -> str | None:
        photo = self.group_photo_path(jid)
        if photo:
            return photo
        for path in self.group_video_paths(jid):
            thumb = path + "_thumb.jpg"
            if os.path.isfile(thumb):
                return thumb
        return None

    def scene_list_thumb_paths(self, jid: str, card_cache=None) -> tuple[str | None, str | None]:
        thumb = self.scene_preview_path(jid)
        return thumb, thumb

    def scene_card_face_path(self, jid: str, card_cache=None) -> str | None:
        return self.group_photo_path(jid)

    def scene_cg_preview_path(self, jid: str) -> str | None:
        return self.scene_preview_path(jid)

    def scene_card_title(self, jid: str, show_date: bool = False) -> str:
        g = self.get_group(jid)
        if not g:
            return telegram_group_key(jid)
        skins = g.get("skin_tags") or []
        if skins:
            title = " · ".join(skins[:2])
            return title if len(title) <= 18 else title[:16] + "…"
        char = g.get("character_tag") or "录屏"
        return char[:18]

    def scene_card_subtitle(self, jid: str, show_date: bool = False) -> str:
        g = self.get_group(jid)
        if not g:
            return ""
        n_vid = sum(1 for f in g.get("files") or [] if f.get("kind") == "video")
        parts = []
        if n_vid:
            parts.append(f"{n_vid} 视频")
        if g.get("date"):
            parts.append(g["date"][:10] if len(g["date"]) > 10 else g["date"])
        return " · ".join(parts)

    def scene_label(self, jid: str) -> str:
        g = self.get_group(jid)
        if not g:
            return telegram_group_key(jid)
        cap = (g.get("caption") or "").strip()
        if cap:
            return cap if len(cap) <= 48 else cap[:46] + "…"
        char = g.get("character_tag") or ""
        skins = " · ".join(g.get("skin_tags") or [])
        return f"{char} {skins}".strip() or g.get("group_key", jid)

    def scene_subtitle(self, jid: str, show_date: bool = False) -> str:
        return self.scene_card_subtitle(jid, show_date)

    def get_update_time(self, jid: str) -> float:
        g = self.get_group(jid)
        if not g:
            return 0.0
        return self._parse_date(g.get("date") or "")

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
