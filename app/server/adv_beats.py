# -*- coding: utf-8 -*-
"""把 ADV 台本编译为手机端「每一拍」（clickwait 之间的状态）。"""
from __future__ import annotations

import os
from typing import Any

from app.core.adv_script import load_adv_commands, resource_path, strip_adv_tags
from app.core.resources import local_resource_path
from app.core.script_dialogue import is_narration, normalize_line_text, normalize_speaker


def _media_url(root: str, abs_path: str | None) -> str | None:
    if not abs_path or not os.path.isfile(abs_path):
        return None
    try:
        rel = os.path.relpath(abs_path, root).replace("\\", "/")
    except ValueError:
        return None
    return f"/media/{rel}"


def _resolve_local(scene_id: str, rel: str) -> str | None:
    rel = (rel or "").replace("\\", "/").strip()
    if not rel:
        return None
    if rel == "color_0_0_0":
        path = resource_path(scene_id, rel)
        return path if path and os.path.isfile(path) else None
    return local_resource_path(scene_id, rel)


def compile_adv_beats(root: str, scene_id: str) -> dict[str, Any]:
    """
    返回:
      beats: 每一拍的绝对画面状态 + 对白
      missing: 台本里提到但本地没有的资源数
    """
    commands = load_adv_commands(scene_id)
    beats: list[dict[str, Any]] = []
    missing_rels: set[str] = set()

    speaker = ""
    text = ""
    bg_rel: str | None = None
    # slot -> list of file rels (intro[, loop])
    movies: dict[str, list[str]] = {}
    voice_rel: str | None = None

    def resolve_url(rel: str | None) -> str | None:
        if not rel:
            return None
        path = _resolve_local(scene_id, rel)
        if not path:
            missing_rels.add(rel)
            return None
        return _media_url(root, path)

    def snapshot() -> dict[str, Any]:
        movie_list = []
        for slot, files in movies.items():
            if not files:
                continue
            urls = []
            for f in files:
                u = resolve_url(f)
                if u:
                    urls.append(u)
            if urls:
                movie_list.append({"slot": slot, "urls": urls})
        return {
            "speaker": speaker,
            "text": text,
            "narration": is_narration(speaker, text),
            "bg_url": resolve_url(bg_rel),
            "movies": movie_list,
            "voice_url": resolve_url(voice_rel),
        }

    def emit():
        beats.append(snapshot())

    for raw in commands:
        line = raw.strip()
        if not line:
            continue
        parts = line.split(",")
        op = parts[0].strip()
        if op == "name":
            speaker = normalize_speaker(parts[1] if len(parts) > 1 else "")
            voice_rel = None
        elif op == "bg":
            if len(parts) > 1:
                bg_rel = parts[1].strip().replace("\\", "/")
        elif op == "msg":
            raw_text = ",".join(parts[2:]) if len(parts) > 2 else ""
            text = normalize_line_text(strip_adv_tags(raw_text))
            voice_rel = None
        elif op == "playvoice":
            if len(parts) > 2:
                voice_rel = parts[2].strip().replace("\\", "/")
        elif op == "movie":
            files = (
                [p.strip().replace("\\", "/") for p in parts[1].split(":") if p.strip()]
                if len(parts) > 1
                else []
            )
            slots = (
                [s.strip() for s in parts[2].split(":") if s.strip()]
                if len(parts) > 2
                else ["default"]
            )
            if files:
                slot = slots[0] if slots else "default"
                movies[slot] = files
        elif op == "movieoff":
            slot = parts[1].strip() if len(parts) > 1 else ""
            if slot.lower() == "all" or not slot:
                movies.clear()
            else:
                movies.pop(slot, None)
        elif op == "clickwait":
            emit()
            voice_rel = None

    if not beats and (text or bg_rel or movies):
        emit()

    return {
        "scene_id": scene_id,
        "kind": "adv",
        "mode": "adv",
        "beat_count": len(beats),
        "missing_resources": len(missing_rels),
        "beats": beats,
    }
