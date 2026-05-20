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


def merge(schema, data):
    out = {}

    cache = data.get("cache", {})

    for appid in schema:
        stats = schema[appid]["stats"]

        for stat_id, stat in stats.items():
            if stat.get("type") not in ("4", "ACHIEVEMENTS"):
                continue

            bits = stat.get("bits", {})
            group = cache.get(stat_id, {})
            times = group.get("AchievementTimes", {})
            prog = group.get("AchievementProgress", {})

            for i, ach in bits.items():
                t = times.get(i)

                obj = {"earned": t is not None and int(t) != 0, "earned_time": int(t) if t else 0}

                prog_info = ach.get("progress")
                if prog_info and "max_val" in prog_info:
                    obj["max_progress"] = int(prog_info["max_val"])
                    obj["progress"] = int(prog_info["min_val"])

                out[ach["name"]] = obj

    return dict(sorted(out.items(), key=lambda x: nat_key(x[0])))


if __name__ == "__main__":
    appid = input("AppID: ")
    userid = 243977152
    stats_path = Path(r"C:\Program Files (x86)\Steam\appcache\stats")

    schema, data = load_steam_stats(stats_path, userid, appid)
    ach_json = merge(schema, data)
    write_json("achievements.json", ach_json)
