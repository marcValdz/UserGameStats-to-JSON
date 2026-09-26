import os
from pathlib import Path

import pytest

import main as app
from bin_to_json import extract_achievements
from factories import APPID, SPARSE_APPID, USERID, make_data, make_schema, make_sparse_schema
from utils import read_bin, read_json, write_bin, write_json


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    cfg = {
        "stats_path": tmp_path / "steam",
        "saves_path": tmp_path / "gse",
        "emu_schema_path": tmp_path / "emu_schema",
        "userid": USERID,
    }
    for key in ("stats_path", "saves_path", "emu_schema_path"):
        cfg[key].mkdir()
    monkeypatch.setattr(app, "load_config", lambda local=False: cfg)
    return cfg


def steam_bin(cfg):
    return cfg["stats_path"] / f"UserGameStats_{USERID}_{APPID}.bin"


def emu_json(cfg):
    return cfg["saves_path"] / APPID / "achievements.json"


def install_steam(cfg, data, schema=None):
    write_bin(cfg["stats_path"] / f"UserGameStatsSchema_{APPID}.bin", schema or make_schema())
    write_bin(steam_bin(cfg), data)


def install_emu(cfg, achievements):
    emu_json(cfg).parent.mkdir()
    write_json(emu_json(cfg), achievements)


def backups(path: Path):
    return list(path.parent.glob(f"{path.name}.*.bak"))


def steam_achievements(cfg):
    return extract_achievements(make_schema(), read_bin(steam_bin(cfg)))


# --- full sync ---------------------------------------------------------------


def test_emu_unlock_is_written_to_steam_and_emu(cfg):
    install_steam(cfg, make_data())
    install_emu(cfg, {"ACH_PLAIN": {"earned": True, "earned_time": 1700000000}})

    app.main([APPID])

    assert steam_achievements(cfg)["ACH_PLAIN"] == {"earned": True, "earned_time": 1700000000}
    emu = read_json(emu_json(cfg))
    assert emu["ACH_PLAIN"] == {"earned": True, "earned_time": 1700000000}
    assert set(emu) == {"ACH_PLAIN", "ACH_KILLS_10", "ACH_KILLS_100", "ACH_OTHER"}


def test_emu_unlock_backs_up_both_files(cfg):
    install_steam(cfg, make_data())
    install_emu(cfg, {"ACH_PLAIN": {"earned": True, "earned_time": 1700000000}})
    original_bin, original_json = steam_bin(cfg).read_bytes(), emu_json(cfg).read_bytes()

    app.main([APPID])

    assert [b.read_bytes() for b in backups(steam_bin(cfg))] == [original_bin]
    assert [b.read_bytes() for b in backups(emu_json(cfg))] == [original_json]


def test_steam_unlock_is_written_to_emu(cfg):
    install_steam(cfg, make_data(earned={"0": 1700000000}))
    install_emu(cfg, {"ACH_PLAIN": {"earned": False, "earned_time": 0}})

    app.main([APPID])

    assert read_json(emu_json(cfg))["ACH_PLAIN"] == {"earned": True, "earned_time": 1700000000}


def test_missing_emu_file_is_created_from_steam(cfg):
    data = make_data(earned={"0": 1700000000}, kills=4)
    install_steam(cfg, data)

    app.main([APPID])

    assert read_json(emu_json(cfg)) == extract_achievements(make_schema(), make_data(earned={"0": 1700000000}, kills=4))


@pytest.mark.parametrize("scenario", ["no emu file", "already in sync", "steam ahead of emu"])
def test_overwritten_files_are_always_recoverable(cfg, scenario):
    """Every existing file is either left byte-identical or backed up first."""
    install_steam(cfg, make_data(earned={"0": 1700000000}, kills=4))
    if scenario == "already in sync":
        install_emu(cfg, extract_achievements(make_schema(), make_data(earned={"0": 1700000000}, kills=4)))
    elif scenario == "steam ahead of emu":
        install_emu(cfg, {"ACH_PLAIN": {"earned": False, "earned_time": 0}})
    originals = {p: p.read_bytes() for p in (steam_bin(cfg), emu_json(cfg)) if p.exists()}

    app.main([APPID])

    for path, before in originals.items():
        unchanged = path.read_bytes() == before
        backed_up = any(b.read_bytes() == before for b in backups(path))
        assert unchanged or backed_up, f"{path.name} overwritten without backup"


def synced_steam_data():
    """kills=500 is past both kill thresholds, so Steam has those bits set too."""
    return make_data(earned={"0": 1700000000, "1": 1700000001, "2": 1700000002}, kills=500)


def test_already_in_sync_writes_nothing(cfg):
    install_steam(cfg, synced_steam_data())
    install_emu(cfg, extract_achievements(make_schema(), synced_steam_data()))
    originals = {p: p.read_bytes() for p in (steam_bin(cfg), emu_json(cfg))}

    app.main([APPID])

    for path, before in originals.items():
        assert path.read_bytes() == before
        assert backups(path) == []


def test_missing_emu_file_leaves_steam_untouched(cfg):
    install_steam(cfg, synced_steam_data())
    before = steam_bin(cfg).read_bytes()

    app.main([APPID])

    assert steam_bin(cfg).read_bytes() == before
    assert backups(steam_bin(cfg)) == []


def test_steam_ahead_is_not_reported_as_up_to_date(cfg, capsys):
    install_steam(cfg, make_data(earned={"0": 1700000000}))
    install_emu(cfg, {"ACH_PLAIN": {"earned": False, "earned_time": 0}})

    app.main([APPID])

    assert "up to date" not in capsys.readouterr().out


def test_unlock_time_only_change_is_not_reported_as_up_to_date(cfg, capsys):
    """Both sides earned it, the emu save recorded it earlier: Steam's time changes."""
    install_steam(cfg, make_data(earned={"0": 1700000500}))
    install_emu(cfg, extract_achievements(make_schema(), make_data(earned={"0": 1700000000})))

    app.main([APPID])

    assert "up to date" not in capsys.readouterr().out
    assert steam_achievements(cfg)["ACH_PLAIN"]["earned_time"] == 1700000000


def test_fallback_schema_builds_steam_files_from_emu(cfg):
    fallback = cfg["emu_schema_path"] / APPID
    fallback.mkdir()
    write_bin(fallback / f"UserGameStatsSchema_{APPID}.bin", make_schema())
    install_emu(cfg, {"ACH_PLAIN": {"earned": True, "earned_time": 1700000000}})

    app.main([APPID])

    assert read_bin(cfg["stats_path"] / f"UserGameStatsSchema_{APPID}.bin") == make_schema()
    assert steam_achievements(cfg)["ACH_PLAIN"] == {"earned": True, "earned_time": 1700000000}


def test_emu_complete_steam_partial_with_sparse_groups(cfg):
    """Emu at 100%, Steam's server copy has a few unlocks with later times."""
    schema = make_sparse_schema()
    write_bin(cfg["stats_path"] / f"UserGameStatsSchema_{SPARSE_APPID}.bin", schema)
    bin_path = cfg["stats_path"] / f"UserGameStats_{USERID}_{SPARSE_APPID}.bin"
    write_bin(bin_path, {"cache": {"crc": 912209226, "PendingChanges": 0, "3": {"data": 1, "AchievementTimes": {"0": 1787142250}}}})
    emu = {name: {"earned": True, "earned_time": 1708234313 + i} for i, name in enumerate(["ACH_16", "ACH_17", "ACH_31", "ACH_A", "ACH_B"])}
    emu_path = cfg["saves_path"] / SPARSE_APPID / "achievements.json"
    emu_path.parent.mkdir()
    write_json(emu_path, emu)
    emu_before = emu_path.read_bytes()

    app.main([SPARSE_APPID])

    cache = read_bin(bin_path)["cache"]
    assert (cache["crc"], cache["PendingChanges"]) == (912209226, 0)
    assert "1" not in cache  # empty achievement group stays absent
    assert cache["2"]["data"] & 0xFFFFFFFF == (1 << 16) | (1 << 17) | (1 << 31)
    assert cache["3"]["data"] == 0b101  # bit position 1 is skipped by the schema
    steam = extract_achievements(schema, read_bin(bin_path))
    assert {name: s["earned_time"] for name, s in steam.items()} == {name: s["earned_time"] for name, s in emu.items()}
    assert emu_path.read_bytes() == emu_before


def test_run_writes_session_log(cfg):
    install_steam(cfg, make_data())
    app.main([APPID])
    assert Path("session.log").exists()


def test_one_failing_appid_does_not_stop_the_rest(cfg):
    install_steam(cfg, make_data(earned={"0": 1700000000}))

    try:
        app.main(["999", APPID])
    except SystemExit:
        pass

    assert emu_json(cfg).exists()
    assert Path("session.log").exists()


# --- output ------------------------------------------------------------------


def test_changes_are_listed_by_display_name(cfg, capsys):
    schema = make_schema()
    schema[APPID]["stats"]["1"]["bits"]["0"]["display"]["name"]["english"] = "First Steps"
    install_steam(cfg, make_data(), schema)
    install_emu(cfg, {"ACH_PLAIN": {"earned": True, "earned_time": 1700000000}})

    app.main([APPID])

    out = capsys.readouterr().out
    assert "First Steps" in out
    assert "ACH_PLAIN" not in out


def test_changes_fall_back_to_api_name_without_display_name(cfg, capsys):
    schema = make_schema()
    del schema[APPID]["stats"]["1"]["bits"]["0"]["display"]
    install_steam(cfg, make_data(), schema)
    install_emu(cfg, {"ACH_PLAIN": {"earned": True, "earned_time": 1700000000}})

    app.main([APPID])

    assert "ACH_PLAIN" in capsys.readouterr().out


# --- CLI ---------------------------------------------------------------------


def killed_steam(process_calls):
    return any("taskkill" in cmd for cmd in process_calls)


def test_no_appids_is_a_usage_error(cfg):
    with pytest.raises(SystemExit) as exc:
        app.main([])
    assert exc.value.code == 2


def test_help_does_not_close_steam(cfg, process_calls):
    with pytest.raises(SystemExit):
        app.main(["--help"])
    assert not killed_steam(process_calls)


def test_bad_arguments_do_not_close_steam(cfg, process_calls):
    with pytest.raises(SystemExit):
        app.main(["--from", "nowhere"])
    assert not killed_steam(process_calls)


def test_local_run_does_not_close_steam(cfg, process_calls):
    """--local works on the project's stats/ and saves/ copies, not Steam's files."""
    install_steam(cfg, make_data())
    app.main(["--local", APPID])
    assert not killed_steam(process_calls)


@pytest.mark.skipif(os.name != "nt", reason="Steam is only closed on Windows")
def test_sync_closes_steam(cfg, process_calls):
    install_steam(cfg, make_data())
    app.main([APPID])
    assert ["taskkill", "/f", "/im", "steam.exe", "/t"] in process_calls


# --- helpers -----------------------------------------------------------------


def test_appids_from_stats_come_from_schema_files(tmp_path):
    for name in (f"UserGameStatsSchema_{APPID}.bin", f"UserGameStats_{USERID}_{APPID}.bin", "notes.txt"):
        (tmp_path / name).touch()
    assert app.get_appids("stats", tmp_path, tmp_path) == [APPID]


def test_appids_from_saves_ignore_non_appid_folders(tmp_path):
    (tmp_path / APPID).mkdir()
    (tmp_path / "settings").mkdir()
    (tmp_path / "readme.txt").touch()
    assert app.get_appids("saves", tmp_path, tmp_path) == [APPID]


def test_diff_reports_earned_and_progress_changes():
    steam = {"A": {"earned": False}, "B": {"earned": False, "progress": 1}, "C": {"earned": True}}
    merged = {"A": {"earned": True}, "B": {"earned": False, "progress": 2}, "C": {"earned": True}}
    assert [name for name, _, _ in app.diff_achievements(steam, merged)] == ["A", "B"]


def test_diff_reports_unlock_time_changes():
    steam = {"A": {"earned": True, "earned_time": 1700000500}, "B": {"earned": True, "earned_time": 1700000000}}
    merged = {"A": {"earned": True, "earned_time": 1700000000}, "B": {"earned": True, "earned_time": 1700000000}}
    assert [name for name, _, _ in app.diff_achievements(steam, merged)] == ["A"]


def test_print_diff_table_reports_whether_there_were_changes():
    assert app.print_diff_table([]) is False
    assert app.print_diff_table([("A", {"earned": False}, {"earned": True})]) is True


def test_backup_file_copies_original(tmp_path):
    """Copy, not move: a failed write afterwards must not leave the path empty."""
    path = tmp_path / "x.bin"
    path.write_bytes(b"original")
    app.backup_file(path)
    assert path.read_bytes() == b"original"
    assert [b.read_bytes() for b in backups(path)] == [b"original"]


def test_backup_file_ignores_missing_file(tmp_path):
    app.backup_file(tmp_path / "missing.bin")
    assert list(tmp_path.iterdir()) == []
