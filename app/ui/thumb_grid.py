# -*- coding: utf-8 -*-
"""缩略图网格（分类 / 场景共用）。"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from app.core.types import ThumbEntry

def _placeholder_pixmap(size: QSize, line1: str, line2: str = "") -> QPixmap:
    pix = QPixmap(size)
    pix.fill(QColor(28, 34, 52))
    painter = QPainter(pix)
    painter.setPen(QColor(140, 150, 170))
    font = QFont()
    font.setPointSize(9)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, line1)
    if line2:
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor(100, 110, 130))
        rect = pix.rect().adjusted(0, size.height() // 3, 0, 0)
        painter.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, line2)
    painter.end()
    return pix


def load_thumb_pixmap(path: str | None, size: QSize, fallback: str, fallback2: str = "") -> QPixmap:
    if path:
        src = QPixmap(path)
        if not src.isNull():
            return src.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return _placeholder_pixmap(size, fallback, fallback2)


def apply_thumb_badge(pix: QPixmap, badge: str) -> QPixmap:
    if not badge or pix.isNull():
        return pix
    out = pix.copy()
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont()
    font.setPointSize(8)
    font.setBold(True)
    painter.setFont(font)
    margin = 4
    text = badge
    metrics = painter.fontMetrics()
    tw = metrics.horizontalAdvance(text) + 10
    th = metrics.height() + 4
    x = out.width() - tw - margin
    y = margin
    if "未下载" in badge:
        fill = QColor(180, 70, 40, 220)
    elif "动态" in badge:
        fill = QColor(70, 100, 180, 220)
    else:
        fill = QColor(180, 70, 40, 220)
    painter.fillRect(x, y, tw, th, fill)
    painter.setPen(QColor(255, 240, 220))
    painter.drawText(x + 5, y + metrics.ascent() + 2, text)
    painter.end()
    return out


class ThumbnailGrid(QWidget):
    """可换行的图标网格，双击或回车触发 activated。"""

    activated = Signal(str)

    def __init__(self, icon_size: QSize, grid_size: QSize, parent=None):
        super().__init__(parent)
        self._icon_size = icon_size
        self._list = QListWidget()
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setFlow(QListWidget.LeftToRight)
        self._list.setWrapping(True)
        self._list.setResizeMode(QListWidget.Adjust)
        self._list.setMovement(QListWidget.Static)
        self._list.setUniformItemSizes(True)
        self._list.setIconSize(icon_size)
        self._list.setGridSize(grid_size)
        self._list.setSpacing(16)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.itemActivated.connect(self._on_activated)
        self._list.itemDoubleClicked.connect(self._on_activated)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._list)

    def clear(self):
        self._list.clear()

    def set_entries(self, entries: list[ThumbEntry]):
        self._list.clear()
        for entry in entries:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, entry.key)
            caption = entry.title
            if entry.subtitle:
                caption = f"{entry.title}\n{entry.subtitle}"
            item.setText(caption)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            item.setToolTip(entry.title if not entry.subtitle else f"{entry.title} — {entry.subtitle}")
            pix = load_thumb_pixmap(
                entry.image_path,
                self._icon_size,
                entry.title,
                entry.subtitle,
            )
            item.setIcon(QIcon(pix))
            self._list.addItem(item)

    def _on_activated(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole)
        if key:
            self.activated.emit(key)
