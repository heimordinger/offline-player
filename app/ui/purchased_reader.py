# -*- coding: utf-8 -*-
"""自购作品阅读器：左侧图片（翻页/条漫）+ 侧栏视频。"""
from __future__ import annotations

import os
import re

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.purchased_catalog import PurchasedCatalog, PurchasedWork
from app.ui.video_controls import VideoControlBar

_DAY_RE = re.compile(r"^(day\d+)", re.I)


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _video_day(path: str) -> str:
    base = os.path.splitext(os.path.basename(path))[0]
    m = _DAY_RE.match(base)
    return m.group(1).lower() if m else "other"


class Rotate90Host(QGraphicsView):
    """承载子控件；开启后逆时针旋转 90°，供手机锁横屏后竖拿阅读。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("QGraphicsView { background: #080a10; border: none; }")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setInteractive(True)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._proxy: QGraphicsProxyWidget | None = None
        self._child: QWidget | None = None
        self._rotated = False

    def set_widget(self, widget: QWidget):
        if self._proxy is not None:
            self._scene.removeItem(self._proxy)
            self._proxy = None
        self._child = widget
        self._proxy = self._scene.addWidget(widget)
        self._proxy.setTransformOriginPoint(0, 0)
        self._apply_transform()

    def is_rotated(self) -> bool:
        return self._rotated

    def set_rotated(self, rotated: bool):
        rotated = bool(rotated)
        if rotated == self._rotated:
            self._apply_transform()
            return
        self._rotated = rotated
        self._apply_transform()

    def _apply_transform(self):
        if self._proxy is None or self._child is None:
            return
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        self.resetTransform()
        if self._rotated:
            # 逻辑尺寸互换。Qt 屏幕坐标 Y 向下：setRotation(-90) 为视觉逆时针
            # (x,y)->(y,-x)，再平移 (0, vh) 才能落在 [0,vw]×[0,vh]
            self._child.setFixedSize(vh, vw)
            self._proxy.setTransformOriginPoint(0, 0)
            self._proxy.setRotation(-90)
            self._proxy.setPos(0, vh)
        else:
            self._child.setMinimumSize(0, 0)
            self._child.setMaximumSize(16777215, 16777215)
            self._child.setFixedSize(vw, vh)
            self._proxy.setRotation(0)
            self._proxy.setPos(0, 0)
        self._scene.setSceneRect(QRectF(0, 0, vw, vh))
        self._proxy.setVisible(True)
        self.fitInView(QRectF(0, 0, vw, vh), Qt.IgnoreAspectRatio)
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_transform()


class ImageCanvas(QLabel):
    """可点击左右区域翻页的图片画布。"""

    prev_requested = Signal()
    next_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: #080a10; color: #8a94a8;")
        self.setText("无图片")
        self._source_path: str | None = None
        self._raw: QPixmap | None = None
        self._queued_path: str | None = None
        self._has_image = False

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

    def set_image_path(self, path: str | None, animate: bool = True):
        if path == self._source_path and self._has_image:
            return
        if (not animate) or (not self._has_image):
            self._fade.stop()
            self._apply_path(path)
            self._opacity.setOpacity(1.0)
            return
        self._queued_path = path
        if self._fade.state() == QPropertyAnimation.Running:
            return
        self._start_fade_out()

    def _start_fade_out(self):
        self._fade.stop()
        try:
            self._fade.finished.disconnect(self._on_fade_out_finished)
        except TypeError:
            pass
        self._fade.setDuration(120)
        self._fade.setStartValue(max(0.05, float(self._opacity.opacity())))
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._on_fade_out_finished)
        self._fade.start()

    def _on_fade_out_finished(self):
        try:
            self._fade.finished.disconnect(self._on_fade_out_finished)
        except TypeError:
            pass
        self._apply_path(self._queued_path)
        self._fade.setDuration(180)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _apply_path(self, path: str | None):
        self._source_path = path
        if not path or not os.path.isfile(path):
            self._raw = None
            self._has_image = False
            self.setPixmap(QPixmap())
            self.setText("图片不存在" if path else "无图片")
            return
        pix = QPixmap(path)
        if pix.isNull():
            self._raw = None
            self._has_image = False
            self.setPixmap(QPixmap())
            self.setText("无法加载图片")
            return
        self._raw = pix
        self._has_image = True
        self.setText("")
        self._relayout()

    def _relayout(self):
        if self._raw is None or self._raw.isNull():
            return
        scaled = self._raw.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.position().x() < self.width() * 0.35:
                self.prev_requested.emit()
            else:
                self.next_requested.emit()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        # 动画进行中忽略连滚，避免连跳多页
        if self._fade.state() == QPropertyAnimation.Running:
            event.accept()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self.prev_requested.emit()
        elif delta < 0:
            self.next_requested.emit()
        event.accept()


class WebtoonView(QScrollArea):
    """条漫：纵向连续滚动；懒加载可见区域附近图片。"""

    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: #080a10; border: none; }")
        self._paths: list[str] = []
        self._labels: list[QLabel] = []
        self._loaded: set[int] = set()
        self._placeholder_h = 480
        self._updating = False
        self._side_margin = 40  # 左右各留边距（像素）
        self._scroll_anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_anim.setDuration(320)

        self._content = QWidget()
        self._content.setStyleSheet("background: #080a10;")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(self._side_margin, 0, self._side_margin, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self.setWidget(self._content)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def side_margin(self) -> int:
        return self._side_margin

    def set_side_margin(self, px: int):
        px = max(0, min(240, int(px)))
        if px == self._side_margin:
            return
        self._side_margin = px
        self._layout.setContentsMargins(px, 0, px, 0)
        self._relayout_images()

    def _relayout_images(self):
        if not self._labels:
            return
        idx = self.current_page()
        scroll = self.verticalScrollBar().value()
        self._loaded.clear()
        for lab in self._labels:
            lab.setPixmap(QPixmap())
            lab.setText("…")
            lab.setFixedHeight(self._placeholder_h)
        self._ensure_range(max(0, idx - 1), min(len(self._labels), idx + 4))
        self.verticalScrollBar().setValue(scroll)

    def set_pages(self, paths: list[str], jump_to: int = 0):
        self._clear()
        self._paths = list(paths)
        for _ in paths:
            lab = QLabel()
            lab.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            lab.setMinimumHeight(self._placeholder_h)
            lab.setStyleSheet("background: #080a10; color: #5a6888;")
            lab.setText("…")
            lab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._labels.append(lab)
            self._layout.insertWidget(self._layout.count() - 1, lab)
        QTimer.singleShot(0, lambda: self.jump_to_page(jump_to, load=True, smooth=False))

    def _clear(self):
        self._loaded.clear()
        while self._labels:
            lab = self._labels.pop()
            self._layout.removeWidget(lab)
            lab.deleteLater()
        self._paths = []

    def page_count(self) -> int:
        return len(self._paths)

    def current_page(self) -> int:
        if not self._labels:
            return 0
        y = self.verticalScrollBar().value() + self.viewport().height() // 3
        acc = 0
        for i, lab in enumerate(self._labels):
            h = max(1, lab.height())
            if acc + h > y:
                return i
            acc += h
        return max(0, len(self._labels) - 1)

    def jump_to_page(self, index: int, load: bool = True, smooth: bool = True):
        if not self._labels:
            return
        index = max(0, min(index, len(self._labels) - 1))
        if load:
            self._ensure_range(max(0, index - 1), min(len(self._labels), index + 3))
        self._content.adjustSize()
        y = 0
        for i in range(index):
            y += max(1, self._labels[i].height())
        if smooth:
            self._animate_scroll_to(y)
        else:
            self._scroll_anim.stop()
            self.verticalScrollBar().setValue(y)
            self._on_scroll()

    def _scroll_base_value(self) -> int:
        if self._scroll_anim.state() == QPropertyAnimation.Running:
            return int(self._scroll_anim.endValue())
        return self.verticalScrollBar().value()

    def _animate_scroll_to(self, value: int):
        bar = self.verticalScrollBar()
        value = max(bar.minimum(), min(bar.maximum(), int(value)))
        start = bar.value()
        if abs(start - value) <= 1:
            bar.setValue(value)
            return
        dist = abs(value - start)
        duration = max(180, min(420, 160 + dist // 4))
        self._scroll_anim.stop()
        self._scroll_anim.setDuration(duration)
        self._scroll_anim.setStartValue(start)
        self._scroll_anim.setEndValue(value)
        self._scroll_anim.start()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        if delta == 0:
            event.accept()
            return
        # 约 1/3 屏平滑滚动
        step = max(80, int(self.viewport().height() * (1 / 3)))
        direction = -1 if delta > 0 else 1
        # 高分辨滚轮：按档数累加，但仍走动画
        notches = max(1, abs(int(delta)) // 120)
        target = self._scroll_base_value() + direction * step * notches
        self._animate_scroll_to(target)
        event.accept()

    def _on_scroll(self, *_):
        if self._updating or not self._labels:
            return
        idx = self.current_page()
        self.page_changed.emit(idx)
        self._ensure_range(max(0, idx - 2), min(len(self._labels), idx + 5))
        self._unload_far(idx)

    def _viewport_width(self) -> int:
        return max(120, self.viewport().width() - 2 * self._side_margin - 8)

    def _ensure_range(self, start: int, end: int):
        width = self._viewport_width()
        for i in range(start, end):
            if i in self._loaded:
                # 宽度变化时重缩放
                lab = self._labels[i]
                pix = lab.pixmap()
                if pix and not pix.isNull() and abs(pix.width() - width) <= 4:
                    continue
            self._load_one(i, width)

    def _load_one(self, index: int, width: int):
        if index < 0 or index >= len(self._paths):
            return
        path = self._paths[index]
        lab = self._labels[index]
        if not os.path.isfile(path):
            lab.setText("缺失")
            lab.setMinimumHeight(80)
            self._loaded.add(index)
            return
        pix = QPixmap(path)
        if pix.isNull():
            lab.setText("无法加载")
            lab.setMinimumHeight(80)
            self._loaded.add(index)
            return
        scaled = pix.scaledToWidth(width, Qt.SmoothTransformation)
        lab.setPixmap(scaled)
        lab.setText("")
        lab.setFixedHeight(scaled.height())
        self._loaded.add(index)

    def _unload_far(self, center: int):
        keep = set(range(max(0, center - 4), min(len(self._labels), center + 8)))
        for i in list(self._loaded):
            if i in keep:
                continue
            lab = self._labels[i]
            lab.setPixmap(QPixmap())
            lab.setText("…")
            lab.setFixedHeight(self._placeholder_h)
            self._loaded.discard(i)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._labels:
            idx = self.current_page()
            self._loaded.clear()
            for lab in self._labels:
                if lab.pixmap() is None or lab.pixmap().isNull():
                    lab.setFixedHeight(self._placeholder_h)
            self._ensure_range(max(0, idx - 1), min(len(self._labels), idx + 4))


class PurchasedReader(QWidget):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._catalog: PurchasedCatalog | None = None
        self._work: PurchasedWork | None = None
        self._pages: list[str] = []
        self._story_pages: list[str] = []
        self._omake_pages: list[str] = []
        self._videos: list[str] = []
        self._page_index = 0
        self._video_index = -1
        self._album = "story"  # story | omake
        self._read_mode = "page"  # page | webtoon
        self._show_image = True
        self._show_video = True
        self._chrome_visible = True
        self._fullscreen = False
        self._phone_mode = False
        self._phone_restore: dict | None = None
        self._saved_sizes = [700, 560]
        self._build_ui()

    def _build_ui(self):
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(8, 8, 8, 8)
        self._root_layout.setSpacing(6)

        self._top_bar = QWidget()
        bar = QHBoxLayout(self._top_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        self._back_btn = QPushButton("← 返回")
        self._back_btn.clicked.connect(self._on_close)
        bar.addWidget(self._back_btn)

        self._title = QLabel("")
        self._title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f0e8d8;")
        bar.addWidget(self._title, 1)

        self._album_story_btn = QPushButton("主线")
        self._album_story_btn.setCheckable(True)
        self._album_story_btn.setChecked(True)
        self._album_story_btn.setToolTip("主线剧情图（快捷键 O 切换）")
        self._album_story_btn.clicked.connect(lambda: self.set_album("story"))
        bar.addWidget(self._album_story_btn)

        self._album_omake_btn = QPushButton("特典")
        self._album_omake_btn.setCheckable(True)
        self._album_omake_btn.setToolTip("omake 特典图（快捷键 O 切换）")
        self._album_omake_btn.clicked.connect(lambda: self.set_album("omake"))
        bar.addWidget(self._album_omake_btn)

        self._mode_page_btn = QPushButton("翻页")
        self._mode_page_btn.setCheckable(True)
        self._mode_page_btn.setChecked(True)
        self._mode_page_btn.setToolTip("单页翻页模式（快捷键 W）")
        self._mode_page_btn.clicked.connect(lambda: self.set_read_mode("page"))
        bar.addWidget(self._mode_page_btn)

        self._mode_webtoon_btn = QPushButton("条漫")
        self._mode_webtoon_btn.setCheckable(True)
        self._mode_webtoon_btn.setToolTip("纵向连续滚动条漫模式（快捷键 W）")
        self._mode_webtoon_btn.clicked.connect(lambda: self.set_read_mode("webtoon"))
        bar.addWidget(self._mode_webtoon_btn)

        self._toggle_image_btn = QPushButton("隐藏图片")
        self._toggle_image_btn.setToolTip("显示/隐藏左侧图片栏（快捷键 1）")
        self._toggle_image_btn.clicked.connect(self.toggle_image_pane)
        bar.addWidget(self._toggle_image_btn)

        self._toggle_video_btn = QPushButton("隐藏视频")
        self._toggle_video_btn.setToolTip("显示/隐藏右侧视频栏（快捷键 2）")
        self._toggle_video_btn.clicked.connect(self.toggle_video_pane)
        bar.addWidget(self._toggle_video_btn)

        self._dual_btn = QPushButton("双栏")
        self._dual_btn.setToolTip("恢复双栏同时显示（快捷键 Tab）")
        self._dual_btn.clicked.connect(self.show_both_panes)
        bar.addWidget(self._dual_btn)

        self._chrome_btn = QPushButton("隐藏栏")
        self._chrome_btn.setToolTip("显示/隐藏顶底工具栏（快捷键 H · 双击画面）")
        self._chrome_btn.clicked.connect(self.toggle_chrome)
        bar.addWidget(self._chrome_btn)

        self._fs_btn = QPushButton("全屏")
        self._fs_btn.setToolTip("进入/退出全屏（快捷键 F11）")
        self._fs_btn.clicked.connect(self.toggle_fullscreen)
        bar.addWidget(self._fs_btn)

        self._phone_btn = QPushButton("手机遥控")
        self._phone_btn.setCheckable(True)
        self._phone_btn.setToolTip(
            "手机锁横屏后竖拿阅读：内容旋转 90°（快捷键 R）"
        )
        self._phone_btn.clicked.connect(self.toggle_phone_mode)
        bar.addWidget(self._phone_btn)

        self._prev_btn = QPushButton("上一页")
        self._prev_btn.clicked.connect(self.prev_page)
        bar.addWidget(self._prev_btn)
        self._next_btn = QPushButton("下一页")
        self._next_btn.clicked.connect(self.next_page)
        bar.addWidget(self._next_btn)
        self._root_layout.addWidget(self._top_bar)


        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(True)

        self._left_pane = QWidget()
        left_layout = QVBoxLayout(self._left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._image_stack = QStackedWidget()
        self._canvas = ImageCanvas()
        self._canvas.prev_requested.connect(self.prev_page)
        self._canvas.next_requested.connect(self.next_page)
        self._image_stack.addWidget(self._canvas)

        self._webtoon = WebtoonView()
        self._webtoon.page_changed.connect(self._on_webtoon_page)
        self._image_stack.addWidget(self._webtoon)

        self._rotate_host = Rotate90Host()
        self._rotate_host.set_widget(self._image_stack)
        left_layout.addWidget(self._rotate_host, 1)

        self._page_bar = QWidget()
        page_row = QHBoxLayout(self._page_bar)
        page_row.setContentsMargins(0, 0, 0, 0)
        page_row.setSpacing(8)
        self._page_label = QLabel("0 / 0")
        self._page_label.setStyleSheet("color: #9aa8c0;")
        page_row.addWidget(self._page_label)
        self._page_slider = QSlider(Qt.Horizontal)
        self._page_slider.setMinimum(0)
        self._page_slider.setMaximum(0)
        self._page_slider.valueChanged.connect(self._on_slider_changed)
        page_row.addWidget(self._page_slider, 1)
        left_layout.addWidget(self._page_bar)

        self._margin_row = QWidget()
        margin_row = QHBoxLayout(self._margin_row)
        margin_row.setContentsMargins(0, 0, 0, 0)
        margin_row.setSpacing(8)
        self._margin_caption = QLabel("条漫边距")
        self._margin_caption.setStyleSheet("color: #9aa8c0;")
        self._margin_caption.setToolTip("左右两侧留白，拖动滑条调节")
        margin_row.addWidget(self._margin_caption)
        self._margin_slider = QSlider(Qt.Horizontal)
        self._margin_slider.setRange(0, 200)
        self._margin_slider.setSingleStep(4)
        self._margin_slider.setPageStep(20)
        self._margin_slider.setValue(self._webtoon.side_margin())
        self._margin_slider.setToolTip("拖动调节条漫左右边距")
        self._margin_slider.valueChanged.connect(self._on_margin_slider)
        margin_row.addWidget(self._margin_slider, 1)
        self._margin_value = QLabel(f"{self._webtoon.side_margin()} px")
        self._margin_value.setStyleSheet("color: #c4a05a; min-width: 48px;")
        self._margin_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        margin_row.addWidget(self._margin_value)
        self._margin_row.hide()
        self._margin_apply_timer = QTimer(self)
        self._margin_apply_timer.setSingleShot(True)
        self._margin_apply_timer.timeout.connect(self._apply_margin_from_slider)
        left_layout.addWidget(self._margin_row)

        self._splitter.addWidget(self._left_pane)

        # 右侧：视频 + 侧栏选集（不用叠在 QVideoWidget 上，否则原生窗体会盖住按钮）
        self._right_pane = QWidget()
        self._right_pane.setMinimumWidth(320)
        right_layout = QVBoxLayout(self._right_pane)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._video_row = QWidget()
        video_row = QHBoxLayout(self._video_row)
        video_row.setContentsMargins(0, 0, 0, 0)
        video_row.setSpacing(0)

        self._video_stage = QWidget()
        self._video_stage.setStyleSheet("background: #000;")
        self._video_stage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        stage_layout = QVBoxLayout(self._video_stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(0)

        self._video_widget = QVideoWidget()
        self._video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._video_widget.setStyleSheet("background: #000;")
        stage_layout.addWidget(self._video_widget, 1)

        self._video_title = QLabel("视频")
        self._video_title.setParent(self._video_stage)
        self._video_title.setStyleSheet(
            "background: rgba(8,10,16,160); color: #e8e0d0; font-size: 12px; padding: 4px 8px;"
        )
        self._video_title.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._audio = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video_widget)

        video_row.addWidget(self._video_stage, 1)

        # 选集列表：作为布局列插入，不遮盖视频原生层
        self._clip_drawer = QFrame()
        self._clip_drawer.setObjectName("clipDrawer")
        self._clip_drawer.setFixedWidth(260)
        self._clip_drawer.setStyleSheet(
            """
            QFrame#clipDrawer {
                background: #10141e;
                border-left: 1px solid #4a5878;
            }
            QListWidget {
                background: transparent; color: #d8d4cc; border: none;
            }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected { background: #243048; }
            QListWidget::item:hover { background: #1a2438; }
            """
        )
        drawer_layout = QVBoxLayout(self._clip_drawer)
        drawer_layout.setContentsMargins(8, 8, 8, 8)
        drawer_layout.setSpacing(6)
        drawer_head = QHBoxLayout()
        self._clip_prev = QPushButton("上一段")
        self._clip_prev.clicked.connect(self.prev_clip)
        drawer_head.addWidget(self._clip_prev)
        self._clip_next = QPushButton("下一段")
        self._clip_next.clicked.connect(self.next_clip)
        drawer_head.addWidget(self._clip_next)
        self._clip_close = QPushButton("关闭")
        self._clip_close.clicked.connect(self.close_clip_drawer)
        drawer_head.addWidget(self._clip_close)
        drawer_layout.addLayout(drawer_head)
        self._clip_list = QListWidget()
        self._clip_list.currentRowChanged.connect(self._on_clip_selected)
        drawer_layout.addWidget(self._clip_list, 1)
        self._clip_hint = QLabel("点「关闭」或「收起」")
        self._clip_hint.setStyleSheet("color: #7a889c; font-size: 11px;")
        drawer_layout.addWidget(self._clip_hint)
        self._clip_drawer.hide()
        self._drawer_open = False
        video_row.addWidget(self._clip_drawer)

        # 最右侧感应栏：悬停后显示「选集」按钮（布局内真实控件）
        self._edge_rail = QFrame()
        self._edge_rail.setObjectName("edgeRail")
        self._edge_rail.setFixedWidth(14)
        self._edge_rail.setCursor(Qt.PointingHandCursor)
        self._edge_rail.setMouseTracking(True)
        self._edge_rail.setStyleSheet(
            """
            QFrame#edgeRail {
                background: #141824;
                border-left: 1px solid #2a3448;
            }
            QFrame#edgeRail[expanded="true"] {
                background: #1c2434;
                border-left: 1px solid #c4a05a;
            }
            """
        )
        rail_layout = QVBoxLayout(self._edge_rail)
        rail_layout.setContentsMargins(4, 8, 4, 8)
        rail_layout.setSpacing(0)
        rail_layout.addStretch(1)
        self._clip_fab = QPushButton("选集")
        self._clip_fab.setObjectName("clipFab")
        self._clip_fab.setCursor(Qt.PointingHandCursor)
        self._clip_fab.setCheckable(True)
        self._clip_fab.setMinimumHeight(72)
        self._clip_fab.setToolTip("打开视频选集列表")
        self._clip_fab.setStyleSheet(
            """
            QPushButton#clipFab {
                background: #2a3a58;
                color: #fff4d8;
                border: 1px solid #c4a05a;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 4px;
            }
            QPushButton#clipFab:hover { background: #3a4c6c; }
            QPushButton#clipFab:checked { background: #4a5c7c; }
            """
        )
        self._clip_fab.hide()
        self._clip_fab.clicked.connect(self.toggle_clip_drawer)
        rail_layout.addWidget(self._clip_fab)
        rail_layout.addStretch(1)
        video_row.addWidget(self._edge_rail)

        self._fab_hide_timer = QTimer(self)
        self._fab_hide_timer.setSingleShot(True)
        self._fab_hide_timer.timeout.connect(self._maybe_hide_fab)

        right_layout.addWidget(self._video_row, 1)

        self._controls = VideoControlBar(self._player, self._audio)
        right_layout.addWidget(self._controls)

        self._splitter.addWidget(self._right_pane)
        self._splitter.setStretchFactor(0, 5)
        self._splitter.setStretchFactor(1, 4)
        self._splitter.setSizes([700, 560])
        self._saved_sizes = [700, 560]
        self._root_layout.addWidget(self._splitter, 1)

        self._hint = QLabel("")
        self._update_hint()
        self._hint.setStyleSheet("color: #7a889c; font-size: 11px;")
        self._root_layout.addWidget(self._hint)

        # 手机遥控大按钮（不旋转，便于竖拿点按）
        self._phone_pad = QFrame(self)
        self._phone_pad.setObjectName("phonePad")
        self._phone_pad.setStyleSheet(
            """
            QFrame#phonePad {
                background: rgba(10, 12, 20, 200);
                border: 1px solid #5a6888;
                border-radius: 12px;
            }
            QPushButton#phoneFab {
                background: #2a3a58;
                color: #fff4d8;
                border: 1px solid #c4a05a;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
                min-height: 52px;
                padding: 8px 14px;
            }
            QPushButton#phoneFab:hover { background: #3a4c6c; }
            """
        )
        pad_layout = QVBoxLayout(self._phone_pad)
        pad_layout.setContentsMargins(10, 10, 10, 10)
        pad_layout.setSpacing(8)
        self._phone_prev = QPushButton("上一张")
        self._phone_prev.setObjectName("phoneFab")
        self._phone_prev.clicked.connect(self.prev_page)
        pad_layout.addWidget(self._phone_prev)
        self._phone_next = QPushButton("下一张")
        self._phone_next.setObjectName("phoneFab")
        self._phone_next.clicked.connect(self.next_page)
        pad_layout.addWidget(self._phone_next)
        self._phone_chrome = QPushButton("显隐栏")
        self._phone_chrome.setObjectName("phoneFab")
        self._phone_chrome.clicked.connect(self.toggle_chrome)
        pad_layout.addWidget(self._phone_chrome)
        self._phone_exit = QPushButton("退出遥控")
        self._phone_exit.setObjectName("phoneFab")
        self._phone_exit.clicked.connect(lambda: self.set_phone_mode(False))
        pad_layout.addWidget(self._phone_exit)
        self._phone_pad.hide()

        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(
            """
            QWidget { background: #0c0e16; color: #ece8e0; }
            QPushButton {
                background: #243048; color: #e8e0d0; border: 1px solid #5a6888;
                border-radius: 6px; padding: 4px 12px;
            }
            QPushButton:hover { background: #2e3c58; border-color: #c4a05a; }
            QPushButton:checked {
                background: #3a4a68; border-color: #c4a05a; color: #fff8e8;
            }
            """
        )

        for w in (
            self._right_pane,
            self._edge_rail,
            self._clip_fab,
            self._clip_drawer,
            self._clip_list,
            self._canvas,
            self._webtoon,
            self._image_stack,
            self._rotate_host,
        ):
            w.installEventFilter(self)

    def set_catalog(self, catalog: PurchasedCatalog | None):
        self._catalog = catalog

    def open_work(self, jid: str):
        if self._catalog is None:
            return
        work = self._catalog.get_work(jid)
        self._work = work
        self._player.stop()
        self._controls.reset()
        if not work:
            self._title.setText("作品不存在")
            self._story_pages = []
            self._omake_pages = []
            self._pages = []
            self._videos = []
            self._page_index = 0
            self._update_album_buttons()
            self._update_mode_buttons()
            self._reload_image_view(force=True)
            self._fill_clips()
            return

        self._title.setText(f"{work.author} · {work.title}")
        self._story_pages = list(work.pages)
        self._omake_pages = list(work.omake)
        self._videos = list(work.videos)
        self._album = "story"
        self._fill_clips()
        self.set_album("story", reset_index=True)
        if self._videos:
            self._play_clip(0, autoplay=False)
        self.show_both_panes()
        self.setFocus()

    def _update_album_buttons(self):
        has_omake = bool(self._omake_pages)
        self._album_omake_btn.setEnabled(has_omake)
        self._album_omake_btn.setText(
            f"特典 ({len(self._omake_pages)})" if has_omake else "特典"
        )
        self._album_story_btn.setText(
            f"主线 ({len(self._story_pages)})" if self._story_pages else "主线"
        )
        self._album_story_btn.setChecked(self._album == "story")
        self._album_omake_btn.setChecked(self._album == "omake")

    def _update_mode_buttons(self):
        self._mode_page_btn.setChecked(self._read_mode == "page")
        self._mode_webtoon_btn.setChecked(self._read_mode == "webtoon")
        if self._read_mode == "webtoon":
            self._prev_btn.setText("上一张")
            self._next_btn.setText("下一张")
        else:
            self._prev_btn.setText("上一页")
            self._next_btn.setText("下一页")
        self._apply_chrome_visibility()

    def set_chrome_visible(self, visible: bool):
        self._chrome_visible = bool(visible)
        self._apply_chrome_visibility()

    def toggle_chrome(self):
        self.set_chrome_visible(not self._chrome_visible)

    def _apply_chrome_visibility(self):
        show = self._chrome_visible
        self._top_bar.setVisible(show)
        self._page_bar.setVisible(show)
        self._hint.setVisible(show)
        # 条漫边距只在条漫 + 显示栏时出现
        self._margin_row.setVisible(show and self._read_mode == "webtoon")
        self._chrome_btn.setText("显示栏" if not show else "隐藏栏")
        if show:
            self._root_layout.setContentsMargins(8, 8, 8, 8)
            self._root_layout.setSpacing(6)
        else:
            self._root_layout.setContentsMargins(0, 0, 0, 0)
            self._root_layout.setSpacing(0)
        QTimer.singleShot(0, self._layout_video_overlays)

    def toggle_fullscreen(self):
        win = self.window()
        if win is None:
            return
        if win.isFullScreen():
            win.showNormal()
            self._fullscreen = False
            self._fs_btn.setText("全屏")
            # 退出全屏时恢复工具栏，方便操作
            self.set_chrome_visible(True)
        else:
            win.showFullScreen()
            self._fullscreen = True
            self._fs_btn.setText("退出全屏")
            # 进入全屏默认隐藏顶底栏，沉浸阅读
            self.set_chrome_visible(False)
        self.setFocus()

    def _exit_fullscreen_if_needed(self) -> bool:
        win = self.window()
        if win is not None and win.isFullScreen():
            win.showNormal()
            self._fullscreen = False
            self._fs_btn.setText("全屏")
            self.set_chrome_visible(True)
            return True
        return False

    def toggle_phone_mode(self):
        self.set_phone_mode(not self._phone_mode)

    def set_phone_mode(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self._phone_mode:
            self._phone_btn.setChecked(enabled)
            self._layout_phone_pad()
            return

        win = self.window()
        if enabled:
            self._phone_restore = {
                "chrome": self._chrome_visible,
                "show_image": self._show_image,
                "show_video": self._show_video,
                "read_mode": self._read_mode,
                "sizes": list(self._splitter.sizes()),
                "fullscreen": bool(win.isFullScreen()) if win else False,
                "geometry": bytes(win.saveGeometry()) if win else None,
            }
            self._phone_mode = True
            self._phone_btn.setChecked(True)
            # 条漫 + 只留图 + 旋转 90° + 全屏藏栏
            self.set_read_mode("webtoon")
            self._show_image = True
            self._show_video = False
            self._apply_pane_visibility()
            self._rotate_host.set_rotated(True)
            self.set_chrome_visible(False)
            if win is not None and not win.isFullScreen():
                win.showFullScreen()
                self._fullscreen = True
                self._fs_btn.setText("退出全屏")
            self._phone_pad.show()
            self._layout_phone_pad()
            QTimer.singleShot(0, self._refresh_after_rotate)
        else:
            restore = self._phone_restore or {}
            self._phone_restore = None
            self._phone_mode = False
            self._phone_btn.setChecked(False)
            self._rotate_host.set_rotated(False)
            self._phone_pad.hide()
            mode = restore.get("read_mode", "page")
            if mode in ("page", "webtoon"):
                self.set_read_mode(mode)
            self._show_image = restore.get("show_image", True)
            self._show_video = restore.get("show_video", True)
            self._apply_pane_visibility()
            sizes = restore.get("sizes")
            if sizes:
                self._splitter.setSizes(sizes)
            self.set_chrome_visible(restore.get("chrome", True))
            if win is not None:
                if restore.get("fullscreen"):
                    win.showFullScreen()
                    self._fullscreen = True
                    self._fs_btn.setText("退出全屏")
                else:
                    win.showNormal()
                    self._fullscreen = False
                    self._fs_btn.setText("全屏")
                    geo = restore.get("geometry")
                    if geo:
                        win.restoreGeometry(geo)
            QTimer.singleShot(0, self._refresh_after_rotate)
        self._update_hint()
        self.setFocus()

    def _refresh_after_rotate(self):
        self._rotate_host._apply_transform()
        if self._read_mode == "webtoon":
            self._webtoon._relayout_images()
        else:
            self._canvas._relayout()
        self._layout_phone_pad()

    def _layout_phone_pad(self):
        if not hasattr(self, "_phone_pad") or not self._phone_pad.isVisible():
            return
        self._phone_pad.adjustSize()
        hint = self._phone_pad.sizeHint()
        pad_w = max(128, hint.width())
        pad_h = max(240, hint.height())
        x = max(8, self.width() - pad_w - 16)
        y = max(8, (self.height() - pad_h) // 2)
        self._phone_pad.setGeometry(x, y, pad_w, pad_h)
        self._phone_pad.raise_()

    def _on_margin_slider(self, value: int):
        self._margin_value.setText(f"{value} px")
        # 拖动时稍作防抖，松手或停顿后再重排图片
        self._margin_apply_timer.start(60)

    def _apply_margin_from_slider(self):
        self._webtoon.set_side_margin(self._margin_slider.value())

    def set_read_mode(self, mode: str):
        if mode not in ("page", "webtoon"):
            return
        changed = mode != self._read_mode
        self._read_mode = mode
        self._update_mode_buttons()
        self._image_stack.setCurrentWidget(
            self._webtoon if mode == "webtoon" else self._canvas
        )
        self._reload_image_view(force=changed or mode == "webtoon")
        self._update_hint()

    def toggle_read_mode(self):
        self.set_read_mode("webtoon" if self._read_mode == "page" else "page")

    def set_album(self, album: str, reset_index: bool = True):
        if album == "omake" and not self._omake_pages:
            album = "story"
        self._album = album
        self._pages = list(self._omake_pages if album == "omake" else self._story_pages)
        if reset_index:
            self._page_index = 0
        else:
            self._page_index = max(0, min(self._page_index, max(0, len(self._pages) - 1)))
        self._page_slider.blockSignals(True)
        self._page_slider.setMaximum(max(0, len(self._pages) - 1))
        self._page_slider.setValue(self._page_index)
        self._page_slider.blockSignals(False)
        self._update_album_buttons()
        # 特典以图为主：默认收起视频，切回主线时恢复双栏（手机遥控除外）
        if album == "omake":
            self._show_image = True
            self._show_video = False
            self._apply_pane_visibility()
        elif not self._phone_mode:
            self.show_both_panes()
        self._reload_image_view(force=True)
        prefix = "特典" if album == "omake" else "主线"
        if self._work:
            self._title.setText(f"{self._work.author} · {self._work.title} · {prefix}")

    def toggle_album(self):
        if self._album == "story" and self._omake_pages:
            self.set_album("omake")
        else:
            self.set_album("story")

    def _reload_image_view(self, force: bool = False):
        if self._read_mode == "webtoon":
            self._image_stack.setCurrentWidget(self._webtoon)
            if force or self._webtoon.page_count() != len(self._pages):
                self._webtoon.set_pages(self._pages, jump_to=self._page_index)
            else:
                self._webtoon.jump_to_page(self._page_index)
            self._sync_page_chrome()
            return
        self._image_stack.setCurrentWidget(self._canvas)
        self._show_page()

    def _fill_clips(self):
        self._clip_list.blockSignals(True)
        self._clip_list.clear()
        for path in self._videos:
            name = os.path.basename(path)
            day = _video_day(path)
            item = QListWidgetItem(f"[{day}] {name}")
            item.setData(Qt.UserRole, path)
            self._clip_list.addItem(item)
        self._clip_list.blockSignals(False)
        self._video_title.setText(
            f"视频 · {len(self._videos)} 段 · 移到最右侧细条"
            if self._videos
            else "视频 · 无"
        )
        if not self._videos:
            self._drawer_open = False
            self._clip_drawer.hide()
            self._clip_fab.hide()
            self._edge_rail.hide()
            self._set_rail_expanded(False)
        else:
            self._edge_rail.show()
            self._set_rail_expanded(False)
        self._layout_video_overlays()

    def _set_rail_expanded(self, expanded: bool):
        self._edge_rail.setFixedWidth(52 if expanded else 14)
        self._edge_rail.setProperty("expanded", "true" if expanded else "false")
        self._edge_rail.style().unpolish(self._edge_rail)
        self._edge_rail.style().polish(self._edge_rail)

    def _layout_video_overlays(self):
        if not hasattr(self, "_video_stage"):
            return
        stage = self._video_stage
        w = max(1, stage.width())
        self._video_title.adjustSize()
        title_w = min(w - 8, max(160, self._video_title.sizeHint().width() + 8))
        self._video_title.setGeometry(4, 4, title_w, self._video_title.sizeHint().height())
        self._video_title.raise_()

    def _show_clip_fab(self):
        if not self._videos:
            return
        self._fab_hide_timer.stop()
        self._set_rail_expanded(True)
        self._clip_fab.show()

    def _maybe_hide_fab(self):
        if self._drawer_open:
            return
        if not self._right_pane.isVisible():
            self._clip_fab.hide()
            self._set_rail_expanded(False)
            return
        pos = self._edge_rail.mapFromGlobal(self.cursor().pos())
        if self._edge_rail.rect().contains(pos):
            return
        self._clip_fab.hide()
        self._set_rail_expanded(False)

    def _schedule_hide_fab(self):
        if self._drawer_open:
            return
        self._fab_hide_timer.start(280)

    def open_clip_drawer(self):
        if not self._videos:
            return
        self._drawer_open = True
        self._show_clip_fab()
        self._clip_fab.setText("收起")
        self._clip_fab.setChecked(True)
        self._clip_drawer.show()

    def close_clip_drawer(self):
        self._drawer_open = False
        self._clip_drawer.hide()
        self._clip_fab.setText("选集")
        self._clip_fab.setChecked(False)
        self._schedule_hide_fab()

    def toggle_clip_drawer(self):
        if not self._videos:
            return
        if self._drawer_open:
            self.close_clip_drawer()
        else:
            self.open_clip_drawer()

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Type.MouseButtonDblClick and obj in (
            getattr(self, "_canvas", None),
            getattr(self, "_webtoon", None),
            getattr(self, "_image_stack", None),
            getattr(self, "_rotate_host", None),
        ):
            self.toggle_chrome()
            return True

        targets = (
            getattr(self, "_right_pane", None),
            getattr(self, "_edge_rail", None),
            getattr(self, "_clip_fab", None),
            getattr(self, "_clip_drawer", None),
            getattr(self, "_clip_list", None),
        )
        if obj in targets and obj is not None:
            if et == QEvent.Type.Resize and obj is self._right_pane:
                self._layout_video_overlays()
            elif et in (QEvent.Type.Enter, QEvent.Type.MouseMove):
                if obj in (self._edge_rail, self._clip_fab):
                    self._show_clip_fab()
                elif obj in (self._clip_drawer, self._clip_list) and self._drawer_open:
                    self._fab_hide_timer.stop()
            elif et == QEvent.Type.Leave:
                if obj in (self._edge_rail, self._clip_fab):
                    self._schedule_hide_fab()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_video_overlays()
        self._layout_phone_pad()

    def _sync_page_chrome(self):
        n = len(self._pages)
        album = "特典" if self._album == "omake" else "主线"
        mode = "条漫" if self._read_mode == "webtoon" else "翻页"
        if n <= 0:
            self._page_label.setText(f"{album} · {mode} · 0 / 0")
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            return
        self._page_index = max(0, min(self._page_index, n - 1))
        path = self._pages[self._page_index]
        self._page_label.setText(
            f"{album} · {mode} · {self._page_index + 1} / {n}  ·  {os.path.basename(path)}"
        )
        self._page_slider.blockSignals(True)
        self._page_slider.setValue(self._page_index)
        self._page_slider.blockSignals(False)
        self._prev_btn.setEnabled(self._page_index > 0)
        self._next_btn.setEnabled(self._page_index < n - 1)

    def _show_page(self):
        n = len(self._pages)
        album = "特典" if self._album == "omake" else "主线"
        if n <= 0:
            self._canvas.set_image_path(None)
            self._page_label.setText(f"{album} · 0 / 0")
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            return
        self._page_index = max(0, min(self._page_index, n - 1))
        path = self._pages[self._page_index]
        self._canvas.set_image_path(path)
        self._sync_page_chrome()

    def _on_webtoon_page(self, index: int):
        if self._read_mode != "webtoon":
            return
        if index < 0 or index >= len(self._pages):
            return
        if index == self._page_index:
            return
        self._page_index = index
        self._sync_page_chrome()

    def prev_page(self):
        if self._page_index > 0:
            self._page_index -= 1
            if self._read_mode == "webtoon":
                self._webtoon.jump_to_page(self._page_index)
                self._sync_page_chrome()
            else:
                self._show_page()

    def next_page(self):
        if self._page_index < len(self._pages) - 1:
            self._page_index += 1
            if self._read_mode == "webtoon":
                self._webtoon.jump_to_page(self._page_index)
                self._sync_page_chrome()
            else:
                self._show_page()

    def _on_slider_changed(self, value: int):
        if value != self._page_index:
            self._page_index = value
            if self._read_mode == "webtoon":
                self._webtoon.jump_to_page(self._page_index)
                self._sync_page_chrome()
            else:
                self._show_page()

    def _update_hint(self):
        if self._phone_mode:
            self._hint.setText(
                "手机遥控：锁横屏后逆时针竖拿 · 内容已转 90° · R/退出遥控 · H 显隐栏 · ←→ 翻页 · Esc 退出遥控"
            )
            return
        both = self._show_image and self._show_video
        mode_tip = "W 翻页/条漫"
        chrome_tip = "H 显隐栏 · F11 全屏 · R 手机遥控 · 双击画面"
        if both:
            self._hint.setText(
                f"←→ 翻页 · {mode_tip} · O 主线/特典 · 右缘选集 · 1/2 显隐 · {chrome_tip} · Esc"
            )
        elif self._show_image:
            tip = (
                "滚轮连续滚动"
                if self._read_mode == "webtoon"
                else "←→ 翻页"
            )
            self._hint.setText(
                f"纯图 · {tip} · {mode_tip} · {chrome_tip} · 2/Tab 视频 · Esc"
            )
        else:
            self._hint.setText(
                f"纯视频 · 右缘选集 · {chrome_tip} · 1/Tab 图片 · Esc"
            )

    def _on_clip_selected(self, row: int):
        if row < 0:
            return
        self._play_clip(row, autoplay=True)

    def _play_clip(self, index: int, autoplay: bool = True):
        if index < 0 or index >= len(self._videos):
            return
        self._video_index = index
        path = self._videos[index]
        self._clip_list.blockSignals(True)
        self._clip_list.setCurrentRow(index)
        self._clip_list.blockSignals(False)
        self._video_title.setText(
            f"视频 · {index + 1}/{len(self._videos)} · {os.path.basename(path)}"
        )
        self._layout_video_overlays()
        self._controls.reset()
        self._player.setSource(QUrl.fromLocalFile(path))
        if autoplay:
            self._player.play()
        else:
            self._player.pause()

    def prev_clip(self):
        if self._video_index > 0:
            self._play_clip(self._video_index - 1)
        elif self._videos and self._video_index < 0:
            self._play_clip(0)

    def next_clip(self):
        if self._video_index + 1 < len(self._videos):
            self._play_clip(self._video_index + 1)

    def _remember_sizes(self):
        sizes = self._splitter.sizes()
        if len(sizes) >= 2 and sizes[0] > 40 and sizes[1] > 40:
            self._saved_sizes = sizes

    def _apply_pane_visibility(self):
        # 至少保留一侧可见
        if not self._show_image and not self._show_video:
            self._show_image = True

        both = self._show_image and self._show_video
        if both:
            self._remember_sizes()

        self._left_pane.setVisible(self._show_image)
        self._right_pane.setVisible(self._show_video)

        if both:
            self._splitter.setSizes(self._saved_sizes or [900, 360])
        elif self._show_image:
            total = sum(self._splitter.sizes()) or 1200
            self._splitter.setSizes([total, 0])
            self._player.pause()
        else:
            total = sum(self._splitter.sizes()) or 1200
            self._splitter.setSizes([0, total])

        self._toggle_image_btn.setText("显示图片" if not self._show_image else "隐藏图片")
        self._toggle_video_btn.setText("显示视频" if not self._show_video else "隐藏视频")
        self._dual_btn.setEnabled(not both)
        self._update_hint()


    def toggle_image_pane(self):
        if self._show_image and not self._show_video:
            return
        self._show_image = not self._show_image
        self._apply_pane_visibility()

    def toggle_video_pane(self):
        if self._phone_mode:
            return
        if self._show_video and not self._show_image:
            return
        self._show_video = not self._show_video
        self._apply_pane_visibility()

    def show_both_panes(self):
        if self._phone_mode:
            return
        self._show_image = True
        self._show_video = True
        self._apply_pane_visibility()

    def _on_close(self):
        if self._phone_mode:
            self.set_phone_mode(False)
        self._exit_fullscreen_if_needed()
        self._player.stop()
        self.closed.emit()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key_Escape:
            if self._phone_mode:
                self.set_phone_mode(False)
                return
            if self._exit_fullscreen_if_needed():
                return
            if not self._chrome_visible:
                self.set_chrome_visible(True)
                return
            self._on_close()
            return
        if key == Qt.Key_Backspace:
            self._on_close()
            return
        if key == Qt.Key_R:
            self.toggle_phone_mode()
            return
        if key == Qt.Key_F11 or key == Qt.Key_F:
            self.toggle_fullscreen()
            return
        if key == Qt.Key_H:
            self.toggle_chrome()
            return
        if key in (Qt.Key_Left, Qt.Key_A, Qt.Key_PageUp):
            self.prev_page()
            return
        if key in (Qt.Key_Right, Qt.Key_D, Qt.Key_PageDown, Qt.Key_Space):
            self.next_page()
            return
        if key == Qt.Key_Home:
            self._page_index = 0
            if self._read_mode == "webtoon":
                self._webtoon.jump_to_page(0)
                self._sync_page_chrome()
            else:
                self._show_page()
            return
        if key == Qt.Key_End and self._pages:
            self._page_index = len(self._pages) - 1
            if self._read_mode == "webtoon":
                self._webtoon.jump_to_page(self._page_index)
                self._sync_page_chrome()
            else:
                self._show_page()
            return
        if key == Qt.Key_W:
            self.toggle_read_mode()
            return
        if key == Qt.Key_Tab:
            self.show_both_panes()
            return
        if key == Qt.Key_O:
            self.toggle_album()
            return
        if key == Qt.Key_1:
            self.toggle_image_pane()
            return
        if key == Qt.Key_2:
            self.toggle_video_pane()
            return
        if key in (Qt.Key_Up, Qt.Key_Q):
            if self._read_mode == "webtoon" and self._show_image and key == Qt.Key_Up:
                step = max(120, int(self._webtoon.viewport().height() * 0.75))
                self._webtoon._animate_scroll_to(self._webtoon._scroll_base_value() - step)
                return
            self.prev_clip()
            return
        if key in (Qt.Key_Down, Qt.Key_E):
            if self._read_mode == "webtoon" and self._show_image and key == Qt.Key_Down:
                step = max(120, int(self._webtoon.viewport().height() * 0.75))
                self._webtoon._animate_scroll_to(self._webtoon._scroll_base_value() + step)
                return
            self.next_clip()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event):
        self._player.pause()
        super().hideEvent(event)
