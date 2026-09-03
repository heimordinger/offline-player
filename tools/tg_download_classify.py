# -*- coding: utf-8 -*-
"""从 Telegram 群下载媒体，并按聊天标签 + 同一媒体组归类。

分类依据（与你截图一致）：
1. 消息 caption / 文本中的 #标签
2. 同一媒体相册 grouped_id（图+多视频同组）；无相册则用单条 message_id

输出目录（默认项目根下 tg_library/）：
  files/<group_key>/meta.json + 媒体文件
  by_tag/<标签>/ -> 指向各 group 的索引
  catalog.json

用法：
  1. 复制 tg_config.example.json 为 tg_config.json 并填写 api_id / api_hash
  2. py -3.13 tools/tg_download_classify.py
  3. 首次运行会要求手机号登录（验证码）

可选：仅根据已有 ChatExport 的 messages 做归类（不下新文件）：
  py -3.13 tools/tg_download_classify.py --from-export ChatExport_xxxx
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CONFIG_PATH = os.path.join(TOOLS_DIR, "tg_config.json")
HASHTAG_RE = re.compile(r"#([^\s#]+)")
SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@dataclass
class MediaItem:
    message_id: int
    grouped_id: int | None
    kind: str
    file_name: str
    size: int | None = None
    local_path: str | None = None
    source_path: str | None = None


@dataclass
class MediaGroup:
    group_key: str
    grouped_id: int | None
    message_ids: list[int] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    caption: str = ""
    date: str = ""
    items: list[MediaItem] = field(default_factory=list)


def load_config(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        example = os.path.join(TOOLS_DIR, "tg_config.example.json")
        print(f"缺少配置文件: {path}")
        print(f"请复制 {example} 为 tg_config.json。")
        print("my.telegram.org 申请失败时，example 里已含 Telegram Desktop 官方凭证，可直接用。")
        raise SystemExit(2)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("api_id") or not cfg.get("api_hash"):
        print("请在 tg_config.json 填写 api_id 与 api_hash。")
        print("若 my.telegram.org 一直 ERROR，复制 tg_config.example.json 里的 Desktop 凭证即可。")
        raise SystemExit(2)
    return cfg


def sanitize(name: str, fallback: str = "untitled") -> str:
    name = SAFE_NAME_RE.sub("_", name).strip(" ._")
    name = name.replace("&", "和").replace(" ", "_")
    return name or fallback


def extract_hashtags_from_text(text: str) -> list[str]:
    if not text:
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for m in HASHTAG_RE.finditer(text):
        tag = m.group(1).strip()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def category_tags(tags: list[str], root_tags: list[str]) -> list[str]:
    roots = {t.lstrip("#") for t in root_tags}
    out = [t for t in tags if t.lstrip("#") not in roots]
    return out or list(tags)


def group_key_for(grouped_id: int | None, message_id: int) -> str:
    if grouped_id is not None:
        return f"g{grouped_id}"
    return f"m{message_id}"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_json(path: str, data: Any) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_catalog(groups: list[MediaGroup], output_dir: str, root_tags: list[str]) -> dict:
    by_tag: dict[str, list[str]] = defaultdict(list)
    catalog_groups = []
    for g in groups:
        cats = category_tags(g.tags, root_tags)
        entry = {
            "group_key": g.group_key,
            "grouped_id": g.grouped_id,
            "message_ids": g.message_ids,
            "tags": g.tags,
            "category_tags": cats,
            "caption": g.caption,
            "date": g.date,
            "dir": os.path.join("files", g.group_key).replace("\\", "/"),
            "files": [
                {
                    "message_id": it.message_id,
                    "kind": it.kind,
                    "file_name": it.file_name,
                    "size": it.size,
                    "local_path": (
                        os.path.relpath(it.local_path, output_dir).replace("\\", "/")
                        if it.local_path
                        else None
                    ),
                }
                for it in g.items
            ],
        }
        catalog_groups.append(entry)
        for tag in cats:
            by_tag[sanitize(tag)].append(g.group_key)

    return {
        "version": 1,
        "group_count": len(catalog_groups),
        "groups": catalog_groups,
        "by_tag": {k: sorted(set(v)) for k, v in sorted(by_tag.items())},
    }


def write_group_outputs(groups: list[MediaGroup], output_dir: str, root_tags: list[str]) -> None:
    files_root = os.path.join(output_dir, "files")
    tag_root = os.path.join(output_dir, "by_tag")
    ensure_dir(files_root)
    ensure_dir(tag_root)

    catalog = build_catalog(groups, output_dir, root_tags)
    write_json(os.path.join(output_dir, "catalog.json"), catalog)

    for g in groups:
        gdir = os.path.join(files_root, g.group_key)
        ensure_dir(gdir)
        meta = {
            "group_key": g.group_key,
            "grouped_id": g.grouped_id,
            "message_ids": g.message_ids,
            "tags": g.tags,
            "category_tags": category_tags(g.tags, root_tags),
            "caption": g.caption,
            "date": g.date,
            "files": [
                {
                    "message_id": it.message_id,
                    "kind": it.kind,
                    "file_name": it.file_name,
                    "size": it.size,
                    "path": os.path.basename(it.local_path) if it.local_path else it.file_name,
                }
                for it in g.items
            ],
        }
        write_json(os.path.join(gdir, "meta.json"), meta)

    # by_tag/<tag>/<group_key>.json 写入轻量索引，避免 Windows 符号链接权限问题
    for tag, keys in catalog["by_tag"].items():
        tdir = os.path.join(tag_root, tag)
        ensure_dir(tdir)
        for key in keys:
            g = next(x for x in groups if x.group_key == key)
            write_json(
                os.path.join(tdir, f"{key}.json"),
                {
                    "group_key": key,
                    "tags": g.tags,
                    "caption": g.caption,
                    "files_dir": os.path.join("files", key).replace("\\", "/"),
                    "file_count": len(g.items),
                },
            )

    print(f"分类完成: {len(groups)} 组, {len(catalog['by_tag'])} 个标签")
    print(f"输出目录: {output_dir}")


# ---------------------------------------------------------------------------
# Telethon 下载
# ---------------------------------------------------------------------------


def media_kind_and_name(message) -> tuple[str, str] | None:
    if not message or not message.media:
        return None
    doc = getattr(message, "document", None)
    if message.photo:
        return "photo", f"{message.id}.jpg"
    if doc:
        name = None
        for attr in getattr(doc, "attributes", []) or []:
            fname = getattr(attr, "file_name", None)
            if fname:
                name = fname
                break
        mime = getattr(doc, "mime_type", "") or ""
        if not name:
            ext = ".bin"
            if "video" in mime:
                ext = ".mp4"
            elif "audio" in mime:
                ext = ".mp3"
            elif "image" in mime:
                ext = ".jpg"
            elif "json" in mime:
                ext = ".json"
            elif "zip" in mime:
                ext = ".zip"
            name = f"{message.id}{ext}"
        if "video" in mime:
            kind = "video"
        elif "image" in mime or name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            kind = "image"
        elif name.lower().endswith((".json", ".json1")):
            kind = "json"
        elif name.lower().endswith((".zip", ".rar", ".7z")):
            kind = "archive"
        else:
            kind = "file"
        return kind, name
    return "file", f"{message.id}.bin"


def extract_hashtags_telethon(message) -> list[str]:
    text = message.message or ""
    tags: list[str] = []
    seen: set[str] = set()
    for e in message.entities or []:
        et = type(e).__name__
        if "Hashtag" in et:
            chunk = text[e.offset : e.offset + e.length]
            tag = chunk.lstrip("#").strip()
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
    if not tags:
        tags = extract_hashtags_from_text(text)
    return tags


async def collect_groups_telethon(
    client, chat, limit: int | None
) -> tuple[dict[str, MediaGroup], dict[int, Any]]:
    """返回 (groups, message_by_id)。message 对象留给下载阶段复用。"""
    from telethon.tl.custom.message import Message

    buckets: dict[str, MediaGroup] = {}
    pending_tags: dict[str, list[str]] = {}
    pending_caption: dict[str, str] = {}
    message_by_id: dict[int, Any] = {}

    async for message in client.iter_messages(chat, limit=limit):
        if not isinstance(message, Message) or not message.media:
            continue
        info = media_kind_and_name(message)
        if not info:
            continue
        kind, file_name = info
        gid = message.grouped_id
        key = group_key_for(gid, message.id)
        tags = extract_hashtags_telethon(message)
        caption = message.message or ""
        message_by_id[message.id] = message

        if key not in buckets:
            buckets[key] = MediaGroup(
                group_key=key,
                grouped_id=gid,
                date=message.date.isoformat() if message.date else "",
            )
        g = buckets[key]
        if message.id not in g.message_ids:
            g.message_ids.append(message.id)
        g.items.append(
            MediaItem(
                message_id=message.id,
                grouped_id=gid,
                kind=kind,
                file_name=file_name,
                size=getattr(getattr(message, "file", None), "size", None),
            )
        )
        if tags:
            pending_tags[key] = tags
            pending_caption[key] = caption

    for key, g in buckets.items():
        if key in pending_tags:
            g.tags = pending_tags[key]
            g.caption = pending_caption.get(key, "")
        g.message_ids.sort()
        g.items.sort(key=lambda x: x.message_id)
    return buckets, message_by_id


async def download_groups(
    client,
    groups: dict[str, MediaGroup],
    message_by_id: dict[int, Any],
    output_dir: str,
    workers: int,
    skip_existing: bool,
    min_file_bytes: int,
) -> None:
    sem = asyncio.Semaphore(max(1, workers))
    files_root = os.path.join(output_dir, "files")
    ensure_dir(files_root)

    by_mid: dict[int, tuple[MediaGroup, MediaItem]] = {}
    for g in groups.values():
        for it in g.items:
            by_mid[it.message_id] = (g, it)

    async def one(mid: int, g: MediaGroup, it: MediaItem):
        gdir = os.path.join(files_root, g.group_key)
        ensure_dir(gdir)
        base = sanitize(it.file_name, fallback=f"{mid}.bin")
        dest = os.path.join(gdir, f"{mid}_{base}")
        if skip_existing and os.path.isfile(dest) and os.path.getsize(dest) > 0:
            if not (min_file_bytes and os.path.getsize(dest) < min_file_bytes):
                it.local_path = dest
                it.size = os.path.getsize(dest)
                print(f"[跳过] 已存在 {g.group_key}/{os.path.basename(dest)}")
                return
        msg = message_by_id.get(mid)
        if msg is None:
            print(f"[失败] 无消息对象 message_id={mid}")
            return
        async with sem:
            try:
                path = await client.download_media(msg, file=dest)
                if path and os.path.isfile(path):
                    it.local_path = path
                    it.size = os.path.getsize(path)
                    print(f"[下载] {g.group_key}/{os.path.basename(path)} ({it.size} bytes)")
                else:
                    print(f"[失败] message_id={mid}")
            except Exception as exc:
                print(f"[失败] message_id={mid}: {exc}")

    tasks = [one(mid, g, it) for mid, (g, it) in by_mid.items()]
    batch = 64
    for i in range(0, len(tasks), batch):
        await asyncio.gather(*tasks[i : i + batch])


async def run_telethon(cfg: dict[str, Any]) -> int:
    try:
        from telethon import TelegramClient
    except ImportError:
        print("未安装 telethon，请执行: py -3.13 -m pip install telethon")
        return 1

    proxy = None
    if cfg.get("proxy"):
        p = cfg["proxy"]
        import socks

        ptype = str(p.get("proxy_type", "socks5")).lower()
        sock_type = socks.SOCKS5 if "socks5" in ptype else socks.HTTP
        proxy = (
            sock_type,
            p.get("addr", "127.0.0.1"),
            int(p.get("port", 1080)),
            True,
            p.get("username"),
            p.get("password"),
        )

    session = os.path.join(TOOLS_DIR, cfg.get("session", "tg_session"))
    output_dir = cfg.get("output_dir", "tg_library")
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(PROJECT_ROOT, output_dir)

    client = TelegramClient(
        session,
        int(cfg["api_id"]),
        str(cfg["api_hash"]),
        proxy=proxy,
        device_model=str(cfg.get("device_model", "Desktop")),
        system_version=str(cfg.get("system_version", "Windows 10")),
        app_version=str(cfg.get("app_version", "5.0 x64")),
        lang_code=str(cfg.get("lang_code", "en")),
        system_lang_code=str(cfg.get("system_lang_code", "en-US")),
    )
    await client.start()
    chat = cfg.get("chat") or "孤儿的工作"
    print(f"已登录，扫描对话: {chat}")
    entity = await client.get_entity(chat)

    limit = cfg.get("limit")
    groups, message_by_id = await collect_groups_telethon(client, entity, limit)
    print(f"发现媒体组: {len(groups)}，媒体数: {len(message_by_id)}")

    await download_groups(
        client,
        groups,
        message_by_id,
        output_dir,
        workers=int(cfg.get("download_workers", 8)),
        skip_existing=bool(cfg.get("skip_existing", True)),
        min_file_bytes=int(cfg.get("min_file_bytes", 0)),
    )

    ordered = sorted(groups.values(), key=lambda g: min(g.message_ids) if g.message_ids else 0)
    write_group_outputs(ordered, output_dir, list(cfg.get("root_tags") or []))
    await client.disconnect()
    return 0


# ---------------------------------------------------------------------------
# 从官方 ChatExport 归类（不下新文件，利用已有文件 + 消息标签）
# ---------------------------------------------------------------------------


def find_export_messages(export_dir: str) -> list[dict]:
    candidates = [
        os.path.join(export_dir, "result.json"),
        os.path.join(export_dir, "messages.json"),
    ]
    for root, _, files in os.walk(export_dir):
        for name in files:
            if name in ("result.json", "messages.json"):
                candidates.append(os.path.join(root, name))
    seen: set[str] = set()
    messages: list[dict] = []
    for path in candidates:
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            print(f"[跳过] 无法读 {path}: {exc}")
            continue
        if isinstance(data, dict) and "messages" in data:
            messages.extend(data["messages"])
        elif isinstance(data, list):
            messages.extend(data)
    return messages


def export_text(msg: dict) -> str:
    text = msg.get("text")
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts = []
        for chunk in text:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                parts.append(str(chunk.get("text", "")))
        return "".join(parts)
    return ""


def export_hashtags(msg: dict) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for ent in msg.get("text_entities") or []:
        if ent.get("type") == "hashtag":
            tag = str(ent.get("text", "")).lstrip("#").strip()
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
    if not tags:
        tags = extract_hashtags_from_text(export_text(msg))
    return tags


def run_from_export(export_dir: str, output_dir: str, root_tags: list[str]) -> int:
    if not os.path.isdir(export_dir):
        print(f"导出目录不存在: {export_dir}")
        return 1
    messages = find_export_messages(export_dir)
    if not messages:
        print("未找到 messages/result.json")
        return 1

    # 官方导出通常无 grouped_id：把「带标签的消息 + 紧随其后的无正文媒体」合成一组
    groups: list[MediaGroup] = []
    current: MediaGroup | None = None

    def flush():
        nonlocal current
        if current and current.items:
            groups.append(current)
        current = None

    for msg in messages:
        if msg.get("type") != "message":
            continue
        mid = int(msg.get("id", 0))
        text = export_text(msg)
        tags = export_hashtags(msg)
        photo = msg.get("photo")
        file_path = msg.get("file") or msg.get("photo")
        media_type = msg.get("media_type") or ("photo" if photo else None)
        if not file_path and not photo:
            if tags:
                flush()
            continue

        rel = file_path or photo
        abs_path = os.path.join(export_dir, rel) if rel else None
        if abs_path and not os.path.isfile(abs_path):
            # 兼容 chats/... 嵌套
            alt = None
            for root, _, files in os.walk(export_dir):
                if os.path.basename(rel) in files:
                    alt = os.path.join(root, os.path.basename(rel))
                    break
            abs_path = alt

        kind = "photo" if photo and not msg.get("file") else (media_type or "file")
        item = MediaItem(
            message_id=mid,
            grouped_id=None,
            kind=str(kind),
            file_name=os.path.basename(rel) if rel else f"{mid}.bin",
            size=os.path.getsize(abs_path) if abs_path and os.path.isfile(abs_path) else None,
            local_path=abs_path if abs_path and os.path.isfile(abs_path) else None,
            source_path=rel,
        )

        if tags or current is None:
            flush()
            current = MediaGroup(
                group_key=f"m{mid}",
                grouped_id=None,
                message_ids=[mid],
                tags=tags,
                caption=text,
                date=str(msg.get("date") or msg.get("date_unixtime") or ""),
                items=[item],
            )
        else:
            # 无正文的后续媒体，并入上一组（模拟相册）
            assert current is not None
            current.message_ids.append(mid)
            current.items.append(item)

    flush()

    # 复制/链到统一 output（已存在则记录路径）
    files_root = os.path.join(output_dir, "files")
    ensure_dir(files_root)
    for g in groups:
        gdir = os.path.join(files_root, g.group_key)
        ensure_dir(gdir)
        for it in g.items:
            if not it.local_path or not os.path.isfile(it.local_path):
                continue
            dest = os.path.join(gdir, f"{it.message_id}_{sanitize(it.file_name)}")
            if not os.path.isfile(dest):
                try:
                    # 硬链接省空间；失败则跳过复制大文件，只写引用
                    os.link(it.local_path, dest)
                    it.local_path = dest
                except OSError:
                    # 跨盘或不支持硬链接：保留原路径引用
                    pass

    write_group_outputs(groups, output_dir, root_tags)
    missing = sum(1 for g in groups for it in g.items if not it.local_path)
    if missing:
        print(f"注意: {missing} 个文件在导出目录中缺失（可能尚未下完），已保留元数据。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram 媒体下载 + 标签/会话组分类")
    parser.add_argument(
        "--config",
        default=CONFIG_PATH,
        help="配置文件路径（默认 tools/tg_config.json）",
    )
    parser.add_argument(
        "--from-export",
        default=None,
        help="仅从官方 ChatExport 目录归类（不联网下载）",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出目录（默认配置中的 output_dir 或 tg_library）",
    )
    args = parser.parse_args()

    if args.from_export:
        export_dir = args.from_export
        if not os.path.isabs(export_dir):
            export_dir = os.path.join(PROJECT_ROOT, export_dir)
        output = args.output or os.path.join(PROJECT_ROOT, "tg_library")
        root_tags = ["孤儿的工作"]
        if os.path.isfile(args.config):
            with open(args.config, encoding="utf-8") as f:
                cfg = json.load(f)
            root_tags = list(cfg.get("root_tags") or root_tags)
            if not args.output and cfg.get("output_dir"):
                output = cfg["output_dir"]
                if not os.path.isabs(output):
                    output = os.path.join(PROJECT_ROOT, output)
        return run_from_export(export_dir, output, root_tags)

    cfg = load_config(args.config)
    if args.output:
        cfg["output_dir"] = args.output
    return asyncio.run(run_telethon(cfg))


if __name__ == "__main__":
    raise SystemExit(main())
