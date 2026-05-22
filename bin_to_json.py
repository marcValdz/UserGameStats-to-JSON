from utils import nat_key, is_stat_based, load_steam_stats, write_json, parse_schema
from config import load_config


def extract_achievements(schema, data):
    out = {}
    cache = data.get("cache", {})
    _, ach_to_stat = parse_schema(schema)

    for appid in schema:
        stats = schema[appid]["stats"]
        for stat_id, stat in stats.items():
            if stat.get("type") not in ("4", "ACHIEVEMENTS"):
                continue

            bits = stat.get("bits", {})
            group = cache.get(stat_id, {})
            times = group.get("AchievementTimes", {})

            for i, ach in bits.items():
                name = ach["name"]
                obj = {}
                prog_info = ach.get("progress")

                # -------------------------
                # STAT-BASED ACHIEVEMENTS
                # -------------------------
                if is_stat_based(prog_info):
                    operand, max_val, cache_key = ach_to_stat[name]
                    current = cache.get(cache_key, {}).get("data", 0)
                    max_val = int(prog_info.get("max_val"))

                    # Check timestamp first, fall back to progress comparison
                    t = times.get(i)
                    if t is not None and int(t) != 0:
                        obj["earned"] = True
                        obj["earned_time"] = int(t)
                    else:
                        obj["earned"] = max_val is not None and current >= max_val
                        obj["earned_time"] = 0

                    if max_val is not None:
                        obj["max_progress"] = int(max_val)
                        obj["progress"] = min(int(current), int(max_val))  # cap at max
                    else:
                        obj["progress"] = int(current)

                # -------------------------
                # NORMAL ACHIEVEMENTS
                # -------------------------
                else:
                    t = times.get(i)

                    obj["earned"] = t is not None and int(t) != 0
                    obj["earned_time"] = int(t) if t else 0

                out[name] = obj

    return dict(sorted(out.items(), key=lambda x: nat_key(x[0])))


if __name__ == "__main__":
    try:
        cfg = load_config()
    except SystemExit:
        raise

    userid = cfg["userid"]
    steam_path = cfg["steam_path"]
    emu_path = cfg["emu_path"]

    appid = input("AppID: ")

    schema, data = load_steam_stats(steam_path, userid, appid)
    ach_json = extract_achievements(schema, data)
    write_json("achievements.json", ach_json)
