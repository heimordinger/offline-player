# -*- coding: utf-8 -*-
"""ADV 脚本读取与文本处理。"""
import json
import os
import re
from pathlib import Path

from project_paths import active, load_settings

RUBY_RE = re.compile(r"<ruby>(.*?)</ruby>")


def use_chinese_script() -> bool:
    try:
        return load_settings().get("翻译api", {}).get("use_translate", "yes") == "yes"
    except Exception:
        return True


def strip_adv_tags(text: str) -> str:
    text = text.replace("<outline width=2 color=black>", "").replace("</outline>", "")
    text = text.replace("<size=31>", "").replace("</size>", "")
    text = text.replace("<size=27>", "").replace("</size>", "")
    for match in RUBY_RE.findall(text):
        text = text.replace(f"<ruby>{match}</ruby>", match.split("|")[0])
    return text


def unescape_script_escapes(text: str) -> str:
    """只还原台本里的 \\n / \\t / \\\"，不动非 ASCII 字节。"""
    return (
        text.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def fix_mojibake_text(text: str) -> str:
    """修复 UTF-8 被 unicode_escape / latin-1 误解码后的乱码（å½ 等）。"""
    if not text or not any(0x80 <= ord(c) <= 0xFF for c in text):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _split_script_lines(text: str) -> list[str]:
    """只按 CR/LF 分行。str.splitlines() 会把乱码里的 U+0085 当成换行，切碎 UTF-8。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def read_text_file(path: str) -> list[str]:
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        for enc in ("utf-8-sig", "utf-8", "cp932"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")
    return [unescape_script_escapes(fix_mojibake_text(line)) for line in _split_script_lines(text)]


def load_adv_commands(json_id: str) -> list[str]:
    json_path = os.path.join(active.json_dir, json_id + ".json")
    with open(json_path, encoding="utf8") as f:
        data = json.load(f)
    script_name = None
    for resource in data.get("resource", []):
        fn = resource.get("fileName", "")
        if "text" in fn.lower():
            script_name = fn.replace("\\", "/")
            break
    if not script_name:
        raise FileNotFoundError(f"未找到剧本文本: {json_id}")

    if use_chinese_script():
        txt_rel = script_name.replace(".txt", "_CN.txt")
    else:
        txt_rel = script_name
    txt_path = os.path.join(active.resource_dir, json_id, txt_rel)
    if not os.path.isfile(txt_path):
        txt_path = os.path.join(active.resource_dir, json_id, script_name)
    if not os.path.isfile(txt_path):
        raise FileNotFoundError(f"剧本不存在: {txt_path}")

    return read_text_file(txt_path)


def resource_path(json_id: str, rel: str) -> str:
    rel = rel.replace("\\", "/")
    if rel == "color_0_0_0":
        from project_paths import LEGACY_DIR

        return os.path.join(LEGACY_DIR, "assets", "color_0_0_0.jpg")
    return os.path.join(active.resource_dir, json_id, rel)
