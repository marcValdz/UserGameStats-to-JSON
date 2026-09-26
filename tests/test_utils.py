import pytest

from factories import APPID, USERID, ach, make_data, make_schema
from utils import is_stat_based, load_steam_stats, nat_key, parse_schema, read_bin, read_json, write_bin, write_json


def test_nat_key_orders_numbers_numerically():
    assert sorted(["ACH_10", "ACH_2", "ACH_1"], key=nat_key) == ["ACH_1", "ACH_2", "ACH_10"]


@pytest.mark.parametrize(
    "prog_info, expected",
    [
        (None, False),
        ({}, False),
        ({"value": "statvalue"}, False),
        ({"value": {"operation": "other"}}, False),
        ({"value": {"operation": "statvalue", "operand1": "kills"}}, True),
    ],
)
def test_is_stat_based(prog_info, expected):
    assert bool(is_stat_based(prog_info)) is expected


def test_bin_round_trip(tmp_path):
    data = make_data(earned={"0": 1700000000}, kills=5, distance=12.5)
    write_bin(tmp_path / "x.bin", data)
    assert read_bin(tmp_path / "x.bin") == data


def test_json_round_trip_keeps_unicode_readable(tmp_path):
    write_json(tmp_path / "x.json", {"名前": "é"})
    assert read_json(tmp_path / "x.json") == {"名前": "é"}
    assert "名前" in (tmp_path / "x.json").read_text(encoding="utf-8")


def test_parse_schema_maps_stat_based_achievements():
    stat_to_achs, ach_to_stat = parse_schema(make_schema())
    assert stat_to_achs == {
        "kills": [("ACH_KILLS_10", 10), ("ACH_KILLS_100", 100)],
        "distance": [("ACH_WALK_1000", 1000)],
    }
    assert ach_to_stat["ACH_KILLS_100"] == ("kills", 100, "2")
    assert ach_to_stat["ACH_WALK_1000"] == ("distance", 1000, "3")
    assert "ACH_PLAIN" not in ach_to_stat


def test_parse_schema_accepts_numeric_type_codes():
    schema = {APPID: {"stats": {"1": {"type": "4", "bits": {"0": ach("A", "s", 5)}}, "2": {"type": "1", "name": "s"}}}}
    _, ach_to_stat = parse_schema(schema)
    assert ach_to_stat == {"A": ("s", 5, "2")}


def test_parse_schema_skips_progress_without_max():
    schema = {APPID: {"stats": {"1": {"type": "ACHIEVEMENTS", "bits": {"0": ach("A", "s", None)}}, "2": {"type": "INT", "name": "s"}}}}
    assert parse_schema(schema) == ({}, {})


def _install(folder, schema=True, data=True):
    folder.mkdir(parents=True, exist_ok=True)
    if schema:
        write_bin(folder / f"UserGameStatsSchema_{APPID}.bin", make_schema())
    if data:
        write_bin(folder / f"UserGameStats_{USERID}_{APPID}.bin", make_data(kills=3))


def test_load_steam_stats_reads_schema_and_data(tmp_path):
    _install(tmp_path / "stats")
    schema, data, is_fallback = load_steam_stats(tmp_path / "stats", USERID, APPID)
    assert schema == make_schema()
    assert data == make_data(kills=3)
    assert is_fallback is False


def test_load_steam_stats_without_data_file_starts_empty(tmp_path):
    _install(tmp_path / "stats", data=False)
    _, data, _ = load_steam_stats(tmp_path / "stats", USERID, APPID)
    assert data == {"cache": {"crc": 0, "PendingChanges": 1}}


def test_load_steam_stats_uses_fallback_schema(tmp_path):
    (tmp_path / "stats").mkdir()
    _install(tmp_path / "fallback", data=False)
    schema, _, is_fallback = load_steam_stats(tmp_path / "stats", USERID, APPID, fallback=tmp_path / "fallback")
    assert schema == make_schema()
    assert is_fallback is True


def test_load_steam_stats_without_any_schema_raises(tmp_path):
    (tmp_path / "stats").mkdir()
    with pytest.raises(FileNotFoundError):
        load_steam_stats(tmp_path / "stats", USERID, APPID, fallback=tmp_path / "missing")
