# -*- coding: utf-8 -*-
"""DeepOne 编号规则解析。

卡面（6 位）
  第1~2位：卡片类型 — 10 主线 / 18 外传 / 19 联动
  第3~4位：角色编号（各类型分别从 01 起）
  第5~6位：该角色卡面编号
    - 主线卡一般从 03 起（也有 04、05）
    - 异典从 80 起
    - 外传 / 联动统一为 04
    - 仅 room 生效的皮肤立绘从 51 起（如 101351）

Memorial 卡面
  前两位固定 60；第3~4 分组从 01；第5~6 为 12（同组另一张早期为 22）

寝室 / 场景预览（常见 8 位）
  卡面编号 + 04/05；异典 3CG 可有 06；皮肤固定 04
  复刻 CG：8 位，首位 9，2~3 复刻序号，4/7/8 为 0，5~6 角色编号
    例 90500800 → 第 5 次复刻、角色 08
  Memorial 寝室：60 + 组号 + 31（同组另一张早期 30）
  家具 CG：前缀 401000 + 后三位家具号

Banner：按活动顺序递增（与 ADV 场景 JSON 分类无关）
"""
from __future__ import annotations

SERIES_MAIN = "10"
SERIES_SIDE = "18"
SERIES_COLLAB = "19"
SERIES_MEMORIAL = "60"
SERIES_REMAKE = "9"
FURNITURE_PREFIX = "401000"

SERIES_LABELS = {
    SERIES_MAIN: "主线",
    SERIES_SIDE: "外传",
    SERIES_COLLAB: "联动",
    SERIES_MEMORIAL: "Memorial",
}

# 顶层分区（浏览用）
HUB_MAIN = "__do_main__"
HUB_SIDE = "__do_side__"
HUB_COLLAB = "__do_collab__"
HUB_MEMORIAL = "__do_memorial__"
HUB_REMAKE = "__do_remake__"
HUB_FURNITURE = "__do_furniture__"
HUB_OTHER = "__do_other__"

HUB_ORDER = (
    HUB_MAIN,
    HUB_SIDE,
    HUB_COLLAB,
    HUB_MEMORIAL,
    HUB_REMAKE,
    HUB_FURNITURE,
    HUB_OTHER,
)

HUB_LABELS = {
    HUB_MAIN: "主线",
    HUB_SIDE: "外传",
    HUB_COLLAB: "联动",
    HUB_MEMORIAL: "Memorial",
    HUB_REMAKE: "复刻",
    HUB_FURNITURE: "家具",
    HUB_OTHER: "其他",
}

# 点进后先列六位卡面的分区（家具直接列场景）
CARD_HUBS = frozenset({HUB_MEMORIAL, HUB_REMAKE, HUB_OTHER})
# 主线 / 外传 / 联动：先列四位角色，再列六位皮肤
CHAR_HUBS = frozenset({HUB_MAIN, HUB_SIDE, HUB_COLLAB})
CHAR_SERIES = frozenset({SERIES_MAIN, SERIES_SIDE, SERIES_COLLAB})

_SERIES_TO_HUB = {
    SERIES_MAIN: HUB_MAIN,
    SERIES_SIDE: HUB_SIDE,
    SERIES_COLLAB: HUB_COLLAB,
    SERIES_MEMORIAL: HUB_MEMORIAL,
    "remake": HUB_REMAKE,
    "furniture": HUB_FURNITURE,
}


def card_id_from_story(story_id: str) -> str:
    """场景 / 故事 ID → 6 位卡面编号（不足则空）。"""
    sid = str(story_id).split("_")[0]
    cid = sid[:6] if len(sid) >= 6 else sid
    return cid if cid.isdigit() and len(cid) == 6 else ""


def deepone_category_of(story_id: str) -> str:
    """分类键：前六位卡面编号；无法解析则用整段 base。"""
    cid = card_id_from_story(story_id)
    if cid:
        return cid
    return str(story_id).split("_")[0]


def series_code(card_id: str) -> str:
    cid = (card_id or "").strip()
    if not cid:
        return ""
    if cid.startswith(FURNITURE_PREFIX):
        return "furniture"
    if cid.isdigit() and len(cid) >= 1 and cid[0] == SERIES_REMAKE:
        return "remake"
    if len(cid) >= 2 and cid[:2].isdigit():
        return cid[:2]
    return ""


def series_label(card_id: str) -> str:
    code = series_code(card_id)
    if code == "furniture":
        return "家具"
    if code == "remake":
        return "复刻"
    return SERIES_LABELS.get(code, "")


def hub_of_card(card_id: str) -> str:
    """六位卡面（或分类键）→ 顶层分区。"""
    return _SERIES_TO_HUB.get(series_code(card_id), HUB_OTHER)


def is_deepone_hub(cat: str) -> bool:
    return cat in HUB_LABELS


def is_deepone_card_hub(cat: str) -> bool:
    return cat in CARD_HUBS


def is_deepone_char_hub(cat: str) -> bool:
    return cat in CHAR_HUBS


def is_deepone_card_category(cat: str) -> bool:
    return bool(cat) and cat.isdigit() and len(cat) == 6


def is_deepone_character_category(cat: str) -> bool:
    """主线/外传/联动的四位角色键，如 1001 / 1802 / 1901。"""
    return bool(cat) and cat.isdigit() and len(cat) == 4 and cat[:2] in CHAR_SERIES


def character_id_from_card(card_id: str) -> str:
    """六位卡面 → 四位角色；非主线/外传/联动则空。"""
    cid = (card_id or "").strip()
    if len(cid) >= 4 and cid[:2] in CHAR_SERIES and cid[:4].isdigit():
        return cid[:4]
    return ""


def preferred_skin_id(skin_ids: list[str]) -> str:
    """角色封面：该角色排序后的第一套卡面（通常卡优先靠序号最小）。"""
    if not skin_ids:
        return ""
    return sort_card_ids(skin_ids)[0]


def character_sort_key(char_id: str) -> tuple:
    slot = character_slot(char_id + "00") if len(char_id) == 4 else character_slot(char_id)
    try:
        slot_n = int(slot) if slot.isdigit() else 999
    except ValueError:
        slot_n = 999
    return (slot_n, char_id)


def sort_character_ids(char_ids: list[str]) -> list[str]:
    return sorted(char_ids, key=character_sort_key)


def card_sort_key(card_id: str) -> tuple:
    """卡面排序：角色槽 → 卡面序号 → 编号。复刻按活动序号再排角色。"""
    cid = card_id or ""
    code = series_code(cid)
    if code == "remake" and len(cid) >= 6 and cid.isdigit():
        try:
            order_n = int(cid[1:3])
        except ValueError:
            order_n = 999
        try:
            char_n = int(cid[4:6])
        except ValueError:
            char_n = 999
        return (order_n, char_n, cid)
    slot = character_slot(cid)
    idx = face_index(cid)
    try:
        slot_n = int(slot) if slot.isdigit() else 999
    except ValueError:
        slot_n = 999
    face_n = idx if idx is not None else 999
    return (slot_n, face_n, cid)


def sort_card_ids(card_ids: list[str]) -> list[str]:
    return sorted(card_ids, key=card_sort_key)


def scene_sort_key(story_id: str) -> tuple:
    """同卡面下场景：寝室后缀 04/05/06… → 完整 id。"""
    base = str(story_id).split("_")[0]
    suf = room_suffix(story_id)
    try:
        suf_n = int(suf) if suf.isdigit() else 999
    except ValueError:
        suf_n = 999
    return (suf_n, base, story_id)


def sort_scene_ids(scene_ids: list[str]) -> list[str]:
    return sorted(scene_ids, key=scene_sort_key)


def face_index(card_id: str) -> int | None:
    """卡面第 5~6 位。"""
    cid = card_id_from_story(card_id) or (card_id if card_id.isdigit() and len(card_id) >= 6 else "")
    if len(cid) < 6:
        return None
    try:
        return int(cid[4:6])
    except ValueError:
        return None


def character_slot(card_id: str) -> str:
    """第 3~4 位角色槽（主线/外传/联动各自从 01 计）。"""
    cid = card_id_from_story(card_id) or (card_id if len(card_id) >= 4 else "")
    if len(cid) < 4:
        return ""
    return cid[2:4]


def variant_label(card_id: str) -> str:
    """异典 / 皮肤；Memorial / 家具 / 复刻由 series_label 表达，这里不再重复。"""
    idx = face_index(card_id)
    if idx is None:
        return ""
    code = series_code(card_id)
    if code in (SERIES_MEMORIAL, "furniture", "remake"):
        return ""
    if idx >= 80:
        return "异典"
    if idx >= 51:
        return "皮肤"
    return ""


def character_title(char_id: str, character_name: str = "") -> str:
    """四位角色标题：角色名，否则「角色01」。"""
    name = (character_name or "").strip()
    if name:
        return name.split("+")[0].strip() or name
    slot = char_id[2:4] if len(char_id) >= 4 else ""
    return f"角色{slot}" if slot else char_id


def skin_title(card_id: str) -> str:
    """六位皮肤标题：通常/异典/皮肤 · 后两位。"""
    cid = (card_id or "").strip()
    v = variant_label(cid) or "通常"
    tail = cid[4:6] if len(cid) >= 6 else cid
    return f"{v} · {tail}"


def card_title(card_id: str, character_name: str = "") -> str:
    """分类标题：类型 · 角色名（或槽位）· 变体。"""
    cid = (card_id or "").strip()
    if not cid:
        return ""
    parts: list[str] = []
    series = series_label(cid)
    if series:
        parts.append(series)
    name = (character_name or "").strip()
    if name:
        parts.append(name)
    else:
        slot = character_slot(cid)
        if slot and series_code(cid) in (
            SERIES_MAIN,
            SERIES_SIDE,
            SERIES_COLLAB,
            SERIES_MEMORIAL,
        ):
            parts.append(f"角色{slot}")
    variant = variant_label(cid)
    if variant and variant not in parts:
        parts.append(variant)
    if not parts:
        return cid
    return " · ".join(parts)


def room_suffix(story_id: str) -> str:
    """寝室预览后缀（卡面后的 04/05/06 等）。"""
    base = str(story_id).split("_")[0]
    if base.isdigit() and len(base) >= 8:
        return base[6:8]
    return ""


def describe_card(card_id: str) -> str:
    """字幕用短描述，含编号。"""
    title = card_title(card_id)
    if title and title != card_id:
        return f"{title} · {card_id}"
    return card_id
