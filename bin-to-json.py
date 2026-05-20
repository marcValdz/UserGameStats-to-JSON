import vdf
import json
from pprint import pprint
from pathlib import Path


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_bin(path):
    with open(path, "rb") as f:
        return vdf.binary_loads(f.read())


def find(folder, pattern):
    matches = list(Path(folder).glob(pattern))
    if not matches:
        raise FileNotFoundError(pattern)
    return matches[0]


def load_steam_stats(folder, userid, appid):
    schema = load_bin(find(folder, f"UserGameStatsSchema_{appid}.bin"))
    data = load_bin(find(folder, f"UserGameStats_{userid}_{appid}.bin"))

    write_json("schema.json", schema)
    write_json("data.json", data)

    return schema, data


def nat_key(s):
    import re

    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def build_stat_index(stats):
    name_to_id = {}
    for stat_id, stat in stats.items():
        name = stat.get("name")
        if name:
            name_to_id[name] = stat_id
    write_json("stat_index.json", name_to_id)
    return name_to_id


def merge(schema, data):
    out = {}
    cache = data.get("cache", {})

    for appid in schema:
        stats = schema[appid]["stats"]

        # OPTIMIZATION: build once per appid
        stat_name_to_id = build_stat_index(stats)

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

                is_stat = prog_info and isinstance(prog_info.get("value"), dict) and prog_info["value"].get("operation") == "statvalue"

                # -------------------------
                # STAT-BASED ACHIEVEMENTS
                # -------------------------
                if is_stat:
                    operand = prog_info["value"]["operand1"]
                    stat_key = stat_name_to_id.get(operand)

                    current = 0
                    if stat_key is not None:
                        current = cache.get(stat_key, {}).get("data", 0)

                    max_val = prog_info.get("max_val")

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
    appid = input("AppID: ")
    userid = 243977152
    stats_path = Path(r"C:\Program Files (x86)\Steam\appcache\stats")

    schema, data = load_steam_stats(stats_path, userid, appid)
    ach_json = merge(schema, data)
    write_json("achievements.json", ach_json)
