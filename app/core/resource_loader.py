# -*- coding: utf-8 -*-
"""播放前在后台下载场景资源。"""
import threading

from PySide6.QtCore import QThread, Signal

from app.core.resources import (
    build_download_order,
    collect_script_resource_rels,
    download_scene_resources,
    get_missing_resources,
)


class ResourceDownloadWorker(QThread):
    progress = Signal(int, int, int)
    item_started = Signal(str)
    finished_ok = Signal(str)
    cancelled = Signal(str)
    failed = Signal(str, str)

    def __init__(
        self,
        json_id: str,
        commands: list[str] | None = None,
        cmd_index: int = 0,
    ):
        super().__init__()
        self._json_id = json_id
        self._commands: list[str] = list(commands or [])
        self._cmd_index = cmd_index
        self._cursor_lock = threading.Lock()
        self._current_item = ""
        self._cancel = False

    def set_play_cursor(self, cmd_index: int, commands: list[str] | None = None):
        with self._cursor_lock:
            self._cmd_index = cmd_index
            if commands is not None:
                self._commands = list(commands)

    def cancel(self):
        self._cancel = True

    def _priority_rels(self) -> list[str]:
        with self._cursor_lock:
            return collect_script_resource_rels(self._commands, self._cmd_index)

    def run(self):
        try:
            with self._cursor_lock:
                ordered = build_download_order(
                    self._json_id, self._commands, self._cmd_index
                )
            if not ordered:
                self.finished_ok.emit(self._json_id)
                return

            def on_prog(done, total, ok):
                self.progress.emit(done, total, ok)

            def on_item(rel: str):
                self._current_item = rel
                self.item_started.emit(rel)

            ok, total = download_scene_resources(
                self._json_id,
                on_progress=on_prog,
                on_item_start=on_item,
                cancel_check=lambda: self._cancel,
                ordered_missing=ordered,
                priority_callback=self._priority_rels,
            )
            if self._cancel:
                print(f"[下载] {self._json_id}: 已终止 ({ok}/{total})")
                self.cancelled.emit(self._json_id)
                return
            if ok < total:
                print(f"[下载] {self._json_id}: 完成 {ok}/{total}，缺失资源将播放时重试")
            self.finished_ok.emit(self._json_id)
        except Exception as exc:
            self.failed.emit(self._json_id, str(exc))
