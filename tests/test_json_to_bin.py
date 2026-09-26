import copy

import pytest

import json_to_bin
from bin_to_json import extract_achievements
from factories import APPID, USERID, ach, make_data, make_schema
from json_to_bin import apply_achievements, merge_achievements, to_signed_int32
from utils import read_bin, read_json, write_bin, write_json


def st(earned=False, t=0, **extra):
    return {"earned": earned, "earned_time": t, **extra}


@pytest.mark.parametrize("value, expected", [(0, 0), (2**31 - 1, 2**31 - 1), (2**31, -(2**31)), (2**32 - 1, -1)])
def test_to_signed_int32(value, expected):
    assert to_signed_int32(value) == expected


# --- merge -------------------------------------------------------------------


def merge(base, patch):
    return merge_achievements(base, patch, make_schema())


def test_merge_earned_on_either_side_is_earned():
    out = merge({"ACH_PLAIN": st()}, {"ACH_PLAIN": st(True, 500)})
    assert out["ACH_PLAIN"] == st(True, 500)


def test_merge_never_unearns():
    out = merge({"ACH_PLAIN": st(True, 100)}, {"ACH_PLAIN": st()})
    assert out["ACH_PLAIN"] == st(True, 100)


@pytest.mark.parametrize("steam_time, emu_time", [(300, 200), (200, 300)])
def test_merge_keeps_earliest_unlock_time_from_either_side(steam_time, emu_time):
    """The actual unlock time is whichever was earliest, from either side."""
    out = merge({"ACH_PLAIN": st(True, steam_time)}, {"ACH_PLAIN": st(True, emu_time)})
    assert out["ACH_PLAIN"]["earned_time"] == 200


def test_merge_ignores_missing_unlock_time():
    """Steam reports a stat-earned achievement without an unlock time."""
    out = merge({"ACH_KILLS_10": st(True, 0, progress=10, max_progress=10)}, {"ACH_KILLS_10": st(True, 400)})
    assert out["ACH_KILLS_10"]["earned_time"] == 400


def test_merge_earned_without_any_time_keeps_zero():
    out = merge({"ACH_KILLS_10": st(True, 0, progress=10, max_progress=10)}, {})
    assert out["ACH_KILLS_10"] == st(True, 0, progress=10, max_progress=10)


def test_merge_earning_higher_tier_earns_lower_tier_of_same_stat():
    base = {"ACH_KILLS_10": st(progress=0, max_progress=10), "ACH_KILLS_100": st(progress=0, max_progress=100)}
    patch = {"ACH_KILLS_100": st(True, 900)}
    out = merge(base, patch)
    assert out["ACH_KILLS_10"]["earned"] is True
    assert out["ACH_KILLS_10"]["progress"] == 10
    assert out["ACH_KILLS_100"] == st(True, 900, progress=100, max_progress=100)


def test_merge_takes_highest_progress_across_sides_and_tiers():
    base = {"ACH_KILLS_10": st(progress=3, max_progress=10), "ACH_KILLS_100": st(progress=3, max_progress=100)}
    patch = {"ACH_KILLS_100": st(progress=7, max_progress=100)}
    out = merge(base, patch)
    assert out["ACH_KILLS_10"]["progress"] == 7
    assert out["ACH_KILLS_100"]["progress"] == 7


def test_merge_progress_reaching_max_earns():
    out = merge({"ACH_KILLS_10": st(progress=4, max_progress=10)}, {"ACH_KILLS_10": st(progress=10, max_progress=10)})
    assert out["ACH_KILLS_10"]["earned"] is True


def test_merge_output_is_naturally_sorted():
    schema = {APPID: {"stats": {}}}
    assert list(merge_achievements({"ACH_10": st()}, {"ACH_2": st()}, schema)) == ["ACH_2", "ACH_10"]


# --- apply -------------------------------------------------------------------


def apply(merged, data):
    return apply_achievements(merged, make_schema(), data)["cache"]


def merged_from(data, **overrides):
    merged = extract_achievements(make_schema(), copy.deepcopy(data))
    for name, state in overrides.items():
        merged[name].update(state)
    return merged


def test_apply_sets_bits_and_times_for_earned():
    data = make_data()
    cache = apply(merged_from(data, ACH_PLAIN=st(True, 111), ACH_OTHER=st(True, 222)), data)
    assert cache["1"]["data"] == (1 << 0) | (1 << 3)
    assert cache["1"]["AchievementTimes"] == {"0": 111, "3": 222}


def test_apply_stamps_stat_earned_achievement_with_now(monkeypatch):
    """Stat past the threshold but no unlock bit on Steam."""
    monkeypatch.setattr(json_to_bin.time, "time", lambda: 1234.9)
    data = make_data(kills=10)
    cache = apply(merged_from(data), data)
    assert cache["1"]["data"] == 1 << 1
    assert cache["1"]["AchievementTimes"] == {"1": 1234}


def test_apply_all_32_bits_round_trips(tmp_path):
    schema = {APPID: {"stats": {"1": {"type": "ACHIEVEMENTS", "bits": {str(i): ach(f"A{i}") for i in range(32)}}}}}
    merged = {f"A{i}": st(True, 1000 + i) for i in range(32)}
    data = apply_achievements(merged, schema, {"cache": {}})
    assert data["cache"]["1"]["data"] == -1

    write_bin(tmp_path / "x.bin", data)
    assert extract_achievements(schema, read_bin(tmp_path / "x.bin")) == merged


def test_apply_raises_stat_to_threshold_of_earned_achievement():
    data = make_data(kills=3)
    cache = apply(merged_from(data, ACH_KILLS_10=st(True, 5)), data)
    assert cache["2"]["data"] == 10


def test_apply_raises_stat_to_emu_progress():
    data = make_data(kills=3)
    cache = apply(merged_from(data, ACH_KILLS_100={"progress": 7}), data)
    assert cache["2"]["data"] == 7


def test_apply_never_lowers_a_stat():
    data = make_data(kills=500)
    cache = apply(merged_from(data), data)
    assert cache["2"]["data"] == 500


def test_apply_does_not_touch_stats_it_does_not_raise():
    data = make_data(kills=500)
    cache = apply(merged_from(data), data)
    assert cache["2"] == {"data": 500}


def test_apply_does_not_add_empty_groups():
    data = {"cache": {"crc": 0, "PendingChanges": 0}}
    merged = extract_achievements(make_schema(), copy.deepcopy(data))
    assert apply_achievements(merged, make_schema(), data) == {"cache": {"crc": 0, "PendingChanges": 0}}


def test_apply_adds_groups_it_needs():
    data = {"cache": {"crc": 0, "PendingChanges": 0}}
    merged = merged_from(data, ACH_PLAIN=st(True, 111), ACH_KILLS_10=st(True, 222))
    cache = apply_achievements(merged, make_schema(), data)["cache"]
    assert cache["1"] == {"AchievementTimes": {"0": 111, "1": 222}, "data": 0b11}
    assert cache["2"] == {"data": 10, "state": 2}


def test_apply_leaves_unrelated_stats_alone():
    data = make_data(unrelated=7, distance=1234.5)
    cache = apply(merged_from(data, ACH_PLAIN=st(True, 1)), data)
    assert cache["3"] == {"data": 1234.5}
    assert cache["4"] == {"data": 7}


def test_apply_then_extract_is_stable():
    data = make_data(earned={"0": 111, "1": 222}, kills=12, distance=5.0)
    merged = merged_from(data)
    assert extract_achievements(make_schema(), apply_achievements(merged, make_schema(), data)) == merged


def test_script_writes_merged_json_and_bin(tmp_path, monkeypatch):
    write_bin(tmp_path / f"UserGameStatsSchema_{APPID}.bin", make_schema())
    write_bin(tmp_path / f"UserGameStats_{USERID}_{APPID}.bin", make_data())
    (tmp_path / APPID).mkdir()
    write_json(tmp_path / APPID / "achievements.json", {"ACH_PLAIN": st(True, 42)})
    write_json("achievements.json", extract_achievements(make_schema(), make_data()))
    cfg = {"stats_path": tmp_path, "saves_path": tmp_path, "emu_schema_path": tmp_path, "userid": USERID}
    monkeypatch.setattr(json_to_bin, "load_config", lambda: cfg)
    monkeypatch.setattr("builtins.input", lambda _: APPID)

    json_to_bin.main()

    assert read_json("merged_achievements.json")["ACH_PLAIN"] == st(True, 42)
    written = read_bin(f"UserGameStats_{USERID}_{APPID}.bin")
    assert extract_achievements(make_schema(), written)["ACH_PLAIN"] == st(True, 42)
