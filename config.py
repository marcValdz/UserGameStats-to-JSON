import configparser
import os
from pathlib import Path

from utils import console

CONFIG_PATH = Path("config.ini")


def check_path(path: Path, name: str) -> Path:
    if not path.exists():
        console.print(f"[red]Invalid config:[/red] '{name}' does not exist")
        console.print(f"[dim]{path}[/dim]")
        raise SystemExit(1)

    return path


def check_userid(value: str) -> int:
    try:
        userid = int(value)
    except ValueError:
        userid = 0
    if userid <= 0:
        console.print(f"[red]Invalid config:[/red] 'userid' must be your Steam32 ID, got '{value}'")
        console.print("[dim]Put only the number on the line, without a comment.[/dim]")
        raise SystemExit(1)

    return userid


def load_config(local=False):
    if not CONFIG_PATH.exists():
        # Values like %APPDATA% are expanded by os.path.expandvars, not configparser
        default = configparser.ConfigParser(interpolation=None)

        default["paths"] = {
            "stats_path": r"C:\Program Files (x86)\Steam\appcache\stats",
            "saves_path": r"%APPDATA%\GSE Saves",
            "emu_schema_path": r"\path\to\generate_emu_config\backup",
        }

        default["user"] = {
            "userid": "0",
        }

        with open(CONFIG_PATH, "w") as f:
            default.write(f)

        console.print(f"[yellow]Created {CONFIG_PATH}.[/yellow] Fill in your paths and Steam user ID, then run again.")
        raise SystemExit(1)

    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(CONFIG_PATH)

    stats_path = Path("stats") if local else Path(os.path.expandvars(cfg["paths"]["stats_path"]))
    saves_path = Path("saves") if local else Path(os.path.expandvars(cfg["paths"]["saves_path"]))
    emu_schema_path = Path(os.path.expandvars(cfg["paths"]["emu_schema_path"]))

    config = {
        "stats_path": check_path(stats_path, "stats_path"),
        "saves_path": check_path(saves_path, "saves_path"),
        # Only a fallback for apps Steam has no schema for, so it may not exist
        "emu_schema_path": emu_schema_path,
        "userid": check_userid(cfg["user"]["userid"]),
    }

    if not any(config["stats_path"].glob(f"UserGameStats_{config['userid']}_*.bin")):
        console.print(f"[yellow]Warning:[/yellow] no UserGameStats_{config['userid']}_*.bin in stats_path; check that userid is your Steam32 ID")

    return config
