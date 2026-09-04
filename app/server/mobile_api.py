# -*- coding: utf-8 -*-
"""手机端 API：加载 Catalog 并序列化为 JSON。"""
from __future__ import annotations

import os
from typing import Any

from app.core.category_loader import scene_list_badge
from app.core.game_registry import GameInfo, get_game
from app.core.purchased_catalog import is_purchased_dir, is_purchased_work
from app.core.scene_catalog import custom_video_path, is_custom_video, LATEST_CATEGORY
from app.core.startup import GameLoadResult, load_one_game
from app.core.telegram_catalog import is_telegram_group
from app.core.types import ThumbEntry

_GAME_CACHE: dict[str, GameLoadResult] = {}


class _SilentProgress:
    def emit(self, *_args, **_kwargs) -> None:
        pass


class _SilentWorker:
    progress = _SilentProgress()


def _media_url(root: str, abs_path: str | None) -> str | None:
    if not abs_path or not os.path.isfile(abs_path):
        return None
    rel = os.path.relpath(abs_path, root).replace("\\", "/")
    return f"/media/{rel}"


def entry_to_dict(root: str, entry: ThumbEntry, catalog=None) -> dict[str, Any]:
    kind = "item"
    if is_purchased_dir(entry.key):
        kind = "folder"
    elif is_purchased_work(entry.key):
        kind = "purchased"
    elif catalog is not None and getattr(catalog, "is_character_hub", lambda _k: False)(entry.key):
        kind = "folder"
    elif catalog is not None and getattr(catalog, "is_card_hub", lambda _k: False)(entry.key):
        # Character / Summon / Skin / DeepOne 主线等：点进去是卡面列表
        kind = "folder"
    elif catalog is not None and getattr(catalog, "is_section_hub", lambda _k: False)(entry.key):
        # DeepOne 家具等分区：点进去是场景列表
        kind = "folder"
    return {
        "key": entry.key,
        "title": entry.title,
        "subtitle": entry.subtitle,
        "image_url": _media_url(root, entry.image_path),
        "badge": entry.badge,
        "missing_count": entry.missing_count,
        "kind": kind,
    }


def ensure_game_loaded(game_id: str) -> GameLoadResult:
    cached = _GAME_CACHE.get(game_id)
    if cached is not None:
        return cached
    game = get_game(game_id)
    if game is None:
        raise KeyError(f"unknown game: {game_id}")
    result = load_one_game(_SilentWorker(), game, 0.0, 1.0)
    _GAME_CACHE[game_id] = result
    return result


def game_bundle(root: str, game_id: str) -> dict[str, Any]:
    from app.core.adapters import adapter_info

    result = ensure_game_loaded(game_id)
    game = result.game
    info = adapter_info(game.kind)
    return {
        "game_id": game.id,
        "name": game.name,
        "description": game.description,
        "kind": game.kind,
        "adapter": info.to_dict(),
        "local_only": game.local_only,
        "categories": [
            entry_to_dict(root, e, catalog=result.catalog) for e in result.category_entries
        ],
    }


def category_items(root: str, game_id: str, category: str) -> dict[str, Any]:
    result = ensure_game_loaded(game_id)
    catalog = result.catalog
    show_date = category == LATEST_CATEGORY
    entries: list[ThumbEntry] = []

    # DeepOne 主线/外传/联动：先列角色
    if getattr(catalog, "is_character_hub", lambda _k: False)(category):
        for char_id in catalog.section_cards_with_scenes(category):
            thumb = catalog.category_icon(char_id) if hasattr(catalog, "category_icon") else None
            entries.append(
                ThumbEntry(
                    key=char_id,
                    title=catalog.category_display_name(char_id),
                    subtitle=catalog.category_caption(char_id),
                    image_path=thumb,
                    hover_image_path=thumb,
                    badge="角色",
                )
            )
        return {
            "game_id": game_id,
            "category": category,
            "items": [
                {
                    **entry_to_dict(root, e, catalog=catalog),
                    "kind": "folder",
                }
                for e in entries
            ],
        }

    # Minashigo / DeepOne：卡面或皮肤列表
    if getattr(catalog, "is_card_hub", lambda _k: False)(category):
        from app.core.deepone_ids import is_deepone_character_category

        badge = "皮肤" if is_deepone_character_category(category) else "卡面"
        for card_id in catalog.section_cards_with_scenes(category):
            thumb = None
            if hasattr(catalog, "category_icon"):
                thumb = catalog.category_icon(card_id)
            entries.append(
                ThumbEntry(
                    key=card_id,
                    title=catalog.category_display_name(card_id),
                    subtitle=catalog.category_caption(card_id),
                    image_path=thumb,
                    hover_image_path=thumb,
                    badge=badge,
                )
            )
        return {
            "game_id": game_id,
            "category": category,
            "items": [
                {
                    **entry_to_dict(root, e, catalog=catalog),
                    "kind": "folder",
                }
                for e in entries
            ],
        }

    scene_ids = catalog.list_by_category(category)
    card_cache: dict[str, str | None] = {}
    for jid in scene_ids:
        badge, missing = scene_list_badge(jid, catalog)
        if is_purchased_dir(jid) or is_purchased_work(jid) or is_telegram_group(jid):
            thumb = catalog.scene_preview_path(jid)
            entries.append(
                ThumbEntry(
                    key=jid,
                    title=catalog.scene_card_title(jid, show_date=show_date),
                    subtitle=catalog.scene_card_subtitle(jid, show_date=show_date),
                    image_path=thumb,
                    hover_image_path=thumb,
                    badge=badge,
                    missing_count=missing,
                )
            )
            continue
        if is_custom_video(jid):
            thumb = catalog.scene_preview_path(jid)
            entries.append(
                ThumbEntry(
                    key=jid,
                    title=catalog.scene_card_title(jid, show_date=show_date),
                    subtitle=catalog.scene_card_subtitle(jid, show_date=show_date),
                    image_path=thumb,
                    hover_image_path=thumb,
                    badge=badge,
                    missing_count=missing,
                )
            )
            continue
        card_path, hover_path = catalog.scene_list_thumb_paths(jid, card_cache)
        entries.append(
            ThumbEntry(
                key=jid,
                title=catalog.scene_card_title(jid, show_date=show_date),
                subtitle=catalog.scene_card_subtitle(jid, show_date=show_date),
                image_path=card_path,
                hover_image_path=hover_path,
                badge=badge,
                missing_count=missing,
            )
        )
    return {
        "game_id": game_id,
        "category": category,
        "items": [entry_to_dict(root, e, catalog=catalog) for e in entries],
    }


def scene_media(root: str, game_id: str, scene_id: str) -> dict[str, Any]:
    result = ensure_game_loaded(game_id)
    catalog = result.catalog
    title = catalog.scene_card_title(scene_id)
    subtitle = catalog.scene_card_subtitle(scene_id)

    if is_purchased_work(scene_id) and hasattr(catalog, "get_work"):
        work = catalog.get_work(scene_id)
        if work:
            pages = [u for p in work.pages if (u := _media_url(root, p))]
            omake = [u for p in work.omake if (u := _media_url(root, p))]
            videos = []
            for path in work.videos:
                u = _media_url(root, path)
                if u:
                    videos.append({"url": u, "name": os.path.basename(path)})
            has_manga = bool(pages or omake)
            has_video = bool(videos)
            if has_manga and has_video:
                profile = "manga_motion"
            elif has_video:
                profile = "video"
            elif has_manga:
                profile = "manga"
            else:
                profile = "empty"
            return {
                "scene_id": scene_id,
                "title": title,
                "subtitle": subtitle,
                "kind": "purchased",
                "author": getattr(work, "author", "") or "",
                "profile": profile,
                "pages": pages,
                "omake": omake,
                "videos": videos,
                "mode": "video" if profile == "video" else "manga",
            }

    if is_telegram_group(scene_id) and hasattr(catalog, "group_video_paths"):
        videos_raw = catalog.group_video_paths(scene_id)
        videos = [_media_url(root, p) for p in videos_raw if _media_url(root, p)]
        thumb = catalog.scene_preview_path(scene_id)
        images = [_media_url(root, thumb)] if thumb else []
        return {
            "scene_id": scene_id,
            "title": title,
            "subtitle": subtitle,
            "mode": "gallery",
            "images": [u for u in images if u],
            "videos": videos,
        }

    if is_custom_video(scene_id):
        path = custom_video_path(scene_id)
        videos = [_media_url(root, path)] if path else []
        thumb = catalog.scene_preview_path(scene_id)
        images = [_media_url(root, thumb)] if thumb else []
        return {
            "scene_id": scene_id,
            "title": title,
            "subtitle": subtitle,
            "mode": "video",
            "images": [u for u in images if u],
            "videos": [u for u in videos if u],
        }

    try:
        from app.server.adv_beats import compile_adv_beats

        adv = compile_adv_beats(root, scene_id)
        if adv.get("beats"):
            return {
                "scene_id": scene_id,
                "title": title,
                "subtitle": subtitle,
                **adv,
            }
    except FileNotFoundError as exc:
        thumb = catalog.scene_preview_path(scene_id)
        primary, hover_path = catalog.scene_list_thumb_paths(scene_id)
        images = []
        for p in (primary, hover_path, thumb):
            u = _media_url(root, p)
            if u and u not in images:
                images.append(u)
        return {
            "scene_id": scene_id,
            "title": title,
            "subtitle": subtitle,
            "kind": "adv",
            "mode": "empty" if not images else "gallery",
            "images": images,
            "videos": [],
            "beats": [],
            "note": f"台本不可用：{exc}",
        }
    except Exception as exc:
        return {
            "scene_id": scene_id,
            "title": title,
            "subtitle": subtitle,
            "kind": "adv",
            "mode": "empty",
            "images": [],
            "videos": [],
            "beats": [],
            "note": f"ADV 加载失败：{exc}",
        }

    thumb = catalog.scene_preview_path(scene_id)
    primary, hover_path = catalog.scene_list_thumb_paths(scene_id)
    images = []
    for p in (primary, hover_path, thumb):
        u = _media_url(root, p)
        if u and u not in images:
            images.append(u)
    return {
        "scene_id": scene_id,
        "title": title,
        "subtitle": subtitle,
        "kind": "adv",
        "mode": "empty" if not images else "gallery",
        "images": images,
        "videos": [],
        "beats": [],
        "note": "台本为空或尚无 clickwait",
    }
