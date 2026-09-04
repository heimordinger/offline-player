# -*- coding: utf-8 -*-
"""启动加载界面：旋转动画 + 进度条 + 三行滚动步骤文字。"""
import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class SplashScreen(QWidget):
    # 滚动区三行槽位间距（像素）
    _SLOT_GAP = 42

    def __init__(self, width: int = 1300, height: int = 960, parent=None):
        super().__init__(parent)
        self._progress = 0.03
        self._anim_t = 0
        self._last_phase = ""
        self._log_lines: list[str] = ["正在启动…"]
        self._display_index = 0.0
        self._target_index = 0
        self._sub_detail = ""
        self.setFixedSize(width, height)
        self.setWindowTitle("离线播放器")
        self.setStyleSheet("background: #0a0c14;")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_progress(self, phase: str, progress: float, detail: str = "", sub_detail: str = ""):
        self._progress = max(0.0, min(1.0, progress))
        self._sub_detail = sub_detail

        if detail:
            line = detail
        elif sub_detail:
            line = f"{phase} · {sub_detail}"
        else:
            line = phase

        if not self._log_lines:
            self._log_lines = [line]
            self._last_phase = phase
            self._target_index = 0
            self._display_index = 0.0
        elif phase != self._last_phase:
            self._last_phase = phase
            if self._log_lines[-1] != line:
                self._log_lines.append(line)
                self._target_index = len(self._log_lines) - 1
        else:
            self._log_lines[-1] = line

    def _tick(self):
        self._anim_t += 1
        diff = self._target_index - self._display_index
        if abs(diff) > 0.004:
            self._display_index += diff * 0.14
        else:
            self._display_index = float(self._target_index)
        self.update()

    def _layout_y(self, h: int) -> dict[str, int]:
        """垂直分区，避免元素互相压住。"""
        mid = h // 2
        return {
            "title": mid - 200,
            "carousel_center": mid - 58,
            "spinner": mid + 36,
            "bar": mid + 88,
            "sub": mid + 132,
            "hint": h - 48,
        }

    def _draw_carousel(self, painter: QPainter, w: int, center_y: int):
        clip_w = min(760, w - 100)
        clip_x = (w - clip_w) // 2
        zone_h = self._SLOT_GAP * 2 + 36
        painter.setClipRect(clip_x, center_y - zone_h // 2, clip_w, zone_h)

        for i, text in enumerate(self._log_lines):
            dist = i - self._display_index
            if abs(dist) > 1.2:
                continue

            y_center = center_y + dist * self._SLOT_GAP
            t = min(1.0, abs(dist))

            if t < 0.25:
                size, bold = 13, True
                color = QColor(228, 236, 248)
            else:
                size, bold = 10, False
                color = QColor(110, 122, 145)

            font = QFont()
            font.setPointSize(size)
            font.setBold(bold)
            painter.setFont(font)

            metrics = painter.fontMetrics()
            elided = metrics.elidedText(text, Qt.ElideRight, clip_w)
            line_h = metrics.height()
            rect_top = int(y_center - line_h / 2)
            painter.setPen(color)
            painter.drawText(
                clip_x,
                rect_top,
                clip_w,
                line_h + 4,
                Qt.AlignHCenter | Qt.AlignVCenter,
                elided,
            )

        painter.setClipping(False)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        y = self._layout_y(h)
        painter.fillRect(0, 0, w, h, QColor(10, 12, 20))

        title_font = QFont()
        title_font.setPointSize(28)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(236, 224, 198))
        title = "DeepOne"
        tw = painter.fontMetrics().horizontalAdvance(title)
        painter.drawText((w - tw) // 2, y["title"], title)

        self._draw_carousel(painter, w, y["carousel_center"])

        cx, cy = w // 2, y["spinner"]
        for i in range(10):
            ang = self._anim_t / 12.0 + i * (6.28318 / 10)
            dot_x = cx + int(math.cos(ang) * 28)
            dot_y = cy + int(math.sin(ang) * 28)
            t = i / 9
            r = int(90 + 80 * t)
            g = int(130 + 70 * t)
            b = int(170 + 60 * t)
            painter.setBrush(QColor(r, g, b))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(dot_x - 5, dot_y - 5, 10, 10)

        bar_w = min(580, w - 80)
        bar_x = (w - bar_w) // 2
        bar_y = y["bar"]
        bar_h = 22
        pct = self._progress

        small_font = QFont()
        small_font.setPointSize(10)
        painter.setFont(small_font)
        painter.setPen(QColor(180, 190, 205))
        label_h = painter.fontMetrics().height()
        painter.drawText(bar_x, bar_y - label_h - 4, "总进度")
        pct_text = f"{int(pct * 100)}%"
        painter.drawText(
            bar_x + bar_w - painter.fontMetrics().horizontalAdvance(pct_text),
            bar_y - label_h - 4,
            pct_text,
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(32, 38, 54))
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 8, 8)
        fill_w = max(0, int(bar_w * pct))
        if fill_w > 0:
            painter.setBrush(QColor(120, 190, 255))
            painter.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 8, 8)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(196, 160, 90), 1))
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 8, 8)

        if self._sub_detail:
            detail_font = QFont()
            detail_font.setPointSize(9)
            painter.setFont(detail_font)
            painter.setPen(QColor(115, 125, 145))
            metrics = painter.fontMetrics()
            elided = metrics.elidedText(self._sub_detail, Qt.ElideRight, bar_w)
            sw = metrics.horizontalAdvance(elided)
            painter.drawText((w - sw) // 2, y["sub"], elided)

        painter.setPen(QColor(130, 140, 158))
        hint = "正在准备资源，请稍候…"
        hw = painter.fontMetrics().horizontalAdvance(hint)
        painter.drawText((w - hw) // 2, y["hint"], hint)

        painter.end()

    def close_splash(self):
        self._timer.stop()
        self.close()
