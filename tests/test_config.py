import configparser
import os
from pathlib import Path

import pytest

import config
from config import load_config


def write_ini(stats, saves, emu_schema, userid="12345"):
    """A value of None leaves that key out of config.ini."""
    paths = {"stats_path": stats, "saves_path": saves, "emu_schema_path": emu_schema}
    lines = "".join(f"{key} = {value}\n" for key, value in paths.items() if value is not None)
    Path("config.ini").write_text(f"[paths]\n{lines}\n[user]\nuserid = {userid}\n", encoding="utf-8")


@pytest.fixture
def dirs(tmp_path):
    paths = {name: tmp_path / name for name in ("steam", "gse", "emu_schema")}
    for p in paths.values():
        p.mkdir()
    return paths


def test_missing_config_creates_template_and_exits():
    with pytest.raises(SystemExit):
        load_config()
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read("config.ini")
    assert set(cfg["paths"]) == {"stats_path", "saves_path", "emu_schema_path"}
    assert set(cfg["user"]) == {"userid"}


def test_missing_config_tells_user_to_fill_it_in(capsys):
    with pytest.raises(SystemExit):
        load_config()
    assert "config.ini" in capsys.readouterr().out


def test_loads_paths_and_userid(dirs):
    write_ini(dirs["steam"], dirs["gse"], dirs["emu_schema"])
    assert load_config() == {
        "stats_path": dirs["steam"],
        "saves_path": dirs["gse"],
        "emu_schema_path": dirs["emu_schema"],
        "userid": 12345,
    }


def test_unset_userid_is_rejected(dirs, capsys):
    """The generated template has userid = 0; syncing with it would create UserGameStats_0_* files in Steam's folder."""
    write_ini(dirs["steam"], dirs["gse"], dirs["emu_schema"], userid="0")
    with pytest.raises(SystemExit) as exc:
        load_config()
    assert exc.value.code == 1
    assert "userid" in capsys.readouterr().out


def test_userid_with_inline_comment_is_rejected_with_message(dirs, capsys):
    """Earlier READMEs showed `userid = 000000000 # Steam32 ID`; configparser keeps the comment."""
    write_ini(dirs["steam"], dirs["gse"], dirs["emu_schema"], userid="12345 # Steam32 ID")
    with pytest.raises(SystemExit) as exc:
        load_config()
    assert exc.value.code == 1
    assert "userid" in capsys.readouterr().out


def test_warns_when_steam_has_no_stats_for_userid(dirs, capsys):
    (dirs["steam"] / "UserGameStats_99999_100.bin").touch()
    write_ini(dirs["steam"], dirs["gse"], dirs["emu_schema"], userid="12345")
    assert load_config()["userid"] == 12345
    assert "12345" in capsys.readouterr().out


def test_no_warning_when_steam_has_stats_for_userid(dirs, capsys):
    (dirs["steam"] / "UserGameStats_12345_100.bin").touch()
    write_ini(dirs["steam"], dirs["gse"], dirs["emu_schema"], userid="12345")
    load_config()
    assert capsys.readouterr().out == ""


@pytest.mark.skipif(os.name != "nt", reason="%VAR% expansion is Windows-only")
def test_expands_windows_env_vars(dirs, monkeypatch):
    monkeypatch.setenv("UGS_TEST_ROOT", str(dirs["gse"].parent))
    write_ini(dirs["steam"], r"%UGS_TEST_ROOT%\gse", dirs["emu_schema"])
    assert load_config()["saves_path"] == dirs["gse"]


def test_local_mode_uses_project_stats_and_saves(dirs, tmp_path):
    (tmp_path / "stats").mkdir()
    (tmp_path / "saves").mkdir()
    write_ini(tmp_path / "nope1", tmp_path / "nope2", dirs["emu_schema"])
    cfg = load_config(local=True)
    assert cfg["stats_path"] == Path("stats")
    assert cfg["saves_path"] == Path("saves")


def test_missing_stats_path_exits_with_error(dirs, tmp_path):
    write_ini(tmp_path / "missing", dirs["gse"], dirs["emu_schema"])
    with pytest.raises(SystemExit) as exc:
        load_config()
    assert exc.value.code == 1


def test_emu_schema_path_is_optional(dirs, tmp_path):
    """Only needed as a fallback when Steam has no schema for an app."""
    write_ini(dirs["steam"], dirs["gse"], tmp_path / "missing")
    assert load_config()["stats_path"] == dirs["steam"]


# --- path detection ----------------------------------------------------------


@pytest.fixture
def steam_install(tmp_path, monkeypatch):
    root = tmp_path / "Steam"
    (root / "appcache" / "stats").mkdir(parents=True)
    monkeypatch.setattr(config, "_steam_install_path", lambda: root)
    return root


@pytest.fixture
def gse_saves(monkeypatch):
    saves = Path(os.environ["APPDATA"]) / "GSE Saves"
    saves.mkdir()
    return saves


def test_empty_paths_are_detected(steam_install, gse_saves, capsys):
    write_ini("", "", "")
    cfg = load_config()
    assert cfg["stats_path"] == steam_install / "appcache" / "stats"
    assert cfg["saves_path"] == gse_saves
    out = capsys.readouterr().out
    assert "stats_path" in out and "saves_path" in out


def test_missing_path_keys_are_detected(steam_install, gse_saves):
    write_ini(None, None, None)
    cfg = load_config()
    assert cfg["stats_path"] == steam_install / "appcache" / "stats"
    assert cfg["saves_path"] == gse_saves


def test_set_paths_win_over_detection(dirs, steam_install, gse_saves):
    write_ini(dirs["steam"], dirs["gse"], dirs["emu_schema"])
    cfg = load_config()
    assert (cfg["stats_path"], cfg["saves_path"]) == (dirs["steam"], dirs["gse"])


@pytest.mark.parametrize("key", ["stats_path", "saves_path"])
def test_undetectable_path_exits_with_message(dirs, steam_install, gse_saves, key, capsys, monkeypatch):
    """No Steam install in the registry, or no GSE Saves in %APPDATA%."""
    if key == "stats_path":
        monkeypatch.setattr(config, "_steam_install_path", lambda: None)
    else:
        gse_saves.rmdir()
    write_ini("", "", "")
    with pytest.raises(SystemExit) as exc:
        load_config()
    assert exc.value.code == 1
    assert key in capsys.readouterr().out


def test_empty_emu_schema_path_means_no_fallback(dirs):
    write_ini(dirs["steam"], dirs["gse"], "")
    assert load_config()["emu_schema_path"] is None


def test_template_leaves_paths_empty_for_detection(steam_install, gse_saves):
    with pytest.raises(SystemExit):
        load_config()
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read("config.ini")
    assert all(value == "" for value in cfg["paths"].values())

    cfg["user"]["userid"] = "12345"
    with open("config.ini", "w") as f:
        cfg.write(f)
    assert load_config()["stats_path"] == steam_install / "appcache" / "stats"
