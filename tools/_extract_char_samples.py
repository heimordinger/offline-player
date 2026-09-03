"""One-off: extract dialogue samples per character category."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from project_paths import set_active_game_paths
from app.core.game_registry import get_game, load_games
from app.core.category_names import load_category_name_cache, resolve_script_path
from app.core.script_dialogue import (
    parse_script_dialogue,
    pick_primary_name,
    speaker_matches,
    split_aliases,
)


def main():
    load_games()
    g = get_game("deepone_one") or list(load_games().values())[0]
    set_active_game_paths(
        g.id,
        json_dir=g.paths.json_dir,
        resource_dir=g.paths.resource_dir,
        episode_dir=g.paths.episode_dir,
        custom_videos_dir=g.paths.custom_videos_dir,
    )
    cache = load_category_name_cache()
    names = cache if isinstance(cache, dict) and "names" not in cache else cache.get("names", {})
    json_dir = g.paths.json_dir
    out = {}
    for k, raw in sorted(names.items()):
        if not k.isdigit() or len(k) != 4:
            continue
        n = int(k)
        if n < 1001 or n > 1058:
            continue
        if not raw.strip():
            continue
        aliases = split_aliases(raw)
        primary = pick_primary_name(raw) or aliases[0]
        lines = []
        narr = []
        if os.path.isdir(json_dir):
            for fn in sorted(os.listdir(json_dir)):
                if not fn.startswith(k) or not fn.endswith(".json"):
                    continue
                jid = fn[:-5]
                path = resolve_script_path(jid)
                if not path:
                    continue
                with open(path, encoding="utf-8") as f:
                    dials = parse_script_dialogue(f.readlines())
                for d in dials:
                    if d["narration"]:
                        t = d["text"].replace("\n", " ")[:150]
                        if t and len(narr) < 3:
                            narr.append(t)
                    elif speaker_matches(d["speaker"], aliases):
                        t = d["text"].replace("\n", " ")[:150]
                        if t and t not in lines:
                            lines.append(t)
                        if len(lines) >= 10:
                            break
                if len(lines) >= 10:
                    break
        out[k] = {
            "primary": primary,
            "aliases": aliases[:6],
            "lines": lines,
            "narration": narr,
        }
    out_path = os.path.join(os.path.dirname(__file__), "_char_samples.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(out)} characters to {out_path}")


if __name__ == "__main__":
    main()
