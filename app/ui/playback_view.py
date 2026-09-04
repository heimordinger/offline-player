# -*- coding: utf-8 -*-
"""ADV / 本地录屏播放页。"""
from __future__ import annotations

import os

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap, QShowEvent, QWheelEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.adv_script import load_adv_commands, resource_path, strip_adv_tags
from app.core.script_dialogue import normalize_line_text, normalize_speaker
from app.core.resource_loader import ResourceDownloadWorker
from app.core.resources import (
    ensure_resource,
    get_missing_resources,
    local_resource_path,
    prepare_script_files,
)
from app.core.scene_catalog import custom_video_path, is_custom_video
from app.core.telegram_catalog import is_telegram_group
from app.ui.dialogue_panel import DialoguePanel
from app.ui.video_controls import SEEK_STEP_MS, VideoControlBar

FF_INTERVAL_MS = 140
LONG_PRESS_MS = 350
ADVANCE_GATE_POLL_MS = 200
MOVIE_PREWARM_MAX_FILES = 2
MOVIE_PREWARM_LOOKAHEAD_LINES = 35
MOVIE_PREWARM_GAP_MS = 80
_MOVIE_READY_STATUSES = frozenset(
    {
        QMediaPlayer.MediaStatus.BufferedMedia,
        QMediaPlayer.MediaStatus.LoadedMedia,
    }
)


def collect_movie_rels(commands: list[str]) -> list[str]:
    """从台本提取 movie 指令中的资源路径（保持出现顺序）。"""
    seen: set[str] = set()
    ordered: list[str] = []
    for line in commands:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if parts[0].strip() != "movie" or len(parts) < 2:
            continue
        for rel in [p.strip() for p in parts[1].split(":") if p.strip()]:
            if rel not in seen:
                seen.add(rel)
                ordered.append(rel)
    return ordered


def collect_movie_rels_ahead(
    commands: list[str],
    start_index: int,
    max_files: int = MOVIE_PREWARM_MAX_FILES,
    max_lines: int = MOVIE_PREWARM_LOOKAHEAD_LINES,
) -> list[str]:
    """从当前进度向前扫描，只收集即将用到的少量 movie 资源。"""
    seen: set[str] = set()
    ordered: list[str] = []
    lines_seen = 0
    for line in commands[start_index:]:
        lines_seen += 1
        if lines_seen > max_lines:
            break
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if parts[0].strip() != "movie" or len(parts) < 2:
            continue
        for rel in [p.strip() for p in parts[1].split(":") if p.strip()]:
            if rel not in seen:
                seen.add(rel)
                ordered.append(rel)
                if len(ordered) >= max_files:
                    return ordered
    return ordered


class _MoviePrewarmPool:
    """播放前顺序预热动态 CG，播到时直接复用已缓冲的 QMediaPlayer。"""

    def __init__(self, stage: "_StageWidget"):
        self._stage = stage
        self._ready: dict[str, _MovieSlot] = {}
        self._queue: list[tuple[str, str]] = []
        self._warming: _MovieSlot | None = None
        self._warming_path = ""
        self._json_id = ""
        self._pending_rels: set[str] = set()
        self._ready_listener = None

    def set_ready_listener(self, listener):
        self._ready_listener = listener

    def clear(self):
        for slot in self._ready.values():
            slot.stop(clear_display=True)
        self._ready.clear()
        self._queue.clear()
        self._pending_rels.clear()
        if self._warming:
            self._warming.stop(clear_display=True)
            self._warming = None
        self._warming_path = ""
        self._json_id = ""

    def start(self, json_id: str, rels: list[str]):
        self.schedule(json_id, rels)

    def schedule(self, json_id: str, rels: list[str]):
        if not rels:
            return
        if json_id != self._json_id:
            self._json_id = json_id
            self._pending_rels.clear()
        for rel in rels:
            rel = rel.replace("\\", "/")
            local = self._local_path(json_id, rel)
            if local:
                self._enqueue_pair(rel, local)
            else:
                self._pending_rels.add(rel)
        if self._queue and not self._warming:
            QTimer.singleShot(MOVIE_PREWARM_GAP_MS, self._warm_next)

    def try_enqueue_rel(self, json_id: str, rel: str):
        """边下边看：单个资源下载完成后尝试加入预热队列。"""
        rel = rel.replace("\\", "/")
        if json_id != self._json_id or rel not in self._pending_rels:
            return
        local = self._local_path(json_id, rel)
        if not local:
            return
        self._pending_rels.discard(rel)
        if self._enqueue_pair(rel, local) and not self._warming:
            QTimer.singleShot(MOVIE_PREWARM_GAP_MS, self._warm_next)

    def flush_pending(self, json_id: str):
        """下载批次结束后，把已落地的待预热资源入队。"""
        if json_id != self._json_id or not self._pending_rels:
            return
        still_pending: set[str] = set()
        for rel in self._pending_rels:
            local = self._local_path(json_id, rel)
            if local:
                self._enqueue_pair(rel, local)
            else:
                still_pending.add(rel)
        self._pending_rels = still_pending
        if self._queue and not self._warming:
            QTimer.singleShot(MOVIE_PREWARM_GAP_MS, self._warm_next)

    def take(self, path: str) -> _MovieSlot | None:
        return self._ready.pop(path, None)

    def movies_ready(self, json_id: str, rels: list[str]) -> bool:
        if not rels:
            return True
        for rel in rels:
            local = self._local_path(json_id, rel)
            if not local or local not in self._ready:
                return False
        return True

    def schedule_rels(self, json_id: str, rels: list[str]):
        self.schedule(json_id, rels)

    def _enqueue_pair(self, rel: str, path: str) -> bool:
        if path in self._ready:
            return False
        if self._warming_path == path:
            return False
        if any(path == item[1] for item in self._queue):
            return False
        self._queue.append((rel, path))
        return True

    def _local_path(self, json_id: str, rel: str) -> str | None:
        return local_resource_path(json_id, rel)

    def _warm_next(self):
        if not self._queue:
            self._warming = None
            self._warming_path = ""
            return
        rel, path = self._queue.pop(0)
        if path in self._ready:
            QTimer.singleShot(0, self._warm_next)
            return
        slot = _MovieSlot(self._stage, show_video=False)
        slot.label.hide()
        self._warming = slot
        self._warming_path = path

        def on_status(status):
            if status not in _MOVIE_READY_STATUSES:
                return
            try:
                slot.player.mediaStatusChanged.disconnect(on_status)
            except TypeError:
                pass
            slot.player.pause()
            slot.player.setPosition(0)
            self._ready[path] = slot
            self._warming = None
            self._warming_path = ""
            print(f"[预热] 动态CG就绪: {os.path.basename(path)}")
            if self._ready_listener:
                QTimer.singleShot(0, self._ready_listener)
            QTimer.singleShot(MOVIE_PREWARM_GAP_MS, self._warm_next)

        QTimer.singleShot(0, lambda: self._begin_warm(slot, path, on_status))

    def _begin_warm(self, slot: _MovieSlot, path: str, on_status):
        slot.player.mediaStatusChanged.connect(on_status)
        slot.player.setSource(QUrl.fromLocalFile(path))
        slot.player.pause()


class _MovieSlot:
    """用 QVideoSink 渲染到 QLabel，避免 QVideoWidget 原生窗口盖住对话框。"""

    def __init__(self, parent: QWidget, show_video: bool = False):
        self._parent = parent
        self._show_video = show_video
        self._play_generation = 0
        self.label = QLabel(parent)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background: transparent;")
        self.label.hide()
        self.player = QMediaPlayer(parent)
        self.audio = QAudioOutput(parent)
        self.player.setAudioOutput(self.audio)
        self.sink = QVideoSink(parent)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._on_frame)

    def _on_frame(self, frame: QVideoFrame):
        if not self._show_video:
            return
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        rect = self._parent.rect()
        if rect.width() < 8 or rect.height() < 8:
            return
        pix = QPixmap.fromImage(image)
        scaled = pix.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(scaled)
        self.label.resize(scaled.size())
        self.label.move((rect.width() - scaled.width()) // 2, (rect.height() - scaled.height()) // 2)
        if not self.label.isVisible():
            self.label.show()

    def invalidate_play(self) -> int:
        """作废进行中的加载/播放（快进连点时避免旧回调误触发）。"""
        self._play_generation += 1
        self.disconnect_player_handlers()
        self.player.stop()
        return self._play_generation

    def disconnect_player_handlers(self):
        try:
            self.player.mediaStatusChanged.disconnect()
        except TypeError:
            pass
        try:
            self.player.playbackStateChanged.disconnect()
        except TypeError:
            pass

    def play_when_ready(self, generation: int, loops: QMediaPlayer.Loops):
        if generation != self._play_generation:
            return

        def begin():
            if generation != self._play_generation:
                return
            self.player.setLoops(loops)
            self.player.setPosition(0)
            self.player.play()

        if self.player.mediaStatus() in _MOVIE_READY_STATUSES:
            begin()
            return

        def on_status(status):
            if status not in _MOVIE_READY_STATUSES:
                return
            if generation != self._play_generation:
                try:
                    self.player.mediaStatusChanged.disconnect(on_status)
                except TypeError:
                    pass
                return
            try:
                self.player.mediaStatusChanged.disconnect(on_status)
            except TypeError:
                pass
            begin()

        self.player.mediaStatusChanged.connect(on_status)

    def stop(self, clear_display: bool = True):
        self.player.stop()
        if clear_display:
            self._clear_display()

    def _clear_display(self):
        self.label.clear()
        self.label.hide()

    def layout(self, rect):
        self.label.setGeometry(rect)

    def absorb_slot(self, donor: _MovieSlot):
        """接管已预热槽的播放器（用于无缝切换）。"""
        donor.label.hide()
        donor._show_video = False
        self._show_video = True
        if donor.player is not self.player:
            self.player.stop()
            try:
                self.player.setVideoSink(None)
            except Exception:
                pass
        self.player = donor.player
        self.audio = donor.audio
        self.player.setAudioOutput(self.audio)
        self.player.setVideoSink(self.sink)


class _StageWidget(QWidget):
    """立绘全屏 + 底部悬浮对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #06080e;")
        self._cg_label = QLabel(self)
        self._cg_label.setAlignment(Qt.AlignCenter)
        self._cg_label.setStyleSheet("background: #06080e;")
        self._dialogue = DialoguePanel(self)
        self._cg_path = ""
        self._cg_rel = ""
        self._json_id = ""
        self._movie_slots: dict[str, _MovieSlot] = {}
        self._prewarm_pool = _MoviePrewarmPool(self)

    def start_movie_prewarm(self, json_id: str, rels: list[str]):
        self._prewarm_pool.schedule(json_id, rels)

    def schedule_movie_prewarm(self, json_id: str, rels: list[str]):
        self._prewarm_pool.schedule(json_id, rels)

    def movies_prewarm_ready(self, json_id: str, rels: list[str]) -> bool:
        return self._prewarm_pool.movies_ready(json_id, rels)

    def schedule_movie_prewarm_rels(self, json_id: str, rels: list[str]):
        self._prewarm_pool.schedule_rels(json_id, rels)

    def set_prewarm_ready_listener(self, listener):
        self._prewarm_pool.set_ready_listener(listener)

    def try_prewarm_movie_rel(self, json_id: str, rel: str):
        self._prewarm_pool.try_enqueue_rel(json_id, rel)

    def flush_movie_prewarm_pending(self, json_id: str):
        self._prewarm_pool.flush_pending(json_id)

    def clear_movie_prewarm(self):
        self._prewarm_pool.clear()

    def reset_visuals(self):
        """进入播放时重置画面，避免与上一轮或预热残留叠加。"""
        self._cg_path = ""
        self._cg_rel = ""
        for movie in self._movie_slots.values():
            movie.invalidate_play()
            movie._clear_display()
        self._movie_slots.clear()
        self.clear_movie_prewarm()
        self._refresh_cg()

    def _raise_dialogue(self):
        self._dialogue.raise_()

    def set_json_id(self, json_id: str):
        self._json_id = json_id

    def set_cg(self, json_id: str, rel: str):
        self._json_id = json_id
        self._cg_rel = rel
        if rel == "color_0_0_0":
            self._cg_path = resource_path(json_id, rel)
        else:
            ensured = ensure_resource(json_id, rel)
            self._cg_path = ensured or ""
            if not self._cg_path:
                print(f"[播放] 背景图缺失: {json_id}/{rel}")
        self._refresh_cg()

    def _movie_slot(self, slot: str) -> _MovieSlot:
        if slot not in self._movie_slots:
            self._movie_slots[slot] = _MovieSlot(self, show_video=True)
        return self._movie_slots[slot]

    def _layout_movies(self):
        rect = self.rect()
        for slot in self._movie_slots.values():
            slot.layout(rect)

    def _hide_other_movie_slots(self, active_slot: str):
        for name, slot in self._movie_slots.items():
            if name != active_slot:
                slot.invalidate_play()
                slot._clear_display()

    def play_movie(self, json_id: str, rel_paths: list[str], slot: str):
        self._json_id = json_id
        resolved = []
        for rel in rel_paths:
            path = ensure_resource(json_id, rel)
            if path:
                resolved.append(path)
            else:
                print(f"[播放] 立绘视频缺失: {json_id}/{rel}")
        if not resolved:
            return

        self._hide_other_movie_slots(slot)
        movie = self._movie_slot(slot)
        gen = movie.invalidate_play()
        movie._clear_display()
        self._refresh_cg()
        rect = self.rect()
        if rect.width() >= 8 and rect.height() >= 8:
            movie.layout(rect)
            movie.label.lower()
            self._cg_label.lower()
        self._raise_dialogue()

        def stale() -> bool:
            return gen != movie._play_generation

        def start_loop(path: str):
            if stale():
                return
            movie.disconnect_player_handlers()
            movie._clear_display()
            prepared = self._prewarm_pool.take(path)
            if prepared:
                movie.absorb_slot(prepared)
            else:
                movie.player.setSource(QUrl.fromLocalFile(path))
            movie.play_when_ready(gen, QMediaPlayer.Loops.Infinite)
            self._raise_dialogue()

        if len(resolved) == 1:
            start_loop(resolved[0])
            return

        intro_path, loop_path = resolved[0], resolved[1]
        if not os.path.isfile(intro_path):
            start_loop(loop_path)
            return

        intro_done = False

        def switch_to_loop():
            nonlocal intro_done
            if intro_done or stale():
                return
            intro_done = True
            movie.disconnect_player_handlers()
            movie._clear_display()
            self._refresh_cg()
            prepared = self._prewarm_pool.take(loop_path)
            if prepared:
                movie.absorb_slot(prepared)
            else:
                movie.player.setSource(QUrl.fromLocalFile(loop_path))
            movie.play_when_ready(gen, QMediaPlayer.Loops.Infinite)
            self._raise_dialogue()

        def on_intro_ended():
            switch_to_loop()

        def on_status(status):
            if stale() or intro_done:
                return
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                try:
                    movie.player.mediaStatusChanged.disconnect(on_status)
                except TypeError:
                    pass
                on_intro_ended()

        def on_playback_state_changed(state):
            if stale() or intro_done:
                return
            if state != QMediaPlayer.PlaybackState.StoppedState:
                return
            if movie.player.loops() != QMediaPlayer.Loops.Once:
                return
            dur = movie.player.duration()
            pos = movie.player.position()
            if dur > 0 and pos >= dur - 120:
                try:
                    movie.player.playbackStateChanged.disconnect(on_playback_state_changed)
                except TypeError:
                    pass
                try:
                    movie.player.mediaStatusChanged.disconnect(on_status)
                except TypeError:
                    pass
                on_intro_ended()

        movie.disconnect_player_handlers()
        prepared_intro = self._prewarm_pool.take(intro_path)
        if prepared_intro:
            movie.absorb_slot(prepared_intro)
        else:
            movie.player.setSource(QUrl.fromLocalFile(intro_path))
        movie.player.mediaStatusChanged.connect(on_status)
        movie.player.playbackStateChanged.connect(on_playback_state_changed)
        movie.play_when_ready(gen, QMediaPlayer.Loops.Once)
        self._raise_dialogue()

    def stop_movie(self, slot: str | None = None):
        if slot:
            if slot in self._movie_slots:
                self._movie_slots[slot].invalidate_play()
                self._movie_slots[slot]._clear_display()
            self._refresh_cg()
            return
        self.invalidate_all_movies()
        self._refresh_cg()

    def invalidate_all_movies(self):
        for movie in self._movie_slots.values():
            movie.invalidate_play()
            movie._clear_display()

    def _refresh_cg(self):
        r = self.rect()
        if r.width() < 8 or r.height() < 8:
            return
        self._cg_label.setGeometry(r)
        if self._cg_path and os.path.isfile(self._cg_path):
            pix = QPixmap(self._cg_path)
            if not pix.isNull():
                scaled = pix.scaled(r.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._cg_label.setPixmap(scaled)
                self._cg_label.resize(scaled.size())
                self._cg_label.move((r.width() - scaled.width()) // 2, (r.height() - scaled.height()) // 2)
                self._cg_label.show()
                return
        ph = QPixmap(r.size())
        ph.fill(Qt.black)
        self._cg_label.setPixmap(ph)
        self._cg_label.show()

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        QTimer.singleShot(0, self._refresh_cg)
        self._layout_movies()
        self._raise_dialogue()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        r = self.rect()
        self._refresh_cg()
        self._layout_movies()
        margin_x = max(16, int(r.width() * 0.03))
        box_h = max(190, min(280, int(r.height() * 0.30)))
        bottom = max(12, int(r.height() * 0.04))
        self._dialogue.setGeometry(
            margin_x,
            r.height() - box_h - bottom,
            r.width() - margin_x * 2,
            box_h,
        )
        self._raise_dialogue()


class PlaybackView(QWidget):
    closed = Signal()
    resources_changed = Signal(str)

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self._catalog = catalog
        self._json_id = ""
        self._commands: list[str] = []
        self._cmd_index = 0
        self._speaker = ""
        self._waiting = False
        self._current_text = ""
        self._dl_worker: ResourceDownloadWorker | None = None
        self._playback_started = False
        self._dl_done = 0
        self._dl_total = 0
        self._dl_ok = 0
        self._tg_playlist: list[str] = []
        self._tg_play_index = 0
        self._tg_play_title = ""
        self._ff_ctrl = False
        self._ff_mouse = False
        self._mouse_down = False
        self._long_press_fired = False
        self._voice = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._voice.setAudioOutput(self._audio)

        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(self._on_long_press)

        self._ff_timer = QTimer(self)
        self._ff_timer.setInterval(FF_INTERVAL_MS)
        self._ff_timer.timeout.connect(self._on_ff_tick)

        self._gate_timer = QTimer(self)
        self._gate_timer.setInterval(ADVANCE_GATE_POLL_MS)
        self._gate_timer.timeout.connect(self._on_advance_gate_poll)

        self.setFocusPolicy(Qt.StrongFocus)

        self._stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        load_page = QWidget()
        load_layout = QVBoxLayout(load_page)
        self._load_label = QLabel("正在准备资源…")
        self._load_label.setAlignment(Qt.AlignCenter)
        self._load_detail = QLabel("")
        self._load_detail.setAlignment(Qt.AlignCenter)
        self._load_detail.setStyleSheet("color: #9aa8c0;")
        load_layout.addStretch(1)
        load_layout.addWidget(self._load_label)
        load_layout.addWidget(self._load_detail)
        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        self._cancel_btn = QPushButton("立即播放")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel_download)
        self._cancel_btn.setStyleSheet(
            "QPushButton { border-color: #886060; } QPushButton:hover { border-color: #c06060; }"
        )
        cancel_row.addWidget(self._cancel_btn)
        cancel_row.addStretch(1)
        load_layout.addLayout(cancel_row)
        load_layout.addStretch(1)
        self._stack.addWidget(load_page)

        self._adv_page = QWidget()
        adv_layout = QVBoxLayout(self._adv_page)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(8, 6, 8, 0)
        self._back_btn = QPushButton("← 退出")
        self._back_btn.clicked.connect(self._exit)
        self._title_label = QLabel("")
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet("color: #b8c0d0;")
        top.addWidget(self._back_btn)
        top.addWidget(self._title_label, 1)
        top.addWidget(QWidget(), 0)
        adv_layout.addLayout(top)

        self._stage = _StageWidget()
        adv_layout.addWidget(self._stage, 1)
        self._dialogue = self._stage._dialogue
        self._dialogue.alpha_changed.connect(lambda _: None)
        self._stage.installEventFilter(self)
        self._dialogue.installEventFilter(self)
        self._adv_page.installEventFilter(self)

        self._stack.addWidget(self._adv_page)

        self._video_page = QWidget()
        video_layout = QVBoxLayout(self._video_page)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)
        video_top = QHBoxLayout()
        video_top.setContentsMargins(8, 6, 8, 0)
        self._video_back = QPushButton("← 退出")
        self._video_back.clicked.connect(self._exit)
        self._video_title = QLabel("")
        self._video_title.setAlignment(Qt.AlignCenter)
        self._video_title.setStyleSheet("color: #b8c0d0;")
        video_top.addWidget(self._video_back)
        video_top.addWidget(self._video_title, 1)
        video_layout.addLayout(video_top)
        self._video_widget = QVideoWidget()
        self._video_player = QMediaPlayer(self)
        self._video_audio = QAudioOutput(self)
        self._video_player.setAudioOutput(self._video_audio)
        self._video_player.setVideoOutput(self._video_widget)
        video_layout.addWidget(self._video_widget, 1)
        self._video_controls = VideoControlBar(self._video_player, self._video_audio)
        video_layout.addWidget(self._video_controls)
        self._video_player.mediaStatusChanged.connect(self._on_video_media_status)
        self._stack.addWidget(self._video_page)

        self.setStyleSheet(
            """
            QWidget { background: #0c0e16; color: #ece8e0; }
            QPushButton {
                background: rgba(36, 48, 72, 200); color: #e8e0d0;
                border: 1px solid #5a6888; border-radius: 6px; padding: 6px 14px;
            }
            QPushButton:hover { border-color: #c4a05a; }
            """
        )

    def set_catalog(self, catalog) -> None:
        self._catalog = catalog

    def play_scene(self, jid: str):
        self._tg_playlist = []
        self._tg_play_index = 0
        self._tg_play_title = ""

        if is_telegram_group(jid):
            videos = self._catalog.group_video_paths(jid)
            title = self._catalog.scene_label(jid)
            if not videos:
                self._load_label.setText("该组暂无已下载视频")
                self._load_detail.setText(title)
                self._stack.setCurrentIndex(0)
                return
            self._tg_playlist = videos
            self._tg_play_title = title
            self._tg_play_index = 0
            self._play_tg_video_at(0)
            return

        if is_custom_video(jid):
            path = custom_video_path(jid, self._catalog._custom_root)
            self._play_custom(path, self._catalog.scene_label(jid))
            return

        self._json_id = jid
        self._playback_started = False
        self._dl_done = 0
        self._dl_total = 0
        self._dl_ok = 0
        self._movie_rels: set[str] = set()
        self._prewarm_started = False
        self._stage.set_json_id(jid)
        self._title_label.setText(jid)

        if not get_missing_resources(jid):
            self._start_playback(jid)
            return

        if prepare_script_files(jid):
            try:
                self._commands = load_adv_commands(jid)
            except Exception:
                self._commands = []
            self._begin_background_download(jid)
            self._start_playback(jid)
            return

        self._load_label.setText(f"正在下载剧本: {jid}")
        self._load_detail.setText("剧本就绪后将自动开始播放")
        self._cancel_btn.setEnabled(True)
        self._stack.setCurrentIndex(0)
        self._begin_background_download(jid)

    def _begin_background_download(self, jid: str):
        if self._dl_worker and self._dl_worker.isRunning():
            return
        self._dl_worker = ResourceDownloadWorker(
            jid, self._commands, self._cmd_index
        )
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.item_started.connect(self._on_dl_item)
        self._dl_worker.finished_ok.connect(self._on_dl_ready)
        self._dl_worker.cancelled.connect(self._on_dl_cancelled)
        self._dl_worker.failed.connect(self._on_dl_failed)
        self._dl_worker.start()

    def _sync_download_priority(self):
        if self._dl_worker and self._dl_worker.isRunning():
            self._dl_worker.set_play_cursor(self._cmd_index, self._commands)

    def _play_tg_video_at(self, index: int):
        if index < 0 or index >= len(self._tg_playlist):
            return
        path = self._tg_playlist[index]
        total = len(self._tg_playlist)
        suffix = f" ({index + 1}/{total})" if total > 1 else ""
        self._play_custom(path, self._tg_play_title + suffix)

    def _on_video_media_status(self, status):
        if not self._tg_playlist:
            return
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        nxt = self._tg_play_index + 1
        if nxt < len(self._tg_playlist):
            self._tg_play_index = nxt
            self._play_tg_video_at(nxt)

    def _play_custom(self, path: str, title: str):
        if not os.path.isfile(path):
            self._load_label.setText("视频文件不存在")
            self._stack.setCurrentIndex(0)
            return
        self._video_title.setText(title)
        self._video_controls.reset()
        self._video_player.setSource(QUrl.fromLocalFile(path))
        self._stack.setCurrentIndex(2)
        self._video_player.play()

    def _is_custom_video_page(self) -> bool:
        return self._stack.currentIndex() == 2

    def _on_dl_progress(self, done: int, total: int, ok: int):
        self._dl_done, self._dl_total, self._dl_ok = done, total, ok
        if self._stack.currentIndex() == 0:
            remain = total - done
            tail = f" · 剩余 {remain} 个" if remain else ""
            self._load_detail.setText(f"下载资源 {done}/{total} · 成功 {ok}{tail}")
        self._update_dl_title()

    def _update_dl_title(self):
        if not self._json_id:
            return
        if (
            self._dl_worker
            and self._dl_worker.isRunning()
            and self._dl_total > 0
            and self._dl_done < self._dl_total
        ):
            self._title_label.setText(
                f"{self._json_id} · 后台下载 {self._dl_done}/{self._dl_total}"
            )
        else:
            self._title_label.setText(self._json_id)

    def _on_dl_item(self, rel: str):
        name = rel.rsplit("/", 1)[-1] if rel else ""
        if name and self._stack.currentIndex() == 0:
            self._load_detail.setText(f"正在下载: {name}")
        if self._stack.currentIndex() == 0 and not self._playback_started:
            if prepare_script_files(self._json_id):
                self._cancel_btn.setEnabled(False)
                self._start_playback(self._json_id)
        if self._stack.currentIndex() == 1 and self._playback_started and self._prewarm_started:
            rel_norm = rel.replace("\\", "/")
            if rel_norm in self._movie_rels:
                self._stage.try_prewarm_movie_rel(self._json_id, rel)
        if self._stack.currentIndex() == 1 and self._playback_started and self._waiting:
            self._on_prewarm_progress()

    def _on_cancel_download(self):
        if not self._dl_worker or not self._dl_worker.isRunning():
            self._exit()
            return

        box = QMessageBox(self)
        box.setWindowTitle("下载中")
        box.setText("资源仍在后台下载，可先进入播放（边下边看）。")
        btn_play = box.addButton("立即播放", QMessageBox.AcceptRole)
        btn_back = box.addButton("返回列表", QMessageBox.RejectRole)
        box.setDefaultButton(btn_play)
        box.exec()

        if box.clickedButton() == btn_play:
            self._cancel_btn.setEnabled(False)
            if prepare_script_files(self._json_id):
                self._start_playback(self._json_id)
            else:
                QMessageBox.information(self, "无法播放", "剧本尚未下载完成，请稍候。")
            return

        self._cancel_btn.setEnabled(False)
        self._load_detail.setText("正在终止下载…")
        self._dl_worker.cancel()

    def _on_dl_cancelled(self, jid: str):
        self._cancel_btn.setEnabled(False)
        if jid != self._json_id:
            return
        self._exit()

    def _on_dl_failed(self, jid: str, msg: str):
        self._cancel_btn.setEnabled(False)
        self._load_label.setText(f"资源准备失败: {msg}")

    def _start_playback(self, jid: str):
        if self._playback_started:
            return
        try:
            self._commands = load_adv_commands(jid)
        except Exception as exc:
            if self._stack.currentIndex() == 0:
                self._load_label.setText(f"无法加载剧本: {exc}")
                self._cancel_btn.setEnabled(True)
            return
        self._playback_started = True
        self._cmd_index = 0
        self._speaker = ""
        self._waiting = False
        self._wait_markers: list[int] = []
        self._prewarm_started = False
        self._stage.reset_visuals()
        self._stack.setCurrentIndex(1)
        missing = len(get_missing_resources(jid))
        if missing:
            print(f"[播放] {jid} 边下边看：仍有 {missing} 个资源待下载")
        movie_rels = collect_movie_rels(self._commands)
        self._movie_rels = set(movie_rels)
        if movie_rels:
            local_cnt = sum(
                1 for rel in movie_rels if local_resource_path(jid, rel)
            )
            pending = len(movie_rels) - local_cnt
            print(
                f"[预热] 动态CG {len(movie_rels)} 个"
                f"（本地 {local_cnt} · 待下载 {pending}）"
            )
        self._update_dl_title()
        self.setFocus(Qt.OtherFocusReason)
        self._stage.set_prewarm_ready_listener(self._on_prewarm_progress)
        self._sync_download_priority()
        QTimer.singleShot(0, self._run_until_wait)

    def _ensure_prewarm_started(self):
        if not self._movie_rels:
            return
        ahead = collect_movie_rels_ahead(self._commands, self._cmd_index)
        if not ahead:
            return
        if not self._prewarm_started:
            self._prewarm_started = True
        QTimer.singleShot(
            MOVIE_PREWARM_GAP_MS,
            lambda: self._stage.schedule_movie_prewarm(self._json_id, ahead),
        )

    def _on_prewarm_progress(self):
        if self._stack.currentIndex() == 1 and self._waiting:
            self._refresh_hint()
            if not self._advance_blocked():
                self._gate_timer.stop()

    @property
    def _ff_active(self) -> bool:
        return self._ff_ctrl or self._ff_mouse

    def _update_ff(self):
        if self._ff_active:
            self._voice.stop()
            if self._waiting:
                self._ff_timer.start()
        else:
            self._ff_timer.stop()
        self._refresh_hint()

    def _on_long_press(self):
        if self._mouse_down and self._stack.currentIndex() == 1:
            self._long_press_fired = True
            self._ff_mouse = True
            self._update_ff()

    def _on_ff_tick(self):
        if not self._ff_active:
            self._ff_timer.stop()
            return
        if self._waiting:
            if self._advance_blocked():
                self._refresh_hint()
                return
            self._advance()

    def _on_advance_gate_poll(self):
        if not self._waiting or self._stack.currentIndex() != 1:
            self._gate_timer.stop()
            return
        if not self._advance_blocked():
            self._gate_timer.stop()
        self._refresh_hint()

    def _scan_upcoming_segment(self) -> tuple[list[str], list[str]]:
        """扫描到下一个 clickwait 前将用到的资源与动态 CG。"""
        resource_rels: list[str] = []
        movie_rels: list[str] = []
        i = self._cmd_index
        while i < len(self._commands):
            line = self._commands[i].strip()
            if line:
                parts = line.split(",")
                op = parts[0].strip()
                if op == "clickwait":
                    break
                if op == "bg" and len(parts) > 1:
                    resource_rels.append(parts[1].strip().replace("\\", "/"))
                elif op == "playvoice" and len(parts) > 2:
                    resource_rels.append(parts[2].strip().replace("\\", "/"))
                elif op == "movie" and len(parts) > 1:
                    for rel in parts[1].split(":"):
                        r = rel.strip().replace("\\", "/")
                        if r:
                            movie_rels.append(r)
            i += 1
        return resource_rels, movie_rels

    def _advance_blocked(self) -> str | None:
        if self._stack.currentIndex() != 1 or not self._playback_started:
            return None
        res_rels, movie_rels = self._scan_upcoming_segment()
        for rel in res_rels:
            if rel == "color_0_0_0":
                continue
            if not local_resource_path(self._json_id, rel):
                return "资源下载中"
        for rel in movie_rels:
            if not local_resource_path(self._json_id, rel):
                return "资源下载中"
        if movie_rels and not self._stage.movies_prewarm_ready(self._json_id, movie_rels):
            if not self._prewarm_started:
                self._prewarm_started = True
            self._stage.schedule_movie_prewarm_rels(self._json_id, movie_rels)
            self._gate_timer.start()
            return "动态CG预热中"
        return None

    def _refresh_hint(self):
        blocked = self._advance_blocked() if self._waiting else None
        if self._ff_active:
            if blocked:
                hint = f"快进等待 · {blocked}"
            else:
                hint = "快进中 · 松开 Ctrl / 鼠标"
        elif self._waiting:
            if blocked:
                hint = f"{blocked} · 请稍候"
            else:
                dl_note = ""
                if (
                    self._dl_worker
                    and self._dl_worker.isRunning()
                    and self._dl_total > self._dl_done
                ):
                    dl_note = f" · 后台下载 {self._dl_done}/{self._dl_total}"
                hint = (
                    f"点击/滚轮下继续 · ←/滚轮上倒退 · Ctrl/长按 快进 · ESC 退出{dl_note}"
                )
        elif self._cmd_index >= len(self._commands):
            hint = "播放结束 · 点击退出"
        else:
            hint = ""
        self._dialogue.set_hint(hint)

    def _handle_adv_press(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        self._mouse_down = True
        self._long_press_fired = False
        self._long_press_timer.start(LONG_PRESS_MS)
        if event.modifiers() & Qt.ControlModifier and not self._ff_ctrl:
            self._ff_ctrl = True
            self._update_ff()

    def _handle_adv_release(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        self._long_press_timer.stop()
        self._mouse_down = False
        if self._long_press_fired:
            self._ff_mouse = False
            self._update_ff()
        elif not self._ff_active:
            self._advance()
        self._long_press_fired = False

    def _handle_adv_wheel(self, event: QWheelEvent) -> bool:
        if self._stack.currentIndex() != 1 or self._ff_active:
            return False
        delta = event.angleDelta().y()
        if delta > 0:
            self._rewind()
            return True
        if delta < 0:
            self._advance()
            return True
        return False

    def eventFilter(self, obj, event):
        if self._stack.currentIndex() == 1:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._handle_adv_press(event)
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._handle_adv_release(event)
            elif event.type() == QEvent.Type.Wheel:
                if self._handle_adv_wheel(event):
                    return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event: QWheelEvent):
        if self._handle_adv_wheel(event):
            event.accept()
            return
        super().wheelEvent(event)

    def _on_dl_ready(self, jid: str):
        self._cancel_btn.setEnabled(False)
        if jid != self._json_id:
            return
        self.resources_changed.emit(jid)
        self._update_dl_title()
        if self._stack.currentIndex() == 1 and self._playback_started:
            self._stage.flush_movie_prewarm_pending(jid)
        if self._stack.currentIndex() != 1:
            self._start_playback(jid)

    def _set_cg(self, rel: str):
        self._stage.set_cg(self._json_id, rel)

    def _set_dialogue(self, text: str):
        self._current_text = text
        self._dialogue.set_speaker(self._speaker)
        self._dialogue.set_text(text)
        self._refresh_hint()
        self._stage._raise_dialogue()

    def _process_command_line(self, pause_on_clickwait: bool) -> bool:
        """执行当前行；pause_on_clickwait 为 True 时在 clickwait 处暂停并返回 True。"""
        if self._cmd_index >= len(self._commands):
            return True
        line = self._commands[self._cmd_index].strip()
        if not line:
            self._cmd_index += 1
            return False
        parts = line.split(",")
        op = parts[0].strip()
        if op == "name":
            raw = parts[1] if len(parts) > 1 else ""
            self._speaker = normalize_speaker(raw)
        elif op == "bg":
            if len(parts) > 1:
                self._set_cg(parts[1].strip())
        elif op == "msg":
            raw = ",".join(parts[2:]) if len(parts) > 2 else ""
            self._set_dialogue(normalize_line_text(strip_adv_tags(raw)))
        elif op == "playvoice":
            if not self._ff_active and len(parts) > 2:
                rel = parts[2].strip()
                vp = local_resource_path(self._json_id, rel) or resource_path(
                    self._json_id, rel
                )
                if not vp or not os.path.isfile(vp):
                    vp = ensure_resource(self._json_id, rel) or vp
                if vp and os.path.isfile(vp):
                    self._voice.setSource(QUrl.fromLocalFile(vp))
                    self._voice.play()
        elif op == "movieoff":
            slot = parts[1].strip() if len(parts) > 1 else ""
            if slot.lower() == "all":
                self._stage.stop_movie()
            else:
                self._stage.stop_movie(slot or None)
        elif op == "movie":
            files = [p.strip() for p in parts[1].split(":") if p.strip()] if len(parts) > 1 else []
            slots = [s.strip() for s in parts[2].split(":") if s.strip()] if len(parts) > 2 else ["default"]
            if files:
                slot = slots[0] if slots else "default"
                self._stage.play_movie(self._json_id, files, slot)
        elif op == "clickwait":
            self._cmd_index += 1
            self._set_dialogue(self._current_text)
            if pause_on_clickwait:
                if self._ff_active:
                    self._waiting = False
                    QTimer.singleShot(FF_INTERVAL_MS, self._run_until_wait)
                else:
                    self._waiting = True
                    self._wait_markers.append(self._cmd_index)
                    self._ensure_prewarm_started()
                    self._sync_download_priority()
                    self._refresh_hint()
                return True
            return False
        self._cmd_index += 1
        return False

    def _restore_at_index(self, target_index: int):
        """从开头重放台本至指定行（用于倒退到上一句）。"""
        self._voice.stop()
        self._cmd_index = 0
        self._speaker = ""
        self._current_text = ""
        self._waiting = False
        self._stage.invalidate_all_movies()
        while self._cmd_index < target_index:
            if self._process_command_line(pause_on_clickwait=False):
                break
        self._waiting = True
        self._set_dialogue(self._current_text)
        self._refresh_hint()
        self._stage._raise_dialogue()

    def _rewind(self):
        if self._stack.currentIndex() != 1 or self._ff_active:
            return
        if len(self._wait_markers) < 2:
            return
        self._wait_markers.pop()
        self._restore_at_index(self._wait_markers[-1])

    def _run_until_wait(self):
        while self._cmd_index < len(self._commands):
            if self._process_command_line(pause_on_clickwait=True):
                return
        self._waiting = True
        self._refresh_hint()

    def _advance(self):
        if not self._waiting:
            return
        if self._cmd_index >= len(self._commands):
            self._exit()
            return
        blocked = self._advance_blocked()
        if blocked:
            self._gate_timer.start()
            self._refresh_hint()
            return
        self._gate_timer.stop()
        self._waiting = False
        self._sync_download_priority()
        self._run_until_wait()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            if self._stack.currentIndex() == 0 and self._dl_worker and self._dl_worker.isRunning():
                self._on_cancel_download()
                return
            self._exit()
            return
        if self._stack.currentIndex() == 1:
            if event.modifiers() & Qt.ControlModifier and not self._ff_ctrl:
                self._ff_ctrl = True
                self._update_ff()
            if event.key() in (Qt.Key_Left, Qt.Key_Backspace) and not self._ff_active:
                self._rewind()
                return
        if self._is_custom_video_page():
            if event.key() == Qt.Key_Space:
                self._video_controls.toggle_playback()
                return
            if event.key() == Qt.Key_Left:
                self._video_controls.seek_relative(-SEEK_STEP_MS)
                return
            if event.key() == Qt.Key_Right:
                self._video_controls.seek_relative(SEEK_STEP_MS)
                return
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            if self._stack.currentIndex() == 1 and not self._ff_active:
                self._advance()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if self._stack.currentIndex() == 1:
            if not (event.modifiers() & Qt.ControlModifier) and self._ff_ctrl:
                self._ff_ctrl = False
                self._update_ff()
        super().keyReleaseEvent(event)

    def _exit(self):
        self._ff_ctrl = False
        self._ff_mouse = False
        self._ff_timer.stop()
        self._long_press_timer.stop()
        self._dialogue.save_alpha()
        self._voice.stop()
        self._stage.stop_movie()
        self._stage.clear_movie_prewarm()
        self._video_player.stop()
        self._tg_playlist = []
        self._tg_play_index = 0
        self._tg_play_title = ""
        if self._dl_worker and self._dl_worker.isRunning():
            self._dl_worker.cancel()
            if not self._dl_worker.wait(3000):
                self._dl_worker.terminate()
                self._dl_worker.wait(1000)
        if self._json_id:
            self.resources_changed.emit(self._json_id)
        self.hide()
        self.closed.emit()
