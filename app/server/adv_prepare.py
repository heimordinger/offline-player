# -*- coding: utf-8 -*-
"""手机端 ADV 开播前下载：后台任务 + 进度查询。"""
from __future__ import annotations

import os
import threading
from typing import Any

from app.core.adv_script import load_adv_commands
from app.core.game_activate import activate_game
from app.core.game_registry import get_game
from app.core.resources import (
    build_download_order,
    download_scene_resources,
    get_missing_resources,
    prepare_script_files,
)

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _key(game_id: str, scene_id: str) -> str:
    return f"{game_id}::{scene_id}"


def _basename(rel: str) -> str:
    return os.path.basename((rel or "").replace("\\", "/")) or rel


def _snapshot(job: dict[str, Any]) -> dict[str, Any]:
    total = int(job.get("total") or 0)
    done = int(job.get("done") or 0)
    pct = 100 if total <= 0 and job.get("status") == "done" else 0
    if total > 0:
        pct = min(99, int(done * 100 / total))
        if job.get("status") in ("done", "cancelled"):
            pct = 100 if job.get("status") == "done" else pct
    return {
        "game_id": job.get("game_id"),
        "scene_id": job.get("scene_id"),
        "status": job.get("status"),  # running | done | error | cancelled
        "total": total,
        "done": done,
        "ok": int(job.get("ok") or 0),
        "current": job.get("current") or "",
        "current_name": _basename(job.get("current") or ""),
        "phase": job.get("phase") or "",
        "message": job.get("message") or "",
        "error": job.get("error"),
        "percent": pct,
        "ready": job.get("status") in ("done", "error", "cancelled"),
        "cancellable": job.get("status") == "running",
    }


def _local_ready_job(game_id: str, scene_id: str) -> dict[str, Any]:
    """local_only：不访问 CDN，只看本地是否齐。"""
    missing = get_missing_resources(scene_id)
    # 中文机翻可选，不算阻塞
    hard = [m for m in missing if not str(m[0]).replace("\\", "/").endswith("_CN.txt")]
    n = len(hard)
    if n:
        msg = f"本地缺 {n} 个资源，将尽量播放（离线包不联网补下）"
    else:
        msg = "本地资源已就绪"
    return {
        "game_id": game_id,
        "scene_id": scene_id,
        "status": "done",
        "total": 0,
        "done": 0,
        "ok": 0,
        "current": "",
        "phase": "ready",
        "message": msg,
        "error": None,
        "cancel": False,
    }


def _run_job(key: str, scene_id: str) -> None:
    job = _JOBS[key]
    try:
        if job.get("cancel"):
            job["status"] = "cancelled"
            job["phase"] = "cancelled"
            job["message"] = "已取消下载"
            return

        job["phase"] = "script"
        job["message"] = "正在准备剧本…"
        job["current"] = ""
        prepare_script_files(scene_id)
        if job.get("cancel"):
            job["status"] = "cancelled"
            job["phase"] = "cancelled"
            job["message"] = "已取消下载"
            return

        commands: list[str] = []
        try:
            commands = load_adv_commands(scene_id)
        except FileNotFoundError:
            commands = []

        job["phase"] = "scan"
        job["message"] = "正在检查缺失资源…"
        ordered = build_download_order(scene_id, commands, 0)
        # 机翻 CN 常 404，不要拖死准备流程：有原文即可播
        ordered = [
            item
            for item in ordered
            if not str(item[0]).replace("\\", "/").endswith("_CN.txt")
        ]
        job["total"] = len(ordered)
        job["done"] = 0
        job["ok"] = 0

        if not ordered:
            job["status"] = "done"
            job["phase"] = "ready"
            job["message"] = "资源已就绪"
            return

        job["phase"] = "download"
        job["message"] = f"正在下载 {len(ordered)} 个文件…"

        def on_progress(done: int, total: int, ok: int) -> None:
            job["done"] = done
            job["total"] = total
            job["ok"] = ok
            job["message"] = f"正在下载 {done}/{total}"

        def on_item(rel: str) -> None:
            job["current"] = rel
            job["message"] = f"正在下载 {_basename(rel)}"

        ok, total = download_scene_resources(
            scene_id,
            on_progress=on_progress,
            on_item_start=on_item,
            ordered_missing=ordered,
            cancel_check=lambda: bool(job.get("cancel")),
        )
        if job.get("cancel"):
            job["status"] = "cancelled"
            job["phase"] = "cancelled"
            job["done"] = ok
            job["ok"] = ok
            job["total"] = total
            job["message"] = "已取消下载"
            job["current"] = ""
            return

        job["done"] = total
        job["ok"] = ok
        job["total"] = total
        still = [
            m
            for m in get_missing_resources(scene_id)
            if not str(m[0]).replace("\\", "/").endswith("_CN.txt")
        ]
        job["status"] = "done"
        job["phase"] = "ready"
        if still:
            job["message"] = f"下载完成 {ok}/{total}，仍缺 {len(still)} 个（将尽量播放）"
        else:
            job["message"] = f"下载完成 {ok}/{total}，可以开始播放"
        job["current"] = ""
    except Exception as exc:
        job["status"] = "error"
        job["phase"] = "error"
        job["error"] = str(exc)
        job["message"] = f"下载失败：{exc}"


def cancel_prepare(game_id: str, scene_id: str) -> dict[str, Any]:
    game = get_game(game_id)
    if game is None:
        raise KeyError(f"unknown game: {game_id}")
    key = _key(game_id, scene_id)
    with _LOCK:
        job = _JOBS.get(key)
        if not job:
            job = {
                "game_id": game_id,
                "scene_id": scene_id,
                "status": "cancelled",
                "total": 0,
                "done": 0,
                "ok": 0,
                "current": "",
                "phase": "cancelled",
                "message": "已取消",
                "error": None,
                "cancel": True,
            }
            _JOBS[key] = job
        else:
            job["cancel"] = True
            if job.get("status") == "running":
                job["message"] = "正在取消…"
            else:
                job["status"] = "cancelled"
                job["phase"] = "cancelled"
                job["message"] = "已取消"
        return _snapshot(job)


def start_or_status(
    game_id: str,
    scene_id: str,
    *,
    force: bool = False,
    cancel: bool = False,
) -> dict[str, Any]:
    """开始（或返回进行中）场景资源下载进度。"""
    from app.core.adapters import CAP_ADV_BEATS, adapter_info

    game = get_game(game_id)
    if game is None:
        raise KeyError(f"unknown game: {game_id}")
    caps = adapter_info(game.kind).capabilities
    if CAP_ADV_BEATS not in caps:
        raise KeyError(f"game kind {game.kind!r} does not support ADV prepare")
    activate_game(game)

    if cancel:
        return cancel_prepare(game_id, scene_id)

    key = _key(game_id, scene_id)

    with _LOCK:
        existing = _JOBS.get(key)
        if existing and existing.get("status") == "running":
            return _snapshot(existing)

        # 已成功/失败的任务默认不再自动重开，避免 404 资源无限循环；
        # 用户取消后再次进入则允许重新开始。
        if (
            existing
            and existing.get("status") in ("done", "error")
            and not force
        ):
            return _snapshot(existing)

        if game.local_only:
            job = _local_ready_job(game_id, scene_id)
            _JOBS[key] = job
            return _snapshot(job)

        # 仅在真正启动新任务时准备剧本（避免每次轮询都打 CDN）
        prepare_script_files(scene_id)
        try:
            commands = load_adv_commands(scene_id)
        except FileNotFoundError:
            commands = []
        ordered = build_download_order(scene_id, commands, 0)
        ordered = [
            item
            for item in ordered
            if not str(item[0]).replace("\\", "/").endswith("_CN.txt")
        ]
        if not ordered:
            job = {
                "game_id": game_id,
                "scene_id": scene_id,
                "status": "done",
                "total": int((existing or {}).get("total") or 0),
                "done": int((existing or {}).get("done") or 0),
                "ok": int((existing or {}).get("ok") or 0),
                "current": "",
                "phase": "ready",
                "message": "资源已就绪，无需下载"
                if not existing
                else (existing.get("message") or "资源已就绪"),
                "error": None,
                "cancel": False,
            }
            if existing and existing.get("status") == "done" and existing.get("total"):
                job["message"] = existing.get("message") or "下载完成，可以开始播放"
            _JOBS[key] = job
            return _snapshot(job)

        job = {
            "game_id": game_id,
            "scene_id": scene_id,
            "status": "running",
            "total": len(ordered),
            "done": 0,
            "ok": 0,
            "current": "",
            "phase": "download",
            "message": f"准备下载 {len(ordered)} 个文件…",
            "error": None,
            "cancel": False,
        }
        _JOBS[key] = job
        threading.Thread(target=_run_job, args=(key, scene_id), daemon=True).start()
        return _snapshot(job)
