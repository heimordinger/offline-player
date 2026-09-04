# -*- coding: utf-8 -*-
"""局域网只读 HTTP 服务：供手机浏览器做设备互通测试。"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from project_paths import PROJECT_ROOT, ensure_app_icon, load_settings


class _QuietHTTPServer(ThreadingHTTPServer):
    """手机取消加载 / 拖进度条时会主动断连，不刷堆栈。"""

    # 条漫连刷大量图片时，默认队列过小会导致新请求被拒 → 手机端 Failed to fetch
    request_queue_size = 256
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        import sys
        import traceback

        err = sys.exc_info()[1]
        if isinstance(err, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        if isinstance(err, OSError) and getattr(err, "winerror", None) in (10053, 10054):
            return
        print("-" * 40, file=sys.stderr)
        print(
            f"Exception occurred during processing of request from {client_address}",
            file=sys.stderr,
        )
        traceback.print_exc()
        print("-" * 40, file=sys.stderr)


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _read_version(root: str) -> str:
    path = os.path.join(root, "VERSION")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


def _lan_settings() -> dict[str, Any]:
    try:
        settings = load_settings()
    except OSError:
        settings = {}
    cfg = settings.get("局域网") or {}
    port = int(cfg.get("port") or 8765)
    token = str(cfg.get("token") or "").strip()
    return {"port": port, "token": token}


def _safe_path(root: str, rel_url_path: str) -> str | None:
    """将 /media/... URL 映射到 root 下真实路径，禁止目录穿越。"""
    rel = urllib.parse.unquote(rel_url_path.lstrip("/"))
    if rel.startswith("media/"):
        rel = rel[6:]
    rel = rel.replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    full = os.path.normpath(os.path.join(root, rel.replace("/", os.sep)))
    root_norm = os.path.normpath(root)
    if not full.startswith(root_norm):
        return None
    if os.path.isfile(full):
        return full
    return None


class LanServer:
    def __init__(
        self,
        root: str | None = None,
        port: int | None = None,
        token: str | None = None,
    ):
        self.root = os.path.abspath(root or PROJECT_ROOT)
        self.port = port if port is not None else _lan_settings()["port"]
        self.token = token if token is not None else _lan_settings()["token"]
        self.web_dir = os.path.join(self.root, "app", "web")
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def urls(self) -> list[str]:
        ip = get_local_ip()
        return [
            f"http://{ip}:{self.port}",
            f"http://127.0.0.1:{self.port}",
        ]

    def start(self) -> None:
        if self._httpd is not None:
            return
        handler = _make_handler(self.root, self.web_dir, self.token)
        self._httpd = _QuietHTTPServer(("0.0.0.0", self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def run_blocking(self) -> None:
        """阻塞运行（供 serve_lan 命令行使用）。"""
        if self._httpd is not None:
            return
        handler = _make_handler(self.root, self.web_dir, self.token)
        self._httpd = _QuietHTTPServer(("0.0.0.0", self.port), handler)
        print("离线播放器 · 局域网测试服务")
        print(f"工作目录: {self.root}")
        if self.token:
            print(f"访问令牌: {self.token}")
        print("请在手机浏览器打开（需同一 WiFi）：")
        for url in self.urls():
            suffix = f"?token={self.token}" if self.token else ""
            print(f"  {url}{suffix}")
        print("VPN 用户请在代理软件中开启「绕过局域网」")
        print("按 Ctrl+C 停止")
        try:
            self._httpd.serve_forever()
        finally:
            self.stop()

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._thread = None


def _json_response(handler: BaseHTTPRequestHandler, data: Any, status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        return


def _file_response(handler: BaseHTTPRequestHandler, path: str, *, cacheable: bool = True) -> None:
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    size = os.path.getsize(path)
    range_header = handler.headers.get("Range")
    start = 0
    end = size - 1
    status = 200
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            if m.group(2):
                end = int(m.group(2))
            end = min(end, size - 1)
            status = 206
    length = end - start + 1
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", mime)
        handler.send_header("Content-Length", str(length))
        handler.send_header("Accept-Ranges", "bytes")
        if status == 206:
            handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if cacheable:
            # 媒体/静态资源可短缓存，减轻来回切图时的重复拉取
            handler.send_header("Cache-Control", "public, max-age=3600")
        else:
            handler.send_header("Cache-Control", "no-store")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        # 手机滑走、取消加载、拖进度条时经常主动断开，不算服务故障
        return


def _make_handler(root: str, web_dir: str, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "OfflinePlayerLAN/0.1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            print(f"[LAN] {self.address_string()} {fmt % args}")

        def _check_token(self) -> bool:
            if not token:
                return True
            q = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(q)
            return params.get("token", [""])[0] == token

        def do_GET(self) -> None:
            try:
                self._dispatch_get()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except OSError as exc:
                if getattr(exc, "winerror", None) in (10053, 10054):
                    return
                try:
                    _json_response(self, {"error": str(exc)}, 500)
                except Exception:
                    return
            except Exception as exc:
                try:
                    _json_response(self, {"error": str(exc)}, 500)
                except Exception:
                    return

        def _dispatch_get(self) -> None:
            if not self._check_token():
                _json_response(self, {"error": "invalid token"}, 403)
                return

            path = urllib.parse.urlparse(self.path).path
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

            if path in ("/", "/index.html"):
                index = os.path.join(web_dir, "index.html")
                if os.path.isfile(index):
                    _file_response(self, index, cacheable=False)
                else:
                    _json_response(self, {"error": "missing index.html"}, 404)
                return

            if path in ("/favicon.ico", "/icon.ico"):
                icon = ensure_app_icon()
                if icon and os.path.isfile(icon):
                    _file_response(self, icon)
                else:
                    self.send_response(404)
                    self.end_headers()
                return

            static_map = {
                "/app.css": "app.css",
                "/app.js": "app.js",
                "/test.html": "test.html",
            }
            if path in static_map:
                static_path = os.path.join(web_dir, static_map[path])
                if os.path.isfile(static_path):
                    # JS/CSS 开发期不长缓存，避免改完不生效；带查询串时可缓存
                    _file_response(self, static_path, cacheable=False)
                else:
                    _json_response(self, {"error": "not found"}, 404)
                return

            if path == "/api/ping":
                _json_response(
                    self,
                    {
                        "ok": True,
                        "service": "offline-player-lan",
                        "version": _read_version(root),
                        "root": root,
                        "host": socket.gethostname(),
                        "lan_ip": get_local_ip(),
                        "token_required": bool(token),
                    },
                )
                return

            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "games" and parts[3] == "load":
                from app.server.mobile_api import game_bundle

                try:
                    bundle = game_bundle(root, parts[2])
                    _json_response(self, bundle)
                except KeyError:
                    _json_response(self, {"error": "unknown game"}, 404)
                except Exception as exc:
                    _json_response(self, {"error": str(exc)}, 500)
                return

            if len(parts) == 4 and parts[0] == "api" and parts[1] == "games" and parts[3] == "items":
                from app.server.mobile_api import category_items

                cat = query.get("cat", [""])[0]
                if not cat:
                    _json_response(self, {"error": "missing cat"}, 400)
                    return
                try:
                    data = category_items(root, parts[2], cat)
                    _json_response(self, data)
                except KeyError:
                    _json_response(self, {"error": "unknown game"}, 404)
                except Exception as exc:
                    _json_response(self, {"error": str(exc)}, 500)
                return

            if len(parts) == 4 and parts[0] == "api" and parts[1] == "games" and parts[3] == "prepare":
                from app.server.adv_prepare import start_or_status

                sid = query.get("sid", [""])[0]
                if not sid:
                    _json_response(self, {"error": "missing sid"}, 400)
                    return
                cancel = query.get("cancel", ["0"])[0] in ("1", "true", "yes")
                force = query.get("force", ["0"])[0] in ("1", "true", "yes")
                try:
                    data = start_or_status(parts[2], sid, force=force, cancel=cancel)
                    _json_response(self, data)
                except KeyError:
                    _json_response(self, {"error": "unknown game"}, 404)
                except Exception as exc:
                    _json_response(self, {"error": str(exc)}, 500)
                return

            if len(parts) == 4 and parts[0] == "api" and parts[1] == "games" and parts[3] == "scene":
                from app.server.mobile_api import scene_media

                sid = query.get("sid", [""])[0]
                if not sid:
                    _json_response(self, {"error": "missing sid"}, 400)
                    return
                try:
                    data = scene_media(root, parts[2], sid)
                    _json_response(self, data)
                except KeyError:
                    _json_response(self, {"error": "unknown game"}, 404)
                except Exception as exc:
                    _json_response(self, {"error": str(exc)}, 500)
                return

            if len(parts) == 4 and parts[0] == "api" and parts[1] == "games" and parts[3] == "samples":
                from app.server.media_probe import find_game_samples

                game_id = parts[2]
                samples = find_game_samples(root, game_id)
                _json_response(self, {"game_id": game_id, "samples": samples})
                return

            if path == "/api/games":
                from app.core.adapters import adapter_info, list_adapters
                from app.core.game_registry import load_games, quick_scene_count

                games = []
                for g in load_games():
                    info = adapter_info(g.kind)
                    games.append(
                        {
                            "id": g.id,
                            "name": g.name,
                            "description": g.description,
                            "kind": g.kind,
                            "local_only": g.local_only,
                            "scene_count": quick_scene_count(g),
                            "root": g.root,
                            "adapter": info.to_dict(),
                        }
                    )
                _json_response(
                    self,
                    {
                        "games": games,
                        "adapters": [a.to_dict() for a in list_adapters()],
                    },
                )
                return

            if path == "/api/sample-media":
                sample = os.path.join(root, "legacy", "assets", "color_0_0_0.jpg")
                if os.path.isfile(sample):
                    rel = os.path.relpath(sample, root).replace("\\", "/")
                    _json_response(
                        self,
                        {
                            "path": rel,
                            "url": f"/media/{rel}",
                        },
                    )
                else:
                    _json_response(self, {"error": "no sample"}, 404)
                return

            if path.startswith("/media/"):
                file_path = _safe_path(root, path)
                if file_path:
                    _file_response(self, file_path, cacheable=True)
                else:
                    _json_response(self, {"error": "not found"}, 404)
                return

            _json_response(self, {"error": "not found"}, 404)

    return Handler
