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


def load_config(local=False):
    if not CONFIG_PATH.exists():
        default = configparser.ConfigParser()

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

        raise SystemExit

    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(CONFIG_PATH)

    stats_path = Path("stats") if local else Path(os.path.expandvars(cfg["paths"]["stats_path"]))
    saves_path = Path("saves") if local else Path(os.path.expandvars(cfg["paths"]["saves_path"]))
    emu_schema_path = Path(os.path.expandvars(cfg["paths"]["emu_schema_path"]))

    return {
        "stats_path": check_path(stats_path, "stats_path"),
        "saves_path": check_path(saves_path, "saves_path"),
        "emu_schema_path": check_path(emu_schema_path, "emu_schema_path"),
        "userid": int(cfg["user"]["userid"]),
    }
