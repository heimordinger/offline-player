# -*- coding: utf-8 -*-
"""后台加载分类场景列表，避免点击大分类时卡死 UI。"""
import json

from PySide6.QtCore import QThread, Signal

from app.core.purchased_catalog import is_purchased_dir, is_purchased_work
from app.core.resources import count_missing_resources, scene_has_mp4
from app.core.scene_catalog import LATEST_CATEGORY, SceneCatalog, is_custom_video
from app.core.telegram_catalog import is_telegram_group
from app.core.types import ThumbEntry


def scene_list_badge(jid: str, catalog=None) -> tuple[str, int]:
    """二级场景卡片标签：动态 CG、未下载等。"""
    parts: list[str] = []
    missing = 0
    if catalog is not None and is_purchased_dir(jid):
        return "文件夹", 0
    if catalog is not None and is_purchased_work(jid):
        work = catalog.get_work(jid) if hasattr(catalog, "get_work") else None
        if work:
            if work.pages:
                parts.append(f"{len(work.pages)}页")
            if getattr(work, "omake", None):
                parts.append(f"特典{len(work.omake)}")
            if work.videos:
                parts.append("动态")
        return " · ".join(parts), 0
    if catalog is not None and is_telegram_group(jid):
        videos = catalog.group_video_paths(jid)
        if videos:
            parts.append("动态")
        missing = catalog.group_missing_count(jid)
        if missing > 0:
            parts.append(f"缺{missing}")
        return " · ".join(parts), missing
    if is_custom_video(jid) or scene_has_mp4(jid):
        parts.append("动态")
    if not is_custom_video(jid):
        try:
            missing = count_missing_resources(jid)
            if missing > 0:
                parts.append("未下载")
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    return " · ".join(parts), missing


def scene_download_badge(jid: str) -> tuple[str, int]:
    return scene_list_badge(jid)


class CategoryLoadWorker(QThread):
    finished_ok = Signal(str, list)
    failed = Signal(str, str)

    def __init__(self, catalog: SceneCatalog, cat: str):
        super().__init__()
        self._catalog = catalog
        self._cat = cat

    def run(self):
        try:
            cat = self._cat
            show_date = cat == LATEST_CATEGORY
            scene_ids = self._catalog.list_by_category(cat)
            entries = []
            card_cache: dict[str, str | None] = {}
            for jid in scene_ids:
                badge, missing = scene_list_badge(jid, self._catalog)
                if is_purchased_dir(jid) or is_purchased_work(jid) or is_telegram_group(jid):
                    thumb = self._catalog.scene_preview_path(jid)
                    entries.append(
                        ThumbEntry(
                            key=jid,
                            title=self._catalog.scene_card_title(jid, show_date=show_date),
                            subtitle=self._catalog.scene_card_subtitle(jid, show_date=show_date),
                            image_path=thumb,
                            hover_image_path=thumb,
                            badge=badge,
                            missing_count=missing,
                        )
                    )
                    continue
                if is_custom_video(jid):
                    thumb = self._catalog.scene_preview_path(jid)
                    entries.append(
                        ThumbEntry(
                            key=jid,
                            title=self._catalog.scene_card_title(jid, show_date=show_date),
                            subtitle=self._catalog.scene_card_subtitle(jid, show_date=show_date),
                            image_path=thumb,
                            hover_image_path=thumb,
                            badge=badge,
                            missing_count=missing,
                        )
                    )
                    continue
                card_path, hover_path = self._catalog.scene_list_thumb_paths(jid, card_cache)
                entries.append(
                    ThumbEntry(
                        key=jid,
                        title=self._catalog.scene_card_title(jid, show_date=show_date),
                        subtitle=self._catalog.scene_card_subtitle(jid, show_date=show_date),
                        image_path=card_path,
                        hover_image_path=hover_path,
                        badge=badge,
                        missing_count=missing,
                    )
                )
            self.finished_ok.emit(cat, entries)
        except Exception as exc:
            self.failed.emit(self._cat, str(exc))
