import configparser
import os
from pathlib import Path

from utils import console

CONFIG_PATH = Path("config.ini")


def load_config():
    if not CONFIG_PATH.exists():
        console.print(f"[yellow]Config file not found: {CONFIG_PATH}[/yellow]")
        console.print("[yellow]Creating default config.ini — please fill in the values and rerun.[/yellow]")
        default = configparser.ConfigParser()
        default["paths"] = {
            "steam_path": r"C:\Program Files (x86)\Steam\appcache\stats",
            "emu_path": r"%APPDATA%\GSE Saves",
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

    return {
        "steam_path": Path(os.path.expandvars(cfg["paths"]["steam_path"])),
        "emu_path": Path(os.path.expandvars(cfg["paths"]["emu_path"])),
        "emu_schema_path": Path(os.path.expandvars(cfg["paths"]["emu_schema_path"])),
        "userid": int(cfg["user"]["userid"]),
    }
