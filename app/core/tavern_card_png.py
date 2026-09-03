# -*- coding: utf-8 -*-
"""将 chara_card_v2 JSON 嵌入 PNG（SillyTavern 头像卡）。"""
from __future__ import annotations

import base64
import json
import os
import struct
import zlib


def _png_insert_chara_chunk(png_bytes: bytes, card: dict) -> bytes:
    payload = base64.b64encode(
        json.dumps(card, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    text_data = b"chara\0" + payload.encode("latin-1")
    chunk_type = b"tEXt"
    crc = zlib.crc32(chunk_type + text_data) & 0xffffffff
    chunk = (
        struct.pack(">I", len(text_data))
        + chunk_type
        + text_data
        + struct.pack(">I", crc)
    )
    marker = png_bytes.rfind(b"IEND")
    if marker < 4:
        raise ValueError("无效 PNG")
    return png_bytes[: marker - 4] + chunk + png_bytes[marker - 4:]


def write_tavern_png_card(card: dict, image_path: str, out_path: str) -> bool:
    """用预览图作头像，嵌入角色卡 JSON，生成可导入 SillyTavern 的 PNG。"""
    if not os.path.isfile(image_path):
        return False

    tmp_path = out_path + ".part.png"
    saved = False
    max_side = 512

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage

        img = QImage(image_path)
        if not img.isNull():
            if img.width() > max_side or img.height() > max_side:
                img = img.scaled(
                    max_side,
                    max_side,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            saved = img.save(tmp_path, "PNG")
    except ImportError:
        saved = False

    if not saved:
        try:
            from PIL import Image

            img = Image.open(image_path).convert("RGBA")
            img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            img.save(tmp_path, "PNG")
            saved = True
        except ImportError:
            return False
        except OSError:
            return False

    if not saved:
        return False

    try:
        with open(tmp_path, "rb") as f:
            raw = f.read()
        out_bytes = _png_insert_chara_chunk(raw, card)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(out_bytes)
        return True
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def find_category_card_face(jids: list[str], fetch: bool = False) -> str | None:
    """分类内按卡面编号排序，取第一张可用的 main.png。"""
    from app.core.preview_loader import card_face_local, card_id_from_story, fetch_card_face

    card_ids = sorted({card_id_from_story(jid) for jid in jids})
    for card_id in card_ids:
        path = card_face_local(card_id)
        if path:
            return path
        if fetch:
            path = fetch_card_face(card_id, quiet=True, skip_if_marked=False)
            if path:
                return path
    return None


def find_category_avatar(jids: list[str]) -> str | None:
    path = find_category_card_face(jids, fetch=True)
    if path:
        return path
    from app.core.preview_loader import first_local_adv_image
    from app.core.scene_catalog import episode_preview_path

    for jid in sorted(jids):
        cg = episode_preview_path(jid)
        if cg and os.path.isfile(cg):
            return cg
        local = first_local_adv_image(jid)
        if local:
            return local
    return None
