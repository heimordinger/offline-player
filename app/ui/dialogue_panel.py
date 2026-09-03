# -*- coding: utf-8 -*-
"""视觉小说风格对话框：悬浮于立绘下方，可调透明度。"""
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from project_paths import SETTINGS_PATH, load_settings

ALPHA_MIN = 20
ALPHA_MAX = 230


def _transparent_label(text: str = "", object_name: str = "") -> QLabel:
    lbl = QLabel(text)
    if object_name:
        lbl.setObjectName(object_name)
    lbl.setAttribute(Qt.WA_TranslucentBackground, True)
    lbl.setStyleSheet("background: transparent; border: none;")
    return lbl


class _NamePlate(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._alpha = 145
        self._text = ""
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumHeight(38)

    def set_alpha(self, alpha: int):
        self._alpha = min(255, alpha + 25)
        self.update()

    def set_text(self, text: str):
        self._text = text.strip()
        self.setVisible(bool(self._text))
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QFont, QFontMetrics

        if not self._text:
            return QSize(0, 0)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        fm = QFontMetrics(font)
        w = max(120, fm.horizontalAdvance(self._text) + 36)
        return QSize(w, 38)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, _event):
        if not self._text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(36, 50, 88, self._alpha))
        p.setPen(QPen(QColor(196, 160, 90, 180), 1))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        p.setPen(QColor(255, 236, 200))
        font = p.font()
        font.setPointSize(11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignCenter, self._text)


class DialoguePanel(QWidget):
    """底部悬浮台词框 + 姓名牌 + 透明度滑块（自绘半透明底）。"""

    alpha_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alpha = self._load_alpha()
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 14, 22, 18)
        root.setSpacing(8)

        top = QHBoxLayout()
        self._name_plate = _NamePlate(self)
        top.addWidget(self._name_plate, 0, Qt.AlignLeft | Qt.AlignBottom)
        top.addStretch(1)
        alpha_row = QHBoxLayout()
        self._alpha_lbl = _transparent_label("透明", "vnMuted")
        self._alpha_slider = QSlider(Qt.Horizontal)
        self._alpha_slider.setRange(0, 100)
        self._alpha_slider.setFixedWidth(130)
        self._alpha_slider.valueChanged.connect(self._on_slider)
        self._alpha_pct = _transparent_label("", "vnMuted")
        self._alpha_pct.setMinimumWidth(36)
        alpha_row.addWidget(self._alpha_lbl)
        alpha_row.addWidget(self._alpha_slider)
        alpha_row.addWidget(self._alpha_pct)
        top.addLayout(alpha_row)
        root.addLayout(top)

        self._text_label = _transparent_label("", "vnText")
        self._text_label.setWordWrap(True)
        self._text_label.setMinimumHeight(72)
        root.addWidget(self._text_label, 1)

        self._hint_label = _transparent_label("", "vnHint")
        self._hint_label.setAlignment(Qt.AlignRight)
        root.addWidget(self._hint_label)

        self._sync_slider()
        self._apply_label_styles()
        self._name_plate.set_alpha(self._alpha)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(12, 16, 30, self._alpha))
        p.setPen(QPen(QColor(196, 160, 90, 200), 1))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 14, 14)

    @staticmethod
    def _load_alpha() -> int:
        try:
            v = int(load_settings().get("对话框透明度", 145))
        except (TypeError, ValueError):
            v = 145
        return max(ALPHA_MIN, min(ALPHA_MAX, v))

    def _alpha_to_slider(self, alpha: int) -> int:
        if ALPHA_MAX <= ALPHA_MIN:
            return 50
        return int((alpha - ALPHA_MIN) / (ALPHA_MAX - ALPHA_MIN) * 100)

    def _slider_to_alpha(self, pos: int) -> int:
        t = max(0, min(100, pos)) / 100.0
        return int(ALPHA_MIN + t * (ALPHA_MAX - ALPHA_MIN))

    def _sync_slider(self):
        self._alpha_slider.blockSignals(True)
        self._alpha_slider.setValue(self._alpha_to_slider(self._alpha))
        self._alpha_slider.blockSignals(False)
        self._alpha_pct.setText(f"{self._alpha_slider.value()}%")

    def _apply_label_styles(self):
        self.setStyleSheet(
            """
            QLabel#vnText {
                color: #f8f8fc;
                font-size: 20px;
                background: transparent;
                border: none;
            }
            QLabel#vnHint {
                color: rgba(200, 210, 225, 180);
                font-size: 12px;
                background: transparent;
                border: none;
            }
            QLabel#vnMuted {
                color: rgba(190, 200, 215, 200);
                font-size: 11px;
                background: transparent;
                border: none;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(50, 56, 72, 160);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 14px; margin: -5px 0;
                background: #f5f0e6;
                border: 1px solid #c4a05a;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(196, 160, 90, 180);
                border-radius: 3px;
            }
            """
        )

    def _on_slider(self, value: int):
        self._alpha = self._slider_to_alpha(value)
        self._alpha_pct.setText(f"{value}%")
        self._name_plate.set_alpha(self._alpha)
        self.update()
        self.alpha_changed.emit(self._alpha)

    def save_alpha(self):
        try:
            settings = load_settings()
            settings["对话框透明度"] = int(self._alpha)
            with open(SETTINGS_PATH, "w", encoding="utf8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        except OSError:
            pass

    def set_speaker(self, name: str):
        self._name_plate.set_text(name)

    def set_text(self, text: str):
        self._text_label.setText(text.replace("\\n", "\n"))

    def set_hint(self, text: str):
        self._hint_label.setText(text)

    def alpha_value(self) -> int:
        return self._alpha
