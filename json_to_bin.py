import time

from utils import console, nat_key, read_json, write_json, write_bin, load_steam_stats, parse_schema
from config import load_config


def to_signed_int32(value):
    """Convert an unsigned 32-bit value into signed 32-bit for VDF binary storage."""
    if value >= 2**31:
        return value - 2**32
    return value


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
            stat_name, max_val, _ = ach_to_stat[k]
            true_val = stat_true_value[stat_name]
            merged["max_progress"] = max_val
            merged["progress"] = min(true_val, max_val)
            earned = true_val >= max_val
        else:
            earned = p.get("earned", b.get("earned", False))

        merged["earned"] = earned
        bt = b.get("earned_time", 0)
        pt = p.get("earned_time", 0)
        merged["earned_time"] = (min(bt, pt) if bt and pt else bt or pt) if earned else 0

        out[k] = merged

    # Sort naturally
    return dict(sorted(out.items(), key=lambda x: nat_key(x[0])))


def apply_achievements(merged, schema, data):
    cache = data.get("cache", {})

    _, ach_to_stat = parse_schema(schema)

    # --- Pass 1: resolve and write the true stat value for each stat ---
    # For each stat, take the max effective value across all sharing achievements.
    # Earned achievements contribute at least their max_val as a floor.
    stat_true_value = {}  # cache_key -> int
    for ach_name, (operand, max_val, cache_key) in ach_to_stat.items():
        state = merged.get(ach_name, {})
        progress = state.get("progress", 0)
        effective = max(progress, max_val) if state.get("earned") else progress
        stat_true_value[cache_key] = max(stat_true_value.get(cache_key, 0), effective)

    for cache_key, value in stat_true_value.items():
        group = cache.setdefault(cache_key, {})
        group["data"] = to_signed_int32(value)
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
                state = merged.get(name)
                bit_index = int(i)

                if not state:
                    continue

                if state.get("earned"):
                    bitmask |= 1 << bit_index
                    t = state.get("earned_time")
                    times[i] = int(t) if t else int(time.time())
                else:
                    times.pop(i, None)

            group["data"] = to_signed_int32(bitmask)

    return data


if __name__ == "__main__":
    try:
        cfg = load_config()
    except SystemExit:
        raise

    userid = cfg["userid"]
    steam_path = cfg["steam_path"]
    emu_path = cfg["emu_path"]

    appid = input("AppID: ")

    schema, data, _ = load_steam_stats(steam_path, userid, appid)

    try:
        b = read_json("achievements.json")
    except FileNotFoundError:
        console.print("[red]Error: achievements.json not found. Please run `python bin_to_json.py` first.[/red]")
        raise

    try:
        p = read_json(emu_path / f"{appid}" / "achievements.json")
    except FileNotFoundError:
        console.print("[red]Error: achievements.json not found in emu path.[/red]")
        raise

    merged = merge_achievements(b, p, schema)

    steam_bin = apply_achievements(merged, schema, data)

    write_json("merged_achievements.json", merged)
    write_bin(f"UserGameStats_{userid}_{appid}.bin", steam_bin)
