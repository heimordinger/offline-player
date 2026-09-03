# -*- coding: utf-8 -*-
"""固定行列的翻页缩略图网格（无滚动条）。"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.types import ThumbEntry
from app.ui.thumb_grid import apply_thumb_badge, load_thumb_pixmap

HOVER_CG_DELAY_MS = 800


class _ThumbCard(QToolButton):
    view_card_requested = Signal(str)

    def __init__(
        self,
        icon_size: QSize,
        cell_size: QSize,
        parent=None,
        text_only: bool = False,
        enable_view_card: bool = False,
        hover_cg_delay_ms: int = 0,
    ):
        super().__init__(parent)
        self._key = ""
        self._text_only = text_only
        self._enable_view_card = enable_view_card
        self._hover_cg_delay_ms = max(0, hover_cg_delay_ms)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._show_hover_cg)
        self._default_path: str | None = None
        self._hover_path: str | None = None
        self._badge = ""
        self._title = ""
        self._subtitle = ""
        self._base_style_thumb = (
            """
            QToolButton {
                background: #1c2234; color: #ddd8d0;
                border: 1px solid #3a4560; border-radius: 8px;
                padding: 6px 6px 8px 6px; font-size: 12px;
            }
            QToolButton:hover { border-color: #c4a05a; background: #243048; }
            """
        )
        self._base_style_text = (
            """
            QToolButton {
                background: #1c2234; color: #f0e8d8;
                border: 1px solid #3a4560; border-radius: 8px;
                padding: 16px 12px; font-size: 14px; font-weight: bold;
            }
            QToolButton:hover { border-color: #c4a05a; background: #243048; }
            """
        )
        self.setFixedSize(cell_size)
        self.setIconSize(icon_size)
        if text_only:
            self.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self.setStyleSheet(self._base_style_text)
        else:
            self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            self.setStyleSheet(self._base_style_thumb)

    def set_entry(self, entry: ThumbEntry | None):
        self._hover_timer.stop()
        if entry is None:
            self._key = ""
            self.hide()
            self.setEnabled(False)
            return
        self._key = entry.key
        self.show()
        self.setEnabled(True)
        # 角标画在缩略图上；文字区只放标题/副标题，避免多行挤扁
        lines = [entry.title]
        if entry.subtitle:
            lines.append(entry.subtitle)
        self.setText("\n".join(lines))
        tip = entry.title
        if entry.badge:
            tip += f" · {entry.badge}"
            if entry.missing_count > 0:
                tip += f"（缺 {entry.missing_count} 个文件）"
        if entry.subtitle:
            tip += f" — {entry.subtitle}"
        self.setToolTip(tip)
        if entry.badge and not self._text_only:
            border = "#c87848"
            hover_border = "#e8a060"
            if "动态" in entry.badge and "未下载" not in entry.badge:
                border = "#5a88c8"
                hover_border = "#7aa8e8"
            self.setStyleSheet(
                self._base_style_thumb
                + f"""
                QToolButton {{ border: 2px solid {border}; }}
                QToolButton:hover {{ border-color: {hover_border}; }}
                """
            )
        elif not self._text_only:
            self.setStyleSheet(self._base_style_thumb)
        if self._text_only:
            self.setIcon(QIcon())
            return
        self._default_path = entry.image_path
        self._hover_path = entry.hover_image_path or entry.image_path
        self._badge = entry.badge
        self._title = entry.title
        self._subtitle = entry.subtitle
        self._set_thumb_icon(self._default_path)

    def _set_thumb_icon(self, path: str | None):
        pix = load_thumb_pixmap(path, self.iconSize(), self._title, self._subtitle)
        if self._badge:
            pix = apply_thumb_badge(pix, self._badge)
        self.setIcon(QIcon(pix))

    def _show_hover_cg(self):
        if (
            not self._text_only
            and self._hover_path
            and self._hover_path != self._default_path
        ):
            self._set_thumb_icon(self._hover_path)

    def enterEvent(self, event):
        if (
            not self._text_only
            and self._hover_path
            and self._hover_path != self._default_path
        ):
            if self._hover_cg_delay_ms <= 0:
                self._set_thumb_icon(self._hover_path)
            else:
                self._hover_timer.start(self._hover_cg_delay_ms)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_timer.stop()
        if not self._text_only:
            self._set_thumb_icon(self._default_path)
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        if not self._enable_view_card or not self._key:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu { background: #1c2234; color: #ece8e0; border: 1px solid #5a6888; }
            QMenu::item:selected { background: #2e3c58; }
            """
        )
        action = menu.addAction("观看卡面")
        chosen = menu.exec(event.globalPos())
        if chosen == action:
            self.view_card_requested.emit(self._key)


class PaginatedThumbnailGrid(QWidget):
    activated = Signal(str)
    view_card_requested = Signal(str)

    def __init__(
        self,
        cols: int,
        rows: int,
        icon_size: QSize,
        cell_size: QSize,
        parent=None,
        wrap_pages: bool = False,
        text_only: bool = False,
        enable_view_card: bool = False,
        hover_cg_delay_ms: int = 0,
    ):
        super().__init__(parent)
        self._cols = cols
        self._rows = rows
        self._per_page = cols * rows
        self._entries: list[ThumbEntry] = []
        self._page = 0
        self._wrap_pages = wrap_pages
        self._hover_cg_delay_ms = hover_cg_delay_ms

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        grid_host = QWidget()
        self._grid = QGridLayout(grid_host)
        self._grid.setSpacing(16)
        self._cards: list[_ThumbCard] = []
        for row in range(rows):
            for col in range(cols):
                card = _ThumbCard(
                    icon_size,
                    cell_size,
                    text_only=text_only,
                    enable_view_card=enable_view_card,
                    hover_cg_delay_ms=self._hover_cg_delay_ms,
                )
                card.clicked.connect(self._on_card_clicked)
                card.view_card_requested.connect(self.view_card_requested.emit)
                self._cards.append(card)
                self._grid.addWidget(card, row, col)
        layout.addWidget(grid_host, 1)

        nav = QHBoxLayout()
        nav.addStretch(1)
        self._prev_btn = QPushButton("◀ 上一页")
        self._prev_btn.clicked.connect(self._prev_page)
        self._page_label = QLabel("1 / 1")
        self._page_label.setAlignment(Qt.AlignCenter)
        self._page_label.setMinimumWidth(100)
        self._next_btn = QPushButton("下一页 ▶")
        self._next_btn.clicked.connect(self._next_page)
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._page_label)
        nav.addWidget(self._next_btn)
        nav.addStretch(1)
        layout.addLayout(nav)

    @property
    def page(self) -> int:
        return self._page

    @property
    def page_count(self) -> int:
        if not self._entries:
            return 1
        return max(1, (len(self._entries) + self._per_page - 1) // self._per_page)

    def set_entries(self, entries: list[ThumbEntry], page: int | None = None):
        self._entries = entries
        if page is not None:
            self._page = max(0, min(page, self.page_count - 1))
        else:
            self._page = 0
        self._refresh_page()

    def update_entry_badge(self, key: str, badge: str, missing_count: int = 0):
        updated: list[ThumbEntry] = []
        changed = False
        for entry in self._entries:
            if entry.key == key:
                if entry.badge != badge or entry.missing_count != missing_count:
                    updated.append(
                        ThumbEntry(
                            key=entry.key,
                            title=entry.title,
                            subtitle=entry.subtitle,
                            image_path=entry.image_path,
                            hover_image_path=entry.hover_image_path,
                            badge=badge,
                            missing_count=missing_count,
                        )
                    )
                    changed = True
                else:
                    updated.append(entry)
            else:
                updated.append(entry)
        if changed:
            self._entries = updated
            self._refresh_page()

    def update_entry_image(self, key: str, image_path: str):
        updated: list[ThumbEntry] = []
        changed = False
        for entry in self._entries:
            if entry.key == key and entry.image_path != image_path:
                updated.append(
                    ThumbEntry(
                        key=entry.key,
                        title=entry.title,
                        subtitle=entry.subtitle,
                        image_path=image_path,
                        hover_image_path=entry.hover_image_path,
                        badge=entry.badge,
                        missing_count=entry.missing_count,
                    )
                )
                changed = True
            else:
                updated.append(entry)
        if changed:
            self._entries = updated
            self._refresh_page()

    def _refresh_page(self):
        start = self._page * self._per_page
        chunk = self._entries[start : start + self._per_page]
        for i, card in enumerate(self._cards):
            entry = chunk[i] if i < len(chunk) else None
            card.set_entry(entry)
        total = self.page_count
        self._page_label.setText(f"{self._page + 1} / {total}")
        if self._wrap_pages and total > 1:
            self._prev_btn.setEnabled(True)
            self._next_btn.setEnabled(True)
        else:
            self._prev_btn.setEnabled(self._page > 0)
            self._next_btn.setEnabled(self._page < total - 1)

    def _prev_page(self):
        total = self.page_count
        if total <= 1:
            return
        if self._page > 0:
            self._page -= 1
        elif self._wrap_pages:
            self._page = total - 1
        self._refresh_page()

    def _next_page(self):
        total = self.page_count
        if total <= 1:
            return
        if self._page < total - 1:
            self._page += 1
        elif self._wrap_pages:
            self._page = 0
        self._refresh_page()

    def _on_card_clicked(self):
        card = self.sender()
        if isinstance(card, _ThumbCard) and card._key:
            self.activated.emit(card._key)
