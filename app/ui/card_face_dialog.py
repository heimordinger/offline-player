# -*- coding: utf-8 -*-
"""全屏查看角色卡面。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout


def show_card_face(parent, image_path: str, title: str = "角色卡面") -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setStyleSheet("QDialog { background: #0c0e16; } QLabel { background: #06080e; }")

    label = QLabel()
    label.setAlignment(Qt.AlignCenter)
    pix = QPixmap(image_path)
    if pix.isNull():
        label.setText("无法加载卡面图片")
        label.setStyleSheet("color: #c0c8d8; font-size: 14px; padding: 32px;")
    else:
        max_w = min(1200, parent.width() if parent else 1200)
        max_h = min(900, parent.height() if parent else 900)
        label.setPixmap(
            pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.addWidget(label)
    dlg.resize(label.sizeHint().width() + 24, label.sizeHint().height() + 24)
    dlg.exec()
