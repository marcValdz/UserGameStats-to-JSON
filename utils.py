# utils.py
import vdf
import json
import re
from pathlib import Path

from rich.console import Console

console = Console(log_time=True, record=True)


def nat_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def is_stat_based(prog_info):
    return prog_info and isinstance(prog_info.get("value"), dict) and prog_info["value"].get("operation") == "statvalue"


def read_bin(path):
    with open(path, "rb") as f:
        return vdf.binary_loads(f.read())


def write_bin(path, data):
    with open(path, "wb") as f:
        f.write(vdf.binary_dumps(data))


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find(folder, pattern):
    matches = list(Path(folder).glob(pattern))
    if not matches:
        return None
    return matches[0]


def load_steam_stats(folder, userid, appid, fallback=None):
    is_fallback = False

    # Load schema file
    schema_file = f"UserGameStatsSchema_{appid}.bin"
    if (schema_path := find(folder, schema_file)) is not None:
        console.print(f"[green]✓[/green] Found Steam stats schema for appid {appid} at {schema_path}.")
    elif fallback and (schema_path := find(fallback, schema_file)) is not None:
        console.print(f"[yellow]Warning: Steam stats not found for appid {appid} and userid {userid}. Using fallback schema from {fallback}.[/yellow]")
        is_fallback = True
    else:
        raise FileNotFoundError(f"Steam stats not found for appid {appid} and userid {userid}, and no valid fallback schema found.")
    schema = read_bin(schema_path)

    # Load data file
    data_path = find(folder, f"UserGameStats_{userid}_{appid}.bin")
    data = read_bin(data_path) if data_path is not None else {"cache": {"crc": 0, "PendingChanges": 1}}

    return schema, data, is_fallback


def parse_schema(schema):
    """
    Walk the schema once and return two lookup maps:
      stat_to_achs: operand_name -> [(ach_name, max_val), ...]
      ach_to_stat:  ach_name     -> (operand_name, max_val, cache_key)
    Only includes stat-based achievements (operation == "statvalue").
    """
    stat_to_achs = {}
    ach_to_stat = {}
    for appid in schema:
        # build operand -> cache_key from INT stats first
        operand_to_cache_key = {stat["name"]: stat_id for stat_id, stat in schema[appid]["stats"].items() if stat.get("name")}
        for stat_id, stat in schema[appid]["stats"].items():
            if stat.get("type") not in ("4", "ACHIEVEMENTS"):
                continue
            for i, ach in stat.get("bits", {}).items():
                name = ach["name"]
                prog_info = ach.get("progress")
                if not is_stat_based(prog_info):
                    continue
                max_val = prog_info.get("max_val")
                if max_val is None:
                    continue
                operand = prog_info["value"]["operand1"]
                cache_key = operand_to_cache_key.get(operand)
                stat_to_achs.setdefault(operand, []).append((name, int(max_val)))
                ach_to_stat[name] = (operand, int(max_val), cache_key)
    return stat_to_achs, ach_to_stat
