import pytest

import bin_to_json
from bin_to_json import extract_achievements
from factories import APPID, USERID, ach, make_data, make_schema
from utils import read_json, write_bin


def test_plain_achievement_earned_from_timestamp():
    out = extract_achievements(make_schema(), make_data(earned={"0": 1700000000}))
    assert out["ACH_PLAIN"] == {"earned": True, "earned_time": 1700000000}
    assert out["ACH_OTHER"] == {"earned": False, "earned_time": 0}


def test_zero_timestamp_is_not_earned():
    out = extract_achievements(make_schema(), make_data(earned={"0": 0}))
    assert out["ACH_PLAIN"]["earned"] is False


def test_stat_based_progress_comes_from_stat():
    out = extract_achievements(make_schema(), make_data(kills=7))
    assert out["ACH_KILLS_10"] == {"earned": False, "earned_time": 0, "max_progress": 10, "progress": 7}


def test_stat_reaching_threshold_counts_as_earned_without_timestamp():
    out = extract_achievements(make_schema(), make_data(kills=10))
    assert out["ACH_KILLS_10"]["earned"] is True
    assert out["ACH_KILLS_10"]["earned_time"] == 0
    assert out["ACH_KILLS_100"]["earned"] is False
    assert out["ACH_KILLS_100"]["progress"] == 10


def test_reported_progress_is_capped_at_max():
    out = extract_achievements(make_schema(), make_data(kills=500))
    assert out["ACH_KILLS_10"]["progress"] == 10
    assert out["ACH_KILLS_100"]["progress"] == 100


def test_timestamp_marks_stat_achievement_earned_even_if_stat_is_low():
    out = extract_achievements(make_schema(), make_data(earned={"2": 1700000000}, kills=0))
    assert out["ACH_KILLS_100"]["earned"] is True
    assert out["ACH_KILLS_100"]["earned_time"] == 1700000000


def test_empty_cache_means_nothing_earned():
    out = extract_achievements(make_schema(), {"cache": {"crc": 0, "PendingChanges": 1}})
    assert not any(a["earned"] for a in out.values())
    assert out["ACH_KILLS_100"]["progress"] == 0


def test_output_is_naturally_sorted():
    schema = {APPID: {"stats": {"1": {"type": "ACHIEVEMENTS", "bits": {"0": ach("ACH_10"), "1": ach("ACH_2")}}}}}
    assert list(extract_achievements(schema, {"cache": {}})) == ["ACH_2", "ACH_10"]


def _cfg(tmp_path):
    return {"stats_path": tmp_path, "saves_path": tmp_path, "emu_schema_path": tmp_path, "userid": USERID}


def test_script_writes_achievements_json(tmp_path, monkeypatch):
    write_bin(tmp_path / f"UserGameStatsSchema_{APPID}.bin", make_schema())
    write_bin(tmp_path / f"UserGameStats_{USERID}_{APPID}.bin", make_data(earned={"0": 1700000000}))
    monkeypatch.setattr(bin_to_json, "load_config", lambda: _cfg(tmp_path))
    monkeypatch.setattr("builtins.input", lambda _: APPID)

    bin_to_json.main()

    assert read_json("achievements.json")["ACH_PLAIN"] == {"earned": True, "earned_time": 1700000000}


def test_script_exits_nonzero_for_unknown_appid(tmp_path, monkeypatch):
    monkeypatch.setattr(bin_to_json, "load_config", lambda: _cfg(tmp_path))
    monkeypatch.setattr("builtins.input", lambda _: "999")

    with pytest.raises(SystemExit) as exc:
        bin_to_json.main()
    assert exc.value.code == 1
