import configparser
import os
from pathlib import Path

from utils import console

CONFIG_PATH = Path("config.ini")


def _steam_install_path():
    """Steam's install folder from the registry, or None."""
    try:
        import winreg
    except ImportError:  # not Windows
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        return None


def find_steam_stats():
    steam = _steam_install_path()
    stats = steam / "appcache" / "stats" if steam else None
    return stats if stats and stats.is_dir() else None


def find_gse_saves():
    appdata = os.environ.get("APPDATA")
    saves = Path(appdata) / "GSE Saves" if appdata else None
    return saves if saves and saves.is_dir() else None


def check_path(path: Path, name: str) -> Path:
    if not path.exists():
        console.print(f"[red]Invalid config:[/red] '{name}' does not exist")
        console.print(f"[dim]{path}[/dim]")
        raise SystemExit(1)

    return path


def resolve_path(value: str, name: str, detect, where: str) -> Path:
    """A path set in config.ini is used as-is; an empty or missing one is detected."""
    if value:
        return check_path(Path(os.path.expandvars(value)), name)

    detected = detect()
    if detected is None:
        console.print(f"[red]Invalid config:[/red] '{name}' is empty and {where} was not found. Set it in {CONFIG_PATH}.")
        raise SystemExit(1)
    console.print(f"[green]✓[/green] Detected {name}: [dim]{detected}[/dim]")
    return detected


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

        # Empty paths are detected: Steam from the registry, GSE Saves from %APPDATA%
        default["paths"] = {
            "stats_path": "",
            "saves_path": "",
            "emu_schema_path": "",
        }

        default["user"] = {
            "userid": "0",
        }

        with open(CONFIG_PATH, "w") as f:
            default.write(f)

        console.print(f"[yellow]Created {CONFIG_PATH}.[/yellow] Set userid to your Steam32 ID, then run again. Leave the paths empty to detect Steam and GSE Saves.")
        raise SystemExit(1)

    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(CONFIG_PATH)

    def setting(section, key, default=""):
        return cfg.get(section, key, fallback=default).strip()

    if local:
        stats_path = check_path(Path("stats"), "stats_path")
        saves_path = check_path(Path("saves"), "saves_path")
    else:
        stats_path = resolve_path(setting("paths", "stats_path"), "stats_path", find_steam_stats, "Steam's appcache/stats folder")
        saves_path = resolve_path(setting("paths", "saves_path"), "saves_path", find_gse_saves, r"%APPDATA%\GSE Saves")
    emu_schema_path = setting("paths", "emu_schema_path")

    config = {
        "stats_path": stats_path,
        "saves_path": saves_path,
        # Only a fallback for apps Steam has no schema for, so it may be unset or not exist
        "emu_schema_path": Path(os.path.expandvars(emu_schema_path)) if emu_schema_path else None,
        "userid": check_userid(setting("user", "userid", "0")),
    }

    if not any(config["stats_path"].glob(f"UserGameStats_{config['userid']}_*.bin")):
        console.print(f"[yellow]Warning:[/yellow] no UserGameStats_{config['userid']}_*.bin in stats_path; check that userid is your Steam32 ID")

    return config
