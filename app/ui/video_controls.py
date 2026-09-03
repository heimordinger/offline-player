# -*- coding: utf-8 -*-
"""录屏播放控件：进度、音量、±5 秒跳转。"""
from PySide6.QtCore import Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

SEEK_STEP_MS = 5000


def _fmt_ms(ms: int) -> str:
    if ms < 0:
        ms = 0
    sec = ms // 1000
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class VideoControlBar(QWidget):
    """底部紧凑控制条，不遮挡视频主体。"""

    def __init__(self, player: QMediaPlayer, audio: QAudioOutput, parent=None):
        super().__init__(parent)
        self._player = player
        self._audio = audio
        self._duration = 0
        self._seeking = False

        self.setFixedHeight(42)
        self.setStyleSheet(
            """
            VideoControlBar {
                background: rgba(10, 12, 20, 210);
                border-top: 1px solid rgba(90, 104, 136, 120);
            }
            QPushButton#vcBtn {
                background: rgba(36, 48, 72, 180);
                color: #e8e0d0;
                border: 1px solid #4a5878;
                border-radius: 4px;
                padding: 2px 7px;
                font-size: 11px;
                min-width: 28px;
            }
            QPushButton#vcBtn:hover { border-color: #c4a05a; }
            QLabel#vcTime {
                color: #a8b4c8;
                font-size: 11px;
                min-width: 78px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(50, 56, 72, 200);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 10px; height: 10px; margin: -4px 0;
                background: #f0ebe0;
                border: 1px solid #c4a05a;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(196, 160, 90, 180);
                border-radius: 2px;
            }
            """
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(6)

        self._back_btn = QPushButton("-5s")
        self._back_btn.setObjectName("vcBtn")
        self._back_btn.setToolTip("后退 5 秒 (←)")
        self._back_btn.clicked.connect(lambda: self.seek_relative(-SEEK_STEP_MS))

        self._play_btn = QPushButton("⏸")
        self._play_btn.setObjectName("vcBtn")
        self._play_btn.setFixedWidth(32)
        self._play_btn.setToolTip("播放/暂停 (Space)")
        self._play_btn.clicked.connect(self.toggle_playback)

        self._fwd_btn = QPushButton("+5s")
        self._fwd_btn.setObjectName("vcBtn")
        self._fwd_btn.setToolTip("前进 5 秒 (→)")
        self._fwd_btn.clicked.connect(lambda: self.seek_relative(SEEK_STEP_MS))

        self._progress = QSlider(Qt.Horizontal)
        self._progress.setRange(0, 0)
        self._progress.sliderPressed.connect(self._on_seek_start)
        self._progress.sliderReleased.connect(self._on_seek_end)
        self._progress.valueChanged.connect(self._on_seek_value)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("vcTime")
        self._time_label.setAlignment(Qt.AlignCenter)

        vol_lbl = QLabel("🔊")
        vol_lbl.setStyleSheet("font-size: 11px; color: #a8b4c8;")

        self._volume = QSlider(Qt.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setFixedWidth(72)
        self._volume.setValue(80)
        self._volume.valueChanged.connect(self._on_volume)

        row.addWidget(self._back_btn)
        row.addWidget(self._play_btn)
        row.addWidget(self._fwd_btn)
        row.addWidget(self._progress, 1)
        row.addWidget(self._time_label)
        row.addWidget(vol_lbl)
        row.addWidget(self._volume)

        player.positionChanged.connect(self._on_position)
        player.durationChanged.connect(self._on_duration)
        player.playbackStateChanged.connect(self._on_state)
        self._audio.setVolume(0.8)

    def _on_volume(self, value: int):
        self._audio.setVolume(max(0.0, min(1.0, value / 100.0)))

    def _on_duration(self, duration: int):
        self._duration = max(0, duration)
        self._progress.setRange(0, self._duration)
        self._refresh_time(self._player.position())

    def _on_position(self, pos: int):
        if not self._seeking:
            self._progress.blockSignals(True)
            self._progress.setValue(min(pos, self._duration))
            self._progress.blockSignals(False)
        self._refresh_time(pos)

    def _refresh_time(self, pos: int):
        self._time_label.setText(f"{_fmt_ms(pos)} / {_fmt_ms(self._duration)}")

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        self._seeking = False
        self._player.setPosition(self._progress.value())

    def _on_seek_value(self, value: int):
        if self._seeking:
            self._refresh_time(value)

    def _on_state(self, state):
        self._play_btn.setText("▶" if state != QMediaPlayer.PlaybackState.PlayingState else "⏸")

    def seek_relative(self, delta_ms: int):
        pos = self._player.position() + delta_ms
        if self._duration > 0:
            pos = max(0, min(pos, self._duration))
        self._player.setPosition(pos)

    def toggle_playback(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def reset(self):
        self._duration = 0
        self._progress.setRange(0, 0)
        self._progress.setValue(0)
        self._time_label.setText("00:00 / 00:00")
        self._play_btn.setText("▶")
