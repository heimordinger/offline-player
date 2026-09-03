# -*- coding: utf-8 -*-
"""本地录屏缩略图：从视频中间帧生成到 custom_videos/.thumbs/。"""
from __future__ import annotations

import contextlib
import io
import os
import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app.core.scene_catalog import CUSTOM_ID_PREFIX, custom_video_path, is_custom_video


def custom_thumb_path(custom_root: str, rel_path: str) -> str:
    safe = rel_path.replace("/", "_").replace("\\", "_")
    return os.path.join(custom_root, ".thumbs", safe + "_mid.jpg")


def _thumb_is_fresh(thumb: str, video: str) -> bool:
    try:
        return os.path.isfile(thumb) and os.path.getmtime(thumb) >= os.path.getmtime(video)
    except OSError:
        return False


def _capture_frame_cv2(video_path: str) -> QImage | None:
    try:
        import cv2
    except ImportError:
        return None
    with _silence_stderr():
        cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        if total > 2:
            cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
        elif fps > 0 and total > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, int((total / fps) * 500))

        ok, frame = cap.read()
        if not ok or frame is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        cap.release()

    if not ok or frame is None:
        return None
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = frame.shape[:2]
    if h <= 0 or w <= 0:
        return None
    return QImage(frame.data, w, h, frame.strides[0], QImage.Format_RGB888).copy()


def _capture_frame_qt(video_path: str) -> QImage | None:
    try:
        from PySide6.QtCore import QUrl, QEventLoop, QTimer
        from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame, QVideoSink
    except ImportError:
        return None

    loop = QEventLoop()
    result: list[QImage] = []
    state = {"seeked": False, "mid_ms": 0}
    player = QMediaPlayer()
    sink = QVideoSink()

    def on_duration(duration: int):
        if duration > 0 and not state["seeked"]:
            state["mid_ms"] = max(0, duration // 2)
            state["seeked"] = True
            player.setPosition(state["mid_ms"])

    def on_frame(frame: QVideoFrame):
        if result or not frame.isValid() or not state["seeked"]:
            return
        if state["mid_ms"] > 0 and player.position() < max(0, state["mid_ms"] - 1500):
            return
        img = frame.toImage()
        if not img.isNull():
            result.append(img.copy())
            player.stop()
            loop.quit()

    sink.videoFrameChanged.connect(on_frame)
    player.setVideoSink(sink)
    player.durationChanged.connect(on_duration)
    player.setSource(QUrl.fromLocalFile(video_path))
    QTimer.singleShot(10000, loop.quit)
    player.play()
    loop.exec()
    player.stop()
    return result[0] if result else None


@contextlib.contextmanager
def _silence_stderr():
    old = sys.stderr
    try:
        sys.stderr = io.StringIO()
        yield
    finally:
        sys.stderr = old


def ensure_custom_thumb(custom_root: str, rel_path: str) -> str | None:
    """生成或返回已有缩略图路径。"""
    video = custom_video_path(rel_path, custom_root)
    if not os.path.isfile(video):
        return None
    thumb = custom_thumb_path(custom_root, rel_path)
    if _thumb_is_fresh(thumb, video):
        return thumb

    image = _capture_frame_cv2(video)
    if image is None or image.isNull():
        image = _capture_frame_qt(video)
    if image is None or image.isNull():
        return None

    os.makedirs(os.path.dirname(thumb) or ".", exist_ok=True)
    if not image.save(thumb, "JPEG", 85):
        return None
    try:
        os.utime(thumb, (os.path.getmtime(video), os.path.getmtime(video)))
    except OSError:
        pass
    return thumb


def collect_missing_custom_thumbs(catalog) -> list[tuple[str, str]]:
    """返回 (jid, rel_path) 待生成缩略图的录屏列表。"""
    missing: list[tuple[str, str]] = []
    root = catalog._custom_root
    for jid in catalog.scan_custom_videos():
        if not is_custom_video(jid):
            continue
        rel = jid[len(CUSTOM_ID_PREFIX) :]
        video = custom_video_path(rel, root)
        thumb = custom_thumb_path(root, rel)
        if not os.path.isfile(video):
            continue
        if not _thumb_is_fresh(thumb, video):
            missing.append((jid, rel))
    return missing


class CustomThumbWorker(QThread):
    """后台批量生成录屏缩略图。"""

    thumb_ready = Signal(str, str)  # jid, thumb_path
    finished_batch = Signal(int, int)  # ok, total

    def __init__(self, catalog, jobs: list[tuple[str, str]] | None = None):
        super().__init__()
        self._catalog = catalog
        self._jobs = jobs

    def run(self):
        jobs = self._jobs
        if jobs is None:
            jobs = collect_missing_custom_thumbs(self._catalog)
        total = len(jobs)
        ok = 0
        root = self._catalog._custom_root
        for jid, rel in jobs:
            path = ensure_custom_thumb(root, rel)
            if path:
                ok += 1
                self.thumb_ready.emit(jid, path)
        self.finished_batch.emit(ok, total)
