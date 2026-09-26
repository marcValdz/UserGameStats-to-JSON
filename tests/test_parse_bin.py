import parse_bin
from factories import APPID, USERID, make_data, make_schema
from utils import read_json, write_bin


def test_schema_file_is_dumped_to_schema_json(tmp_path, monkeypatch):
    path = tmp_path / f"UserGameStatsSchema_{APPID}.bin"
    write_bin(path, make_schema())
    monkeypatch.setattr("builtins.input", lambda _: f'"{path}"')

    parse_bin.main()

    assert read_json("schema.json") == make_schema()


def test_data_file_is_dumped_to_data_json(tmp_path, monkeypatch):
    path = tmp_path / f"UserGameStats_{USERID}_{APPID}.bin"
    write_bin(path, make_data(kills=3))
    monkeypatch.setattr("builtins.input", lambda _: str(path))

    parse_bin.main()

    assert read_json("data.json") == make_data(kills=3)
