# -*- coding: utf-8 -*-
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.core.category_loader import CategoryLoadWorker, scene_list_badge
from app.core.custom_thumb import CustomThumbWorker, collect_missing_custom_thumbs
from app.core.game_registry import GameInfo
from app.core.minashigo_ids import (
    CHARACTER_HUB,
    MAIN_STORY,
    SECTION_HUBS,
    SITUATION_HUB,
    SIDE_STORY,
    SKIN_HUB,
    SUMMON_HUB,
)
from app.core.minashigo_viewer_index import is_card_category
from app.core.deepone_ids import (
    character_id_from_card,
    hub_of_card,
    is_deepone_card_category,
    is_deepone_character_category,
)
from app.core.preview_loader import card_id_from_story, fetch_card_face
from app.core.purchased_catalog import (
    PurchasedCatalog,
    is_purchased_dir,
    is_purchased_work,
)
from app.core.scene_catalog import (
    CUSTOM_CATEGORY,
    LATEST_CATEGORY,
    SceneCatalog,
    is_custom_video,
)
from app.core.startup import (
    GameLoadResult,
    GameLoadWorker,
    StartupResult,
    activate_game,
    build_game_entries,
)
from app.core.types import ThumbEntry
from app.ui.card_face_dialog import show_card_face
from app.ui.paginated_grid import HOVER_CG_DELAY_MS, PaginatedThumbnailGrid
from app.ui.playback_view import PlaybackView
from app.ui.purchased_reader import PurchasedReader
from app.ui.splash_screen import SplashScreen

PAGE_GAMES = 0
PAGE_HOME = 1
PAGE_SCENES = 2
PAGE_PLAY = 3
PAGE_BUY = 4
PAGE_LAN = 5

GRID_COLS = 4
GRID_ROWS = 3
GAME_ICON = QSize(1, 1)
GAME_CELL = QSize(300, 120)
# 图标下方需容纳标题+副标题两行中文；原先 cell 过矮会裁切副标题上沿
CAT_ICON = QSize(240, 118)
CAT_CELL = QSize(256, 196)
SCENE_ICON = QSize(192, 96)
SCENE_CELL = QSize(220, 176)


class MainWindow(QMainWindow):
    def __init__(self, startup: StartupResult):
        super().__init__()
        self._startup = startup
        self._games: list[GameInfo] = list(startup.games)
        self._loaded: dict[str, GameLoadResult] = dict(startup.loaded)
        self._game_entries: list[ThumbEntry] = list(startup.game_entries)
        self._current_game: GameInfo | None = None
        self.catalog: SceneCatalog | None = None
        self._category_entries: list[ThumbEntry] = []
        self._current_category = ""
        self._category_worker: CategoryLoadWorker | None = None
        self._thumb_worker: CustomThumbWorker | None = None
        self._game_load_worker: GameLoadWorker | None = None
        self._load_splash: SplashScreen | None = None
        self._pending_game_id: str = ""
        self._character_browse = False
        self._browse_section = ""
        self._browse_parent = ""
        self._section_list_cache: dict[str, list[ThumbEntry]] = {}
        self._scene_list_cache: dict[str, list[ThumbEntry]] = {}
        self.setWindowTitle("离线播放器")
        from project_paths import load_settings

        settings = load_settings()
        self.resize(int(settings.get("窗口宽度", 1300)), int(settings.get("窗口高度", 960)))
        self._apply_style()
        self._build_ui()
        self._show_games()

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #0c0e16; color: #ece8e0; }
            QLabel#title { font-size: 20px; font-weight: bold; color: #f0e8d8; }
            QLabel#hint { color: #9aa8c0; }
            QPushButton {
                background: #243048; color: #e8e0d0; border: 1px solid #5a6888;
                border-radius: 6px; padding: 6px 16px;
            }
            QPushButton:hover { background: #2e3c58; border-color: #c4a05a; }
            QPushButton:disabled { color: #666; border-color: #333; }
            QListWidget {
                background: #0c0e16; color: #ddd8d0;
                border: none; outline: none;
            }
            QListWidget::item { padding: 4px; }
            QListWidget::item:selected { background: #1e2840; border-radius: 6px; }
            """
        )

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 8)

        self._stack = QStackedWidget()

        # —— 游戏选择 ——
        games = QWidget()
        games_layout = QVBoxLayout(games)
        games_title = QLabel("选择游戏")
        games_title.setObjectName("title")
        games_title.setAlignment(Qt.AlignCenter)
        games_layout.addWidget(games_title)
        self._games_hint = QLabel("后续可在 games.json 中添加更多游戏")
        self._games_hint.setObjectName("hint")
        self._games_hint.setAlignment(Qt.AlignCenter)
        games_layout.addWidget(self._games_hint)
        lan_row = QHBoxLayout()
        lan_row.addStretch(1)
        self._lan_btn = QPushButton("双端 · 局域网")
        self._lan_btn.setToolTip(
            "启动手机端服务；访问密令用于同网鉴权，复制地址可带密令直进"
        )
        self._lan_btn.clicked.connect(self._open_lan_panel)
        lan_row.addWidget(self._lan_btn)
        lan_row.addStretch(1)
        games_layout.addLayout(lan_row)
        self._game_grid = PaginatedThumbnailGrid(
            GRID_COLS, GRID_ROWS, GAME_ICON, GAME_CELL, wrap_pages=True, text_only=True
        )
        self._game_grid.activated.connect(self._open_game)
        games_layout.addWidget(self._game_grid, 1)
        self._stack.addWidget(games)

        # —— 分类首页 ——
        home = QWidget()
        home_layout = QVBoxLayout(home)

        home_bar = QHBoxLayout()
        self._home_back_btn = QPushButton("← 游戏")
        self._home_back_btn.clicked.connect(self._home_back_clicked)
        home_bar.addWidget(self._home_back_btn)
        home_bar.addStretch(1)
        self._home_title = QLabel("选择分类")
        self._home_title.setObjectName("title")
        self._home_title.setAlignment(Qt.AlignCenter)
        home_bar.addWidget(self._home_title, 1)
        home_bar.addStretch(1)
        spacer_h = QLabel("")
        spacer_h.setMinimumWidth(self._home_back_btn.sizeHint().width())
        home_bar.addWidget(spacer_h)
        home_layout.addLayout(home_bar)

        self._category_grid = PaginatedThumbnailGrid(
            GRID_COLS, GRID_ROWS, CAT_ICON, CAT_CELL, wrap_pages=True
        )
        self._category_grid.activated.connect(self._open_category)
        home_layout.addWidget(self._category_grid, 1)
        self._stack.addWidget(home)

        # —— 场景列表 ——
        scenes = QWidget()
        scenes_layout = QVBoxLayout(scenes)

        bar = QHBoxLayout()
        self._back_btn = QPushButton("← 返回")
        self._back_btn.clicked.connect(self._back_from_scenes)
        bar.addWidget(self._back_btn)
        bar.addStretch(1)
        self._scene_title = QLabel("")
        self._scene_title.setObjectName("title")
        self._scene_title.setAlignment(Qt.AlignCenter)
        bar.addWidget(self._scene_title, 1)
        bar.addStretch(1)
        spacer = QLabel("")
        spacer.setMinimumWidth(self._back_btn.sizeHint().width())
        bar.addWidget(spacer)
        scenes_layout.addLayout(bar)

        self._scene_hint = QLabel("")
        self._scene_hint.setObjectName("hint")
        self._scene_hint.setAlignment(Qt.AlignCenter)
        scenes_layout.addWidget(self._scene_hint)

        self._scene_grid = PaginatedThumbnailGrid(
            GRID_COLS,
            GRID_ROWS,
            SCENE_ICON,
            SCENE_CELL,
            wrap_pages=True,
            enable_view_card=True,
            hover_cg_delay_ms=HOVER_CG_DELAY_MS,
        )
        self._scene_grid.activated.connect(self._on_scene_activated)
        self._scene_grid.view_card_requested.connect(self._on_view_card_face)
        scenes_layout.addWidget(self._scene_grid, 1)

        self._detail_label = QLabel("")
        self._detail_label.setObjectName("hint")
        self._detail_label.setAlignment(Qt.AlignCenter)
        self._detail_label.setWordWrap(True)
        scenes_layout.addWidget(self._detail_label)

        self._stack.addWidget(scenes)

        # PlaybackView 需要 catalog；先用第一个已加载游戏占位，进入游戏时再切换
        first = next(iter(self._loaded.values()), None)
        initial_catalog = first.catalog if first else SceneCatalog(auto_load=False)
        self._playback = PlaybackView(initial_catalog)
        self._playback.closed.connect(self._on_playback_closed)
        self._playback.resources_changed.connect(self._on_scene_resources_updated)
        self._stack.addWidget(self._playback)

        self._buy_reader = PurchasedReader()
        self._buy_reader.closed.connect(self._on_buy_reader_closed)
        self._stack.addWidget(self._buy_reader)

        try:
            from app.ui.lan_panel import LanPanel

            self._lan_panel = LanPanel()
            self._lan_panel.back_requested.connect(self._show_games)
            self._stack.addWidget(self._lan_panel)
            self._lan_available = True
        except Exception as exc:
            print(f"[双端] 面板不可用: {exc}")
            self._lan_panel = None
            self._lan_available = False
            # 占位，保持 PAGE_LAN 索引稳定
            self._stack.addWidget(QWidget())

        outer.addWidget(self._stack, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            f"共 {len(self._games)} 个游戏 · 点击进入 · 翻页可循环"
        )

    def _show_games(self):
        self._current_game = None
        self.catalog = None
        self._category_entries = []
        self._current_category = ""
        self._scene_title.setText("")
        self._scene_hint.setText("")
        self._detail_label.setText("")
        self.setWindowTitle("离线播放器")
        page = self._game_grid.page if self._game_grid.page_count > 0 else 0
        self._game_grid.set_entries(self._game_entries, page=page)
        n = len(self._games)
        self._games_hint.setText(
            f"已注册 {n} 个游戏 · 在 games.json 中可继续添加"
            if n
            else "请在 games.json 中添加游戏"
        )
        self._stack.setCurrentIndex(PAGE_GAMES)
        self.statusBar().showMessage(f"共 {n} 个游戏 · 点击进入")
        if hasattr(self, "_lan_btn"):
            self._lan_btn.setEnabled(getattr(self, "_lan_available", False))

    def _open_lan_panel(self):
        if not getattr(self, "_lan_available", False) or self._lan_panel is None:
            QMessageBox.warning(
                self,
                "双端不可用",
                "未找到局域网服务模块（app/server、app/web）。",
            )
            return
        self._stack.setCurrentIndex(PAGE_LAN)
        self.setWindowTitle("离线播放器 · 双端")
        self.statusBar().showMessage("双端 · 局域网服务")

    def closeEvent(self, event):
        panel = getattr(self, "_lan_panel", None)
        if panel is not None and hasattr(panel, "shutdown"):
            try:
                panel.shutdown()
            except Exception:
                pass
        super().closeEvent(event)

    def _open_game(self, game_id: str):
        if self._game_load_worker and self._game_load_worker.isRunning():
            return
        game = next((g for g in self._games if g.id == game_id), None)
        if game is None:
            self.statusBar().showMessage(f"未找到游戏: {game_id}")
            return

        result = self._loaded.get(game_id)
        if result is not None:
            self._enter_game(game, result)
            return

        self._pending_game_id = game_id
        self._game_grid.setEnabled(False)
        self.statusBar().showMessage(f"正在加载 {game.name}…")
        self._load_splash = SplashScreen(self.width(), self.height(), self)
        self._load_splash.set_progress("正在加载", 0.02, f"准备加载 {game.name}…", game.id)
        self._load_splash.show()
        QApplication.processEvents()

        self._game_load_worker = GameLoadWorker(game)
        self._game_load_worker.progress.connect(self._on_game_load_progress)
        self._game_load_worker.finished_ok.connect(self._on_game_loaded)
        self._game_load_worker.failed.connect(self._on_game_load_failed)
        self._game_load_worker.start()

    def _on_game_load_progress(self, phase: str, progress: float, detail: str, sub: str = ""):
        if self._load_splash is not None:
            self._load_splash.set_progress(phase, progress, detail, sub)

    def _on_game_loaded(self, result: GameLoadResult):
        game = result.game
        self._loaded[game.id] = result
        self._game_entries = build_game_entries(self._games, self._loaded)
        self._close_load_splash()
        self._game_grid.setEnabled(True)
        self._enter_game(game, result)

    def _on_game_load_failed(self, message: str):
        game = next((g for g in self._games if g.id == self._pending_game_id), None)
        name = game.name if game else self._pending_game_id
        self._close_load_splash()
        self._game_grid.setEnabled(True)
        self._pending_game_id = ""
        QMessageBox.critical(self, "加载失败", f"{name}\n\n{message}")
        self.statusBar().showMessage(f"{name} 加载失败")

    def _close_load_splash(self):
        if self._load_splash is not None:
            self._load_splash.close_splash()
            self._load_splash = None

    def _enter_game(self, game: GameInfo, result: GameLoadResult):
        activate_game(game)
        self._current_game = game
        self.catalog = result.catalog
        self._category_entries = list(result.category_entries)
        self._section_list_cache.clear()
        self._scene_list_cache.clear()
        self._playback.set_catalog(self.catalog)
        if isinstance(result.catalog, PurchasedCatalog):
            self._buy_reader.set_catalog(result.catalog)
        self.setWindowTitle(f"离线播放器 · {game.name}")
        self._show_home()

    def _home_back_clicked(self):
        if self._character_browse and self._browse_parent:
            self._show_section_cards(self._browse_parent)
            return
        if self._character_browse:
            self._show_home()
        else:
            self._show_games()

    def _show_home(self):
        if self._current_game is None or self.catalog is None:
            self._show_games()
            return
        self._character_browse = False
        self._browse_section = ""
        self._browse_parent = ""
        self._current_category = ""
        self._scene_title.setText("")
        self._scene_hint.setText("")
        self._detail_label.setText("")
        self._home_title.setText(f"{self._current_game.name} · 选择分类")
        self._home_back_btn.setText("← 游戏")
        page = self._category_grid.page if self._category_grid.page_count > 0 else 0
        self._category_grid.set_entries(self._category_entries, page=page)
        self._stack.setCurrentIndex(PAGE_HOME)
        self.statusBar().showMessage(
            f"{self._current_game.name} · 已加载 {len(self.catalog.json_list)} 个场景"
        )

    def _show_section_cards(self, section: str):
        if self.catalog is None or self._current_game is None:
            self._show_home()
            return
        from app.core.deepone_ids import hub_of_card, is_deepone_character_category

        self._character_browse = True
        self._browse_section = section
        self._browse_parent = (
            hub_of_card(section) if is_deepone_character_category(section) else ""
        )
        self._current_category = section
        cached = self._section_list_cache.get(section)
        if cached is not None:
            entries = cached
        else:
            cards = self.catalog.section_cards_with_scenes(section)
            entries = []
            for card_id in cards:
                entries.append(
                    ThumbEntry(
                        key=card_id,
                        title=self.catalog.category_display_name(card_id),
                        subtitle=self.catalog.category_caption(card_id),
                        image_path=self.catalog.category_icon(card_id),
                    )
                )
            self._section_list_cache[section] = entries
        title = self.catalog.category_display_name(section)
        self._home_title.setText(f"{self._current_game.name} · {title}")
        self._home_back_btn.setText("← 角色" if self._browse_parent else "← 分类")
        self._category_grid.set_entries(entries, page=0)
        self._stack.setCurrentIndex(PAGE_HOME)
        self.statusBar().showMessage(
            f"{self._current_game.name} · {title} · {self.catalog.category_caption(section)}"
        )

    def _back_from_scenes(self):
        if (
            self._character_browse
            and self.catalog
            and self._current_category
            and is_card_category(self._current_category, self.catalog._viewer_index)
        ):
            self._show_section_cards(self._browse_section)
            return
        # DeepOne：场景 → 皮肤列表（四位角色）或分区卡面列表
        if (
            self.catalog
            and is_deepone_card_category(self._current_category or "")
            and getattr(self.catalog, "_category_mode", "") != "minashigo"
        ):
            char_id = character_id_from_card(self._current_category)
            if char_id:
                self._show_section_cards(char_id)
                return
            self._show_section_cards(hub_of_card(self._current_category))
            return
        if (
            self._character_browse
            and self.catalog
            and is_deepone_character_category(self._current_category or "")
        ):
            parent = self._browse_parent or hub_of_card(self._current_category)
            if parent:
                self._show_section_cards(parent)
                return
        if (
            isinstance(self.catalog, PurchasedCatalog)
            and self._current_category
            and self._current_category != LATEST_CATEGORY
        ):
            parent = self.catalog.parent_browse_key(self._current_category)
            if parent:
                self._open_category(parent)
                return
        self._show_home()

    def _open_category(self, cat: str):
        if self.catalog is None:
            return
        if self._category_worker and self._category_worker.isRunning():
            return

        if self.catalog.is_character_hub(cat) if hasattr(self.catalog, "is_character_hub") else False:
            self._show_section_cards(cat)
            return
        if self.catalog.is_card_hub(cat) if hasattr(self.catalog, "is_card_hub") else False:
            self._show_section_cards(cat)
            return

        self._current_category = cat

        if cat == LATEST_CATEGORY:
            self._scene_title.setText("最新更新 · 按文件时间排序")
            self._scene_hint.setText("正在加载…")
            if getattr(self.catalog, "catalog_kind", "") == "purchased":
                self._back_btn.setText("← 分类")
        elif cat == CUSTOM_CATEGORY:
            self._scene_title.setText("我的录屏 · 本地视频")
            self._scene_hint.setText(f"目录: {getattr(self.catalog, '_custom_root', '')} · 正在加载…")
        elif getattr(self.catalog, "catalog_kind", "") == "telegram":
            self._scene_title.setText(self.catalog.category_display_name(cat))
            self._scene_hint.setText("Telegram 录屏 · 同组视频将连续播放 · 正在加载…")
        elif getattr(self.catalog, "catalog_kind", "") == "purchased":
            title = (
                self.catalog.browse_title(cat)
                if hasattr(self.catalog, "browse_title")
                else self.catalog.category_display_name(cat)
            )
            self._scene_title.setText(title)
            self._scene_hint.setText("按文件夹层级浏览 · 文件夹进入下一级 · 作品打开阅读器 · 正在加载…")
            if self.catalog.parent_browse_key(cat):
                self._back_btn.setText("← 上级")
            else:
                self._back_btn.setText("← 分类")
        else:
            self._scene_title.setText(self.catalog.category_display_name(cat))
            self._scene_hint.setText("正在加载…")
            self._back_btn.setText("← 返回")

        cached = self._scene_list_cache.get(cat)
        if cached is not None:
            self._stack.setCurrentIndex(PAGE_SCENES)
            self._on_category_loaded(cat, cached)
            return

        self._detail_label.setText("正在列出作品…")
        self._scene_grid.set_entries([], page=0)
        self._scene_grid.setEnabled(False)
        self._stack.setCurrentIndex(PAGE_SCENES)
        self.statusBar().showMessage(f"正在加载分类：{self._scene_title.text()}")
        QApplication.processEvents()

        try:
            self._category_worker = CategoryLoadWorker(self.catalog, cat)
            self._category_worker.finished_ok.connect(self._on_category_loaded)
            self._category_worker.failed.connect(self._on_category_load_failed)
            self._category_worker.start()
        except Exception as exc:
            self._scene_grid.setEnabled(True)
            self._scene_hint.setText(f"加载失败：{exc}")
            self._detail_label.setText(str(exc))
            self.statusBar().showMessage(f"分类加载失败：{exc}")
            return

    def _on_category_loaded(self, cat: str, entries: list):
        if cat != self._current_category or self.catalog is None:
            return
        self._scene_list_cache[cat] = entries
        self._scene_grid.setEnabled(True)
        is_custom = cat == CUSTOM_CATEGORY
        count = len(entries)

        if cat == LATEST_CATEGORY:
            self._scene_hint.setText(f"{count} 个最近更新")
        elif cat == CUSTOM_CATEGORY:
            self._scene_hint.setText(f"目录: {getattr(self.catalog, '_custom_root', '')} · {count} 个视频")
        elif getattr(self.catalog, "catalog_kind", "") == "telegram":
            self._scene_hint.setText(f"{count} 组录屏 · 左键播放 · 同组多视频自动连播")
        elif getattr(self.catalog, "catalog_kind", "") == "purchased":
            n_dirs = sum(1 for e in entries if is_purchased_dir(getattr(e, "key", "")))
            n_works = sum(1 for e in entries if is_purchased_work(getattr(e, "key", "")))
            if n_dirs and n_works:
                self._scene_hint.setText(f"{n_dirs} 个文件夹 · {n_works} 个作品")
            elif n_dirs:
                self._scene_hint.setText(f"{n_dirs} 个文件夹 · 左键进入下一级")
            else:
                self._scene_hint.setText(f"{n_works} 个作品 · 左键打开阅读器（图主线 + 侧栏视频）")
        else:
            self._scene_hint.setText(f"{count} 个场景")

        self._scene_grid.set_entries(entries, page=0)
        kind = getattr(self.catalog, "catalog_kind", "")
        self._detail_label.setText(
            "暂无录屏，请将视频放入该游戏的 custom_videos 文件夹"
            if is_custom and not entries
            else (
                "左键播放 · 同组内多个视频将连续播放"
                if kind == "telegram" and entries
                else (
                    "左键：进文件夹 / 开作品 · 返回可回到上级文件夹"
                    if kind == "purchased" and entries
                    else (
                        "左键播放场景 · 右键观看卡面"
                        if not is_custom and entries and kind not in ("telegram", "purchased")
                        else ("暂无内容" if not entries else "")
                    )
                )
            )
        )
        self.statusBar().showMessage(
            f"{self._current_game.name if self._current_game else ''} · {self._scene_title.text()} · {count} 项"
        )
        if is_custom and entries:
            self._start_custom_thumb_worker()

    def _start_custom_thumb_worker(self):
        if self.catalog is None:
            return
        missing = collect_missing_custom_thumbs(self.catalog)
        if not missing:
            return
        if self._thumb_worker and self._thumb_worker.isRunning():
            return
        self._thumb_worker = CustomThumbWorker(self.catalog, missing)
        self._thumb_worker.thumb_ready.connect(self._on_custom_thumb_ready)
        self._thumb_worker.finished_batch.connect(self._on_custom_thumbs_done)
        self._thumb_worker.start()

    def _on_custom_thumb_ready(self, jid: str, thumb_path: str):
        if self._current_category != CUSTOM_CATEGORY:
            return
        self._scene_grid.update_entry_image(jid, thumb_path)

    def _on_custom_thumbs_done(self, ok: int, total: int):
        if ok and self._current_category == CUSTOM_CATEGORY and self.catalog is not None:
            self._scene_hint.setText(
                f"目录: {self.catalog._custom_root} · "
                f"{len(self.catalog.scan_custom_videos())} 个视频 · 已生成 {ok}/{total} 预览"
            )

    def _on_category_load_failed(self, cat: str, message: str):
        if cat != self._current_category:
            return
        self._scene_grid.setEnabled(True)
        self._scene_hint.setText(f"加载失败: {message}")
        self._detail_label.setText(message)
        self.statusBar().showMessage(f"分类加载失败：{message}")

    def _on_scene_activated(self, jid: str):
        if is_purchased_dir(jid):
            self._open_category(jid)
            return
        if is_purchased_work(jid):
            if isinstance(self.catalog, PurchasedCatalog):
                self._buy_reader.set_catalog(self.catalog)
            self._buy_reader.open_work(jid)
            self._stack.setCurrentIndex(PAGE_BUY)
            self._buy_reader.setFocus()
            return
        self._stack.setCurrentIndex(PAGE_PLAY)
        self._playback.play_scene(jid)

    def _on_view_card_face(self, jid: str):
        if self.catalog is None:
            return
        if is_purchased_dir(jid) or is_purchased_work(jid):
            photo = self.catalog.scene_preview_path(jid)
            if photo:
                show_card_face(self, photo, self.catalog.scene_label(jid))
            else:
                QMessageBox.information(self, "预览", self.catalog.scene_label(jid))
            return
        if getattr(self.catalog, "catalog_kind", "") == "telegram":
            photo = self.catalog.group_photo_path(jid)
            if photo:
                show_card_face(self, photo, self.catalog.scene_label(jid))
            else:
                QMessageBox.information(self, "预览", self.catalog.scene_label(jid))
            return
        if is_custom_video(jid):
            QMessageBox.information(self, "观看卡面", "本地录屏无角色卡面")
            return
        path = self.catalog.scene_card_face_path(jid)
        if not path:
            card_id = card_id_from_story(jid)
            path = fetch_card_face(card_id, quiet=True, skip_if_marked=False)
        if not path:
            QMessageBox.information(
                self,
                "观看卡面",
                f"暂无卡面（{card_id_from_story(jid)}）",
            )
            return
        title = f"{self.catalog.scene_label(jid)} · 角色卡面"
        show_card_face(self, path, title)

    def _on_scene_resources_updated(self, jid: str):
        if self._current_category == CUSTOM_CATEGORY:
            return
        badge, missing = scene_list_badge(jid, self.catalog)
        self._scene_grid.update_entry_badge(jid, badge, missing)

    def _on_playback_closed(self):
        if self._current_category:
            self._stack.setCurrentIndex(PAGE_SCENES)
        elif self._current_game is not None:
            self._show_home()
        else:
            self._show_games()

    def _on_buy_reader_closed(self):
        if self._current_category:
            self._stack.setCurrentIndex(PAGE_SCENES)
        elif self._current_game is not None:
            self._show_home()
        else:
            self._show_games()
