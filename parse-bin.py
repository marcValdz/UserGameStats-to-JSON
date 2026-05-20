import vdf
import json
from pathlib import Path


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_bin(file, path):
    with open(Path(path), "rb") as f:
        bin = vdf.binary_loads(f.read())
    write_json(file, bin)


if __name__ == "__main__":
    path = input("Path to UserGameStats*.bin: ").strip('"')
    if path.find("Schema") != -1:
        print("Detected Schema File (UserGameStatsSchema.bin)")
        load_bin("schema.json", path)
    else:
        print("Detected Data File (UserGameStats.bin)")
        load_bin("data.json", path)
