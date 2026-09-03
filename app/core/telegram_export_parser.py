# -*- coding: utf-8 -*-
"""解析 Telegram Desktop 导出的 messages.html，建立媒体组与 #标签 关联。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

HASHTAG_RE = re.compile(r'ShowHashtag\(&quot;([^&]+)&quot;\)')
PHOTO_HREF_RE = re.compile(
    r'class="photo_wrap[^"]*"[^>]*href="([^"]+)"', re.I
)
VIDEO_HREF_RE = re.compile(
    r'class="video_file_wrap[^"]*"[^>]*href="([^"]+)"', re.I
)
MSG_BLOCK_RE = re.compile(
    r'<div class="message default clearfix(?P<joined> joined)?" id="message(?P<mid>\d+)">',
    re.I,
)
DATE_TITLE_RE = re.compile(r'title="(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})')


@dataclass
class ExportMediaFile:
    message_id: int
    kind: str
    rel_path: str
    exists: bool = False


@dataclass
class ExportMediaGroup:
    group_key: str
    message_ids: list[int] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    caption: str = ""
    date: str = ""
    files: list[ExportMediaFile] = field(default_factory=list)

    @property
    def character_tag(self) -> str:
        return category_tags(self.tags, _DEFAULT_ROOTS)[0] if category_tags(self.tags, _DEFAULT_ROOTS) else "未分类"

    @property
    def skin_tags(self) -> list[str]:
        cats = category_tags(self.tags, _DEFAULT_ROOTS)
        return cats[1:] if len(cats) > 1 else []


_DEFAULT_ROOTS = ("孤儿的工作", "孤子的工作")


def category_tags(tags: list[str], root_tags: list[str] | tuple[str, ...]) -> list[str]:
    roots = {t.lstrip("#") for t in root_tags}
    out = [t for t in tags if t.lstrip("#") not in roots]
    return out or list(tags)


def _strip_html_text(block: str) -> str:
    text_match = re.search(r'<div class="text">\s*(.*?)\s*</div>', block, re.S)
    if not text_match:
        return ""
    raw = text_match.group(1)
    raw = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _extract_tags(block: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for m in HASHTAG_RE.finditer(block):
        tag = m.group(1).strip()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _extract_media(block: str, export_dir: str) -> list[ExportMediaFile]:
    items: list[ExportMediaFile] = []
    mid_match = re.search(r'id="message(\d+)"', block)
    mid = int(mid_match.group(1)) if mid_match else 0

    for href in PHOTO_HREF_RE.findall(block):
        rel = href.replace("\\", "/")
        abs_path = os.path.join(export_dir, rel)
        items.append(
            ExportMediaFile(
                message_id=mid,
                kind="photo",
                rel_path=rel,
                exists=os.path.isfile(abs_path),
            )
        )

    for href in VIDEO_HREF_RE.findall(block):
        rel = href.replace("\\", "/")
        abs_path = os.path.join(export_dir, rel)
        items.append(
            ExportMediaFile(
                message_id=mid,
                kind="video",
                rel_path=rel,
                exists=os.path.isfile(abs_path),
            )
        )
    return items


def parse_messages_html(
    html_path: str,
    export_dir: str,
    root_tags: list[str] | None = None,
) -> list[ExportMediaGroup]:
    """按 joined 消息链合并相册；标签取自组内任意一条。"""
    if not os.path.isfile(html_path):
        return []
    with open(html_path, encoding="utf-8") as f:
        html = f.read()

    roots = list(root_tags or _DEFAULT_ROOTS)
    matches = list(MSG_BLOCK_RE.finditer(html))
    groups: list[ExportMediaGroup] = []
    current: ExportMediaGroup | None = None

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        block = html[start:end]
        joined = bool(m.group("joined"))
        mid = int(m.group("mid"))

        if not joined or current is None:
            if current and current.files:
                groups.append(current)
            current = ExportMediaGroup(group_key=f"m{mid}", message_ids=[mid])
        else:
            assert current is not None
            current.message_ids.append(mid)

        media = _extract_media(block, export_dir)
        current.files.extend(media)

        tags = _extract_tags(block)
        caption = _strip_html_text(block)
        if tags:
            current.tags = tags
        if caption and ("#" in caption or not current.caption):
            current.caption = caption

        date_m = DATE_TITLE_RE.search(block)
        if date_m and not current.date:
            current.date = date_m.group(1)

    if current and current.files:
        groups.append(current)

    for g in groups:
        g.message_ids = sorted(set(g.message_ids))
    return groups


def build_catalog_data(
    groups: list[ExportMediaGroup],
    export_dir: str,
    root_tags: list[str] | None = None,
) -> dict[str, Any]:
    roots = list(root_tags or _DEFAULT_ROOTS)
    by_tag: dict[str, list[str]] = {}
    catalog_groups = []

    for g in groups:
        cats = category_tags(g.tags, roots)
        char = cats[0] if cats else "未分类"
        entry = {
            "group_key": g.group_key,
            "message_ids": g.message_ids,
            "tags": g.tags,
            "category_tags": cats,
            "character_tag": char,
            "skin_tags": g.skin_tags,
            "caption": g.caption,
            "date": g.date,
            "files": [
                {
                    "message_id": f.message_id,
                    "kind": f.kind,
                    "path": f.rel_path,
                    "exists": f.exists,
                }
                for f in g.files
            ],
        }
        catalog_groups.append(entry)
        by_tag.setdefault(char, []).append(g.group_key)

    return {
        "version": 1,
        "export_dir": os.path.relpath(export_dir, os.path.dirname(export_dir)).replace("\\", "/")
        if not os.path.isabs(export_dir)
        else export_dir,
        "root_tags": roots,
        "group_count": len(catalog_groups),
        "groups": catalog_groups,
        "by_tag": {k: sorted(set(v)) for k, v in sorted(by_tag.items())},
    }


def resolve_export_dir(export_dir: str, project_root: str) -> str:
    if os.path.isabs(export_dir):
        return os.path.normpath(export_dir)
    return os.path.normpath(os.path.join(project_root, export_dir))


def build_catalog_from_export(
    export_dir: str,
    project_root: str,
    root_tags: list[str] | None = None,
) -> dict[str, Any]:
    export_abs = resolve_export_dir(export_dir, project_root)
    html_path = os.path.join(export_abs, "messages.html")
    groups = parse_messages_html(html_path, export_abs, root_tags)
    data = build_catalog_data(groups, export_abs, root_tags)
    data["export_dir"] = export_dir.replace("\\", "/")
    data["messages_html"] = os.path.join(export_dir, "messages.html").replace("\\", "/")
    return data


def save_catalog(catalog: dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)


def load_catalog(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def catalog_needs_refresh(catalog_path: str, export_dir: str, project_root: str) -> bool:
    if not os.path.isfile(catalog_path):
        return True
    export_abs = resolve_export_dir(export_dir, project_root)
    html_path = os.path.join(export_abs, "messages.html")
    if not os.path.isfile(html_path):
        return False
    try:
        return os.path.getmtime(html_path) > os.path.getmtime(catalog_path)
    except OSError:
        return True
