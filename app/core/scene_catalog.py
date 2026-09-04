# -*- coding: utf-8 -*-
"""场景目录：分类、最新更新、自定义录屏（与 legacy 逻辑对齐，共用根目录资源）。"""
import json
import os
import time

from app.core.preview_loader import (
    card_face_local,
    card_id_from_story,
    deepone_category_of,
    first_local_adv_image,
)
from project_paths import active, load_settings

try:
    from app.core.minashigo_ids import (
        CHARACTER_HUB,
        MAIN_STORY,
        SECTION_HUBS,
        SECTION_LABELS,
        SITUATION_HUB,
        SKIN_HUB,
        SIDE_STORY,
        SUMMON_HUB,
    )
    from app.core.minashigo_viewer_index import (
        category_of_scene,
        is_card_category,
        is_section_hub as is_viewer_section_hub,
        load_viewer_index,
        section_cards,
    )
except ImportError:
    CHARACTER_HUB = "__character__"
    SUMMON_HUB = "__summon__"
    SITUATION_HUB = "__situation__"
    SKIN_HUB = "__skin__"
    MAIN_STORY = "main_story"
    SIDE_STORY = "side_story"
    SECTION_HUBS = ()
    SECTION_LABELS = {}
    category_of_scene = None
    is_card_category = None
    is_viewer_section_hub = None
    load_viewer_index = None
    section_cards = None

LATEST_CATEGORY = "最新更新"
CUSTOM_CATEGORY = "我的录屏"
CUSTOM_ID_PREFIX = "__custom__:"
CUSTOM_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi")
PREVIEW_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def story_id(jid: str) -> str:
    return str(jid).split("_")[0]


def is_custom_video(jid: str) -> bool:
    return isinstance(jid, str) and jid.startswith(CUSTOM_ID_PREFIX)


def custom_video_rel(jid: str) -> str:
    return jid[len(CUSTOM_ID_PREFIX) :]


def custom_video_path(jid_or_rel: str, custom_root: str | None = None) -> str:
    root = custom_root or active.custom_videos_dir
    if is_custom_video(jid_or_rel):
        rel = jid_or_rel[len(CUSTOM_ID_PREFIX) :]
    else:
        rel = jid_or_rel.replace("\\", "/")
    return os.path.normpath(os.path.join(root, rel))


def episode_preview_path(jid: str) -> str | None:
    sid = story_id(jid)
    for ext in PREVIEW_EXTS:
        path = os.path.join(active.episode_dir, sid + ext)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None


def scene_update_time(jid: str) -> float:
    latest = 0.0
    json_path = os.path.join(active.json_dir, jid + ".json")
    if os.path.exists(json_path):
        try:
            latest = max(latest, os.path.getmtime(json_path))
        except OSError:
            pass
    res_dir = os.path.join(active.resource_dir, jid)
    if os.path.isdir(res_dir):
        for root, _, files in os.walk(res_dir):
            for name in files:
                try:
                    latest = max(latest, os.path.getmtime(os.path.join(root, name)))
                except OSError:
                    pass
    return latest


def format_scene_date(ts: float) -> str:
    if ts <= 0:
        return ""
    lt = time.localtime(ts)
    now = time.localtime()
    if lt.tm_year != now.tm_year:
        return time.strftime("%Y-%m-%d", lt)
    return time.strftime("%m-%d", lt)


class SceneCatalog:
    def __init__(self, auto_load: bool = True):
        self._json_list: list[str] = []
        self._custom_root = active.custom_videos_dir
        self._latest_limit = 24
        self._category_icon_cache: dict[str, str | None] = {}
        self._category_name_cache: dict[str, str] = {}
        self._category_counts: dict[str, int] = {}
        self._mtime_cache: dict[str, float] = {}
        self._recent_cache: list[str] | None = None
        self._category_mode = "deepone"
        self._scene_tags: dict[str, dict] = {}
        self._viewer_index: dict | None = None
        if auto_load:
            self.reload()

    def set_category_mode(self, mode: str) -> None:
        self._category_mode = mode or "deepone"
        if self._category_mode == "minashigo" and load_viewer_index:
            self._viewer_index = load_viewer_index(active.json_dir)
        else:
            self._viewer_index = None

    def load_scene_tags(self) -> None:
        path = os.path.join(os.path.dirname(active.json_dir), "scene_tags.json")
        if not os.path.isfile(path):
            self._scene_tags = {}
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            scenes = data.get("scenes") if isinstance(data, dict) else {}
            self._scene_tags = scenes if isinstance(scenes, dict) else {}
        except (OSError, json.JSONDecodeError):
            self._scene_tags = {}

    def _category_of(self, jid: str) -> str:
        if self._category_mode == "minashigo" and category_of_scene:
            return category_of_scene(jid, self._viewer_index)
        return deepone_category_of(jid)

    def _minashigo_category_order(self, cats: set[str]) -> list[str]:
        if self._viewer_index:
            return [c for c in self._viewer_index.get("category_order", []) if c in cats]
        return [c for c in (MAIN_STORY, SIDE_STORY, *SECTION_HUBS) if c in cats]

    def is_section_hub(self, cat: str) -> bool:
        if self._category_mode == "minashigo":
            return bool(is_viewer_section_hub and is_viewer_section_hub(cat))
        if self._category_mode != "minashigo":
            from app.core.deepone_ids import is_deepone_hub

            return is_deepone_hub(cat)
        return False

    def is_card_hub(self, cat: str) -> bool:
        """点进后先显示卡面/皮肤列表。"""
        if self._category_mode == "minashigo":
            return self.is_section_hub(cat) and cat in (CHARACTER_HUB, SUMMON_HUB, SKIN_HUB)
        from app.core.deepone_ids import is_deepone_card_hub, is_deepone_character_category

        return is_deepone_card_hub(cat) or is_deepone_character_category(cat)

    def is_character_hub(self, cat: str) -> bool:
        """DeepOne 主线/外传/联动：点进后先列四位角色。"""
        if self._category_mode == "minashigo":
            return False
        from app.core.deepone_ids import is_deepone_char_hub

        return is_deepone_char_hub(cat)

    def section_cards_with_scenes(self, section: str) -> list[str]:
        if self._category_mode == "minashigo":
            if not section_cards:
                return []
            present = {self._category_of(j) for j in self._json_list}
            return [c for c in section_cards(self._viewer_index, section) if c in present]
        from app.core.deepone_ids import (
            character_id_from_card,
            hub_of_card,
            is_deepone_card_hub,
            is_deepone_char_hub,
            is_deepone_character_category,
            is_deepone_hub,
            sort_card_ids,
            sort_character_ids,
        )

        if is_deepone_char_hub(section):
            chars = {
                character_id_from_card(self._category_of(j))
                for j in self._json_list
                if hub_of_card(self._category_of(j)) == section
            }
            chars.discard("")
            return sort_character_ids(list(chars))
        if is_deepone_character_category(section):
            skins = {
                self._category_of(j)
                for j in self._json_list
                if character_id_from_card(self._category_of(j)) == section
            }
            return sort_card_ids(list(skins))
        if is_deepone_card_hub(section) or is_deepone_hub(section):
            present = {
                self._category_of(j)
                for j in self._json_list
                if hub_of_card(self._category_of(j)) == section
            }
            return sort_card_ids(list(present))
        return []

    def section_scene_count(self, section: str) -> int:
        if self._category_mode == "minashigo":
            if section in (MAIN_STORY, SIDE_STORY, SITUATION_HUB):
                return len(self.list_by_category(section))
            return sum(
                len(self.list_by_category(card))
                for card in self.section_cards_with_scenes(section)
            )
        from app.core.deepone_ids import (
            character_id_from_card,
            hub_of_card,
            is_deepone_character_category,
            is_deepone_hub,
        )

        if is_deepone_character_category(section):
            return sum(
                1
                for j in self._json_list
                if character_id_from_card(self._category_of(j)) == section
            )
        if is_deepone_hub(section):
            return sum(
                1 for j in self._json_list if hub_of_card(self._category_of(j)) == section
            )
        return len(self.list_by_category(section))

    def scene_tags_for(self, jid: str) -> dict:
        return self._scene_tags.get(jid) or {}

    def apply_settings(self):
        settings = load_settings()
        # 多游戏：优先当前游戏路径；仅当设置了绝对自定义目录时才覆盖
        custom_dir = settings.get("自定义视频目录", "")
        if custom_dir and os.path.isabs(str(custom_dir)):
            self._custom_root = str(custom_dir)
        else:
            self._custom_root = active.custom_videos_dir
        self._latest_limit = max(1, int(settings.get("最新显示数量", 24)))

    def set_json_list(self, ids: list[str]):
        self._json_list = ids

    def set_category_icon_cache(self, cache: dict[str, str | None]):
        self._category_icon_cache = cache

    def set_category_name_cache(self, cache: dict[str, str]):
        self._category_name_cache = cache

    def set_category_counts(self, counts: dict[str, int]):
        self._category_counts = counts

    def reload(self):
        self.apply_settings()
        self._json_list = self._scan_json_ids()

    @staticmethod
    def _scan_json_ids() -> list[str]:
        if not os.path.isdir(active.json_dir):
            return []
        ids = []
        for name in os.listdir(active.json_dir):
            if name.lower().endswith(".json"):
                ids.append(name[:-5])
        ids.sort()
        return ids

    @property
    def json_list(self) -> list[str]:
        return self._json_list

    def scan_custom_videos(self) -> list[str]:
        found: list[tuple[float, str]] = []
        if not os.path.isdir(self._custom_root):
            return []
        for root, dirs, files in os.walk(self._custom_root):
            dirs[:] = [d for d in dirs if d != ".thumbs"]
            for name in files:
                if name.lower().endswith(CUSTOM_VIDEO_EXTS):
                    abs_path = os.path.join(root, name)
                    rel = os.path.relpath(abs_path, self._custom_root).replace("\\", "/")
                    try:
                        mtime = os.path.getmtime(abs_path)
                    except OSError:
                        mtime = 0
                    found.append((mtime, rel))
        found.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [CUSTOM_ID_PREFIX + rel for _, rel in found]

    def build_mtime_cache(self, json_only: bool = True) -> None:
        """预计算场景更新时间（默认仅 json mtime，避免遍历 resource）。"""
        cache: dict[str, float] = {}
        for jid in self._json_list:
            latest = 0.0
            json_path = os.path.join(active.json_dir, jid + ".json")
            try:
                latest = os.path.getmtime(json_path)
            except OSError:
                pass
            if not json_only:
                latest = max(latest, self._resource_mtime(jid))
            cache[jid] = latest
        self._mtime_cache = cache

    @staticmethod
    def _resource_mtime(jid: str) -> float:
        latest = 0.0
        res_dir = os.path.join(active.resource_dir, jid)
        if not os.path.isdir(res_dir):
            return latest
        for root, _, files in os.walk(res_dir):
            for name in files:
                try:
                    latest = max(latest, os.path.getmtime(os.path.join(root, name)))
                except OSError:
                    pass
        return latest

    def refresh_recent_cache(self) -> list[str]:
        limit = self._latest_limit
        if not self._mtime_cache:
            self.build_mtime_cache(json_only=True)
        scored = sorted(
            ((self._mtime_cache.get(jid, 0.0), jid) for jid in self._json_list),
            key=lambda x: (x[0], x[1]),
            reverse=True,
        )
        recent = [jid for ts, jid in scored[:limit] if ts > 0]
        self._recent_cache = recent or [jid for _, jid in scored[:limit]]
        return self._recent_cache

    def get_update_time(self, jid: str) -> float:
        if jid in self._mtime_cache:
            return self._mtime_cache[jid]
        ts = scene_update_time(jid)
        self._mtime_cache[jid] = ts
        return ts

    def recent_json_list(self, limit: int | None = None) -> list[str]:
        if limit is None and self._recent_cache is not None:
            return list(self._recent_cache)
        limit = self._latest_limit if limit is None else max(1, limit)
        if not self._mtime_cache:
            self.build_mtime_cache(json_only=True)
        scored = sorted(
            ((self._mtime_cache.get(jid, 0.0), jid) for jid in self._json_list),
            key=lambda x: (x[0], x[1]),
            reverse=True,
        )
        recent = [jid for ts, jid in scored[:limit] if ts > 0]
        return recent or [jid for _, jid in scored[:limit]]

    def categories(self) -> list[str]:
        cats = {self._category_of(j) for j in self._json_list}
        if self._category_mode == "minashigo":
            top: set[str] = set()
            if MAIN_STORY in cats:
                top.add(MAIN_STORY)
            if SIDE_STORY in cats:
                top.add(SIDE_STORY)
            if self.section_cards_with_scenes(CHARACTER_HUB):
                top.add(CHARACTER_HUB)
            if self.section_cards_with_scenes(SUMMON_HUB):
                top.add(SUMMON_HUB)
            if SITUATION_HUB in cats:
                top.add(SITUATION_HUB)
            if self.section_cards_with_scenes(SKIN_HUB):
                top.add(SKIN_HUB)
            ordered = self._minashigo_category_order(top)
            return [LATEST_CATEGORY, CUSTOM_CATEGORY] + ordered
        # DeepOne：按编号规则顶层分区
        from app.core.deepone_ids import HUB_ORDER, hub_of_card

        hubs: set[str] = {hub_of_card(c) for c in cats}
        ordered = [h for h in HUB_ORDER if h in hubs]
        return [LATEST_CATEGORY, CUSTOM_CATEGORY] + ordered

    def list_by_category(self, cat: str) -> list[str]:
        if cat == LATEST_CATEGORY:
            return self.recent_json_list()
        if cat == CUSTOM_CATEGORY:
            return self.scan_custom_videos()
        if self.is_card_hub(cat) or self.is_character_hub(cat):
            return []
        from app.core.deepone_ids import (
            hub_of_card,
            is_deepone_hub,
            sort_scene_ids,
        )

        if self._category_mode != "minashigo" and is_deepone_hub(cat):
            # 家具等：分区下直接列场景
            found = [
                j for j in self._json_list if hub_of_card(self._category_of(j)) == cat
            ]
            return sort_scene_ids(found)
        found = [j for j in self._json_list if self._category_of(j) == cat]
        if self._category_mode != "minashigo":
            return sort_scene_ids(found)
        return found

    def category_display_name(self, cat: str) -> str:
        if cat in (LATEST_CATEGORY, CUSTOM_CATEGORY):
            return cat
        if self._viewer_index:
            names = self._viewer_index.get("category_names") or {}
            if cat in names and names[cat]:
                return names[cat]
        from app.core.deepone_ids import (
            HUB_LABELS,
            card_title,
            character_id_from_card,
            character_title,
            is_deepone_character_category,
            is_deepone_hub,
            skin_title,
        )

        if self._category_mode != "minashigo" and is_deepone_hub(cat):
            return HUB_LABELS.get(cat, cat)
        cached = self._category_name_cache.get(cat) or ""
        if self._category_mode != "minashigo" and is_deepone_character_category(cat):
            return character_title(cat, self._name_for_character(cat))
        if self._category_mode != "minashigo" and cat.isdigit() and len(cat) == 6:
            if character_id_from_card(cat):
                return skin_title(cat)
            return card_title(cat, cached)
        if cached:
            return cached
        if cat == MAIN_STORY:
            return "メインストーリー"
        if cat == SIDE_STORY:
            return "サイドストーリー"
        if cat in SECTION_LABELS:
            return SECTION_LABELS[cat]
        return cat

    def category_caption(self, cat: str) -> str:
        if cat == LATEST_CATEGORY:
            return f"{self._latest_limit} 个最近更新"
        if cat == CUSTOM_CATEGORY:
            return f"{len(self.scan_custom_videos())} 个本地录屏"
        if self.is_character_hub(cat):
            chars = self.section_cards_with_scenes(cat)
            n = self.section_scene_count(cat)
            return f"{len(chars)} 个角色 · {n} 个场景"
        if self.is_card_hub(cat):
            cards = self.section_cards_with_scenes(cat)
            n = self.section_scene_count(cat)
            from app.core.deepone_ids import is_deepone_character_category

            if is_deepone_character_category(cat):
                return f"{len(cards)} 套皮肤 · {n} 个场景"
            return f"{len(cards)} 张卡面 · {n} 个场景"
        if cat == SITUATION_HUB:
            return f"{len(self.list_by_category(cat))} 个场景"
        from app.core.deepone_ids import is_deepone_hub

        if self._category_mode != "minashigo" and is_deepone_hub(cat):
            n = self.section_scene_count(cat)
            return f"{n} 个场景"
        n = self._category_counts.get(cat)
        if n is None:
            n = len(self.list_by_category(cat))
        if self._category_mode != "minashigo" and cat.isdigit() and len(cat) == 6:
            return f"{n} 个场景 · {cat}"
        return f"{n} 个场景"

    def _minashigo_card_id(self, jid: str) -> str:
        """孤儿场景 → 6 位卡面 ID（与 DeepOne 的 story[:6] 不同）。"""
        cat = self._category_of(jid)
        if is_card_category and is_card_category(cat, self._viewer_index):
            return cat
        try:
            from app.core.minashigo_ids import character_card_id_from_scene

            return character_card_id_from_scene(jid) or ""
        except ImportError:
            return ""

    def _name_for_character(self, char_id: str) -> str:
        """从该角色任一套皮肤的台本名缓存取显示名。"""
        for skin in self.section_cards_with_scenes(char_id):
            name = (self._category_name_cache.get(skin) or "").strip()
            if name:
                return name.split("+")[0].strip() or name
        return ""

    def category_icon(self, cat: str) -> str | None:
        if cat in self._category_icon_cache:
            return self._category_icon_cache[cat]
        path = self._resolve_category_icon(cat)
        self._category_icon_cache[cat] = path
        return path

    def _resolve_category_icon(self, cat: str) -> str | None:
        if cat == LATEST_CATEGORY:
            return self.category_preview_path(self.recent_json_list())
        if cat == CUSTOM_CATEGORY:
            thumb_root = os.path.join(self._custom_root, ".thumbs")
            for jid in self.scan_custom_videos():
                rel = custom_video_rel(jid)
                safe = rel.replace("/", "_").replace("\\", "_")
                thumb = os.path.join(thumb_root, safe + "_mid.jpg")
                if os.path.exists(thumb):
                    return thumb
                legacy = os.path.join(thumb_root, safe + ".jpg")
                if os.path.exists(legacy):
                    return legacy
            return None
        # DeepOne 四位角色：封面 = 第一套可用卡面，本地没有则下载
        if self._category_mode != "minashigo":
            from app.core.deepone_ids import is_deepone_character_category, sort_card_ids
            from app.core.preview_loader import fetch_card_face

            if is_deepone_character_category(cat):
                skins = sort_card_ids(self.section_cards_with_scenes(cat))
                for skin in skins:
                    face = card_face_local(skin) or fetch_card_face(
                        skin, quiet=True, skip_if_marked=True
                    )
                    if face:
                        return face
                for skin in skins:
                    for jid in self.list_by_category(skin):
                        cg = self.scene_cg_preview_path(jid)
                        if cg:
                            return cg
                return None
        # 孤儿 / DeepOne：六位卡面分类直接用该编号卡面
        if cat.isdigit() and len(cat) == 6:
            face = card_face_local(cat)
            if face:
                return face
            if (
                self._category_mode == "minashigo"
                and is_card_category
                and is_card_category(cat, self._viewer_index)
            ):
                pass  # 无立绘时继续用场景预览兜底
        # DeepOne 顶层分区：卡面分区取首张卡面，家具取首张 CG
        if self._category_mode != "minashigo":
            from app.core.deepone_ids import (
                is_deepone_card_hub,
                is_deepone_char_hub,
                is_deepone_hub,
            )

            if is_deepone_hub(cat):
                if is_deepone_char_hub(cat):
                    for char_id in self.section_cards_with_scenes(cat):
                        icon = self.category_icon(char_id)
                        if icon:
                            return icon
                    return None
                if is_deepone_card_hub(cat):
                    for cid in self.section_cards_with_scenes(cat):
                        face = card_face_local(cid)
                        if face:
                            return face
                        for jid in self.list_by_category(cid):
                            cg = self.scene_cg_preview_path(jid)
                            if cg:
                                return cg
                    return None
                jids = self.list_by_category(cat)
                if jids:
                    return self.category_preview_path(jids)
                return None
        jids = self.list_by_category(cat)
        if jids and cat not in (LATEST_CATEGORY, CUSTOM_CATEGORY):
            return self.category_preview_path(jids)
        return None

    def scene_list_thumb_paths(
        self,
        jid: str,
        card_cache: dict[str, str | None] | None = None,
    ) -> tuple[str | None, str | None]:
        """场景列表缩略图。

        DeepOne：组内用第一张 CG 做封面；孤儿仍优先卡面/立绘。
        """
        if is_custom_video(jid):
            thumb = self.scene_preview_path(jid)
            return thumb, thumb
        cg_path = self.scene_cg_preview_path(jid)
        if self._category_mode != "minashigo":
            if cg_path:
                return cg_path, cg_path
            card_path = self.scene_card_face_path(jid, card_cache)
            return card_path, card_path
        card_path = self.scene_card_face_path(jid, card_cache)
        primary = card_path or cg_path
        hover = cg_path or card_path
        return primary, hover

    def category_preview_path(self, jids: list[str]) -> str | None:
        """分类入口图：首张卡面，无则第一张 CG。"""
        if self._category_mode == "minashigo":
            seen: set[str] = set()
            for jid in sorted(jids):
                cid = self._minashigo_card_id(jid)
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                face = card_face_local(cid)
                if face:
                    return face
            for jid in sorted(jids):
                cg = self.scene_cg_preview_path(jid)
                if cg:
                    return cg
            return None

        from app.core.tavern_card_png import find_category_card_face

        path = find_category_card_face(jids, fetch=False)
        if path:
            return path
        for jid in sorted(jids):
            cg = self.scene_cg_preview_path(jid)
            if cg:
                return cg
        return None

    def scene_card_face_path(self, jid: str, card_cache: dict[str, str | None] | None = None) -> str | None:
        if is_custom_video(jid):
            return None
        if self._category_mode == "minashigo":
            card_id = self._minashigo_card_id(jid)
        else:
            card_id = card_id_from_story(jid)
        if not card_id:
            return None
        if card_cache is not None:
            if card_id not in card_cache:
                card_cache[card_id] = card_face_local(card_id)
            return card_cache[card_id]
        return card_face_local(card_id)

    def scene_cg_preview_path(self, jid: str) -> str | None:
        if is_custom_video(jid):
            return self.scene_preview_path(jid)
        cg = episode_preview_path(jid)
        if cg:
            return cg
        return first_local_adv_image(jid)

    def scene_preview_path(self, jid: str) -> str | None:
        if is_custom_video(jid):
            rel = custom_video_rel(jid)
            safe = rel.replace("/", "_").replace("\\", "_")
            thumb = os.path.join(self._custom_root, ".thumbs", safe + "_mid.jpg")
            if os.path.exists(thumb):
                return thumb
            legacy = os.path.join(self._custom_root, ".thumbs", safe + ".jpg")
            if os.path.exists(legacy):
                return legacy
            return None
        return episode_preview_path(jid)

    def scene_card_title(self, jid: str, show_date: bool = False) -> str:
        if is_custom_video(jid):
            name = os.path.splitext(os.path.basename(custom_video_rel(jid)))[0]
            if len(name) > 14:
                return name[:12] + "…"
            return name
        tags = self.scene_tags_for(jid)
        if tags:
            char = tags.get("character_ja") or tags.get("character_id") or ""
            typ = tags.get("type_zh") or tags.get("type_ja") or ""
            title = f"{char} · {typ}".strip(" ·")
            if title:
                return title if len(title) <= 18 else title[:16] + "…"
        sid = story_id(jid)
        return sid[-6:] if len(sid) >= 6 else sid

    def scene_card_subtitle(self, jid: str, show_date: bool = False) -> str:
        if is_custom_video(jid):
            return self.scene_subtitle(jid)
        tags = self.scene_tags_for(jid)
        if tags:
            labels = tags.get("labels_ja") or []
            if labels:
                sub = " / ".join(str(x) for x in labels[:2])
                return sub if len(sub) <= 24 else sub[:22] + "…"
        if show_date:
            ts = self.get_update_time(jid)
            if ts > 0 and (time.time() - ts) < 7 * 86400:
                return "NEW"
            return format_scene_date(ts)
        return ""

    def scene_label(self, jid: str) -> str:
        if is_custom_video(jid):
            return custom_video_rel(jid)
        return jid

    def scene_subtitle(self, jid: str, show_date: bool = False) -> str:
        if is_custom_video(jid):
            path = custom_video_path(jid, self._custom_root)
            try:
                return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
            except OSError:
                return ""
        if show_date:
            return format_scene_date(self.get_update_time(jid))
        return ""
