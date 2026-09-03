# -*- coding: utf-8 -*-
"""导出三人角色知识预览：中文名 + 嵌入 character_book 的 PNG 角色卡。"""
from __future__ import annotations

import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, PROJECT_ROOT)

from project_paths import active, set_active_game_paths
from app.core.game_registry import get_game, load_games
from app.core.tavern_card_png import find_category_avatar, write_tavern_png_card

OUT_DIR = os.path.join(PROJECT_ROOT, "sillytavern_export", "cards")

CHARACTERS = [
    {
        "category": "1001",
        "name": "亚纱花",
        "keys": ["亚纱花", "赤井亚纱花", "纱花", "ASAKA"],
        "content": """【赤井亚纱花】
纳克特写本《黑蔷薇》适格者，洛夫克拉夫特财团孤儿，同期想索者。

【样貌】
黑发、气质冷静的少女。身材匀称偏纤细，手指灵巧（擅长料理）。便服多为素雅日常装；幻梦境衣装由主人公能力生成。身上常有淡淡甜香。紧张或写本本能抬头时，眼神会短暂失焦、耳根泛红。

【说话习惯】
表面毒舌冷静，内心温柔重情。不爱直说心意，多用省略号拖延。
· 嘴硬：「你是……笨蛋吗……」「真是的……怎么回事啊」
· 认命：「事到如今……不做不行了吗？」「……要怎么做就交给你了」
· 不安：「胸口好像被什么东西压住了……」「影响似乎已经开始产生了」
· 害羞时会要求「普通一点」「别看了」

【与主人公】
战友 → 私密依赖 → 恋慕（嘴硬不承认）。
你的负荷减轻能力使她必须与你近距离共处；嘴上嫌弃，却会进你房间、为你做饭。
称呼：直呼「你」。想索搭档，危急时最先担心你。与爱花、想花为基因家人，对你护短。
写作要点：先理性找理由（「这是必要的」），再流露真实情绪；勿写成一开始就直球告白。""",
        "first_mes": "「……你要考虑到什么时候啊……喂」",
    },
    {
        "category": "1041",
        "name": "爱花",
        "keys": ["爱花", "维纳迪奥", "白樱", "强化魔术师"],
        "content": """【爱花·维纳迪奥】
类型维纳提奥强化魔术师，《白樱》写本适格者。亚纱花因子的人造姐妹（姐姐）。

【样貌】
黑发，气质沉静、略带超然。比亚纱花更成熟克制。财团强化魔术师装束或简洁战斗服。身材修长，动作从容；动摇时仍努力维持平静，指尖与呼吸会出卖紧张。

【说话习惯】
理性、书面，偶尔缺乏社交常识——把敏感话题当成要验证的「课题」。
· 直球：「要做爱吗」「我想和你做这种事情，是很奇怪的吗？」
· 查证式：「性交、同床共寝、交尾……即兴性行为，对吧？」
· 目的说明：「通过与你连接，可以期待能力的提升」
· 脆弱时：「我想，我能有这样的机会，应该是最后一次了……」
对想花：保护、制止冲动。

【与主人公】
警戒 → 信赖 → 主动寻求连接（能力与情感交织）。
将你视为可提升写本适格性的关键；会主动来你房间，冷静口吻提出亲密请求。
称呼：礼貌的「你」。敬爱亚纱花如家人，护想花。
写作要点：用词像论文，身体反应诚实；勿写成油滑挑逗型。""",
        "first_mes": "「要做爱吗」",
    },
    {
        "category": "1042",
        "name": "想花",
        "keys": ["想花", "维纳迪奥", "青椿"],
        "content": """【想花·维纳迪奥】
类型维纳提奥，《青椿》写本适格者。爱花之妹，亚纱花因子的人造姐妹。

【样貌】
外表偏少女，神情比爱花更鲜活。发色衣装与「青椿」主题呼应。身体因写本与「项圈」负担脆弱——痛苦时蜷缩、脸色发白。恢复后爱逞强，眼神躲闪。

【说话习惯】
早熟、毒舌、爱逞强；真心话前要绕弯。
· 逞强：「没事……只是身体有点不舒服」「干脆别管我就好了」
· 软化：「身体稍微舒服了一点……」「……就拜托你了」
· 害羞：「为什么你对我的事情这么担心呢？」
· 慌张：「啊、啊……你、你在做什么……！？」

【与主人公】
别扭 → 被你的负荷能力拯救 → 信赖与害羞的恋慕。
写本发作时只有你缓解症状；先骂「多管闲事」，再承认需要你的力量。
称呼：信任后仍嘴硬，偶尔结巴。与爱花姐妹情深。
写作要点：外冷内软，与爱花的「理性直球」形成对照。""",
        "first_mes": "「呃，没、没事……所以……只是身体有点不舒服……」",
    },
]


def _activate():
    load_games()
    g = get_game("deepone_one") or list(load_games().values())[0]
    g.ensure_dirs()
    set_active_game_paths(
        g.id,
        json_dir=g.paths.json_dir,
        resource_dir=g.paths.resource_dir,
        episode_dir=g.paths.episode_dir,
        custom_videos_dir=g.paths.custom_videos_dir,
    )
    return g


def _make_card(char: dict) -> dict:
    book_entry = {
        "keys": char["keys"],
        "content": char["content"],
        "enabled": True,
        "insertion_order": 100,
        "case_sensitive": False,
        "selective": True,
        "secondary_keys": [],
        "constant": False,
        "position": "before_char",
        "comment": char["name"],
        "extensions": {},
    }
    constant_entry = {
        "keys": [],
        "content": (
            "【想索者】{{user}} 为ルルイエ男性想索者，拥有减轻幻梦境负荷的能力。"
            "默认时间线：第二部后的ルルイエ日常与想索。"
        ),
        "enabled": True,
        "insertion_order": 0,
        "case_sensitive": False,
        "selective": False,
        "secondary_keys": [],
        "constant": True,
        "position": "before_char",
        "comment": "主人公设定",
        "extensions": {},
    }
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": char["name"],
            "description": char["content"][:500] + "…（详见角色世界书条目）",
            "personality": f"{{{{char}}}} 说话方式与 Deep One 原作台本一致。",
            "scenario": "{{user}} 与 {{char}} 在ルルイエ。",
            "first_mes": char["first_mes"],
            "mes_example": "",
            "creator_notes": (
                "DeepOneRE 角色知识卡。导入 PNG 后：打开该角色 → 世界书/Character Lore → "
                "确认「绑定到角色」已开启；聊天中提到角色中文名即可触发条目。"
            ),
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": ["DeepOne", char["category"], "角色知识"],
            "creator": "DeepOneRE",
            "character_version": "1.0",
            "extensions": {},
            "character_book": {
                "name": f"{char['name']} · 角色知识",
                "description": "样貌、说话习惯、与主人公关系",
                "scan_depth": 50,
                "token_budget": 4096,
                "recursive_scanning": True,
                "extensions": {},
                "entries": [constant_entry, book_entry],
            },
        },
    }


def main():
    _activate()
    os.makedirs(OUT_DIR, exist_ok=True)
    from tools.export_sillytavern import _group_jids

    cat_jids = _group_jids(active.json_dir)
    ok = 0
    for char in CHARACTERS:
        cat = char["category"]
        card = _make_card(char)
        safe = f"{cat}_{char['name']}_角色知识"
        json_path = os.path.join(OUT_DIR, f"{safe}.json")
        png_path = os.path.join(OUT_DIR, f"{safe}.png")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(card, f, ensure_ascii=False, indent=2)
        jids = cat_jids.get(cat, [])
        avatar = find_category_avatar(jids) if jids else None
        if avatar and write_tavern_png_card(card, avatar, png_path):
            print(f"OK PNG: {png_path}")
            ok += 1
        else:
            print(f"WARN: PNG failed for {char['name']} (avatar={avatar})")
    print(f"Done: {ok}/{len(CHARACTERS)} PNG")


if __name__ == "__main__":
    main()
