import os
import subprocess
import configparser
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.status import Status
from rich.table import Table

from utils import read_json, write_json, write_bin, load_steam_stats
from bin_to_json import extract_achievements
from json_to_bin import merge_achievements, apply_achievements

CONFIG_PATH = Path("config.ini")
console = Console()


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


def diff_achievements(steam, merged):
    """Return list of (name, old, new) for achievements that changed state."""
    changes = []
    for name, new in merged.items():
        old = steam.get(name, {})
        earned_changed = old.get("earned") != new.get("earned")
        progress_changed = old.get("progress") != new.get("progress")
        if earned_changed or progress_changed:
            changes.append((name, old, new))
    return changes


def print_diff_table(changes):
    if not changes:
        console.print("\n[dim]No achievement changes.[/dim]")
        return

    table = Table(title="Achievement Changes", header_style="bold cyan")
    table.add_column("Achievement", style="bold")
    table.add_column("Earned", justify="center")
    table.add_column("Progress", justify="right")

    for name, old, new in sorted(changes):
        earned_old = old.get("earned", False)
        earned_new = new.get("earned", False)
        prog_old = old.get("progress", 0)
        prog_new = new.get("progress", 0)
        max_prog = new.get("max_progress")

        if earned_old != earned_new:
            earned_str = "[red]✗[/red] → [green]✓[/green]" if earned_new else "[green]✓[/green] → [red]✗[/red]"
        else:
            earned_str = "[green]✓[/green]" if earned_new else "[red]✗[/red]"

        if max_prog is not None:
            progress_str = f"{prog_old}/{max_prog} → [cyan]{prog_new}/{max_prog}[/cyan]"
        else:
            progress_str = ""

        table.add_row(name, earned_str, progress_str)

    console.print()
    console.print(table)


def backup_file(path: Path):
    if not path.exists():
        return

    timestamp = datetime.now().strftime("%H-%M-%S_%m-%d-%Y")
    backup = path.with_suffix(f"{path.suffix}.{timestamp}.bak")

    path.replace(backup)


def steam_is_running():
    if os.name != "nt":
        return False

    result = subprocess.run(
        ["tasklist", "/fi", "imagename eq steam.exe", "/nh"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout.strip()
    return bool(output and "steam.exe" in output.lower())


def close_steam():
    if os.name != "nt":
        return

    subprocess.run(
        ["taskkill", "/f", "/im", "steam.exe", "/t"],
        capture_output=True,
        text=True,
        check=False,
    )


def ensure_steam_closed():
    if steam_is_running():
        console.print("[yellow]Steam is running. Closing Steam to avoid file conflicts...[/yellow]")
        close_steam()
        console.print("[green]✓[/green] Steam close command issued")


if __name__ == "__main__":
    ensure_steam_closed()

    console.rule("[bold cyan]Steam ↔ Emu Achievement Sync[/bold cyan]")

    try:
        cfg = load_config()
    except SystemExit:
        raise

    userid = cfg["userid"]
    steam_path = cfg["steam_path"]
    emu_path = cfg["emu_path"]

    appids = []

    if mode := console.input("[bold]Select mode:[/bold] [blue]Auto-detect AppIDs from (S)team folder, (E)mu folder, or Single (A)ppID?[/blue] ").strip().lower():
        if mode == "s":
            appids = [str(d.name).split(".")[0].split("_")[1] for d in steam_path.iterdir() if d.is_file() and d.name.startswith("UserGameStatsSchema_") and d.name.endswith(".bin")]
            console.print(f"[green]✓[/green] Auto-detected {len(appids)} AppIDs from Steam folder")
        elif mode == "e":
            appids = [d.name for d in emu_path.iterdir() if d.is_dir()]
            console.print(f"[green]✓[/green] Auto-detected {len(appids)} AppIDs from Emu folder")
        elif mode == "a":
            appids.append(console.input("[bold]AppID:[/bold] ").strip())

    for appid in appids:
        try:
            emu_schema_path = Path(cfg["emu_schema_path"]) / appid
            with Status("[cyan]Loading schema and data...[/cyan]", console=console):
                schema, data = load_steam_stats(steam_path, userid, appid, emu_schema_path)
            console.print("[green]✓[/green] Schema and data loaded")

            with Status("[cyan]Extracting Steam achievements...[/cyan]", console=console):
                steam_ach = extract_achievements(schema, data)
                # write_json("achievements.json", steam_ach)
            console.print(f"[green]✓[/green] Steam achievements extracted ({len(steam_ach)} total)")

            emu_ach_path = emu_path / appid / "achievements.json"
            try:
                with Status("[cyan]Loading emu achievements...[/cyan]", console=console):
                    emu_ach = read_json(emu_ach_path)
                console.print(f"[green]✓[/green] Emu achievements loaded from [dim]{emu_ach_path}[/dim]")
            except FileNotFoundError:
                console.print("[yellow]⚠[/yellow] No emu achievements found — starting from Steam data")
                emu_ach = {}

            with Status("[cyan]Merging achievements...[/cyan]", console=console):
                merged = merge_achievements(base=steam_ach, patch=emu_ach, schema=schema)
                # write_json("merged_achievements.json", merged)
            console.print("[green]✓[/green] Achievements merged")

            steam_bin_path = steam_path / f"UserGameStats_{userid}_{appid}.bin"
            with Status("[cyan]Writing files...[/cyan]", console=console):
                backup_file(emu_ach_path)
                backup_file(steam_bin_path)

                steam_bin = apply_achievements(merged, schema, data)
                write_bin(steam_bin_path, steam_bin)

                emu_ach_path.parent.mkdir(parents=True, exist_ok=True)
                write_json(emu_ach_path, merged)

            console.print(f"[green]✓[/green] Bin written to [dim]{steam_bin_path}[/dim]")
            console.print(f"[green]✓[/green] Emu achievements written to [dim]{emu_ach_path}[/dim]")

        except Exception as e:
            console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")
            raise

        changes = diff_achievements(steam_ach, merged)
        print_diff_table(changes)

        earned_total = sum(1 for a in merged.values() if a.get("earned"))
        console.print(f"\n[bold]Earned:[/bold] {earned_total}/{len(merged)}")
        console.rule("[dim]Done[/dim]")
