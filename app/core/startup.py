# -*- coding: utf-8 -*-
"""启动后台任务：按游戏分步扫描、下载预览、预建分类缩略图。"""
import os
from dataclasses import dataclass, field

from PySide6.QtCore import QThread, Signal

from app.core.category_names import category_names_cache_path, resolve_category_name_map
from app.core.game_registry import GameInfo, load_games, quick_scene_count
from app.core.preview_loader import (
    collect_missing_card_ids,
    collect_missing_preview_ids,
    card_face_local,
    download_card_faces,
    download_previews,
    load_card_fail_ids,
)
from app.core.scene_catalog import (
    CUSTOM_CATEGORY,
    CUSTOM_VIDEO_EXTS,
    LATEST_CATEGORY,
    PREVIEW_EXTS,
    SceneCatalog,
)
from app.core.telegram_catalog import TelegramCatalog
from app.core.purchased_catalog import PurchasedCatalog
from app.core.types import ThumbEntry
from project_paths import load_settings, set_active_game_paths


@dataclass
class GameLoadResult:
    game: GameInfo
    catalog: SceneCatalog | TelegramCatalog | PurchasedCatalog
    category_entries: list[ThumbEntry] = field(default_factory=list)
    scene_count: int = 0


@dataclass
class StartupResult:
    games: list[GameInfo] = field(default_factory=list)
    loaded: dict[str, GameLoadResult] = field(default_factory=dict)
    game_entries: list[ThumbEntry] = field(default_factory=list)


def _emit(worker, phase: str, progress: float, detail: str, sub: str = ""):
    worker.progress.emit(phase, progress, detail, sub)
    if sub:
        print(f"[{phase}] {detail} | {sub}")
    else:
        print(f"[{phase}] {detail}")


def activate_game(game: GameInfo) -> None:
    game.ensure_dirs()
    set_active_game_paths(
        game.id,
        json_dir=game.paths.json_dir,
        resource_dir=game.paths.resource_dir,
        episode_dir=game.paths.episode_dir,
        custom_videos_dir=game.paths.custom_videos_dir,
    )


def scan_json_list(json_dir: str, on_step=None) -> list[str]:
    if not os.path.isdir(json_dir):
        return []
    names = [n for n in os.listdir(json_dir) if n.lower().endswith(".json")]
    total = len(names)
    ids = []
    for i, name in enumerate(names):
        ids.append(name[:-5])
        if on_step and (i % 300 == 0 or i == total - 1):
            on_step(i + 1, total)
    ids.sort()
    return ids


def scan_episode_index(episode_dir: str, on_step=None) -> dict[str, str]:
    idx: dict[str, str] = {}
    if not os.path.isdir(episode_dir):
        return idx
    names = os.listdir(episode_dir)
    total = len(names)
    for i, name in enumerate(names):
        low = name.lower()
        for ext in PREVIEW_EXTS:
            if low.endswith(ext):
                path = os.path.join(episode_dir, name)
                try:
                    if os.path.getsize(path) > 0:
                        idx[name[: -len(ext)]] = path
                except OSError:
                    pass
                break
        if on_step and (i % 500 == 0 or i == total - 1):
            on_step(i + 1, total, len(idx))
    return idx


def scan_custom_video_count(custom_root: str) -> int:
    count = 0
    if not os.path.isdir(custom_root):
        return 0
    for root, dirs, files in os.walk(custom_root):
        dirs[:] = [d for d in dirs if d != ".thumbs"]
        for name in files:
            if name.lower().endswith(CUSTOM_VIDEO_EXTS):
                count += 1
    return count


def build_category_meta(catalog: SceneCatalog, json_list: list[str]) -> tuple[dict[str, int], dict[str, str]]:
    counts: dict[str, int] = {}
    first_jid: dict[str, str] = {}
    for jid in json_list:
        cat = catalog._category_of(jid)
        counts[cat] = counts.get(cat, 0) + 1
        if cat not in first_jid:
            first_jid[cat] = jid
    return counts, first_jid


def first_custom_thumb(custom_root: str) -> str | None:
    thumb_root = os.path.join(custom_root, ".thumbs")
    if not os.path.isdir(thumb_root):
        return None
    for name in sorted(os.listdir(thumb_root)):
        if name.lower().endswith(".jpg"):
            return os.path.join(thumb_root, name)
    return None


def build_category_jids(catalog: SceneCatalog, json_list: list[str]) -> dict[str, list[str]]:
    cat_jids: dict[str, list[str]] = {}
    for jid in json_list:
        cat = catalog._category_of(jid)
        cat_jids.setdefault(cat, []).append(jid)
    for cat in cat_jids:
        cat_jids[cat].sort()
    return cat_jids


def build_category_icon_map(
    catalog: SceneCatalog,
    json_list: list[str],
    cat_counts: dict[str, int],
) -> dict[str, str | None]:
    icons: dict[str, str | None] = {}
    for cat, jids in build_category_jids(catalog, json_list).items():
        icons[cat] = catalog.category_preview_path(jids)
    icons[LATEST_CATEGORY] = catalog.category_preview_path(catalog.recent_json_list())
    icons[CUSTOM_CATEGORY] = first_custom_thumb(catalog._custom_root)
    catalog.set_category_counts(cat_counts)
    return icons


def category_caption_fast(
    cat: str, cat_counts: dict[str, int], latest_limit: int, custom_count: int
) -> str:
    if cat == LATEST_CATEGORY:
        return f"{latest_limit} 个最近更新"
    if cat == CUSTOM_CATEGORY:
        return f"{custom_count} 个本地录屏"
    return f"{cat_counts.get(cat, 0)} 个场景"


def load_purchased_game(worker, game: GameInfo, progress_lo: float, progress_hi: float) -> GameLoadResult:
    span = max(0.01, progress_hi - progress_lo)

    def prog(local: float) -> float:
        return progress_lo + span * local

    lib = game.library_dir or ""
    if not lib:
        raise RuntimeError(f"{game.name} 未配置 library_dir")

    _emit(
        worker,
        f"正在扫描 · {game.name}",
        prog(0.15),
        f"读取自购索引 / 增量扫描…",
        lib,
    )
    catalog = PurchasedCatalog(lib, auto_load=True)
    stats = catalog.last_reload_stats
    n = len(catalog.json_list)
    folders = [c for c in catalog.categories() if c != LATEST_CATEGORY]
    detail = (
        f"缓存命中 {stats.get('cached', 0)}，重扫 {stats.get('scanned', 0)}"
        if n
        else "空库"
    )
    _emit(
        worker,
        f"正在索引 · {game.name}",
        prog(0.55),
        f"{game.name}：已索引 {n} 个作品",
        f"{len(folders)} 个顶层文件夹 · {detail}",
    )
    icon_map = catalog.build_category_icon_map()
    entries = []
    for cat in catalog.categories():
        entries.append(
            ThumbEntry(
                key=cat,
                title=catalog.category_display_name(cat),
                subtitle=catalog.category_caption(cat),
                image_path=icon_map.get(cat),
            )
        )
    _emit(
        worker,
        f"加载完成 · {game.name}",
        prog(1.0),
        f"{game.name}：{n} 个作品，{len(folders)} 个顶层文件夹",
        game.id,
    )
    return GameLoadResult(
        game=game, catalog=catalog, category_entries=entries, scene_count=n
    )


def load_telegram_game(worker, game: GameInfo, progress_lo: float, progress_hi: float) -> GameLoadResult:
    span = max(0.01, progress_hi - progress_lo)

    def prog(local: float) -> float:
        return progress_lo + span * local

    if not game.export_dir:
        raise RuntimeError(f"{game.name} 未配置 export_dir")

    _emit(
        worker,
        f"正在扫描 · {game.name}",
        prog(0.1),
        f"解析 Telegram 导出…",
        game.export_dir,
    )

    catalog = TelegramCatalog(
        export_dir=game.export_dir,
        catalog_path=game.catalog_file or "",
        root_tags=list(game.root_tags) or None,
        auto_load=True,
    )
    n = len(catalog.json_list)
    _emit(
        worker,
        f"正在索引 · {game.name}",
        prog(0.5),
        f"{game.name}：已索引 {n} 组录屏",
        f"{len(catalog.categories()) - 1} 个角色标签",
    )

    icon_map = catalog.build_category_icon_map()
    cats = catalog.categories()
    entries = []
    for cat in cats:
        entries.append(
            ThumbEntry(
                key=cat,
                title=catalog.category_display_name(cat),
                subtitle=catalog.category_caption(cat),
                image_path=icon_map.get(cat),
            )
        )

    _emit(
        worker,
        f"加载完成 · {game.name}",
        prog(1.0),
        f"{game.name}：{n} 组录屏，{len(cats)} 个分类",
        game.id,
    )
    return GameLoadResult(
        game=game, catalog=catalog, category_entries=entries, scene_count=n
    )


def load_one_game(worker, game: GameInfo, progress_lo: float, progress_hi: float) -> GameLoadResult:
    if game.kind == "telegram":
        return load_telegram_game(worker, game, progress_lo, progress_hi)
    if game.kind == "purchased":
        return load_purchased_game(worker, game, progress_lo, progress_hi)
    """在已 activate_game 的前提下加载单个游戏。"""
    span = max(0.01, progress_hi - progress_lo)

    def prog(local: float) -> float:
        return progress_lo + span * local

    settings = load_settings()
    threads = int(settings.get("下载线程数", 8))
    paths = game.paths

    catalog = SceneCatalog(auto_load=False)
    catalog.apply_settings()
    catalog.set_category_mode(game.category_mode)

    _emit(
        worker,
        f"正在扫描 · {game.name}",
        prog(0.05),
        f"扫描 {game.name} 场景清单…",
        paths.json_dir,
    )

    def on_json(done, total):
        _emit(
            worker,
            f"正在扫描 · {game.name}",
            prog(0.05 + 0.15 * (done / max(1, total))),
            f"{game.name}：读取场景 {done}/{total}",
            "按文件名建立场景索引",
        )

    json_list = scan_json_list(paths.json_dir, on_json)
    catalog.set_json_list(json_list)
    catalog.load_scene_tags()
    n = len(json_list)
    _emit(
        worker,
        f"正在扫描 · {game.name}",
        prog(0.22),
        f"{game.name}：场景清单完成",
        f"共 {n} 个场景",
    )

    catalog.build_mtime_cache(json_only=True)
    recent = catalog.refresh_recent_cache()
    _emit(
        worker,
        f"正在索引 · {game.name}",
        prog(0.25),
        f"{game.name}：最近更新已就绪",
        f"共 {len(recent)} 个条目",
    )

    video_count = scan_custom_video_count(catalog._custom_root)
    _emit(
        worker,
        f"正在扫描 · {game.name}",
        prog(0.28),
        f"{game.name}：本地录屏扫描完成",
        f"共 {video_count} 个视频",
    )

    def on_ep(done, total, found):
        _emit(
            worker,
            f"正在扫描预览 · {game.name}",
            prog(0.28 + 0.08 * (done / max(1, total))),
            f"{game.name}：检查预览 {done}/{total}",
            f"已缓存 {found} 张",
        )

    episode_index = scan_episode_index(paths.episode_dir, on_ep)
    _emit(
        worker,
        f"正在扫描预览 · {game.name}",
        prog(0.38),
        f"{game.name}：预览缓存扫描完成",
        f"本地已有 {len(episode_index)} 张",
    )

    def on_missing(done, total, _sid):
        _emit(
            worker,
            f"正在检查预览 · {game.name}",
            prog(0.38 + 0.08 * (done / max(1, total))),
            f"{game.name}：检查进度 {done}/{total}",
            "统计需联网补下的预览",
        )

    missing = [] if game.local_only else collect_missing_preview_ids(json_list, on_missing)
    _emit(
        worker,
        f"正在检查预览 · {game.name}",
        prog(0.48),
        f"{game.name}：需下载 {len(missing)} 张预览",
        f"已有 {len(episode_index)} 张，场景 {n} 个",
    )

    if missing:
        _emit(
            worker,
            f"正在下载预览 · {game.name}",
            prog(0.50),
            f"{game.name}：开始下载 {len(missing)} 张",
            f"使用 {threads} 线程",
        )

        def on_dl(done, total, ok, local_prog):
            t = (local_prog - 0.25) / max(0.01, 0.92 - 0.25)
            _emit(
                worker,
                f"正在下载预览 · {game.name}",
                prog(0.50 + 0.22 * max(0.0, min(1.0, t))),
                f"{game.name}：预览 {done}/{total} · 成功 {ok}",
                "联网下载 gallery 小图或首张 CG",
            )

        ok, _ = download_previews(missing, on_dl)
        episode_index = scan_episode_index(paths.episode_dir)
        _emit(
            worker,
            f"正在下载预览 · {game.name}",
            prog(0.74),
            f"{game.name}：预览下载结束",
            f"成功 {ok}/{len(missing)}，本地共 {len(episode_index)} 张",
        )
    else:
        _emit(
            worker,
            f"预览已就绪 · {game.name}",
            prog(0.74),
            f"{game.name}：无需下载预览",
            "全部场景均有本地预览或无需预览",
        )

    def on_card_missing(done, total, _cid):
        _emit(
            worker,
            f"正在检查卡面 · {game.name}",
            prog(0.74 + 0.04 * (done / max(1, total))),
            f"{game.name}：检查卡面 {done}/{total}",
            "统计需联网补下的角色卡面",
        )

    missing_cards = [] if game.local_only else collect_missing_card_ids(json_list, on_card_missing)
    skipped_cards = sum(
        1
        for cid in load_card_fail_ids()
        if not card_face_local(cid)
    )
    sub = "character/{编号}/image/main.png"
    if skipped_cards:
        sub += f" · 已跳过 {skipped_cards} 个无卡面编号"
    _emit(
        worker,
        f"正在检查卡面 · {game.name}",
        prog(0.80),
        f"{game.name}：需下载 {len(missing_cards)} 张卡面",
        sub,
    )

    if missing_cards:
        _emit(
            worker,
            f"正在下载卡面 · {game.name}",
            prog(0.81),
            f"{game.name}：开始下载 {len(missing_cards)} 张卡面",
            f"使用 {threads} 线程",
        )

        def on_card_dl(done, total, ok, local_prog):
            t = (local_prog - 0.25) / max(0.01, 0.92 - 0.25)
            _emit(
                worker,
                f"正在下载卡面 · {game.name}",
                prog(0.81 + 0.09 * max(0.0, min(1.0, t))),
                f"{game.name}：卡面 {done}/{total} · 成功 {ok}",
                "缓存至 episode/cards/",
            )

        card_ok, _ = download_card_faces(missing_cards, on_card_dl)
        _emit(
            worker,
            f"正在下载卡面 · {game.name}",
            prog(0.90),
            f"{game.name}：卡面下载结束",
            f"成功 {card_ok}/{len(missing_cards)}",
        )
    else:
        _emit(
            worker,
            f"卡面已就绪 · {game.name}",
            prog(0.90),
            f"{game.name}：无需下载卡面",
            "本地 episode/cards 已齐全",
        )

    cats = catalog.categories()
    cat_counts, _ = build_category_meta(catalog, json_list)
    icon_map = build_category_icon_map(catalog, json_list, cat_counts)
    catalog.set_category_icon_cache(icon_map)

    cache_path = category_names_cache_path()

    _emit(
        worker,
        f"正在加载角色名 · {game.name}",
        prog(0.91),
        f"{game.name}：读取本地映射…",
        os.path.basename(cache_path),
    )

    def on_names(done, total, found):
        _emit(
            worker,
            f"正在统计角色名 · {game.name}",
            prog(0.91 + 0.03 * (done / max(1, total))),
            f"{game.name}：补扫台本 {done}/{total}",
            f"已识别 {found} 个有角色名的分类",
        )

    if game.category_mode == "minashigo":
        idx = catalog._viewer_index or {}
        name_map = dict(idx.get("category_names") or {})
        if not name_map and os.path.isfile(cache_path):
            from app.core.category_names import load_category_name_cache

            name_map = load_category_name_cache()
        catalog.set_category_name_cache(name_map)
        scanned = 0
        titled = sum(1 for v in name_map.values() if v)
        detail = "已从 MinashigoViewer 菜单索引加载日文角色名"
    else:
        name_map, scanned, titled = resolve_category_name_map(json_list, on_names)
        catalog.set_category_name_cache(name_map)
        if scanned:
            detail = f"新扫描 {scanned} 个分类，已写入 {os.path.basename(cache_path)}"
        else:
            detail = f"已从 {os.path.basename(cache_path)} 加载，无需扫台本"
    _emit(
        worker,
        f"角色名就绪 · {game.name}",
        prog(0.94),
        f"{game.name}：{titled} 个分类有角色名",
        detail,
    )

    entries = []
    for cat in cats:
        title = catalog.category_display_name(cat)
        if game.category_mode == "minashigo":
            subtitle = catalog.category_caption(cat)
        else:
            subtitle = category_caption_fast(
                cat, cat_counts, catalog._latest_limit, video_count
            )
        entries.append(
            ThumbEntry(
                key=cat,
                title=title,
                subtitle=subtitle,
                image_path=icon_map.get(cat),
            )
        )

    _emit(
        worker,
        f"加载完成 · {game.name}",
        prog(1.0),
        f"{game.name}：{n} 个场景，{len(cats)} 个分类",
        game.id,
    )
    return GameLoadResult(
        game=game, catalog=catalog, category_entries=entries, scene_count=n
    )


def build_game_entries(
    games: list[GameInfo], loaded: dict[str, GameLoadResult]
) -> list[ThumbEntry]:
    """游戏层暂不显示预览图，仅标题 + 文字说明；cover 字段留给后续指定预览。"""
    entries: list[ThumbEntry] = []
    for game in games:
        result = loaded.get(game.id)
        if result:
            count = result.scene_count
            unit = (
                "组录屏"
                if game.kind == "telegram"
                else ("个作品" if game.kind == "purchased" else "个场景")
            )
            if game.description:
                subtitle = f"{game.description} · {count} {unit}"
            else:
                subtitle = f"{count} {unit}"
        else:
            count = quick_scene_count(game)
            unit = (
                "组录屏"
                if game.kind == "telegram"
                else ("个作品" if game.kind == "purchased" else "个场景")
            )
            if game.description and count:
                subtitle = f"{game.description} · {count} {unit}"
            elif game.description:
                subtitle = game.description
            elif count:
                subtitle = f"{count} {unit}"
            else:
                subtitle = "尚未导入资源"
        entries.append(
            ThumbEntry(
                key=game.id,
                title=game.name,
                subtitle=subtitle,
                image_path=None,
            )
        )
    return entries


class StartupWorker(QThread):
    """快速启动：只读 games.json，完整加载推迟到用户点选游戏时。"""

    progress = Signal(str, float, str, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            _emit(self, "正在启动", 0.02, "读取游戏列表…", "games.json")
            games = load_games()
            if not games:
                raise RuntimeError("games.json 中没有可用游戏")

            _emit(
                self,
                "正在启动",
                0.35,
                f"发现 {len(games)} 个游戏",
                "、".join(g.name for g in games),
            )

            game_entries = build_game_entries(games, {})
            _emit(
                self,
                "加载完成",
                1.0,
                f"共 {len(games)} 个游戏",
                "点击进入后再加载资源（启动更快）",
            )
            self.finished_ok.emit(
                StartupResult(games=games, loaded={}, game_entries=game_entries)
            )
        except Exception as exc:
            import traceback

            traceback.print_exc()
            self.failed.emit(str(exc))


class GameLoadWorker(QThread):
    """用户选择某个游戏后，再执行扫描 / 预览 / 索引。"""

    progress = Signal(str, float, str, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, game: GameInfo):
        super().__init__()
        self._game = game

    def run(self):
        try:
            activate_game(self._game)
            result = load_one_game(self, self._game, 0.05, 0.95)
            _emit(
                self,
                "加载完成",
                1.0,
                f"{self._game.name} 已就绪",
                self._game.id,
            )
            self.finished_ok.emit(result)
        except Exception as exc:
            import traceback

            traceback.print_exc()
            self.failed.emit(str(exc))
