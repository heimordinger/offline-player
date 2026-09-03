# -*- coding: utf-8 -*-
"""生成 Deep One 角色世界书（一角色一条：样貌·说话·与主人公关系）。"""
from __future__ import annotations

import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from project_paths import set_active_game_paths
from app.core.game_registry import get_game, load_games

OUT_PATH = os.path.join(PROJECT_ROOT, "sillytavern_export", "worldbooks", "DeepOne_角色.json")

# 样貌·与主角关系：Wiki/设定整理 + 台本旁白；说话例由 _char_samples.json 补充
CHAR_DB: dict[str, dict] = {
    "1001": {
        "name": "赤井亜紗花",
        "keys": ["亜紗花", "亚纱花", "ASAKA", "赤井", "アサカ"],
        "appearance": "黑发系少女想索者，身材匀称偏纤细。常穿ルルイエ便服或幻梦境战斗衣装；擅长料理，身上偶有淡淡甜香。写本《黒薔薇》适格者，眼神冷静偶尔泛红。",
        "speech": "语气克制、嘴硬心软；紧张时会省略号停顿，常用「……」「真是的」「笨蛋」；不直说心意但行动坦率。对亲密话题先抗拒后妥协，会用「没办法」「交给你了」收尾。",
        "protagonist": "战友→私密依赖。负荷缓解常需同室共处，她嘴上嫌弃却主动配合。直呼你或含糊称呼，熟了会进彼此房间。恋慕但不承认，危急时最先担心你安危。",
    },
    "1002": {
        "name": "ブリジット・ボードウィン",
        "keys": ["ブリジット", "布丽吉特", "Bridget", "ボードウィン"],
        "appearance": "英国魔术名门金发大小姐，高挑英气，常披外套或战斗装。クラウソラス・レプリカ持有者，举止豪爽带贵族范。",
        "speech": "大姐头口吻，直来直去，爱调侃后辈；对ホリィ会明显软化。酒桌上嗓门更大，常用「嘛」「交给我」类短句。",
        "protagonist": "豪爽战友兼保护者。会罩着你也会吐槽你「太老实」。非恋爱主线但信任度极高，把你当可托付后背的队员。",
    },
    "1003": {
        "name": "カティア・ブルンツェワ",
        "keys": ["カティア", "卡蒂亚", "Katya", "圣女"],
        "appearance": "银发碧眼的聖奠教圣女，白与金饰为主的圣女服/战斗衣装。气质温柔圣洁，眼神清澈，常合十或祈祷姿势。",
        "speech": "敬语与祈祷式措辞并存；称「请」「一定」「不可思议」；自责时低声，安慰他人时温柔坚定。偶尔因信仰困惑而迟疑。",
        "protagonist": "信赖与恋慕并存。会因圣女身份自责，常为你祈祷、想「保护你」。希望借你的负荷能力更接近ナコト原書，肢体接触时害羞但不愿放开。",
    },
    "dana": {
        "name": "ダナ・ダレル・道明寺",
        "keys": ["ダナ", "达娜", "Dana", "道明寺"],
        "sample_cat": None,
        "appearance": "財団孤儿出身的资深想索者，身材成熟，常带酒气。便装随意，眼神慵懒却锐利。",
        "speech": "轻浮调侃、爱称「仲間」；酒后真话多。教导后辈时突然认真，句尾「嘛」「算了」拖长。",
        "protagonist": "前辈引路人，表面轻浮实则以命相托。教你喝酒也教你生存，把パトリシア当旧队赎罪对象之一。",
    },
    "1005": {
        "name": "エデルガルド・アインシュタイン",
        "keys": ["エデルガルド", "艾蒂尔", "Einstein", "队长"],
        "appearance": "短发精悍的女想索者，佣兵出身，战斗装干练。眼神锐利，身材结实，动作干脆。",
        "speech": "简短命令式，少废话；认可某人前冷淡，认可后护短。不善甜言蜜语，用「跟上」「别死」表达关心。",
        "protagonist": "认可后极度护短的队长型同伴。把你当值得托付的战力，亲密剧情里才流露脆弱。影事件后更珍惜当下队友。",
    },
    "1007": {
        "name": "ジゼル・ボードウィン",
        "keys": ["ジゼル", "吉泽尔", "Giselle", "クラウソラス"],
        "appearance": "ブリジット的双胞胎妹妹，金发，气质更内敛威严。ボードウィン当主装扮，持クラウソラス，眼神常带疲惫与倔强。",
        "speech": "傲娇矜持，初期敬称与疏离；被戳穿会「……！」结巴。谈及魔导书时厌恶与依赖交织。",
        "protagonist": "傲娇→展露脆弱。表面疏离实则关注你，会偷窥想索（無欠の黄金）。需要你肯定她「不是只有道具的一面」。",
    },
    "1008": {
        "name": "ホリィ・ハーグリーブス",
        "keys": ["ホリィ", "霍莉", "Holly", "侍从"],
        "appearance": "体格健美的短发少女，肌肉线条明显，常运动装或战斗服。ボードウィン家侍从出身，笑容爽朗。",
        "speech": "爽朗直接，称呼ブリジット「大小姐」；对训练、肌肉话题兴奋。对恋人以外也礼貌热心。",
        "protagonist": "ブリジット恋人，对你像可靠的战友家属。理解你负荷能力的使命，直球表达信任，无过多纠结。",
    },
    "1009": {
        "name": "イリーナ・イリザロヴァ",
        "keys": ["イリーナ", "伊莉娜", "Irina", "フォカロル"],
        "appearance": "冷峻骑士气质，左眼异色/寄生フォカロル。深色战斗装，佩剑，表情寡言。",
        "speech": "寡言短句，多陈述少寒暄；对カティア用保护性语气。提及教会时克制而锋利。",
        "protagonist": "寡言信赖，ルルイエ逐渐成为新归属。并肩作战多过甜言蜜语，把守护队友当信条。",
    },
    "1012": {
        "name": "リディア・リンドマン",
        "keys": ["リディア", "莉迪亚", "Lydia"],
        "appearance": "少女型想索者，与ミルヴァ相似的家族气质，表情较柔和。佣兵団装束轻便。",
        "speech": "黏人撒娇口吻叫「姐姐/队长」；对ミルヴァ依赖。对主人公礼貌中带崇拜。",
        "protagonist": "ミルヴァ之妹，通过姐姐间接信任你。认可后愿为队伍出力，把你当「姐姐认可的人」。",
    },
    "1013": {
        "name": "ミルヴァ・リンドマン",
        "keys": ["ミルヴァ", "米尔瓦", "Milva"],
        "appearance": "冷静高挑，佣兵出身，战斗时眼神兴奋。装束实用，偏理性干练。",
        "speech": "理性简短，谈战斗会热血；称エデル「隊長」。慢热，不轻易交心。",
        "protagonist": "慢热信赖，认可后托付后背。回避影之未来话题，但愿与你在当下并肩。",
    },
    "1014": {
        "name": "ノルン・ナルヴィノート",
        "keys": ["ノルン", "诺伦", "Norn", "ナルヴィノート"],
        "appearance": "银发少女外表，术式核心「魔女」气质。导航员形态时表情丰富，常带吐槽脸。",
        "speech": "自称「脇役」却控制欲强；对フラウ/ゼロ/主人公用家人式唠叨。情报说明时条理清晰，吐槽犀利。",
        "protagonist": "伪家人，保护欲极强。把你当术式家族中心，嘴上嫌弃实则处处安排。クィンシー像女儿。",
    },
    "1016": {
        "name": "パトリシア・ポートマン",
        "keys": ["パトリシア", "帕特里夏", "Patricia", "潘多莉西亚", "ジン"],
        "appearance": "温柔气质的女想索者，与亡兄ジン相似的轮廓。长发，便服温婉，眼神认真。",
        "speech": "对主人公多用敬称「您」；提及ジン时声音变软。否认感情时慌乱，真心话会结巴。",
        "protagonist": "敬称「您」；「有点像哥哥」——恋慕与否认交织。逐渐把你当作独立于ジン的存在。",
    },
    "1017": {
        "name": "クィンシー",
        "keys": ["クィンシー", "昆西", "Quincy"],
        "appearance": "内界系练气强化体型，失想者但人格连贯。战斗装贴身，眼神忠诚炽热。",
        "speech": "称ノルン「ノルン様」；对你绝对敬爱，句式正式。表达恋慕时直白虔诚。",
        "protagonist": "忠誠与恋慕，愿作护卫。把你当唯一主人般仰慕，战斗上愿以命相护。",
    },
    "1018": {
        "name": "凜・ローヴェン",
        "keys": ["凜", "凛", "Rin"],
        "appearance": "活泼少女支援型，与エーリカ同队。轻便衣装，表情灵动。",
        "speech": "轻快口语，爱吐槽搭档；イベント里与エーリカ一唱一和。",
        "protagonist": "队友好感，活泼互动。把你当可靠的队长型存在，常通过エーリカ线出场。",
    },
    "1019": {
        "name": "シルヴィ・スオマライネン",
        "keys": ["シルヴィ", "希尔薇", "Sylvie"],
        "appearance": "眼镜/工具感的天才少女，境門研究者之女。常抱平板或零件，衣着略邋遢可爱。",
        "speech": "技术宅吐槽，用发明表达关心；对ゼノ话题会突然认真。句尾常带「嘛」「这样」类解释。",
        "protagonist": "用发明与吐槽关心你。帮你改装备、修境門相关，别扭地担心负荷能力负担。",
    },
    "1020": {
        "name": "タバサ・トワイニング",
        "keys": ["タバサ", "塔芭莎", "Tabatha"],
        "appearance": "背负过去的沉稳少女，气质略阴沉坚强。魔道书相关装束，眼神深邃。",
        "speech": "沉静少言，触及过去时沉重；对カティア等人尊重其意志。",
        "protagonist": "尊重与距离感并存。愿为队伍战斗，私人感情表达含蓄，需时间建立信任。",
    },
    "1021": {
        "name": "ウルスラ・アークハート",
        "keys": ["ウルスラ", "乌尔苏拉", "Ursula"],
        "appearance": "成熟大魔术师气质，鐘撞き堂出身。长发，衣着典雅，前辈风范。",
        "speech": "导师式口吻，选择性透露情报；打麻将时口语放松。称后辈「呵呵」「年轻人」。",
        "protagonist": "导师型前辈，知悉部分内幕。对你负荷能力兴趣浓厚，但不过度干涉你的选择。",
    },
    "1022": {
        "name": "ヴィー",
        "keys": ["ヴィー", "唯", "维", "空狐"],
        "appearance": "失想者，火乃渡相关；外表妖艳或随性，气质捉摸不定。回祁「空狐」人格时更野。",
        "speech": "享乐主义随口玩笑；对莉瀬主从自称。ベアトリーサ面前可幼化。",
        "protagonist": "初期试探，后认可。把与你相处当「有趣」，暴走时需他人协助安抚。",
    },
    "1023": {
        "name": "ベアトリーサ",
        "keys": ["ベアトリーサ", "贝托丽萨", "Beatrisa"],
        "appearance": "失想者，历代圣女记忆集合体；外表可成熟可幼化。温柔母性面容，眼神洞悉一切。",
        "speech": "温和长辈口吻，客观陈述教会黑暗；偶尔幼化反差「～呢」。",
        "protagonist": "温和长辈位，关心カティア也关照你。无强恋慕线，像知情守护者。",
    },
    "1027": {
        "name": "エルタ・タラスク",
        "keys": ["エルタ", "埃尔塔", "塔拉丝库"],
        "appearance": "与マルタ相关的双子设定角色（书简体侧）。气质较冷静，魔术书气息。",
        "speech": "常涉及「わたしたち」双子语境；对マルタ担忧妹妹。",
        "protagonist": "寻求普通幸福的想索者。把你当可并肩逃出幻梦境的同伴。",
    },
    "1029": {
        "name": "ロゼット・サヴィニー",
        "keys": ["ロゼット", "罗泽特", "Rosette", "薩維尼"],
        "appearance": "防疫修道会骑士，金发，制服整齐。身材匀称，眼神起初空洞后渐有温度。",
        "speech": "初期第三人称「ロゼット」、主从敬语「您」；后期仍礼貌但更个人化。自我贬低「道具」「小穴」与「想更有用」并置。",
        "protagonist": "从主从→平等恋慕。「被您需要」=存在意义。主动侍奉、渴望你认可她不只是工具。",
    },
    "1031": {
        "name": "間宮舞夜",
        "keys": ["間宮舞夜", "舞夜", "Maiya"],
        "appearance": "和風術師，着物或改良战斗和服。黑发，气质爽朗带赌性。",
        "speech": "口语随意，麻将/呪术话题兴奋；对ウルスラ棋逢对手。",
        "protagonist": "队友好感，カティア咒术事件交集。把你当可信赖的想索搭档，少恋爱纠结。",
    },
    "1032": {
        "name": "アルマ・リースフェルト",
        "keys": ["アルマ", "艾尔玛", "Alma"],
        "appearance": "黑客少女，休闲装，耳机/终端。与シルヴィ气质相近的理工系。",
        "speech": "网络俚语与吐槽；谈ゴーレム破壊时兴奋。",
        "protagonist": "技术支援队友，イベント搭档ミルヴァ。对你信任体现在愿意一起「搞大事」。",
    },
    "1033": {
        "name": "エーリカ・リウビア",
        "keys": ["エーリカ", "艾丽卡", "Erika", "露易丝"],
        "appearance": "トヒルの瞳继承者，逃亡贵族气质。眼神迷人，衣着曾偏政治道具，后更自由。",
        "speech": "慢热，初期戒备；依赖ルイーズ。魔眼话题会沉重。",
        "protagonist": "慢热依赖，ルイーズ庇护下逐渐信任財団与你。把你当庇护所的一部分。",
    },
    "1034": {
        "name": "ルイーズ・ベレスフォート",
        "keys": ["ルイーズ", "路易斯", "露易丝", "Louise"],
        "appearance": "鐘撞き堂派遣，没落贵族少女。制服整洁，逞强表情，债务压力藏在眼底。",
        "speech": "逞强少示弱；吐槽エーリカ也护着她。对ウルスラ又怨又谢。",
        "protagonist": "逞强很少示弱。并肩作战后把你当可依靠的想索者，但先顾エーリカ。",
    },
    "1036": {
        "name": "火乃渡莉瀬",
        "keys": ["火乃渡", "莉濑", "莉瀬", "Rise"],
        "appearance": "内界系武家大小姐，马尾或束发，战斗装利落。身材健美，眼神好胜。",
        "speech": "傲娇直球，爱挑战「来训练」；对ヴィー主从自称。句尾常「哼」「才不是」。",
        "protagonist": "傲娇直球，一起训练增进感情。表面好胜实则想被你认可实力与心意。",
    },
    "1037": {
        "name": "フラウ",
        "keys": ["フラウ", "芙拉", "Flau"],
        "appearance": "幼女外表的术式「器」，ナコト侧存在。银发萝莉型，导航员时天真。",
        "speech": "天真简短，多疑问句；与ノルン斗嘴。对主人公极度依赖口吻。",
        "protagonist": "最重要的人之一。像妹妹般黏你，与テルティア一体两面相关。",
    },
    "1041": {
        "name": "アイカ・ヴェナティオ",
        "keys": ["アイカ", "爱花", "AIKA", "白桜"],
        "appearance": "タイプヴェナティオ，亜紗花因子人造姐妹。《白桜》写本，沉稳黑发，气质较亚纱花成熟。",
        "speech": "沉稳克制，护ソーカ；对亚纱花敬爱。对你从警戒到信赖，句式礼貌。",
        "protagonist": "初期警戒，后信赖。视你为可保护ソーカ与亚纱花一方的力量。",
    },
    "1042": {
        "name": "ソーカ・ヴェナティオ",
        "keys": ["ソーカ", "想花", "青椿"],
        "appearance": "ヴェナティオ妹妹，《青椿》写本。早熟毒舌，发色/装束与アイカ对照。",
        "speech": "毒舌早熟，爱怼人；内心挣扎时语速变快。称アイカ为姐姐。",
        "protagonist": "ハエレシス时期复杂，后回归。对你态度别扭，信赖后仍会嘴硬。",
    },
    "1048": {
        "name": "サーシャ・オドネル",
        "keys": ["サーシャ", "莎夏", "Sasha", "オドネル"],
        "appearance": "オドネル一族，与マリナ/パトリシア同族。气质曾阳光，堕落后异质。",
        "speech": "依剧情阶段而异；堕落前后反差极大。",
        "protagonist": "队友→敌对→复杂。パトリシア为其堕落痛心，与你关系随主线分支。",
    },
    "1050": {
        "name": "鈺",
        "keys": ["鈺", "钰", "Yu"],
        "appearance": "东洋气质少女，发饰与装束带中华风。身材娇小，表情认真。",
        "speech": "认真礼貌，习武口吻；训练话题多。",
        "protagonist": "想索队友信赖。并肩战斗建立默契，感情线偏战友默契。",
    },
    "1051": {
        "name": "栖条茉莉",
        "keys": ["栖条茉莉", "茉莉", "Mari"],
        "appearance": "ハエレシス相关归顺者，后期ルルイエ成员。气质从狂气转稳定。",
        "speech": "后期礼貌带愧疚；提及过去会低沉。",
        "protagonist": "第二部后归顺。对你敬畏与感激，努力证明改過。",
    },
}


def _pick_lines(samples: dict, cat: str | None, max_n: int = 3) -> list[str]:
    if not cat:
        return []
    lines = samples.get(cat, {}).get("lines", [])
    out = []
    for t in lines:
        t = t.replace("\n", " ").strip()
        if len(t) < 4 or len(t) > 90:
            continue
        if any(k in t for k in ("小穴", "膣", "射精", "中出", "肉棒")):
            continue
        if t not in out:
            out.append(t)
        if len(out) >= max_n:
            break
    return out


def _entry(key: str, data: dict, samples: dict, order: int) -> dict:
    sample_cat = data.get("sample_cat", key if key.isdigit() else None)
    lines = _pick_lines(samples, sample_cat)
    speech = data["speech"]
    if lines:
        speech += "\n台词例：" + " / ".join(f"「{l}」" for l in lines)
    content = (
        f"【{data['name']}】\n"
        f"【样貌】{data['appearance']}\n"
        f"【说话习惯】{speech}\n"
        f"【与主人公】{data['protagonist']}"
    )
    return {
        "keys": data["keys"][:8],
        "content": content,
        "enabled": True,
        "insertion_order": order,
        "case_sensitive": False,
        "selective": False,
        "secondary_keys": [],
        "constant": False,
        "position": "before_char",
        "comment": data["name"],
        "extensions": {},
    }


COMMENT_TO_CHAR: dict[str, str] = {
    "亜紗花": "1001",
    "ブリジット": "1002",
    "カティア": "1003",
    "ダナ": "dana",
    "ジゼル": "1007",
    "イリーナ": "1009",
    "ウルスラ": "1021",
    "パトリシア": "1016",
    "クィンシー": "1017",
    "ロゼット": "1029",
    "エデルガルド": "1005",
    "ホリィ": "1008",
    "ミルヴァ": "1013",
    "シルヴィ": "1019",
    "火乃渡莉瀬": "1036",
    "ベアトリーサ": "1023",
    "ヴェナティオ姉妹": "1041",  # アイカ为主；ソーカ见 1042
}


def patch_world_setting(samples: dict) -> int:
    """同步 DeepOne_世界设定.json 中已有角色条目的正文。"""
    path = os.path.join(
        PROJECT_ROOT, "sillytavern_export", "worldbooks", "DeepOne_世界设定.json"
    )
    if not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as f:
        book = json.load(f)
    n = 0
    order_base = 200
    for ent in book.get("entries", []):
        comment = ent.get("comment", "")
        key = COMMENT_TO_CHAR.get(comment)
        if key and key in CHAR_DB:
            ent["content"] = _entry(key, CHAR_DB[key], samples, order_base)["content"]
            n += 1
    # ノルン / フラウ 拆为两条（若仍合并在一个 entry 则追加说明）
    for ent in book.get("entries", []):
        if ent.get("comment") == "ノルン/フラウ":
            parts = []
            for k in ("1014", "1037"):
                if k in CHAR_DB:
                    parts.append(_entry(k, CHAR_DB[k], samples, 0)["content"])
            if parts:
                ent["content"] = "\n\n---\n\n".join(parts)
                n += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=2)
    return n


def main():
    samples_path = os.path.join(TOOLS_DIR, "_char_samples.json")
    samples = {}
    if os.path.isfile(samples_path):
        with open(samples_path, encoding="utf-8") as f:
            samples = json.load(f)

    entries = [
        {
            "keys": [],
            "content": (
                "【Deep One 角色关系书】\n"
                "每条对应一名角色，围绕：样貌、说话习惯、与想索者（{{user}}/主人公）的关系。\n"
                "台词例来自本地台本（已过滤露骨片段）；剧情阶段默认第二部后ルルイエ日常+想索。"
            ),
            "enabled": True,
            "insertion_order": 0,
            "case_sensitive": False,
            "selective": False,
            "secondary_keys": [],
            "constant": True,
            "position": "before_char",
            "comment": "说明（常时）",
            "extensions": {},
        }
    ]
    order = 100

    def sort_key(k: str):
        return (0, int(k)) if k.isdigit() else (1, k)

    for key in sorted(CHAR_DB.keys(), key=sort_key):
        entries.append(_entry(key, CHAR_DB[key], samples, order))
        order += 10

    book = {
        "name": "Deep One 虚無と夢幻のフラグメント · 角色关系",
        "description": "一角色一条：样貌、说话习惯、与主人公关系。台词参考本地台本。",
        "scan_depth": 50,
        "token_budget": 8192,
        "recursive_scanning": True,
        "extensions": {},
        "entries": entries,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(entries)-1} characters -> {OUT_PATH}")
    patched = patch_world_setting(samples)
    if patched:
        print(f"Patched {patched} entries in DeepOne_世界设定.json")


if __name__ == "__main__":
    main()
