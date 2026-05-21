from utils import read_bin, write_json


if __name__ == "__main__":
    path = input("Path to UserGameStats*.bin: ").strip('"')
    if path.find("Schema") != -1:
        print("Detected Schema File (UserGameStatsSchema.bin)")
        schema = read_bin(path)
        write_json("schema.json", schema)
    else:
        print("Detected Data File (UserGameStats.bin)")
        data = read_bin(path)
        write_json("data.json", data)
