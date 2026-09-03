# -*- coding: utf-8 -*-
"""从 ChatExport_2026-08-24 导入 JSON（仅缺失）与录屏 MP4（覆盖到 custom_videos）。

- JSON：按 story 基址去后缀比较，仅复制项目中尚不存在的条目
- MP4：全部写入 custom_videos/（录屏分区），直接覆盖，不写 resource/
- 支持 zip / rar / 7z（密码默认 @shuyibaifa）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from project_paths import CUSTOM_VIDEOS_DIR, JSON_DIR, PROJECT_ROOT

try:
    import py7zr
except ImportError:
    py7zr = None

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

EXPORT = os.path.join(PROJECT_ROOT, "ChatExport_2026-08-24")
FILES_DIR = os.path.join(
    EXPORT, "chats", "chat_562953575216835", "topic_15952", "files"
)
ARCHIVE_PASSWORDS = ("@shuyibaifa", "红叶可爱捏")
UNRAR = r"C:\Program Files\WinRAR\UnRAR.exe"
SEVEN_ZIP = r"C:\Program Files\7-Zip\7z.exe"
NOW = time.time()


def _rar_list(archive: str) -> list[str] | None:
    for pwd in ARCHIVE_PASSWORDS:
        r = subprocess.run(
            [UNRAR, "lb", f"-p{pwd}", archive],
            capture_output=True,
            check=False,
        )
        if r.returncode == 0:
            return [
                line.strip()
                for line in r.stdout.decode("utf-8", errors="replace").splitlines()
                if line.strip()
            ]
    return None


def _extract_7z(archive: str, out_dir: str) -> bool:
    if not os.path.isfile(SEVEN_ZIP):
        return False
    for pwd in ARCHIVE_PASSWORDS:
        r = subprocess.run(
            [SEVEN_ZIP, "x", f"-p{pwd}", f"-o{out_dir}", archive, "-y"],
            capture_output=True,
            check=False,
        )
        if r.returncode == 0:
            return True
    return False


from tools.dedupe_json import parse_json_name

CANONICAL_JSON_RE = re.compile(r"^(\d+(?:_\d+)?)\.json$", re.I)
PAREN_JSON_RE = re.compile(r"^(\d+)\s*\((\d+)\)\.json$", re.I)
SCENE_MP4_RE = re.compile(r"^(\d{6,9})(?:\s*\(\d+\))?\.mp4$", re.I)
TELEGRAM_SUBDIR = "telegram"


def normalize_json_name(name: str) -> str | None:
    base = os.path.basename(name).strip()
    base = re.sub(r" \(\d+\)(?=\.json)", "", base, flags=re.I)
    if base.lower().endswith(".json1"):
        base = base[:-1]
    m = CANONICAL_JSON_RE.match(base)
    if m:
        return m.group(1) + ".json"
    m = PAREN_JSON_RE.match(base)
    if m:
        return f"{m.group(1)}_{m.group(2)}.json"
    return None


def json_story_base(filename: str) -> str | None:
    parsed = parse_json_name(filename)
    if parsed:
        return parsed[0]
    return None


def existing_story_bases() -> set[str]:
    bases: set[str] = set()
    if not os.path.isdir(JSON_DIR):
        return bases
    for name in os.listdir(JSON_DIR):
        if not name.lower().endswith(".json") or name.startswith("."):
            continue
        base = json_story_base(name)
        if base:
            bases.add(base)
    return bases


def is_valid_json_bytes(data: bytes) -> bool:
    try:
        obj = json.loads(data.decode("utf-8"))
        return isinstance(obj, dict) and "storyIds" in obj
    except Exception:
        return False


def iter_archive_json() -> list[tuple[str, str, object]]:
    """返回 (canonical_name, display_src, reader)，reader 为 path 或 (archive, member)。"""
    seen: dict[str, tuple[str, object]] = {}

    def consider(raw_name: str, src_label: str, reader):
        norm = normalize_json_name(raw_name)
        if not norm:
            return
        stem = norm[:-5]
        suffix = 0
        if "_" in stem:
            parts = stem.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                suffix = int(parts[1])
        prev = seen.get(norm)
        if prev is None:
            seen[norm] = (src_label, reader, suffix)
            return
        if suffix < prev[2]:
            seen[norm] = (src_label, reader, suffix)

    if os.path.isdir(FILES_DIR):
        for name in os.listdir(FILES_DIR):
            if name.lower().endswith((".json", ".json1")):
                consider(name, f"loose:{name}", os.path.join(FILES_DIR, name))

    if not os.path.isdir(FILES_DIR):
        return []

    for name in sorted(os.listdir(FILES_DIR)):
        low = name.lower()
        path = os.path.join(FILES_DIR, name)
        if low.endswith(".zip"):
            try:
                with zipfile.ZipFile(path) as zf:
                    for entry in zf.namelist():
                        if entry.endswith("/"):
                            continue
                        consider(
                            os.path.basename(entry),
                            f"zip:{name}:{entry}",
                            (path, entry),
                        )
            except zipfile.BadZipFile:
                print(f"[跳过] 损坏 zip: {name}")
        elif low.endswith(".rar") and os.path.isfile(UNRAR):
            try:
                entries = _rar_list(path)
                if entries is None:
                    print(f"[跳过] 无法读取 rar: {name}")
                    continue
                for entry in entries:
                    consider(
                        os.path.basename(entry),
                        f"rar:{name}:{entry}",
                        (path, entry),
                    )
            except OSError as exc:
                print(f"[跳过] rar 列表失败 {name}: {exc}")

    out = []
    for norm, (src_label, reader, _suffix) in sorted(seen.items()):
        out.append((norm, src_label, reader))
    return out


def read_json_bytes(reader) -> bytes:
    if isinstance(reader, str):
        with open(reader, "rb") as f:
            return f.read()
    if isinstance(reader, tuple) and len(reader) == 2:
        archive, member = reader
        if archive.lower().endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                return zf.read(member)
        if archive.lower().endswith(".rar"):
            with tempfile.TemporaryDirectory(prefix="tg_json_") as tmp:
                for pwd in ARCHIVE_PASSWORDS:
                    subprocess.run(
                        [
                            UNRAR,
                            "x",
                            "-y",
                            f"-p{pwd}",
                            archive,
                            member,
                            tmp + os.sep,
                        ],
                        capture_output=True,
                        check=False,
                    )
                    dst = os.path.join(tmp, os.path.basename(member))
                    if os.path.isfile(dst):
                        with open(dst, "rb") as f:
                            return f.read()
                    full = os.path.join(tmp, member.replace("/", os.sep))
                    if os.path.isfile(full):
                        with open(full, "rb") as f:
                            return f.read()
            raise FileNotFoundError(member)
    raise TypeError(type(reader))


def import_json_files() -> tuple[list[str], list[str], list[str]]:
    existing = existing_story_bases()
    added: list[str] = []
    skipped_existing: list[str] = []
    skipped_invalid: list[str] = []

    for norm, src_label, reader in iter_archive_json():
        base = json_story_base(norm)
        if not base or base in existing:
            skipped_existing.append(norm)
            continue
        try:
            data = read_json_bytes(reader)
        except Exception as exc:
            print(f"[JSON] 读取失败 {norm} ({src_label}): {exc}")
            skipped_invalid.append(norm)
            continue
        if not is_valid_json_bytes(data):
            skipped_invalid.append(norm)
            continue
        dst = os.path.join(JSON_DIR, norm)
        os.makedirs(JSON_DIR, exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        os.utime(dst, (NOW, NOW))
        existing.add(base)
        added.append(norm)
        print(f"[JSON] 新增 {norm} <- {src_label}")

    return added, skipped_existing, skipped_invalid


def custom_video_target(inner_path: str, filename: str) -> str:
    """录屏分区路径：场景 ID 命名 -> 根目录；其余 -> telegram/ 下按相对路径。"""
    name = os.path.basename(filename or inner_path)
    m = SCENE_MP4_RE.match(name)
    if m:
        return os.path.join(CUSTOM_VIDEOS_DIR, f"{m.group(1)}.mp4")

    rel = inner_path.replace("\\", "/").lstrip("./")
    rel = re.sub(r'[<>:"|?*]', "_", rel)
    return os.path.join(CUSTOM_VIDEOS_DIR, TELEGRAM_SUBDIR, rel.replace("/", os.sep))


def write_mp4_bytes(data: bytes, dst: str) -> bool:
    if len(data) <= 0:
        return False
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "wb") as f:
        f.write(data)
    os.utime(dst, (NOW, NOW))
    return True


def copy_mp4_file(src_path: str, dst: str) -> bool:
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(src_path, "rb") as src, open(dst, "wb") as out:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    os.utime(dst, (NOW, NOW))
    return True


def iter_mp4_sources() -> list[tuple[str, str]]:
    """(kind, locator) kind=loose|zip|rar|7z"""
    items: list[tuple[str, str]] = []
    if os.path.isdir(EXPORT):
        for root, dirs, files in os.walk(EXPORT):
            dirs[:] = [d for d in dirs if d not in (".thumbs", "__MACOSX")]
            for name in files:
                if name.lower().endswith(".mp4"):
                    items.append(("loose", os.path.join(root, name)))
    if not os.path.isdir(FILES_DIR):
        return items
    for name in sorted(os.listdir(FILES_DIR)):
        low = name.lower()
        path = os.path.join(FILES_DIR, name)
        if low.endswith(".zip"):
            try:
                with zipfile.ZipFile(path) as zf:
                    for entry in zf.namelist():
                        if entry.lower().endswith(".mp4"):
                            items.append(("zip", f"{path}|{entry}"))
            except zipfile.BadZipFile:
                pass
        elif low.endswith(".rar") and os.path.isfile(UNRAR):
            entries = _rar_list(path)
            if entries:
                for entry in entries:
                    if entry.lower().endswith(".mp4"):
                        items.append(("rar", f"{path}|{entry}"))
        elif low.endswith(".7z") and (
            os.path.isfile(SEVEN_ZIP) or py7zr is not None
        ):
            names: list[str] = []
            if os.path.isfile(SEVEN_ZIP):
                for pwd in ARCHIVE_PASSWORDS:
                    r = subprocess.run(
                        [SEVEN_ZIP, "l", f"-p{pwd}", path],
                        capture_output=True,
                        check=False,
                    )
                    if r.returncode != 0:
                        continue
                    for line in r.stdout.decode("utf-8", errors="replace").splitlines():
                        parts = line.split()
                        if parts and parts[-1].lower().endswith(".mp4"):
                            names.append(parts[-1])
                    if names:
                        break
            elif py7zr is not None:
                for pwd in ARCHIVE_PASSWORDS:
                    try:
                        with py7zr.SevenZipFile(path, mode="r", password=pwd) as zf:
                            names = [
                                n for n in zf.getnames() if n.lower().endswith(".mp4")
                            ]
                        if names:
                            break
                    except Exception:
                        continue
            for entry in names:
                items.append(("7z", f"{path}|{entry}"))
    return items


def read_mp4(kind: str, locator: str) -> tuple[str, bytes]:
    if kind == "loose":
        with open(locator, "rb") as f:
            return os.path.basename(locator), f.read()
    archive, member = locator.split("|", 1)
    member_name = os.path.basename(member)
    if kind == "zip":
        with zipfile.ZipFile(archive) as zf:
            return member_name, zf.read(member)
    if kind == "rar":
        with tempfile.TemporaryDirectory(prefix="tg_mp4_") as tmp:
            for pwd in ARCHIVE_PASSWORDS:
                subprocess.run(
                    [
                        UNRAR,
                        "x",
                        "-y",
                        f"-p{pwd}",
                        archive,
                        member,
                        tmp + os.sep,
                    ],
                    capture_output=True,
                    check=False,
                )
                candidates = [
                    os.path.join(tmp, os.path.basename(member)),
                    os.path.join(tmp, member.replace("/", os.sep)),
                ]
                for cand in candidates:
                    if os.path.isfile(cand):
                        with open(cand, "rb") as f:
                            return member_name, f.read()
        raise FileNotFoundError(member)
    if kind == "7z":
        with tempfile.TemporaryDirectory(prefix="tg_mp4_") as tmp:
            if not _extract_7z(archive, tmp) and py7zr is not None:
                for pwd in ARCHIVE_PASSWORDS:
                    try:
                        with py7zr.SevenZipFile(archive, mode="r", password=pwd) as zf:
                            zf.extract(path=tmp, targets=[member])
                        break
                    except Exception:
                        continue
            candidates = [
                os.path.join(tmp, os.path.basename(member)),
                os.path.join(tmp, member.replace("/", os.sep)),
            ]
            for root, _, files in os.walk(tmp):
                for fname in files:
                    if fname == os.path.basename(member):
                        candidates.append(os.path.join(root, fname))
            for cand in candidates:
                if os.path.isfile(cand):
                    with open(cand, "rb") as f:
                        return member_name, f.read()
        raise FileNotFoundError(member)
    raise ValueError(kind)


def import_mp4_files() -> tuple[list[str], list[str], list[str]]:
    overwritten: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for kind, locator in iter_mp4_sources():
        try:
            if kind == "loose":
                inner_path = os.path.relpath(locator, EXPORT).replace("\\", "/")
                name = os.path.basename(locator)
                data = None
                with open(locator, "rb") as f:
                    data = f.read()
            else:
                member = locator.split("|", 1)[1]
                inner_path = member.replace("\\", "/")
                name, data = read_mp4(kind, locator)
        except Exception as exc:
            failed.append(f"{locator}: {exc}")
            continue

        dst = custom_video_target(inner_path, name or inner_path)

        try:
            if write_mp4_bytes(data, dst):
                rel = os.path.relpath(dst, PROJECT_ROOT).replace("\\", "/")
                overwritten.append(rel)
                print(f"[录屏] 覆盖 {rel} <- {inner_path}")
        except OSError as exc:
            failed.append(f"{inner_path}: {exc}")

    return overwritten, skipped, failed


def main() -> int:
    if not os.path.isdir(EXPORT):
        print(f"未找到导出目录: {EXPORT}")
        return 1

    print("=== 导入 JSON（仅缺失 story 基址）===")
    added, skip_exist, skip_bad = import_json_files()
    print(f"新增: {len(added)}")
    print(f"跳过(已有): {len(skip_exist)}")
    print(f"跳过(无效/读失败): {len(skip_bad)}")

    print("\n=== 导入录屏 MP4 到 custom_videos（覆盖）===")
    overwritten, skipped, failed = import_mp4_files()
    print(f"覆盖: {len(overwritten)}")
    print(f"跳过: {len(skipped)}")
    print(f"失败: {len(failed)}")
    if failed[:5]:
        for item in failed[:5]:
            print(f"  - {item!r}")

    print("\n完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
