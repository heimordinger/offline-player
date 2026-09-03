# -*- coding: utf-8 -*-
"""ADV 脚本读取与文本处理。"""
import json
import os
import re

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

    with open(txt_path, encoding="utf8") as f:
        return [line.rstrip("\n") for line in f.readlines()]


def resource_path(json_id: str, rel: str) -> str:
    rel = rel.replace("\\", "/")
    if rel == "color_0_0_0":
        from project_paths import PROJECT_ROOT

        return os.path.join(PROJECT_ROOT, "legacy", "assets", "color_0_0_0.jpg")
    return os.path.join(active.resource_dir, json_id, rel)
