import json
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


def update_bin(updated_path, schema_path, data_path, output_path):
    updated = load_json(updated_path)
    schema = load_json(schema_path)
    data = load_json(data_path)

    cache = data.get("cache", {})

    for appid in schema:
        stats = schema[appid]["stats"]

        for stat_id, stat in stats.items():
            if stat.get("type") not in ("4", "ACHIEVEMENTS"):
                continue

            bits = stat.get("bits", {})

            group = cache.setdefault(stat_id, {})
            times = group.setdefault("AchievementTimes", {})

            bitmask = 0

            for i, ach in bits.items():
                name = ach["name"]
                state = updated.get(name)

                if not state:
                    continue

                if state.get("earned"):
                    bitmask |= 1 << int(i)

                    if state.get("earned_time"):
                        times[i] = int(state["earned_time"])
                    else:
                        import time

                        times[i] = int(time.time())

                else:
                    if i in times:
                        del times[i]

            group["data"] = bitmask

    write_bin(output_path, data)


def nat_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def merge_achievements(a, b):
    out = {}
    keys = set(a) | set(b)

    for k in keys:
        x = a.get(k)
        y = b.get(k)

        if x is None:
            out[k] = y
            continue
        if y is None:
            out[k] = x
            continue

        merged = dict(x)

        # rule: both earned → keep older timestamp (smaller value)
        if x.get("earned") and y.get("earned"):
            merged["earned_time"] = min(x.get("earned_time", 0), y.get("earned_time", 0))
        # otherwise prefer whichever is earned
        else:
            if y.get("earned"):
                merged = dict(y)

        out[k] = merged

    return dict(sorted(out.items(), key=lambda x: nat_key(x[0])))


if __name__ == "__main__":
    appid = input("AppID: ")
    userid = 243977152

    aw_ach_path = Path(os.environ["APPDATA"]) / "GSE Saves" / f"{appid}" / "achievements.json"
    aw_ach = load_json(aw_ach_path)

    steam_ach_path = Path("achievements.json")
    steam_ach = load_json(steam_ach_path)

    merged = merge_achievements(aw_ach, steam_ach)
    write_json("merged_achievements.json", merged)

    out_path = Path(f"UserGameStats_{userid}_{appid}.bin")
    update_bin("merged_achievements.json", "schema.json", "data.json", out_path)

    # Close steam
    # Wait 1000ms
    # Write bin to steam\appcache\stats
    stats_path = Path(r"C:\Program Files (x86)\Steam\appcache\stats")
    # Relaunch Steam
