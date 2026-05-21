import json
import time
import vdf
import os
import re
from pathlib import Path


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_bin(path, data):
    with open(path, "wb") as f:
        f.write(vdf.binary_dumps(data))


def nat_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def parse_schema(schema):
    """
    Walk the schema once and return two lookup maps:
      stat_to_achs: operand_name -> [(ach_name, max_val), ...]
      ach_to_stat:  ach_name     -> (operand_name, max_val)
    Only includes stat-based achievements (operation == "statvalue").
    """
    stat_to_achs = {}
    ach_to_stat = {}
    for appid in schema:
        for stat_id, stat in schema[appid]["stats"].items():
            if stat.get("type") not in ("4", "ACHIEVEMENTS"):
                continue
            for i, ach in stat.get("bits", {}).items():
                name = ach["name"]
                prog_info = ach.get("progress")
                if not (prog_info and isinstance(prog_info.get("value"), dict) and prog_info["value"].get("operation") == "statvalue"):
                    continue
                max_val = prog_info.get("max_val")
                if max_val is None:
                    continue
                operand = prog_info["value"]["operand1"]
                stat_to_achs.setdefault(operand, []).append((name, int(max_val)))
                ach_to_stat[name] = (operand, int(max_val))
    return stat_to_achs, ach_to_stat


def merge_achievements(base, patch, schema):
    stat_to_achs, ach_to_stat = parse_schema(schema)

    # Resolve true stat value for each stat operand:
    # - earned achievements contribute at least their max_val as a floor
    # - unearned achievements contribute their raw progress
    # - take the max across all sharing achievements
    stat_true_value = {}
    for stat_name, achs in stat_to_achs.items():
        best = 0
        for ach_name, max_val in achs:
            b = base.get(ach_name, {})
            p = patch.get(ach_name, {})
            earned = b.get("earned") or p.get("earned")
            raw = max(b.get("progress", 0), p.get("progress", 0))
            best = max(best, max_val if earned else raw)
        stat_true_value[stat_name] = best

    out = {}
    keys = set(base) | set(patch)

    for k in keys:
        b = base.get(k, {})
        p = patch.get(k, {})
        merged = dict(b)

        if k in ach_to_stat:
            # Stat-based achievement: derive everything from the true stat value
            stat_name, max_val = ach_to_stat[k]
            true_val = stat_true_value[stat_name]

            merged["max_progress"] = max_val
            merged["progress"] = min(true_val, max_val)
            earned = true_val >= max_val

            bt = b.get("earned_time", 0)
            pt = p.get("earned_time", 0)
            if bt and pt:
                merged["earned_time"] = min(bt, pt)  # keep older timestamp
            else:
                merged["earned_time"] = bt or pt

            if earned:
                merged["earned"] = True
            else:
                merged["earned"] = False
                merged["earned_time"] = 0

        else:
            # Normal achievement
            earned = p.get("earned", b.get("earned", False))
            if earned:
                merged["earned"] = True
                bt = b.get("earned_time", 0)
                pt = p.get("earned_time", 0)
                merged["earned_time"] = min(bt, pt) if bt and pt else bt or pt
            else:
                merged["earned"] = False
                merged["earned_time"] = 0

        out[k] = merged

    return dict(sorted(out.items(), key=lambda x: nat_key(x[0])))


def update_bin(updated_path, schema_path, data_path, output_path):
    updated = load_json(updated_path)
    schema = load_json(schema_path)
    data = load_json(data_path)
    stat_index = load_json("stat_index.json")

    cache = data.get("cache", {})
    debug_bits = {}

    _, ach_to_stat = parse_schema(schema)

    # --- Pass 1: resolve and write the true stat value for each stat ---
    # For each stat, take the max effective value across all sharing achievements.
    # Earned achievements contribute at least their max_val as a floor.
    stat_true_value = {}  # cache_key -> int
    for ach_name, (operand, max_val) in ach_to_stat.items():
        cache_key = stat_index.get(operand)
        if cache_key is None:
            continue
        state = updated.get(ach_name, {})
        progress = state.get("progress", 0)
        effective = max(progress, max_val) if state.get("earned") else progress
        stat_true_value[cache_key] = max(stat_true_value.get(cache_key, 0), effective)

    for cache_key, value in stat_true_value.items():
        group = cache.setdefault(cache_key, {})
        group["data"] = value
        group["state"] = 2

    # --- Pass 2: write bitmasks and timestamps ---
    for appid in schema:
        stats = schema[appid]["stats"]
        for schema_stat_id, stat in stats.items():
            if stat.get("type") not in ("4", "ACHIEVEMENTS"):
                continue

            bits = stat.get("bits", {})
            group = cache.setdefault(schema_stat_id, {})
            times = group.setdefault("AchievementTimes", {})

            bitmask = 0

            for i, ach in bits.items():
                name = ach["name"]
                state = updated.get(name)
                bit_index = int(i)

                # keep track of bit mapping — can change between game updates
                # when developers add or remove achievement/stat entries
                debug_bits.setdefault(schema_stat_id, {})[name] = bit_index

                if not state:
                    continue

                if state.get("earned"):
                    bitmask |= 1 << bit_index
                    t = state.get("earned_time")
                    times[i] = int(t) if t else int(time.time())
                else:
                    times.pop(i, None)

            group["data"] = bitmask

    write_bin(output_path, data)
    write_json("bits.json", debug_bits)


if __name__ == "__main__":
    appid = input("AppID: ")
    userid = 243977152

    aw_ach_path = Path(os.environ["APPDATA"]) / "GSE Saves" / f"{appid}" / "achievements.json"
    aw_ach = load_json(aw_ach_path)

    steam_ach_path = Path("achievements.json")
    steam_ach = load_json(steam_ach_path)

    schema = load_json("schema.json")

    merged = merge_achievements(base=steam_ach, patch=aw_ach, schema=schema)
    write_json("merged_achievements.json", merged)

    out_path = Path(f"UserGameStats_{userid}_{appid}.bin")
    update_bin("merged_achievements.json", "schema.json", "data.json", out_path)

    # Close steam
    # Wait 1000ms
    # Write bin to steam\appcache\stats
    stats_path = Path(r"C:\Program Files (x86)\Steam\appcache\stats")
    # Relaunch Steam
