# -*- coding: utf-8 -*-
"""从 ADV 台本解析对白行。"""
from __future__ import annotations

import re

from app.core.adv_script import strip_adv_tags

RUBY_RE = re.compile(r"<ruby>(.*?)</ruby>")


def normalize_speaker(raw: str) -> str:
    text = strip_adv_tags(raw).strip()
    return text


def normalize_line_text(text: str) -> str:
    return text.replace("\\n", "\n").strip()


def is_narration(speaker: str, text: str) -> bool:
    if not speaker:
        return True
    if speaker in ("0", "旁白", "ナレーション"):
        return True
    return False


def parse_script_dialogue(lines: list[str]) -> list[dict]:
    """解析台本为对白列表：speaker, text, narration。"""
    dialogues: list[dict] = []
    speaker = ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("name,"):
            parts = line.split(",")
            speaker = normalize_speaker(parts[1] if len(parts) > 1 else "")
            continue
        if not line.startswith("msg,"):
            continue
        parts = line.split(",")
        if len(parts) < 3:
            continue
        text = normalize_line_text(strip_adv_tags(parts[2]))
        if not text:
            continue
        dialogues.append(
            {
                "speaker": speaker,
                "text": text,
                "narration": is_narration(speaker, text),
            }
        )
    return dialogues


def speaker_matches(speaker: str, aliases: list[str]) -> bool:
    if not speaker or not aliases:
        return False
    s = speaker.replace(" ", "").replace("　", "")
    for alias in aliases:
        a = alias.replace(" ", "").replace("　", "")
        if not a:
            continue
        if s == a or a in s or s in a:
            return True
    return False


def pick_primary_name(name_field: str) -> str:
    """category_names 里 + 分隔的第一个名作为主角色名。"""
    for part in name_field.split("+"):
        part = part.strip()
        if part:
            return part
    return name_field.strip()


def split_aliases(name_field: str) -> list[str]:
    parts = [p.strip() for p in name_field.split("+") if p.strip()]
    return parts or [name_field.strip()]


def format_dialogue_block(dialogues: list[dict], max_lines: int = 0) -> str:
    lines: list[str] = []
    for d in dialogues:
        if max_lines and len(lines) >= max_lines:
            break
        if d["narration"]:
            lines.append(d["text"])
        else:
            lines.append("「" + d["speaker"] + "」" + d["text"])
    return "\n".join(lines)


def build_mes_example(
    dialogues: list[dict],
    char_aliases: list[str],
    max_blocks: int = 3,
) -> str:
    """生成 SillyTavern mes_example（{{char}} / {{user}}）。"""
    blocks: list[str] = []
    pending_user: str | None = None
    for d in dialogues:
        if d["narration"]:
            if pending_user is None:
                pending_user = d["text"]
            else:
                pending_user = f"{pending_user}\n{d['text']}"
            continue
        if speaker_matches(d["speaker"], char_aliases):
            user_line = pending_user or "……"
            char_line = d["text"]
            blocks.append(f"<START>\n{{{{user}}}}: {user_line}\n{{{{char}}}}: {char_line}")
            pending_user = None
            if len(blocks) >= max_blocks:
                break
        else:
            other = "「" + d["speaker"] + "」" + d["text"]
            pending_user = other if pending_user is None else f"{pending_user}\n{other}"
    return "\n".join(blocks)

