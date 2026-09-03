import pygame
import os
import re
import json
import math
from urllib.request import urlretrieve
from pygame.locals import *
from random import randrange
from sys import exit
# 降低 OpenCV/FFmpeg 解码日志噪音（须在 import cv2 前尽量设置）
os.environ.setdefault("OPENCV_LOG_LEVEL", "OFF")
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "quiet")
import cv2
try:
    cv2.setLogLevel(0)
except Exception:
    pass
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass
import threading
import hashlib
import requests
import concurrent.futures
import time
import webbrowser
import subprocess
import shutil

LEGACY_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(LEGACY_DIR)
import sys
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.chdir(PROJECT_ROOT)
os.makedirs("./resource/", exist_ok=True)
os.makedirs("./episode/", exist_ok=True)


def _legacy_asset(name):
    return os.path.join(LEGACY_DIR, "assets", name)

# 下载进度跟踪
download_total = 0
download_completed = 0
is_downloading = False

user_setting_file = open("settings.json",'r',encoding='utf8')
user_setting = json.load(user_setting_file)
user_setting_file.close()

# 用户自定义录屏目录（把 mp4 放进去即可在「我的录屏」中播放）
_custom_dir = user_setting.get("自定义视频目录", "custom_videos")
CUSTOM_VIDEO_DIR = _custom_dir if os.path.isabs(_custom_dir) else os.path.join(".", _custom_dir)
os.makedirs(CUSTOM_VIDEO_DIR, exist_ok=True)
_custom_readme = os.path.join(CUSTOM_VIDEO_DIR, "把mp4录屏放这里.txt")
if not os.path.exists(_custom_readme):
    with open(_custom_readme, "w", encoding="utf8") as _f:
        _f.write(
            "将 mp4 / webm / mov 录屏放在此文件夹（可建子文件夹）。\n"
            "启动程序后，在首页进入「我的录屏」分类即可播放。\n"
        )

class Button:
    rect = (0, 0, 0, 0)
    text = 0
    text_color = (240, 230, 210)
    button_color = (36, 48, 72)
    button_image = ""
    accent = (196, 160, 90)

    def __init__(self, rect, text):
        self.rect = rect
        self.text = text

    def set_img(self,img):
        self.button_image = img

    def set_rect(self, r):
        self.rect = r

    def set_text(self, t):
        self.text = t

    def set_rect_x(self, x):
        new_rect = (x, self.rect[1], self.rect[2], self.rect[3])
        self.rect = new_rect

    def set_rect_y(self, y):
        new_rect = (self.rect[0], y, self.rect[2], self.rect[3])
        self.rect = new_rect

    def set_rect_w(self, w):
        new_rect = (self.rect[0], self.rect[1], w, self.rect[3])
        self.rect = new_rect

    def set_rect_h(self, h):
        new_rect = (self.rect[0], self.rect[1], self.rect[2], h)
        self.rect = new_rect

    def show_image(self):
        cg = pygame.image.load(self.button_image).convert_alpha()
        screen.blit(cg, self.rect[:2])

    def show_button(self):
        x, y, w, h = self.rect
        pygame.draw.rect(screen, self.button_color, (x, y, w, h), border_radius=6)
        pygame.draw.rect(screen, self.accent, (x, y, w, h), 1, border_radius=6)
        # 用较小字号适配按钮
        try:
            btn_font = small_font
        except NameError:
            btn_font = game_font
        button_text = btn_font.render(str(self.text), True, self.text_color)
        tw, th = button_text.get_size()
        screen.blit(button_text, (x + (w - tw) // 2, y + (h - th) // 2))

    def in_rect(self, x, y):
        rx, ry, rw, rh = self.rect
        return rx <= x < rx + rw and ry <= y < ry + rh

def getMD5(input):
    input = '47cd76e43f74bbc2e1baaf194d07e1fa' + input
    result = hashlib.md5(input.encode())
    return result.hexdigest()

def get_real_path(str1):
    e=''
    i=''
    a=''
    n=''
    if str1[0]=='c' or str1[0]=='d' or str1[0]== 'e' or str1[0]=='f':
        e = str1[6:8]+'/'
        i = str1[2:4] + "/"
        a = str1[4:6] + "/"
        n = str1[0:2] + "/"
    elif str1[0]=='8' or str1[0] =='9' or str1[0]=='a' or str1[0] =='b':
        e = str1[4:6]+ "/"
        i = str1[0:2]+ "/"
        a = str1[6:8]+ "/"
        n = str1[2:4]+ "/"
    elif int(str1[0])>=4 and int(str1[0])<=7:
        e = str1[2:4]+ "/"
        i = str1[6:8]+ "/"
        a = str1[0:2]+ "/"
    elif int(str1[0])>=0 and int(str1[0])<=3:
        e = str1[0:2]+ "/"
        i = str1[4:6]+ "/"
    return  e + i + a + n

def get_url(file_name):
    cdn_url = "https://tonofura-r-cdn-resource.deepone-online.com/deep_one/download_game_hd/"
    md5 = getMD5(file_name)
    path = get_real_path(md5)
    file_end = '.'+file_name.split(".")[-1]
    if '.atlas.txt' in file_name:
        file_end = '.atlas.txt'
    return cdn_url+path+md5+file_end

def download_file(url, filename):
    global download_completed

    print(f'Downloading {filename}...')
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        print(f'{filename} 已下载，跳过.')
        download_completed += 1
        return True
    # 清掉损坏的空文件
    if os.path.exists(filename):
        try:
            os.remove(filename)
        except Exception:
            pass
    download_times = 5
    ok = False
    while download_times > 0:
        try:
            urlretrieve(url, filename)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                ok = True
                break
        except Exception:
            print("error downloading : " + filename)
        download_times = download_times - 1
    download_completed += 1
    if ok:
        print(f'{filename} downloaded.')
    else:
        print(f'{filename} 下载失败.')
    return ok

def fetch_file(url, filename, quiet=False):
    """同步下载单个文件（不改全局进度计数），成功返回 True。"""
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        return True
    if os.path.exists(filename):
        try:
            os.remove(filename)
        except Exception:
            pass
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    for _ in range(5):
        try:
            if not quiet:
                print(f"补下: {filename}")
            urlretrieve(url, filename)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return True
        except Exception as e:
            if not quiet:
                print(f"补下失败 {filename}: {e}")
    return False

def iter_resource_entries(jsonId):
    """读取 json 资源列表，yield (rel_path, local_path, url)。"""
    json_path = "./json/" + jsonId + ".json"
    with open(json_path, "r", encoding="utf8") as load_f:
        dojson = json.load(load_f)
    for r in dojson["resource"]:
        rel = r["fileName"].replace("\\", "/")
        local = "./resource/" + jsonId + "/" + rel
        end = rel.split(".")[-1]
        url = ("https://tonofura-r-cdn-resource.deepone-online.com/deep_one/download_adv/"
               + r["path"] + "/" + r["md5"] + "." + end)
        yield rel, local, url
        if rel.endswith(".txt"):
            cn_rel = rel.replace(".txt", "_CN.txt")
            cn_local = "./resource/" + jsonId + "/" + cn_rel
            cn_url = "https://lisanjin.github.io//DeepOne_translate_CN/" + rel
            yield cn_rel, cn_local, cn_url

def get_missing_resources(jsonId, media_only=False):
    """返回缺失资源列表 [(url, local_path), ...]。"""
    missing = []
    for rel, local, url in iter_resource_entries(jsonId):
        if media_only:
            low = rel.lower()
            if not low.endswith((".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm")):
                continue
        if not (os.path.exists(local) and os.path.getsize(local) > 0):
            missing.append((url, local))
    return missing

def begin_scene_select(jid):
    """选中场景（资源检查放后台，避免点击卡顿）。"""
    global jsonId, json_selected, _selected_missing_count, _selection_checking
    jsonId = jid
    json_selected = True
    if is_custom_video(jid):
        _selected_missing_count = 0
        _selection_checking = False
        mark_ui_dirty()
        return
    _selected_missing_count = -1
    _selection_checking = True
    mark_ui_dirty()

    def worker():
        global _selected_missing_count, _selection_checking
        try:
            _selected_missing_count = len(get_missing_resources(jid, media_only=False))
        except Exception:
            _selected_missing_count = 0
        finally:
            _selection_checking = False
            mark_ui_dirty()

    threading.Thread(target=worker, daemon=True).start()

def push_video_surface(surface):
    """视频线程只投递帧，由主线程绘制（pygame 非线程安全）。"""
    global _latest_video_surface
    try:
        owned = surface.copy()
    except Exception:
        owned = surface
    with _video_surface_lock:
        _latest_video_surface = owned

def clear_video_surface():
    global _latest_video_surface
    with _video_surface_lock:
        _latest_video_surface = None

def render_video_frame():
    """主线程绘制最新视频帧。"""
    with _video_surface_lock:
        surf = _latest_video_surface
    if surf is None:
        return False
    blit_cg(surf)
    if is_custom_play:
        draw_custom_play_hud()
    else:
        draw_dialogue_chrome()
        prog = (play_count / len(commands)) if commands else 0
        draw_playback_hud(prog)
    return True

def layout_nav_buttons():
    """根据窗口尺寸摆放翻页/播放按钮，避免与场景块重叠。"""
    y = GAME_SIZE[1] - 62
    cx = GAME_SIZE[0] // 2
    pages_down_button.set_rect((cx - 140, y, 120, 42))
    pages_up_button.set_rect((cx + 20, y, 120, 42))
    cat_down_button.set_rect((cx - 140, y, 120, 42))
    cat_up_button.set_rect((cx + 20, y, 120, 42))
    play_button.set_rect((cx - 80, GAME_SIZE[1] - 90, 160, 52))

def ensure_scene_resources(jsonId):
    """播放前补全该场景全部缺失资源（文本/语音/图片/视频），带进度刷新。"""
    global download_total, download_completed, is_downloading
    missing = get_missing_resources(jsonId, media_only=False)
    if not missing:
        return 0

    print(f"发现 {len(missing)} 个缺失资源，开始下载…")
    download_total = len(missing)
    download_completed = 0
    is_downloading = True

    file_dict = {}
    for url, local in missing:
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        file_dict[url] = local

    with concurrent.futures.ThreadPoolExecutor(max_workers=下载线程数) as executor:
        futures = [executor.submit(download_file, url, filename)
                   for url, filename in file_dict.items()]
        while any(not f.done() for f in futures):
            # 保持窗口可响应并刷新进度条
            for event in pygame.event.get():
                if event.type == QUIT:
                    exit()
            prog = download_completed / download_total if download_total else 0
            overlay = pygame.Surface(GAME_SIZE, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))
            draw_progress_bar(
                GAME_SIZE[0] // 2 - 300, GAME_SIZE[1] // 2 - 20, 600, 36,
                prog,
                f"下载资源 {download_completed}/{download_total}",
                (0, 180, 220),
            )
            tip = small_font.render("首次播放会自动下载，请稍候…", True, (255, 230, 180))
            screen.blit(tip, (GAME_SIZE[0] // 2 - 160, GAME_SIZE[1] // 2 + 30))
            pygame.display.flip()
            time.sleep(0.05)
        for f in futures:
            try:
                f.result()
            except Exception:
                pass

    is_downloading = False
    left = len(get_missing_resources(jsonId, media_only=False))
    print(f"资源下载完成，仍缺失 {left} 个")
    return left

def ensure_local_media(rel_path):
    """确保单个相对路径资源存在（播放中按需补下）。"""
    rel_path = rel_path.replace("\\", "/")
    if rel_path == "color_0_0_0":
        return None
    local = "./resource/" + jsonId + "/" + rel_path
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return local
    for rel, path, url in iter_resource_entries(jsonId):
        if rel == rel_path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            if fetch_file(url, path):
                return path
            break
    return None

# 加载资源
def get_resource(jsonId):
    global download_total, download_completed, is_downloading

    file_dict = {}
    for rel, fileName, url in iter_resource_entries(jsonId):
        name = fileName.split("/")[-1]
        os.makedirs(fileName.replace("/" + name, ""), exist_ok=True)
        file_dict[url] = fileName

    download_total = len(file_dict)
    download_completed = 0
    is_downloading = True
    threading.Thread(target=_do_download, args=(file_dict,), daemon=True).start()

# 加载预览图（后台按需下载，不阻塞启动）
_preview_loading = False

def get_story_id(jid):
    return str(jid).split("_")[0]

def get_episode_preview_local(story_id):
    """返回已存在的预览图路径（png/jpg 均可）。"""
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        path = "episode/" + story_id + ext
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None

def get_first_cg_url_for_story(story_id):
    """从场景 JSON 取第一张 CG 的 CDN 地址（仅一张图，不下载完整资源包）。"""
    json_dir = "./json/"
    if not os.path.isdir(json_dir):
        return None, None
    names = []
    primary = story_id + ".json"
    if os.path.exists(os.path.join(json_dir, primary)):
        names.append(primary)
    for name in sorted(os.listdir(json_dir)):
        if name == primary or not name.endswith(".json"):
            continue
        if name.startswith(story_id + "_"):
            names.append(name)
    for name in names:
        try:
            with open(os.path.join(json_dir, name), "r", encoding="utf8") as f:
                data = json.load(f)
        except Exception:
            continue
        for r in data.get("resource", []):
            fn = r.get("fileName", "").replace("\\", "/")
            low = fn.lower()
            if "/image/" in low and low.endswith((".jpg", ".jpeg", ".png", ".webp")):
                end = fn.split(".")[-1]
                url = ("https://tonofura-r-cdn-resource.deepone-online.com/deep_one/download_adv/"
                       + r["path"] + "/" + r["md5"] + "." + end)
                return url, end
    return None, None

def fetch_episode_preview(story_id, quiet=False):
    """下载单个场景预览：优先 gallery 小图（约 14KB），失败则下首张 CG。"""
    if get_episode_preview_local(story_id):
        return True
    os.makedirs("./episode/", exist_ok=True)
    local_png = "episode/" + story_id + ".png"
    episode_name = "gallery/episode/" + story_id + ".png"
    if fetch_file(get_url(episode_name), local_png, quiet=quiet):
        return True
    url, ext = get_first_cg_url_for_story(story_id)
    if url and ext:
        return fetch_file(url, "episode/" + story_id + "." + ext, quiet=quiet)
    return False

def collect_missing_preview_ids(json_list):
    """收集仍缺预览图的 storyId（去重）。"""
    missing = []
    seen = set()
    for jid in json_list:
        story_id = get_story_id(jid)
        if story_id in seen:
            continue
        seen.add(story_id)
        if not get_episode_preview_local(story_id):
            missing.append(story_id)
    return missing

def resolve_scene_preview_path(jid):
    """场景列表用的预览图路径。"""
    return get_episode_preview_local(get_story_id(jid)) or ""

def start_preview_loader(json_list, only_ids=None):
    """后台补下缺失预览（浏览时按需触发）。"""
    global _preview_loading
    if _preview_loading:
        return
    if only_ids is None:
        targets = collect_missing_preview_ids(json_list)
    else:
        targets = [sid for sid in only_ids if not get_episode_preview_local(sid)]
    if not targets:
        return
    _preview_loading = True

    def worker():
        global _preview_loading
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=下载线程数) as executor:
                list(executor.map(lambda sid: fetch_episode_preview(sid, quiet=True), targets))
        finally:
            _preview_loading = False
            mark_ui_dirty()

    threading.Thread(target=worker, daemon=True).start()

def _do_download(file_dict):
    global is_downloading
    with concurrent.futures.ThreadPoolExecutor(max_workers=下载线程数) as executor:
        futures = [executor.submit(download_file, url, filename) for url, filename in file_dict.items()]
        # 等待所有下载完成
        for f in concurrent.futures.as_completed(futures):
            pass
    is_downloading = False
    mark_ui_dirty()
    print("下载完毕")


import os
import json


def rename_json(path):
    """
    Rename a JSON file to be a pure number-based name, removing any text after an underscore ('_').
    If the new file name already exists, add a numeric suffix to ensure uniqueness.

    :param path: The original path of the JSON file.
    :return: None
    """
    try:
        if not os.path.exists('./json/' + path):
            print(f"Error: File '{path}' does not exist.")
            return

        with open('./json/' + path, "r", encoding="utf8") as f:
            json_data = json.loads(f.read())

        new_name = f"{json_data['storyIds'][0]}.json"

        if path == new_name:
            return

        if os.path.exists('./json/' + new_name):
            suffix = 1
            while os.path.exists(f'./json/{new_name[:-5]}_{suffix}.json'):
                suffix += 1
            new_name = f'{new_name[:-5]}_{suffix}.json'

        os.rename(f'./json/{path}', f'./json/{new_name}')
        print(f"File '{path}' renamed to '{new_name}'")

    except Exception as e:
        print(f"Error renaming file '{path}': {e}")


def rename_json_list():
    files = os.listdir('./json/')
    for file in files:
        if not (file.endswith('.json') or file.endswith('.txt')):
            continue
        # 文件名已以数字开头（如 10508105.json 或 10508105_1.json），说明已是规范名，跳过
        if re.match(r'^\d+(_\d+)?\.json$', file):
            continue
        rename_json(file)


def reconcile_resources():
    """
    一次性修复：重命名混乱导致资源目录名和 JSON 文件名不匹配的问题。
    对于每个 JSON 文件，检查其资源目录是否存在；若不存在但存在同 storyId 的
    孤儿资源目录，将其重命名为当前 jsonId，避免重复下载。
    """
    json_ids = set()
    for f in os.listdir('./json/'):
        if f.endswith('.json'):
            json_ids.add(f.replace('.json', ''))

    resource_dirs = set()
    for d in os.listdir('./resource/'):
        if os.path.isdir(os.path.join('./resource/', d)):
            resource_dirs.add(d)

    # 找出孤儿资源目录（没有对应 JSON 文件的）
    orphans = {}
    for d in resource_dirs:
        if d not in json_ids:
            sid = d.split('_')[0]
            orphans.setdefault(sid, []).append(d)

    if not orphans:
        return

    total_fixed = 0
    # 对于每个 JSON，检查资源目录是否存在
    for jid in sorted(json_ids):
        res_dir = './resource/' + jid
        # 目录存在且非空则跳过
        if os.path.isdir(res_dir) and os.listdir(res_dir):
            continue

        # 查找同 storyId 的孤儿目录
        sid = jid.split('_')[0]
        if sid not in orphans:
            continue

        cand_list = orphans[sid]
        if not cand_list:
            continue

        # 选文件最多的孤儿目录
        best = max(cand_list, key=lambda d: sum(len(files) for _, _, files in os.walk('./resource/' + d)))
        src = './resource/' + best
        dst = './resource/' + jid

        try:
            # 目标目录如果存在但为空，先删掉
            if os.path.isdir(dst):
                os.rmdir(dst)
            os.rename(src, dst)
            print(f"资源归位: {best} → {jid}")
            total_fixed += 1
        except Exception as e:
            print(f"资源归位失败 {best} → {jid}: {e}")

        # 从候选列表中移除已处理的
        orphans[sid] = [d for d in cand_list if d != best]

    # 清理完全无用的空孤儿目录（去掉最后只剩空壳的目录）
    for sid, cand_list in list(orphans.items()):
        for d in cand_list:
            path = './resource/' + d
            try:
                if os.path.isdir(path) and not os.listdir(path):
                    os.rmdir(path)
                    print(f"清理空目录: {d}")
            except:
                pass

    if total_fixed > 0:
        print(f"资源归位完成，共修复 {total_fixed} 个目录")


# 获取列表
def get_list():
    json_dir = './json/'  # 定义 JSON 文件所在目录
    # 检查目录是否存在
    if not os.path.exists(json_dir):
        print(f"Warning: Directory '{json_dir}' does not exist.")
        return []
    # 获取目录下所有 JSON 文件的文件名（去掉扩展名）并按名称升序排序
    json_list = sorted(
        file.replace('.json', '') for file in os.listdir(json_dir)
        if file.endswith('.json')
    )
    return json_list

LATEST_CATEGORY = "最新更新"

def get_scene_update_time(jid):
    """场景最近更新时间：json 与 resource 目录内文件的最大修改时间。"""
    latest = 0.0
    json_path = './json/' + jid + '.json'
    if os.path.exists(json_path):
        try:
            latest = max(latest, os.path.getmtime(json_path))
        except OSError:
            pass
    res_dir = './resource/' + jid
    if os.path.isdir(res_dir):
        for root, _, files in os.walk(res_dir):
            for name in files:
                try:
                    latest = max(latest, os.path.getmtime(os.path.join(root, name)))
                except OSError:
                    pass
    return latest

def format_scene_date(ts):
    """将时间戳格式化为 MM-DD 或 YYYY-MM-DD（跨年）。"""
    if ts <= 0:
        return ""
    lt = time.localtime(ts)
    now = time.localtime()
    if lt.tm_year != now.tm_year:
        return time.strftime("%Y-%m-%d", lt)
    return time.strftime("%m-%d", lt)

def get_recent_json_list(limit=None):
    """按最近更新时间排序的场景列表。"""
    if limit is None:
        limit = int(user_setting.get("最新显示数量", 24))
    limit = max(1, limit)
    scored = [(get_scene_update_time(jid), jid) for jid in json_list]
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [jid for ts, jid in scored[:limit] if ts > 0] or [jid for _, jid in scored[:limit]]

_recent_list_cache = None
_recent_list_cache_at = 0
_custom_list_cache = None
_custom_list_cache_at = 0
_icon_surface_cache = {}
_ui_dirty = True
_cached_category_page = -1
_cached_category_buttons = []
_cached_scene_key = None
_cached_scene_items = []
_cached_json_buttons = []
_selected_missing_count = 0
_selection_checking = False
pending_play_after_download = ""
_video_surface_lock = threading.Lock()
_latest_video_surface = None
_blink_on = False
_blink_tick = 0
LIST_CACHE_SEC = 20

def mark_ui_dirty():
    global _ui_dirty
    _ui_dirty = True

def invalidate_list_caches():
    global _recent_list_cache, _custom_list_cache
    _recent_list_cache = None
    _custom_list_cache = None

def get_recent_json_list_cached():
    global _recent_list_cache, _recent_list_cache_at
    now = time.time()
    if _recent_list_cache is None or now - _recent_list_cache_at > LIST_CACHE_SEC:
        _recent_list_cache = get_recent_json_list()
        _recent_list_cache_at = now
    return _recent_list_cache

def scan_custom_videos_cached():
    global _custom_list_cache, _custom_list_cache_at
    now = time.time()
    if _custom_list_cache is None or now - _custom_list_cache_at > LIST_CACHE_SEC:
        _custom_list_cache = scan_custom_videos()
        _custom_list_cache_at = now
    return _custom_list_cache

def get_cached_icon(path, size):
    if not path or not os.path.exists(path):
        return None
    key = (path, size[0], size[1], os.path.getmtime(path))
    cached = _icon_surface_cache.get(key)
    if cached is not None:
        return cached
    try:
        icon = pygame.image.load(path).convert_alpha()
        if icon.get_size() != size:
            icon = pygame.transform.smoothscale(icon, size)
        if len(_icon_surface_cache) > 256:
            _icon_surface_cache.clear()
        _icon_surface_cache[key] = icon
        return icon
    except Exception:
        return None

CUSTOM_ID_PREFIX = "__custom__:"
CUSTOM_CATEGORY = "我的录屏"
CUSTOM_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi")

def is_custom_video(jid):
    return isinstance(jid, str) and jid.startswith(CUSTOM_ID_PREFIX)

def get_custom_video_rel(jid):
    return jid[len(CUSTOM_ID_PREFIX):]

def get_custom_video_path(jid):
    return os.path.normpath(os.path.join(CUSTOM_VIDEO_DIR, get_custom_video_rel(jid)))

def scan_custom_videos():
    """扫描自定义录屏目录，返回带前缀的列表（按修改时间倒序）。"""
    found = []
    if not os.path.isdir(CUSTOM_VIDEO_DIR):
        return found
    for root, dirs, files in os.walk(CUSTOM_VIDEO_DIR):
        dirs[:] = [d for d in dirs if d != ".thumbs"]
        for name in files:
            if name.lower().endswith(CUSTOM_VIDEO_EXTS):
                abs_path = os.path.join(root, name)
                rel = os.path.relpath(abs_path, CUSTOM_VIDEO_DIR).replace("\\", "/")
                try:
                    mtime = os.path.getmtime(abs_path)
                except OSError:
                    mtime = 0
                found.append((mtime, rel))
    found.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [CUSTOM_ID_PREFIX + rel for _, rel in found]

def get_custom_thumb_path(rel_path):
    safe = rel_path.replace("/", "_").replace("\\", "_")
    return os.path.join(CUSTOM_VIDEO_DIR, ".thumbs", safe + ".jpg")

def ensure_custom_thumb(abs_path, rel_path):
    """为自定义视频生成首帧缩略图（同步，仅后台线程调用）。"""
    thumb = get_custom_thumb_path(rel_path)
    try:
        if os.path.exists(thumb) and os.path.getmtime(thumb) >= os.path.getmtime(abs_path):
            return thumb
    except OSError:
        pass
    os.makedirs(os.path.dirname(thumb), exist_ok=True)
    with _silence_ffmpeg_stderr():
        cap = cv2.VideoCapture(abs_path)
        ok, frame = cap.read()
        cap.release()
    if not ok:
        return None
    try:
        surf = cv_frame_to_surface(frame)
        pygame.image.save(surf, thumb)
        return thumb
    except Exception:
        return None

_thumb_queue = []
_thumb_queued = set()
_thumb_gen_running = False
_thumb_gen_lock = threading.Lock()

def queue_custom_thumb(abs_path, rel_path):
    """返回已有缩略图；缺失则加入后台队列生成，不阻塞界面。"""
    thumb = get_custom_thumb_path(rel_path)
    try:
        if os.path.exists(thumb) and os.path.getmtime(thumb) >= os.path.getmtime(abs_path):
            return thumb
    except OSError:
        pass
    key = (abs_path, rel_path)
    with _thumb_gen_lock:
        if key not in _thumb_queued:
            _thumb_queued.add(key)
            _thumb_queue.append((abs_path, rel_path))
    start_custom_thumb_loader()
    return None

def start_custom_thumb_loader():
    global _thumb_gen_running
    if _thumb_gen_running:
        return
    _thumb_gen_running = True

    def worker():
        global _thumb_gen_running
        try:
            while True:
                with _thumb_gen_lock:
                    if not _thumb_queue:
                        break
                    abs_path, rel_path = _thumb_queue.pop(0)
                    _thumb_queued.discard((abs_path, rel_path))
                ensure_custom_thumb(abs_path, rel_path)
                mark_ui_dirty()
        finally:
            _thumb_gen_running = False
            with _thumb_gen_lock:
                if _thumb_queue:
                    start_custom_thumb_loader()

    threading.Thread(target=worker, daemon=True).start()

def start_custom_playback(video_path):
    """播放用户本地录屏（循环，ESC 退出）。"""
    global is_play, is_main, json_selected, is_custom_play, commands, play_count
    global auto_play, th_list, th_count
    is_play = True
    is_custom_play = True
    json_selected = False
    is_main = False
    auto_play = False
    commands = []
    play_count = 0
    name = os.path.splitext(os.path.basename(video_path))[0]
    playback_ui["name"] = name
    playback_ui["lines"] = []
    playback_ui["waiting"] = False
    playback_ui["last_cg"] = None
    reset_video_playback()
    screen.fill((8, 10, 16))
    stop_all_videos()
    th_count = "custom"
    player = play_video()
    player.set_video_path(video_path)
    player.set_loop_count(True)
    globals()["th_custom"] = player
    globals()["th_custom"].start()
    th_list.append("th_custom")
    mark_ui_dirty()

# 列表分页
def page_list(p, items):
    new_list = []
    list_len = len(items)
    i = 0
    while (i < 9) and (p*9+i < list_len):
        new_list.append(items[p*9+i])
        i = i+1
    return new_list

# 显示列表
def build_scene_items(scene_list, show_update_date=False, is_custom=False):
    """构建场景列表数据（不绘制）。"""
    items = []
    now_ts = time.time()
    cols = 3
    card_w, card_h = 192, 108
    start_x = max(40, (GAME_SIZE[0] - cols * card_w - (cols - 1) * 24) // 2)
    start_y = 100
    gap_x, gap_y = 24, 16
    for i, li in enumerate(scene_list):
        col = i % cols
        row = i // cols
        li_rect = (
            start_x + col * (card_w + gap_x),
            start_y + row * (card_h + gap_y),
            card_w,
            card_h,
        )
        if is_custom and is_custom_video(li):
            rel = get_custom_video_rel(li)
            abs_path = get_custom_video_path(li)
            img_path = queue_custom_thumb(abs_path, rel) or ""
            label_text = os.path.splitext(os.path.basename(rel))[0]
            if len(label_text) > 14:
                label_text = label_text[:12] + "…"
            label_color = (180, 220, 255)
        else:
            img_path = resolve_scene_preview_path(li) or ""
            if show_update_date:
                ts = get_scene_update_time(li)
                date_str = format_scene_date(ts)
                if ts > 0 and (now_ts - ts) < 7 * 86400:
                    label_text = f"{li.split('_')[0][-6:]} · NEW"
                    label_color = (255, 210, 120)
                else:
                    label_text = f"{li.split('_')[0][-6:]} · {date_str}" if date_str else li.split('_')[0][-6:]
                    label_color = (230, 230, 235)
            else:
                label_text = li.split('_')[0][-6:]
                label_color = (230, 230, 235)
        items.append({
            "rect": li_rect,
            "id": li,
            "img_path": img_path,
            "label": label_text,
            "color": label_color,
            "is_custom": is_custom,
        })
    return items

def draw_scene_list(items):
    """根据缓存数据绘制场景网格。"""
    buttons = []
    for it in items:
        li_rect = it["rect"]
        btn = Button(li_rect, it["id"])
        pygame.draw.rect(screen, (28, 34, 52), li_rect, border_radius=6)
        icon = get_cached_icon(it["img_path"], (li_rect[2], li_rect[3]))
        if icon:
            screen.blit(icon, li_rect[:2])
        border = (120, 190, 255) if it["is_custom"] else (196, 160, 90)
        pygame.draw.rect(screen, border, li_rect, 1, border_radius=6)
        label = small_font.render(it["label"], True, it["color"])
        screen.blit(label, (li_rect[0] + 6, li_rect[1] + li_rect[3] - 22))
        buttons.append(btn)
    return buttons

def load_list(scene_list, show_update_date=False, is_custom=False):
    """兼容旧接口：构建并绘制场景列表。"""
    items = build_scene_items(scene_list, show_update_date, is_custom)
    return draw_scene_list(items)


# ——— ADV 播放界面状态 ———
playback_ui = {
    "name": "",
    "lines": [],
    "waiting": False,
    "last_cg": None,       # 最近一帧静图 Surface（独立拷贝，可安全重绘）
}

video_playback = {
    "active": False,
    "path": "",
    "frame": 0,
    "total_frames": 0,
    "fps": 30.0,
    "seek_to": None,
    "paused": False,
    "bar_dragging": False,
}

def format_video_time(seconds):
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def get_video_seek_layout():
    w, h = GAME_SIZE
    bar_h = 54
    bar_y = h - bar_h - 14
    margin = 20
    time_w = 64
    track_x = margin + time_w + 10
    track_w = max(120, w - 2 * margin - 2 * (time_w + 10))
    return {
        "bar": (margin, bar_y, w - 2 * margin, bar_h),
        "track": (track_x, bar_y + 16, track_w, 8),
        "hit": (track_x - 6, bar_y, track_w + 12, bar_h),
        "time_left": (margin, bar_y + 12),
        "time_right": (w - margin - time_w, bar_y + 12),
    }

def init_video_playback(path, fps, total_frames):
    video_playback.update({
        "active": True,
        "path": path,
        "frame": 0,
        "total_frames": max(0, int(total_frames or 0)),
        "fps": float(fps or 30),
        "seek_to": None,
        "paused": False,
        "bar_dragging": False,
        "audio_start": None,
        "audio_seek": None,
        "audio_loop": True,
        "_audio_paused_applied": False,
        "audio_has_track": False,
    })

def reset_video_playback():
    video_playback.update({
        "active": False,
        "path": "",
        "frame": 0,
        "total_frames": 0,
        "fps": 30.0,
        "seek_to": None,
        "paused": False,
        "bar_dragging": False,
        "audio_start": None,
        "audio_seek": None,
        "audio_loop": True,
        "_audio_paused_applied": False,
        "audio_has_track": False,
    })

_AUDIO_CACHE_DIR = os.path.join(".cache", "video_audio")

def _find_ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def get_video_audio_wav(video_path):
    """从 MP4 提取音轨为 wav（缓存）。OpenCV 不解码音频，需单独处理。"""
    video_path = os.path.abspath(video_path)
    if not os.path.isfile(video_path):
        return None
    os.makedirs(_AUDIO_CACHE_DIR, exist_ok=True)
    cache_name = hashlib.md5(video_path.encode("utf-8")).hexdigest() + ".wav"
    wav_path = os.path.join(_AUDIO_CACHE_DIR, cache_name)
    try:
        if os.path.exists(wav_path) and os.path.getmtime(wav_path) >= os.path.getmtime(video_path):
            if os.path.getsize(wav_path) > 64:
                return wav_path
    except OSError:
        pass
    ffmpeg = _find_ffmpeg_exe()
    if not ffmpeg:
        print("未找到 ffmpeg，MP4 将无声音（可执行: pip install imageio-ffmpeg）")
        return None
    cmd = [
        ffmpeg, "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        wav_path,
    ]
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, creationflags=flags,
        )
    except Exception as e:
        print("提取音轨失败:", e)
        return None
    if os.path.exists(wav_path) and os.path.getsize(wav_path) > 64:
        return wav_path
    try:
        if os.path.exists(wav_path):
            os.remove(wav_path)
    except OSError:
        pass
    return None

def start_video_audio(video_path, start_sec=0.0, loop=False):
    """主线程：播放已提取的音轨。"""
    wav = get_video_audio_wav(video_path)
    if not wav:
        video_playback["audio_has_track"] = False
        return False
    try:
        pygame.mixer.music.load(wav)
        pygame.mixer.music.play(-1 if loop else 0, start=max(0.0, float(start_sec)))
        video_playback["audio_has_track"] = True
        return True
    except Exception as e:
        print("音轨播放失败:", e)
        video_playback["audio_has_track"] = False
        return False

def stop_video_audio():
    video_playback["audio_has_track"] = False
    video_playback["_audio_paused_applied"] = False
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass

def set_video_audio_paused(paused):
    try:
        if paused:
            pygame.mixer.music.pause()
        else:
            pygame.mixer.music.unpause()
    except Exception:
        pass

def queue_video_audio_start(video_path, start_sec=0.0, loop=True):
    """后台提取音轨，完成后由主线程开始播放。"""
    def worker():
        if get_video_audio_wav(video_path):
            video_playback["audio_start"] = (video_path, float(start_sec), bool(loop))
    threading.Thread(target=worker, daemon=True).start()

def process_video_audio():
    """主线程处理音轨启动/跳转/暂停（pygame.mixer 须在主线程调用）。"""
    if not (is_custom_play and video_playback.get("active")):
        return
    pending = video_playback.pop("audio_start", None)
    if pending:
        path, start, loop = pending
        start_video_audio(path, start_sec=start, loop=loop)
    seek_sec = video_playback.pop("audio_seek", None)
    if seek_sec is not None:
        path = video_playback.get("path") or ""
        loop = video_playback.get("audio_loop", True)
        if path:
            start_video_audio(path, start_sec=seek_sec, loop=loop)
    paused = bool(video_playback.get("paused"))
    if paused != video_playback.get("_audio_paused_applied", False):
        if video_playback.get("audio_has_track"):
            set_video_audio_paused(paused)
        video_playback["_audio_paused_applied"] = paused

def video_seek_hit(x, y):
    if not video_playback.get("active"):
        return False
    hx, hy, hw, hh = get_video_seek_layout()["hit"]
    return hx <= x <= hx + hw and hy <= y <= hy + hh

def apply_video_seek_from_x(x):
    if not video_playback.get("active"):
        return
    tx, ty, tw, th = get_video_seek_layout()["track"]
    total = int(video_playback.get("total_frames") or 0)
    if total <= 1 or tw <= 0:
        return
    t = max(0.0, min(1.0, (x - tx) / tw))
    video_playback["seek_to"] = int(t * (total - 1))
    mark_ui_dirty()

def seek_video_relative(seconds):
    if not video_playback.get("active"):
        return
    fps = float(video_playback.get("fps") or 30)
    total = int(video_playback.get("total_frames") or 0)
    if total <= 0:
        return
    delta = int(seconds * fps)
    current = int(video_playback.get("frame") or 0)
    target = max(0, min(total - 1, current + delta))
    video_playback["seek_to"] = target
    mark_ui_dirty()

def toggle_video_pause():
    if video_playback.get("active"):
        video_playback["paused"] = not video_playback.get("paused")
        mark_ui_dirty()

def _open_video_capture(video_fold):
    cap = cv2.VideoCapture(video_fold)
    if not cap.isOpened():
        return None, 30.0, 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    if fps < 1 or fps > 120:
        fps = 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    return cap, fps, total

def _seek_video_capture(video_fold, cap, frame_idx, fps):
    frame_idx = max(0, int(frame_idx))
    cap.release()
    cap = cv2.VideoCapture(video_fold)
    if frame_idx > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, (frame_idx / max(fps, 1)) * 1000.0)
        actual = int(cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
        if actual <= 0 or abs(actual - frame_idx) > max(3, int(fps)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    return cap, int(cap.get(cv2.CAP_PROP_POS_FRAMES) or frame_idx)

# 对话框遮罩透明度 20~230（越大越不透明），可在播放时用滑块调节
dialogue_alpha = int(user_setting.get("对话框透明度", 145))
dialogue_alpha = max(20, min(230, dialogue_alpha))
alpha_slider_dragging = False

def get_layout():
    """根据窗口尺寸计算 CG 与对话框布局。"""
    w, h = GAME_SIZE
    # 对话框固定在底部，CG 尽量铺满剩余区域（接近原版 1280x720）
    box_h = min(170, max(130, h // 6))
    box_margin = 16
    box_y = h - box_h - 10
    box = (box_margin, box_y, w - box_margin * 2, box_h)

    avail_h = max(240, box_y - 8)
    # 优先使用原版 CG 尺寸，窗口不够再缩小
    cg_w, cg_h = 1280, 720
    if cg_w > w - 8 or cg_h > avail_h:
        scale = min((w - 8) / 1280, avail_h / 720)
        cg_w = max(2, int(1280 * scale))
        cg_h = max(2, int(720 * scale))
    cg_x = (w - cg_w) // 2
    cg_y = max(0, (avail_h - cg_h) // 2)
    name_rect = (box[0] + 18, box[1] - 36, 260, 34)

    # 对话框右上角透明度滑块
    track_w, track_h = 120, 6
    track_x = box[0] + box[2] - track_w - 56
    track_y = box[1] + 14
    slider = {
        "track": (track_x, track_y, track_w, track_h),
        "hit": (track_x - 8, track_y - 12, track_w + 48, 32),
        "label": (track_x - 52, track_y - 6),
    }
    return {
        "cg": (cg_x, cg_y, cg_w, cg_h),
        "box": box,
        "name": name_rect,
        "cg_size": (cg_w, cg_h),
        "slider": slider,
    }

def save_dialogue_alpha():
    """把当前透明度写回 settings.json。"""
    try:
        user_setting["对话框透明度"] = int(dialogue_alpha)
        with open("settings.json", "w", encoding="utf8") as f:
            json.dump(user_setting, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("保存透明度失败:", e)

def set_dialogue_alpha_from_x(x):
    """根据鼠标 x 更新透明度。"""
    global dialogue_alpha
    track = get_layout()["slider"]["track"]
    tx, ty, tw, th = track
    t = 0.0 if tw <= 0 else (x - tx) / tw
    t = max(0.0, min(1.0, t))
    dialogue_alpha = int(20 + t * (230 - 20))

def alpha_slider_hit(x, y):
    hx, hy, hw, hh = get_layout()["slider"]["hit"]
    return hx <= x <= hx + hw and hy <= y <= hy + hh

def draw_alpha_slider():
    """在对话框上绘制透明度滑块。"""
    layout = get_layout()
    track = layout["slider"]["track"]
    tx, ty, tw, th = track
    lx, ly = layout["slider"]["label"]

    label = small_font.render("透明", True, (210, 210, 220))
    screen.blit(label, (lx, ly))

    # 轨道
    pygame.draw.rect(screen, (50, 56, 72), (tx, ty, tw, th), border_radius=3)
    t = (dialogue_alpha - 20) / (230 - 20)
    fill_w = int(tw * t)
    if fill_w > 0:
        pygame.draw.rect(screen, (196, 160, 90), (tx, ty, fill_w, th), border_radius=3)

    # 滑块圆点
    kx = tx + fill_w
    ky = ty + th // 2
    pygame.draw.circle(screen, (245, 240, 230), (kx, ky), 8)
    pygame.draw.circle(screen, (196, 160, 90), (kx, ky), 8, 1)

    pct = small_font.render(f"{int(t * 100)}%", True, (200, 200, 210))
    screen.blit(pct, (tx + tw + 8, ty - 6))

def cv_frame_to_surface(frame):
    """OpenCV BGR 帧 → 独立的 pygame Surface（必须拷贝，避免缓冲失效）。"""
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = frame_rgb.shape[:2]
    surf = pygame.image.frombytes(frame_rgb.tobytes(), (w, h), "RGB")
    return surf.convert()

def store_cg(surface):
    """保存可重复绘制的 CG 拷贝。"""
    if surface is None:
        playback_ui["last_cg"] = None
        return None
    # 统一转成普通显示格式并独立拷贝
    try:
        owned = surface.convert().copy()
    except pygame.error:
        owned = surface.copy()
    playback_ui["last_cg"] = owned
    return owned

def blit_cg(surface):
    """将 CG/视频帧居中绘制到屏幕。"""
    layout = get_layout()
    cx, cy, cw, ch = layout["cg"]
    if surface.get_size() != (cw, ch):
        try:
            surface = pygame.transform.smoothscale(surface, (cw, ch))
        except pygame.error:
            surface = pygame.transform.scale(surface, (cw, ch))
    screen.fill((8, 10, 16))
    screen.blit(surface, (cx, cy))
    store_cg(surface)
    return surface

def blit_frosted_rect(rect, tint=(16, 20, 34, 150), blur_factor=14,
                      border_color=(255, 255, 255, 50), accent=None, radius=12):
    """在已有画面上绘制毛玻璃面板（先截取再模糊再着色）。"""
    x, y, w, h = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
    sw, sh = screen.get_size()
    x = max(0, min(x, sw - 1))
    y = max(0, min(y, sh - 1))
    w = max(0, min(w, sw - x))
    h = max(0, min(h, sh - y))
    if w < 4 or h < 4:
        return

    try:
        region = screen.subsurface((x, y, w, h)).copy()
    except pygame.error:
        return

    # 两次降采样放大 = 近似高斯模糊，性能好
    bf = max(4, int(blur_factor))
    tw, th = max(1, w // bf), max(1, h // bf)
    small = pygame.transform.smoothscale(region, (tw, th))
    frosted = pygame.transform.smoothscale(small, (w, h))
    tw2, th2 = max(1, w // max(2, bf // 2)), max(1, h // max(2, bf // 2))
    frosted = pygame.transform.smoothscale(
        pygame.transform.smoothscale(frosted, (tw2, th2)), (w, h))

    glass = pygame.Surface((w, h), pygame.SRCALPHA)
    glass.blit(frosted, (0, 0))

    # 冷色半透明罩 + 顶部高光，做出玻璃质感
    veil = pygame.Surface((w, h), pygame.SRCALPHA)
    veil.fill(tint)
    glass.blit(veil, (0, 0))
    hi_h = max(3, h // 4)
    highlight = pygame.Surface((w, hi_h), pygame.SRCALPHA)
    for i in range(hi_h):
        a = int(28 * (1.0 - i / max(hi_h - 1, 1)))
        pygame.draw.line(highlight, (255, 255, 255, a), (0, i), (w, i))
    glass.blit(highlight, (0, 0))

    # 圆角裁剪
    if radius > 0:
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
        glass.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    screen.blit(glass, (x, y))
    if border_color is not None:
        bc = border_color[:3]
        pygame.draw.rect(screen, bc, (x, y, w, h), 1, border_radius=radius)
    if accent is not None:
        pygame.draw.rect(screen, accent[:3], (x + 2, y, w - 4, 2), border_radius=1)


def draw_dialogue_chrome():
    """绘制毛玻璃对话框、姓名牌、继续提示（不清除 CG）。"""
    layout = get_layout()
    bx, by, bw, bh = layout["box"]
    a = max(20, min(230, int(dialogue_alpha)))
    name_a = max(20, min(230, int(a + 15)))

    blit_frosted_rect(
        (bx, by, bw, bh),
        tint=(12, 16, 30, a),
        blur_factor=16,
        border_color=(220, 210, 190),
        accent=(196, 160, 90),
        radius=14,
    )

    name = (playback_ui.get("name") or "").strip()
    if name:
        nx, ny, nw, nh = layout["name"]
        name_surf_tmp = text_font.render(name, True, (255, 236, 200))
        nw = max(120, name_surf_tmp.get_width() + 28)
        blit_frosted_rect(
            (nx, ny, nw, nh),
            tint=(36, 50, 88, name_a),
            blur_factor=12,
            border_color=(196, 160, 90),
            accent=None,
            radius=8,
        )
        screen.blit(name_surf_tmp, (nx + 14, ny + (nh - name_surf_tmp.get_height()) // 2))

    draw_alpha_slider()

    ty = by + 34  # 给顶部滑块留一行空间
    max_lines = max(1, (bh - 42) // 36)
    for line in (playback_ui.get("lines") or [])[:max_lines]:
        # 轻描边，保证毛玻璃上文字可读
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            shadow = text_font.render(line, True, (0, 0, 0))
            screen.blit(shadow, (bx + 26 + ox, ty + oy))
        ts = text_font.render(line, True, (248, 248, 252))
        screen.blit(ts, (bx + 26, ty))
        ty += 36

    if playback_ui.get("waiting"):
        blink = (pygame.time.get_ticks() // 400) % 2 == 0
        if blink:
            ax = bx + bw - 36
            ay = by + bh - 28
            pygame.draw.polygon(screen, (220, 190, 120),
                                [(ax, ay), (ax + 14, ay + 8), (ax, ay + 16)])

def draw_custom_play_hud():
    """自定义录屏播放时的控制条（顶部信息 + 底部可拖拽进度）。"""
    w, h = GAME_SIZE
    top = pygame.Surface((w - 24, 36), pygame.SRCALPHA)
    top.fill((10, 14, 26, 190))
    screen.blit(top, (12, 4))
    name = playback_ui.get("name") or "录屏"
    paused = video_playback.get("paused")
    state = "已暂停" if paused else "播放中"
    hint = f"{name}  ·  {state}  ·  空格暂停  ·  ←/→ ±5秒  ·  ESC 退出"
    hs = small_font.render(hint, True, (220, 235, 255))
    screen.blit(hs, (24, 14))

    if not video_playback.get("active"):
        return

    layout = get_video_seek_layout()
    bx, by, bw, bh = layout["bar"]
    panel = pygame.Surface((bw, bh), pygame.SRCALPHA)
    panel.fill((10, 14, 26, 210))
    screen.blit(panel, (bx, by))

    tx, ty, tw, th = layout["track"]
    total = max(1, int(video_playback.get("total_frames") or 1))
    frame = max(0, min(int(video_playback.get("frame") or 0), total - 1))
    fps = float(video_playback.get("fps") or 30)
    progress = frame / max(1, total - 1)

    cur_t = format_video_time(frame / fps)
    tot_t = format_video_time(total / fps)
    screen.blit(small_font.render(cur_t, True, (210, 220, 235)), layout["time_left"])
    screen.blit(small_font.render(tot_t, True, (210, 220, 235)), layout["time_right"])

    pygame.draw.rect(screen, (50, 56, 72), (tx, ty, tw, th), border_radius=4)
    fill_w = int(tw * progress)
    if fill_w > 0:
        pygame.draw.rect(screen, (120, 190, 255), (tx, ty, fill_w, th), border_radius=4)
    kx = tx + fill_w
    ky = ty + th // 2
    pygame.draw.circle(screen, (245, 240, 230), (kx, ky), 8)
    pygame.draw.circle(screen, (120, 190, 255), (kx, ky), 8, 1)

    tip = small_font.render("拖动进度条跳转", True, (170, 185, 205))
    screen.blit(tip, (bx + bw // 2 - tip.get_width() // 2, by + bh - 18))

def draw_playback_hud(progress=0.0):
    """播放页顶部 HUD：毛玻璃条 + 进度 + 快捷键提示。"""
    w, h = GAME_SIZE
    hud_h = 42
    blit_frosted_rect(
        (12, 4, w - 24, hud_h),
        tint=(10, 14, 26, 130),
        blur_factor=12,
        border_color=(255, 255, 255),
        accent=None,
        radius=10,
    )

    bar_w = max(100, w - 200)
    bar_x, bar_y = 100, 12
    pygame.draw.rect(screen, (40, 46, 62), (bar_x, bar_y, bar_w, 6), border_radius=3)
    if progress > 0:
        fill = int(bar_w * min(progress, 1.0))
        pygame.draw.rect(screen, (196, 160, 90), (bar_x, bar_y, fill, 6), border_radius=3)

    hint = "点击/空格 继续 · A 自动 · ESC 退出"
    if auto_play:
        hint = "自动播放中 · A 关闭 · ESC 退出"
    hs = small_font.render(hint, True, (220, 222, 230))
    screen.blit(hs, (bar_x, bar_y + 12))

    if commands:
        pct = small_font.render(f"{play_count}/{len(commands)}", True, (230, 230, 235))
        screen.blit(pct, (w - pct.get_width() - 28, bar_y + 12))

def refresh_adv_frame(base=None):
    """重绘一帧 ADV：CG + 对话框 + HUD。"""
    if base is not None:
        blit_cg(base)
    elif playback_ui.get("last_cg") is not None:
        layout = get_layout()
        cx, cy, cw, ch = layout["cg"]
        screen.fill((8, 10, 16))
        cg = playback_ui["last_cg"]
        if cg.get_size() != (cw, ch):
            try:
                cg = pygame.transform.smoothscale(cg, (cw, ch))
            except pygame.error:
                cg = pygame.transform.scale(cg, (cw, ch))
            store_cg(cg)
        else:
            cg = playback_ui["last_cg"]
        screen.blit(cg, (cx, cy))
    else:
        screen.fill((8, 10, 16))
    draw_dialogue_chrome()
    prog = (play_count / len(commands)) if commands else 0
    draw_playback_hud(prog)

def stop_all_videos():
    global th_list
    try:
        for th in th_list:
            t = globals().get(th)
            if t is not None:
                t.set_run_count(True)
    except Exception:
        pass
    th_list = []

def any_video_running():
    for th in th_list:
        try:
            t = globals().get(th)
            if t is not None and t.is_alive() and not t.run_count:
                return True
        except Exception:
            pass
    return False

def exit_playback():
    """结束播放并回到分类列表。"""
    global is_play, is_main, json_selected, play_count, auto_play, is_custom_play
    global pending_play_after_download
    print("播放结束 / 退出")
    play_count = 0
    is_play = False
    is_main = True
    json_selected = False
    auto_play = False
    is_custom_play = False
    pending_play_after_download = ""
    playback_ui["name"] = ""
    playback_ui["lines"] = []
    playback_ui["waiting"] = False
    playback_ui["last_cg"] = None
    reset_video_playback()
    clear_video_surface()
    stop_video_audio()
    stop_all_videos()
    screen.fill((8, 10, 16))
    mark_ui_dirty()

def _silence_ffmpeg_stderr():
    """临时屏蔽 FFmpeg/H264 往控制台刷的 Invalid NAL 等日志。"""
    class _Ctx:
        def __enter__(self):
            try:
                self._err = os.dup(2)
                self._null = os.open(os.devnull, os.O_WRONLY)
                os.dup2(self._null, 2)
                self._ok = True
            except Exception:
                self._ok = False
            return self

        def __exit__(self, *args):
            if not getattr(self, "_ok", False):
                return
            try:
                os.dup2(self._err, 2)
                os.close(self._null)
                os.close(self._err)
            except Exception:
                pass
    return _Ctx()

class play_video(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.run_count = False
        self.loop_count = True
        self.video_file_name = ""
        self.video_path = ""  # 绝对路径，优先于 resource 相对路径

    def set_video_file_name(self, video_file_name):
        self.video_file_name = video_file_name

    def set_video_path(self, video_path):
        self.video_path = video_path

    def set_run_count(self, count):
        self.run_count = count

    def set_loop_count(self, count):
        self.loop_count = count

    def run(self):
        if self.video_path:
            video_fold = self.video_path
        else:
            video_fold = './resource/' + jsonId + '/' + self.video_file_name
            if not os.path.exists(video_fold):
                ensure_local_media(self.video_file_name)
        if not os.path.exists(video_fold) or os.path.getsize(video_fold) <= 0:
            print(f"视频文件不存在: {video_fold}")
            self.run_count = True
            return

        track_progress = bool(self.video_path)
        # 循环时重新打开文件，避免 CAP_PROP_POS_FRAMES seek 触发 h264 NAL 报错
        with _silence_ffmpeg_stderr():
            while not self.run_count:
                with _silence_ffmpeg_stderr():
                    video, fps, total_frames = _open_video_capture(video_fold)
                if video is None:
                    print(f"无法打开视频: {video_fold}")
                    self.run_count = True
                    break

                if track_progress:
                    init_video_playback(video_fold, fps, total_frames)
                    video_playback["audio_loop"] = self.loop_count
                    queue_video_audio_start(video_fold, 0.0, self.loop_count)

                current_frame = 0
                got_any_frame = False
                while not self.run_count:
                    seek_to = video_playback.get("seek_to")
                    if seek_to is not None and track_progress:
                        video_playback["seek_to"] = None
                        with _silence_ffmpeg_stderr():
                            video, current_frame = _seek_video_capture(
                                video_fold, video, seek_to, fps)
                        video_playback["frame"] = current_frame
                        fps_val = float(video_playback.get("fps") or fps or 30)
                        video_playback["audio_seek"] = current_frame / max(1.0, fps_val)

                    while video_playback.get("paused") and not self.run_count:
                        time.sleep(0.03)

                    success, video_image = video.read()
                    if not success:
                        break
                    got_any_frame = True
                    current_frame += 1
                    if track_progress:
                        video_playback["frame"] = min(
                            current_frame,
                            max(1, int(video_playback.get("total_frames") or current_frame)),
                        )

                    frame_interval = 1.0 / max(1.0, fps)
                    frame_start = time.perf_counter()

                    try:
                        video_surf = cv_frame_to_surface(video_image)
                        layout = get_layout()
                        video_surf = pygame.transform.scale(video_surf, layout["cg_size"])
                        push_video_surface(video_surf)
                    except Exception:
                        continue

                    elapsed = time.perf_counter() - frame_start
                    sleep_t = frame_interval - elapsed
                    if sleep_t > 0:
                        time.sleep(sleep_t)

                video.release()

                if not got_any_frame:
                    if self.video_path:
                        print(f"自定义视频无法解码，已跳过: {video_fold}")
                        self.run_count = True
                        break
                    print(f"视频无法解码，尝试重新下载: {self.video_file_name}")
                    try:
                        if os.path.exists(video_fold):
                            os.remove(video_fold)
                    except Exception:
                        pass
                    ensure_local_media(self.video_file_name)
                    video = cv2.VideoCapture(video_fold)
                    ok = video.isOpened() and video.read()[0]
                    video.release()
                    if not ok:
                        print(f"视频仍无法播放，已跳过: {video_fold}")
                        self.run_count = True
                        break
                    continue

                if not self.loop_count:
                    break


# 播放指令相关
def read_adv(jsonId):
    with open("./json/"+jsonId+'.json', 'r') as f:
        dojson = json.load(f)
        resources= dojson["resource"]
        for resource in resources:
            if "text" in resource["fileName"]:
                fileName = resource["fileName"]
                break

    if use_translate:
        txt_path = "./resource/"+jsonId+"/"+fileName.replace(".txt","_CN.txt")
    else:
        txt_path = "./resource/"+jsonId+"/"+fileName
    commands =[]
    with open(txt_path, "r", encoding='utf8') as f:
        commands= f.readlines()
    return commands

def wrap_text(text, font, max_width):
    """将文本按像素宽度自动换行，返回行列表。"""
    lines = []
    current_line = ""
    for char in text:
        test_line = current_line + char
        w, _ = font.size(test_line)
        if w > max_width and current_line:
            lines.append(current_line)
            current_line = char
        else:
            current_line = test_line
    if current_line:
        lines.append(current_line)
    return lines

def strip_adv_tags(text):
    text = text.replace("<outline width=2 color=black>","").replace("</outline>","")
    text = text.replace("<size=31>","").replace("</size>","")
    text = text.replace("<size=27>","").replace("</size>","")
    if "<ruby>" in text:
        pattern = re.compile(r'<ruby>(.*?)</ruby>')
        matches = pattern.findall(text)
        for r in matches:
            text = text.replace("<ruby>"+r+"</ruby>", r.split("|")[0])
    return text

def load_bg_image(params_path):
    """加载背景图；缺失时尝试补下，再回退黑图。"""
    if params_path == "color_0_0_0":
        return pygame.image.load(_legacy_asset('color_0_0_0.jpg')).convert()
    img_path = "./resource/" + jsonId + "/" + params_path.replace("\\", "/")
    if not (os.path.exists(img_path) and os.path.getsize(img_path) > 0):
        ensured = ensure_local_media(params_path)
        if ensured:
            img_path = ensured
    if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
        try:
            return pygame.image.load(img_path).convert()
        except Exception as e:
            print(f"图片加载失败: {img_path} ({e})")
    else:
        print(f"图片文件不存在，跳过: {img_path}")
    return pygame.image.load(_legacy_asset('color_0_0_0.jpg')).convert()

def read_command(commands,count):
    playback_ui["waiting"] = False
    while(count<len(commands)):

        command = commands[count].strip()
        params = command.split(",")
        print(count,params[0])
        if params[0] == "name":
            if len(params) > 1 and params[1].strip():
                name = strip_adv_tags(params[1])
            else:
                name = ""
            playback_ui["name"] = name.strip()
            # 姓名变化时只更新字幕层，避免无 CG 时整屏刷黑
            if playback_ui.get("last_cg") is not None:
                refresh_adv_frame()

        elif params[0] == "bg":
            cg = load_bg_image(params[1])
            layout = get_layout()
            try:
                cg = pygame.transform.smoothscale(cg, layout["cg_size"])
            except pygame.error:
                cg = pygame.transform.scale(cg, layout["cg_size"])
            blit_cg(cg)
            draw_dialogue_chrome()
            prog = (count / len(commands)) if commands else 0
            draw_playback_hud(prog)
            pygame.display.flip()

        elif params[0] == "playvoice":
            voice_path = "./resource/"+jsonId+"/"+params[2]
            try:
                pygame.mixer.music.load(voice_path)
                pygame.mixer.music.play()
            except FileNotFoundError:
                print(f"语音文件不存在，跳过: {voice_path}")

        elif params[0] == "movieoff":
            global th_count
            try:
                globals()["th_"+th_count].set_run_count(True)
                print("关闭上个视频线程")
            except:
                print(th_count)
                print("关闭上个视频线程失败")

        elif params[0] == "movie":
            movie_file_list = params[1].split(":")
            # 播放前按需补下视频
            for mf in movie_file_list:
                ensure_local_media(mf)
            if len(movie_file_list)==1:
                movie_file= movie_file_list[0]
            if len(movie_file_list)==2:
                video_file = './resource/' + jsonId + '/' + movie_file_list[0]
                with _silence_ffmpeg_stderr():
                    video = cv2.VideoCapture(video_file)
                    if not video.isOpened():
                        print(f"视频文件不存在，跳过: {video_file}")
                        movie_file = movie_file_list[1]
                    else:
                        fps = video.get(cv2.CAP_PROP_FPS) or 30
                        if fps < 1 or fps > 120:
                            fps = 30
                        while True:
                            clock.tick(fps)
                            success, video_image = video.read()
                            if success:
                                try:
                                    video_surf = cv_frame_to_surface(video_image)
                                    layout = get_layout()
                                    video_surf = pygame.transform.scale(video_surf, layout["cg_size"])
                                    blit_cg(video_surf)
                                    draw_dialogue_chrome()
                                    prog = (count / len(commands)) if commands else 0
                                    draw_playback_hud(prog)
                                    pygame.display.flip()
                                except Exception:
                                    continue
                            else:
                                break
                        video.release()
                        movie_file= movie_file_list[1]

            th_count = movie_file
            try:
                for th in th_list:
                    t = globals().get(th)
                    if t is not None:
                        t.set_run_count(True)
            except:
                pass
            globals()["th_"+str(th_count)] = play_video()
            globals()["th_"+str(th_count)].set_video_file_name(movie_file)
            globals()["th_"+str(th_count)].start()
            th_list.append("th_"+str(th_count))


        elif params[0] == "msg":
            text = strip_adv_tags(params[2]) if len(params) > 2 else ""
            layout = get_layout()
            bx, by, bw, bh = layout["box"]
            max_text_width = bw - 52
            wrapped_lines = []
            if text.strip():
                text_lines = text.split('\\n')
                for line in text_lines:
                    wrapped_lines.extend(wrap_text(line, text_font, max_text_width))
            playback_ui["lines"] = wrapped_lines
            refresh_adv_frame()
            pygame.display.flip()

        elif params[0] == "clickwait":
            playback_ui["waiting"] = True
            refresh_adv_frame()
            pygame.display.flip()
            count = count+1
            break

        else:
            pass
        count = count+1
    return count

#翻译相关
#md5
def generate_sign(appid, q, salt, secret_key):
    sign_str = appid + q + salt + secret_key
    sign = hashlib.md5(sign_str.encode()).hexdigest()
    return sign


# 常量

WHITE = (255, 255, 255)
RED = (255, 0, 0)

CG_SIZE = (1280, 720)
TEXT_SIZE = (1000, 200)

display_width = user_setting['窗口宽度']
display_height = user_setting['窗口高度']
GAME_SIZE = (display_width, display_height)

下载线程数 = user_setting['下载线程数']
use_translate = True if user_setting['翻译api']['use_translate'] == 'yes' else False
bot_check = True if user_setting['是否喜欢furau'] == 'yes' else False

# 初始化
pygame.init()
pygame.mixer.init()

# 获取屏幕分辨率，限制窗口不能超出屏幕
display_info = pygame.display.Info()
max_w = display_info.current_w
max_h = display_info.current_h
if GAME_SIZE[0] > max_w - 50:
    GAME_SIZE = (max_w - 50, GAME_SIZE[1])
if GAME_SIZE[1] > max_h - 50:
    GAME_SIZE = (GAME_SIZE[0], max_h - 50)

os.environ['SDL_VIDEO_CENTERED'] = '1'  # 窗口居中（必须在 set_mode 前设置）
clock = pygame.time.Clock()
screen = pygame.display.set_mode(GAME_SIZE, pygame.RESIZABLE, 32)
pygame.display.set_caption("DeepOne")
game_font = pygame.font.Font(_legacy_asset('msgothic.ttc'), 50)


# rect
play_button_rect = (GAME_SIZE[0] // 2 - 80, 700, 160, 52)
pages_up_rect = (700, 700, 120, 42)
page_down_rect = (480, 700, 120, 42)
cat_up_rect = (700, 700, 120, 42)
cat_down_rect = (480, 700, 120, 42)

# button
play_button = Button(play_button_rect, 'PLAY')
pages_up_button = Button(pages_up_rect, "下一頁")
pages_down_button = Button(page_down_rect, "上一頁")
cat_up_button = Button(cat_up_rect, "下一頁")
cat_down_button = Button(cat_down_rect, "上一頁")


def draw_progress_bar(x, y, w, h, progress, label, color=(0, 255, 0)):
    """绘制进度条"""
    # 背景
    pygame.draw.rect(screen, (60, 60, 60), (x, y, w, h))
    # 进度
    if progress > 0:
        fill_w = int(w * min(progress, 1.0))
        pygame.draw.rect(screen, color, (x, y, fill_w, h))
    # 文字
    text = small_font.render(f"{label} {int(progress * 100)}%", True, (255, 255, 255))
    screen.blit(text, (x + 10, y + 5))


def pump_startup_events():
    """启动加载时处理退出，避免窗口假死。"""
    for event in pygame.event.get():
        if event.type == QUIT:
            pygame.quit()
            exit()


def draw_loading_screen(phase, progress, detail="", anim_t=0):
    """绘制启动加载界面：旋转动画 + 进度条。"""
    w, h = GAME_SIZE
    screen.fill((10, 12, 20))

    title = title_font.render("DeepOne", True, (236, 224, 198))
    screen.blit(title, (w // 2 - title.get_width() // 2, h // 2 - 155))

    phase_surf = text_font.render(phase, True, (210, 220, 235))
    screen.blit(phase_surf, (w // 2 - phase_surf.get_width() // 2, h // 2 - 95))

    # 旋转加载点
    cx, cy = w // 2, h // 2 - 30
    for i in range(10):
        ang = anim_t / 120.0 + i * (6.28318 / 10)
        dot_x = cx + int(math.cos(ang) * 28)
        dot_y = cy + int(math.sin(ang) * 28)
        t = i / 9
        r = int(90 + 80 * t)
        g = int(130 + 70 * t)
        b = int(170 + 60 * t)
        pygame.draw.circle(screen, (r, g, b), (dot_x, dot_y), 5)

    # 进度条区域
    bar_w = min(580, w - 80)
    bar_x = (w - bar_w) // 2
    bar_y = h // 2 + 10
    bar_h = 22
    pct = max(0.0, min(1.0, progress))

    label = small_font.render("总进度", True, (180, 190, 205))
    screen.blit(label, (bar_x, bar_y - 26))
    pct_text = small_font.render(f"{int(pct * 100)}%", True, (220, 230, 240))
    screen.blit(pct_text, (bar_x + bar_w - pct_text.get_width(), bar_y - 26))

    pygame.draw.rect(screen, (32, 38, 54), (bar_x, bar_y, bar_w, bar_h), border_radius=8)
    fill_w = max(0, int(bar_w * pct))
    if fill_w > 0:
        pygame.draw.rect(screen, (120, 190, 255), (bar_x, bar_y, fill_w, bar_h), border_radius=8)
    pygame.draw.rect(screen, (196, 160, 90), (bar_x, bar_y, bar_w, bar_h), 1, border_radius=8)

    if detail:
        detail_surf = small_font.render(detail, True, (165, 175, 190))
        screen.blit(detail_surf, (w // 2 - detail_surf.get_width() // 2, bar_y + bar_h + 14))

    hint = small_font.render("正在准备资源，请稍候…", True, (130, 140, 158))
    screen.blit(hint, (w // 2 - hint.get_width() // 2, h - 52))

    pygame.display.flip()


def run_loading_animation_loop(state, lock):
    """主线程持续刷新加载动画（60fps），直到 state['done'] 为 True。"""
    while True:
        with lock:
            phase = state.get("phase", "")
            progress = state.get("progress", 0.0)
            detail = state.get("detail", "")
            finished = state.get("done", False)
        draw_loading_screen(phase, progress, detail, pygame.time.get_ticks())
        pump_startup_events()
        clock.tick(60)
        if finished:
            break


def download_previews_with_progress(story_ids, update_fn, progress_start=0.25, progress_end=0.92):
    """多线程下载预览图，通过 update_fn 更新共享进度（不阻塞动画）。"""
    total = len(story_ids)
    if total <= 0:
        return 0, 0

    done = 0
    ok = 0
    lock = threading.Lock()

    def on_one(fut):
        nonlocal done, ok
        try:
            success = bool(fut.result())
        except Exception:
            success = False
        with lock:
            done += 1
            if success:
                ok += 1
            cur_done, cur_ok = done, ok
        prog = progress_start + (progress_end - progress_start) * (cur_done / total)
        update_fn("正在下载预览图", prog, f"预览图 {cur_done}/{total}  ·  成功 {cur_ok}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=下载线程数) as executor:
        futures = [executor.submit(fetch_episode_preview, sid, True) for sid in story_ids]
        for fut in concurrent.futures.as_completed(futures):
            on_one(fut)
    return ok, total


def run_startup_sequence():
    """启动加载：后台执行任务，主线程持续播放流畅动画。"""
    global json_list, categories, category_buttons, pages_size, current_list

    state = {
        "phase": "正在初始化",
        "progress": 0.03,
        "detail": "",
        "done": False,
        "result": [],
    }
    lock = threading.Lock()

    def update(phase, progress, detail=""):
        with lock:
            state["phase"] = phase
            state["progress"] = progress
            state["detail"] = detail

    def worker():
        try:
            update("正在整理场景文件", 0.10)
            rename_json_list()

            update("正在修复资源目录", 0.18)
            reconcile_resources()

            update("正在扫描场景列表", 0.25)
            jl = get_list()
            print(f"场景数量: {len(jl)}")

            missing = collect_missing_preview_ids(jl)
            print(f"待下载预览: {len(missing)}")
            if missing:
                download_previews_with_progress(missing, update)
            else:
                update("预览图已就绪", 0.90, "无需下载")

            update("正在准备界面", 0.96)
            global json_list, categories, category_buttons, pages_size, current_list
            json_list = jl
            invalidate_list_caches()
            categories = get_categories()
            category_buttons = load_categories(categories[:cat_per_page])
            current_list = jl
            pages_size = math.ceil(len(jl) / 12)

            update("加载完成", 1.0, f"共 {len(jl)} 个场景")
            with lock:
                state["result"] = jl
        finally:
            with lock:
                state["done"] = True

    threading.Thread(target=worker, daemon=True).start()
    run_loading_animation_loop(state, lock)
    time.sleep(0.25)
    mark_ui_dirty()
    return state["result"]


# ————————分类相关——————
def get_categories():
    """按ID前4位提取分类列表，并在最前加入「最新更新」「我的录屏」。"""
    cats = set()
    for j in json_list:
        cats.add(j.split('_')[0][:4])
    return [LATEST_CATEGORY, CUSTOM_CATEGORY] + sorted(cats)

def get_list_by_category(cat):
    """获取指定分类下的场景列表。"""
    if cat == LATEST_CATEGORY:
        return get_recent_json_list_cached()
    if cat == CUSTOM_CATEGORY:
        return scan_custom_videos_cached()
    return [j for j in json_list if j.split('_')[0].startswith(cat)]

def get_category_icon(cat):
    """找到分类的第一张可用预览图。"""
    if cat == LATEST_CATEGORY:
        for s in get_recent_json_list_cached():
            icon_path = resolve_scene_preview_path(s)
            if icon_path:
                return icon_path
        return None
    if cat == CUSTOM_CATEGORY:
        for s in scan_custom_videos_cached():
            rel = get_custom_video_rel(s)
            thumb = get_custom_thumb_path(rel)
            if os.path.exists(thumb):
                return thumb
            abs_path = get_custom_video_path(s)
            if os.path.exists(abs_path):
                queue_custom_thumb(abs_path, rel)
        return None
    scenes = get_list_by_category(cat)
    for s in scenes:
        icon_path = resolve_scene_preview_path(s)
        if icon_path:
            return icon_path
    return None

def load_categories(cat_list):
    """构建分类按钮元数据（不绘制）。"""
    buttons = []
    cols = 4
    for i, cat in enumerate(cat_list):
        col = i % cols
        row = i // cols
        x = 60 + col * 300
        y = 90 + row * 165
        rect = (x, y, 240, 135)
        btn = Button(rect, cat)
        if cat == LATEST_CATEGORY:
            btn.count_text = f"{len(get_recent_json_list_cached())} 个最近更新"
            btn.is_latest = True
            btn.is_custom = False
        elif cat == CUSTOM_CATEGORY:
            btn.count_text = f"{len(scan_custom_videos_cached())} 个本地录屏"
            btn.is_latest = False
            btn.is_custom = True
        else:
            btn.count_text = f"{len(get_list_by_category(cat))} 个场景"
            btn.is_latest = False
            btn.is_custom = False
        btn.icon_path = get_category_icon(cat)
        buttons.append(btn)
    return buttons

def draw_category_grid(buttons):
    """绘制分类网格。"""
    for bt in buttons:
        rect = bt.rect
        pygame.draw.rect(screen, (28, 34, 52), rect, border_radius=8)
        icon = get_cached_icon(bt.icon_path, (rect[2], rect[3])) if bt.icon_path else None
        if icon:
            screen.blit(icon, rect[:2])
            overlay = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 110))
            screen.blit(overlay, rect[:2])
        border_color = (255, 190, 90) if getattr(bt, "is_latest", False) else (
            (120, 190, 255) if getattr(bt, "is_custom", False) else (196, 160, 90))
        pygame.draw.rect(screen, border_color, rect,
                         2 if (getattr(bt, "is_latest", False) or getattr(bt, "is_custom", False)) else 1,
                         border_radius=8)
        if getattr(bt, "is_latest", False):
            cat_color = (255, 236, 200)
        elif getattr(bt, "is_custom", False):
            cat_color = (200, 230, 255)
        else:
            cat_color = (255, 255, 255)
        cat_text = text_font.render(bt.text, True, cat_color)
        screen.blit(cat_text, (rect[0] + 10, rect[1] + 10))
        count_text = small_font.render(
            bt.count_text if hasattr(bt, "count_text") else "",
            True, (200, 200, 200))
        screen.blit(count_text, (rect[0] + 10, rect[1] + rect[3] - 25))

def start_adv_playback(jid):
    """进入 ADV 播放。"""
    global is_play, is_main, json_selected, auto_play, commands, play_count, jsonId
    global auto_play_next_at, pending_play_after_download
    jsonId = jid
    commands = read_adv(jid)
    is_play = True
    json_selected = False
    is_main = False
    auto_play = False
    pending_play_after_download = ""
    playback_ui["name"] = ""
    playback_ui["lines"] = []
    playback_ui["waiting"] = False
    playback_ui["last_cg"] = None
    screen.fill((8, 10, 16))
    play_count = read_command(commands, 0)
    auto_play_next_at = pygame.time.get_ticks() + auto_play_ms
    mark_ui_dirty()
    if play_count == len(commands):
        exit_playback()

def request_play_scene(jid):
    """请求播放：缺资源则后台下载，齐了之后自动开播。"""
    global pending_play_after_download, json_selected
    if is_custom_video(jid):
        start_custom_playback(get_custom_video_path(jid))
        return
    if get_missing_resources(jid, media_only=False):
        pending_play_after_download = jid
        json_selected = False
        get_resource(jid)
        mark_ui_dirty()
    else:
        start_adv_playback(jid)

# ————————控制参数————

# 寝室id
jsonId = ''
# 播放状态
is_play = False
is_main = True
in_category = False  # 是否在分类浏览模式
current_category = ''  # 当前选中的分类
json_selected = False
play_count= 0
th_list=[]
th_count = ""
commands = []
auto_play = False
auto_play_ms = 2800  # 自动播放间隔
auto_play_next_at = 0
is_custom_play = False  # 是否正在播放用户本地录屏

#翻译状态
if use_translate:
    text_font = pygame.font.Font(_legacy_asset('SIMFANG.TTF'), 30)
    small_font = pygame.font.Font(_legacy_asset('SIMFANG.TTF'), 24)
    title_font = pygame.font.Font(_legacy_asset('SIMFANG.TTF'), 40)
else:
    text_font = pygame.font.Font(_legacy_asset('msgothic.ttc'), 30)
    small_font = pygame.font.Font(_legacy_asset('msgothic.ttc'), 24)
    title_font = pygame.font.Font(_legacy_asset('msgothic.ttc'), 40)
# 初始页码
json_list_page = 0
json_list = []

# --寝室列表（在加载界面中执行）
categories = []
category_page = 0  # 分类当前页码
cat_per_page = 12  # 每页12个分类（4列×3行）
current_list = []
category_buttons = []
pages_size = 1
video_control = False
pending_play_after_download = ""

# 分类返回按钮
back_button = Button((20, 20, 80, 40), "← 返回")
json_button_list = []  # 场景按钮列表，在绘制时更新

print('----用户设置，请到setting.json中修改------')
print(user_setting)
print('----------------------------------------')

json_list = run_startup_sequence()

while bot_check:
    # ——— 事件处理 ———
    for event in pygame.event.get():
        if event.type == QUIT:
            exit()
        if event.type == pygame.VIDEORESIZE:
            GAME_SIZE = (event.w, event.h)
            screen = pygame.display.set_mode(GAME_SIZE, pygame.RESIZABLE, 32)
            _icon_surface_cache.clear()
            layout_nav_buttons()
            mark_ui_dirty()
            if is_play:
                refresh_adv_frame()

        # 播放中：键盘快捷键
        if is_play and event.type == KEYDOWN:
            if event.key == K_ESCAPE:
                exit_playback()
            elif is_custom_play:
                if event.key == K_SPACE:
                    toggle_video_pause()
                elif event.key == K_LEFT:
                    seek_video_relative(-5)
                elif event.key == K_RIGHT:
                    seek_video_relative(5)
            elif not is_custom_play:
                if event.key in (K_SPACE, K_RETURN, K_RIGHT):
                    play_count = read_command(commands, play_count)
                    auto_play_next_at = pygame.time.get_ticks() + auto_play_ms
                    mark_ui_dirty()
                    if play_count == len(commands):
                        exit_playback()
                elif event.key == K_a:
                    auto_play = not auto_play
                    auto_play_next_at = pygame.time.get_ticks() + auto_play_ms
                    refresh_adv_frame()
                    mark_ui_dirty()

        # 分类浏览（显示分类网格）
        if is_main and not in_category and not json_selected and event.type == MOUSEBUTTONDOWN and event.button == 1:
            x = event.pos[0]
            y = event.pos[1]
            for bt in category_buttons:
                if bt.in_rect(x, y):
                    current_category = bt.text
                    current_list = get_list_by_category(current_category)
                    json_list_page = 0
                    pages_size = math.ceil(len(current_list) / 9)
                    in_category = True
                    _cached_scene_key = None
                    mark_ui_dirty()
                    break
            else:
                cat_total = max(1, math.ceil(len(categories) / cat_per_page))
                if cat_up_button.in_rect(x, y):
                    category_page = (category_page + 1) % cat_total
                    mark_ui_dirty()
                elif cat_down_button.in_rect(x, y):
                    category_page = (category_page - 1) % cat_total
                    mark_ui_dirty()

        # 滚轮翻页（分类 / 场景）
        if is_main and not json_selected and event.type == pygame.MOUSEWHEEL:
            if in_category:
                json_list_page = json_list_page - event.y
                if json_list_page < 0:
                    json_list_page = pages_size - 1
                elif json_list_page >= pages_size:
                    json_list_page = 0
                _cached_scene_key = None
            else:
                cat_total = max(1, math.ceil(len(categories) / cat_per_page))
                category_page = (category_page - event.y) % cat_total
            mark_ui_dirty()

        # 场景浏览（显示该分类下的场景列表 + 返回按钮）
        if is_main and in_category and not json_selected and event.type == MOUSEBUTTONDOWN and event.button == 1:
            x = event.pos[0]
            y = event.pos[1]
            if back_button.in_rect(x, y):
                in_category = False
                current_list = json_list
                pages_size = math.ceil(len(current_list) / 9)
                json_list_page = 0
                _cached_scene_key = None
                mark_ui_dirty()
            elif pages_up_button.in_rect(x, y):
                json_list_page = json_list_page + 1
                if json_list_page + 1 > pages_size:
                    json_list_page = 0
                _cached_scene_key = None
                mark_ui_dirty()
            elif pages_down_button.in_rect(x, y):
                json_list_page = json_list_page - 1
                if json_list_page < 0:
                    json_list_page = pages_size - 1
                _cached_scene_key = None
                mark_ui_dirty()
            else:
                for bt in json_button_list:
                    if bt.in_rect(x, y):
                        begin_scene_select(bt.text)
                        break

        if is_main and in_category and json_selected and event.type == MOUSEBUTTONDOWN and event.button == 1:
            x = event.pos[0]
            y = event.pos[1]
            if back_button.in_rect(x, y):
                json_selected = False
                mark_ui_dirty()
            elif play_button.in_rect(x, y) and not _selection_checking:
                try:
                    request_play_scene(jsonId)
                except Exception as e:
                    print("播放失败:", e)

        if json_selected and not in_category and event.type == MOUSEBUTTONDOWN and event.button == 1:
            x = event.pos[0]
            y = event.pos[1]
            if play_button.in_rect(x, y) and not _selection_checking:
                try:
                    request_play_scene(jsonId)
                except Exception as e:
                    print("播放失败:", e)

        if is_play and is_custom_play and event.type == MOUSEBUTTONDOWN and event.button == 1:
            if video_seek_hit(event.pos[0], event.pos[1]):
                video_playback["bar_dragging"] = True
                apply_video_seek_from_x(event.pos[0])

        elif is_play and is_custom_play and event.type == MOUSEBUTTONUP and event.button == 1:
            if video_playback.get("bar_dragging"):
                video_playback["bar_dragging"] = False

        elif is_play and is_custom_play and event.type == MOUSEMOTION and video_playback.get("bar_dragging"):
            apply_video_seek_from_x(event.pos[0])

        # 注意：必须用 elif，避免点 PLAY 的同一次点击被当成“下一句”而跳过第一句
        elif is_play and not is_custom_play and event.type == MOUSEBUTTONDOWN and event.button == 1:
            x, y = event.pos
            if alpha_slider_hit(x, y):
                alpha_slider_dragging = True
                set_dialogue_alpha_from_x(x)
                refresh_adv_frame()
            else:
                play_count = read_command(commands, play_count)
                auto_play_next_at = pygame.time.get_ticks() + auto_play_ms
                mark_ui_dirty()
                if play_count == len(commands):
                    exit_playback()

        elif is_play and event.type == MOUSEBUTTONUP and event.button == 1:
            if alpha_slider_dragging:
                alpha_slider_dragging = False
                save_dialogue_alpha()

        elif is_play and event.type == MOUSEMOTION and alpha_slider_dragging:
            set_dialogue_alpha_from_x(event.pos[0])
            refresh_adv_frame()

    # 录屏音轨（主线程处理）
    process_video_audio()

    # 下载完成后自动开播
    if pending_play_after_download and not is_downloading:
        jid = pending_play_after_download
        if not get_missing_resources(jid, media_only=False):
            try:
                start_adv_playback(jid)
            except Exception as e:
                print("自动播放失败:", e)
                pending_play_after_download = ""

    # 自动播放
    if is_play and not is_custom_play and auto_play and playback_ui.get("waiting"):
        now = pygame.time.get_ticks()
        if now >= auto_play_next_at:
            play_count = read_command(commands, play_count)
            auto_play_next_at = now + auto_play_ms
            mark_ui_dirty()
            if play_count == len(commands):
                exit_playback()

    # 等待点击时的闪烁提示：仅在闪烁状态变化时重绘
    blink_changed = False
    if is_play and not any_video_running() and playback_ui.get("waiting"):
        now = pygame.time.get_ticks()
        blink = (now // 400) % 2 == 0
        if blink != _blink_on:
            _blink_on = blink
            blink_changed = True

    need_redraw = (_ui_dirty or is_downloading or pending_play_after_download
                   or blink_changed or (is_play and any_video_running()))

    if need_redraw:
        layout_nav_buttons()
        # ——— 全部绘制 ———
        if is_main and not in_category and not json_selected:
            screen.fill((12, 14, 22))
            if category_page != _cached_category_page:
                start = category_page * cat_per_page
                end = start + cat_per_page
                page_cats = categories[start:end]
                _cached_category_buttons = load_categories(page_cats)
                category_buttons = _cached_category_buttons
                _cached_category_page = category_page
            title = title_font.render("选择角色分类", True, (240, 230, 210))
            screen.blit(title, (max(40, GAME_SIZE[0] // 2 - 140), 20))
            draw_category_grid(category_buttons)
            cat_up_button.show_button()
            cat_down_button.show_button()
            cat_total = max(1, math.ceil(len(categories) / cat_per_page))
            page_text = small_font.render(f"分类 {category_page+1}/{cat_total}", True, (180, 180, 180))
            screen.blit(page_text, (GAME_SIZE[0] // 2 - 40, 660))

        if is_main and in_category and not json_selected:
            screen.fill((12, 14, 22))
            scene_key = (current_category, json_list_page, len(current_list))
            if scene_key != _cached_scene_key:
                new_list = page_list(json_list_page, current_list)
                _cached_scene_items = build_scene_items(
                    new_list,
                    show_update_date=(current_category == LATEST_CATEGORY),
                    is_custom=(current_category == CUSTOM_CATEGORY),
                )
                _cached_scene_key = scene_key
            json_button_list = draw_scene_list(_cached_scene_items)
            back_button.show_button()
            pages_up_button.show_button()
            pages_down_button.show_button()
            if current_category == LATEST_CATEGORY:
                cat_title = title_font.render("最新更新 · 按文件时间排序", True, (255, 230, 180))
            elif current_category == CUSTOM_CATEGORY:
                cat_title = title_font.render("我的录屏 · 本地 mp4", True, (200, 230, 255))
                hint = small_font.render(f"视频目录: {os.path.abspath(CUSTOM_VIDEO_DIR)}", True, (160, 180, 200))
                screen.blit(hint, (max(40, GAME_SIZE[0] // 2 - 280), 58))
            else:
                cat_title = title_font.render(f"分类: {current_category}", True, (240, 230, 210))
            screen.blit(cat_title, (max(80, GAME_SIZE[0] // 2 - 180), 20))
            if current_category == CUSTOM_CATEGORY and not current_list:
                empty = small_font.render("暂无录屏，请将 mp4 放入 custom_videos 文件夹", True, (200, 200, 210))
                screen.blit(empty, (max(80, GAME_SIZE[0] // 2 - 240), 360))

        if json_selected:
            if is_main and in_category:
                screen.fill((12, 14, 22))
                if _cached_scene_items:
                    draw_scene_list(_cached_scene_items)
                    back_button.show_button()
            elif is_main and not in_category:
                screen.fill((12, 14, 22))
                if category_buttons:
                    draw_category_grid(category_buttons)
            px, py, pw, ph = GAME_SIZE[0] // 2 - 260, GAME_SIZE[1] - 200, 520, 140
            panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
            panel.fill((14, 20, 36, 220))
            pygame.draw.rect(panel, (196, 160, 90, 200), (0, 0, pw, ph), 1)
            screen.blit(panel, (px, py))
            if is_custom_video(jsonId):
                rel = get_custom_video_rel(jsonId)
                tip = small_font.render(f"本地录屏: {rel}", True, (235, 235, 240))
                screen.blit(tip, (GAME_SIZE[0] // 2 - min(260, len(rel) * 4), py + 20))
                ready = small_font.render("点 PLAY 播放 · 可拖进度条 · ESC 退出", True, (160, 220, 170))
                screen.blit(ready, (GAME_SIZE[0] // 2 - 150, py + 48))
            else:
                tip = small_font.render(f"已选择: {jsonId}", True, (235, 235, 240))
                screen.blit(tip, (GAME_SIZE[0] // 2 - 100, py + 20))
                if _selection_checking or _selected_missing_count < 0:
                    warn = small_font.render("正在检查资源，请稍候…", True, (180, 200, 220))
                    screen.blit(warn, (GAME_SIZE[0] // 2 - 120, py + 48))
                elif _selected_missing_count > 0:
                    warn = small_font.render(f"缺 {_selected_missing_count} 个文件，点 PLAY 将自动下载", True, (255, 180, 120))
                    screen.blit(warn, (GAME_SIZE[0] // 2 - 170, py + 48))
                else:
                    ready = small_font.render("资源已就绪，可直接播放", True, (160, 220, 170))
                    screen.blit(ready, (GAME_SIZE[0] // 2 - 120, py + 48))
            play_button.show_button()

        if is_downloading or pending_play_after_download:
            overlay = pygame.Surface(GAME_SIZE, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            screen.blit(overlay, (0, 0))
            draw_progress_bar(
                GAME_SIZE[0] // 2 - 300, GAME_SIZE[1] // 2 - 20, 600, 36,
                download_completed / download_total if download_total > 0 else 0,
                f"下载资源 {download_completed}/{download_total}",
                (0, 180, 220),
            )
            tip = small_font.render("下载中，请稍候…", True, (255, 230, 180))
            screen.blit(tip, (GAME_SIZE[0] // 2 - 80, GAME_SIZE[1] // 2 + 30))

        if is_play and any_video_running():
            render_video_frame()
        elif is_play and not any_video_running():
            if playback_ui.get("waiting"):
                refresh_adv_frame()

        pygame.display.flip()
        _ui_dirty = False

    clock.tick(60)

print("不喜欢就爬！")

while True:
    print("————————开始植入芙拉病毒————————")
    print("————————神绊导师！启动！————————")
    webbrowser.open('https://pc-play.games.dmm.co.jp/play/cravesagax/')
    time.sleep(10)