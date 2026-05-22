import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.status import Status
from rich.table import Table

from utils import read_json, write_json, write_bin, load_steam_stats
from bin_to_json import extract_achievements
from json_to_bin import merge_achievements, apply_achievements
from config import load_config

console = Console()


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
        console.print("\n[dim]No new achievements to sync (everything is up to date).[/dim]")
        return False

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
    return True

def backup_file(path: Path):
    if not path.exists():
        return

    timestamp = datetime.now().strftime("%H-%M-%S_%m-%d-%Y")
    backup = path.with_suffix(f"{path.suffix}.{timestamp}.bak")

    path.replace(backup)


def ensure_steam_closed():
    if os.name != "nt":
        return

    result = subprocess.run(["taskkill", "/f", "/im", "steam.exe", "/t"], capture_output=True, text=True)

    if result.returncode == 0:
        console.print("[yellow]Steam was running. Closed Steam to avoid file conflicts...[/yellow]")
    else:
        console.print("[green]✓[/green] Steam is not running (or already closed).")


if __name__ == "__main__":
    ensure_steam_closed()

    console.rule("[bold cyan]Steam ↔ Emu Achievement Sync[/bold cyan]")

    try:
        cfg = load_config()
    except SystemExit:
        raise

    userid = cfg["userid"]
    steam_path = Path(cfg["steam_path"])
    emu_path = Path(cfg["emu_path"])
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
        # --- 1. SETUP PATHS ---
        emu_ach_path = emu_path / appid / "achievements.json"
        emu_schema_path = Path(cfg["emu_schema_path"]) / appid

        steam_bin_path = steam_path / f"UserGameStats_{userid}_{appid}.bin"
        steam_schema = steam_path / f"UserGameStatsSchema_{appid}.bin"

        # --- 2. DATA LOADING & PROCESSING ---
        with Status(f"[cyan]Processing AppID {appid}...[/cyan]", console=console):
            schema, data, is_fallback = load_steam_stats(steam_path, userid, appid, emu_schema_path)
            steam_ach = extract_achievements(schema, data)

            try:
                emu_ach = read_json(emu_ach_path)
                merged = merge_achievements(base=steam_ach, patch=emu_ach, schema=schema)
            except FileNotFoundError:
                emu_ach = None
                merged = steam_ach

            steam_bin = apply_achievements(merged, schema, data)
        
        has_changes = False

        console.print(f"[green]✓[/green] Steam data loaded ({len(steam_ach)} achievements found)")
        if is_fallback:
            console.print("[yellow]⚠[/yellow] Local Steam data missing. Generating fresh Steam .bin using your emulator history")
        elif emu_ach is not None:
            console.print(f"[green]✓[/green] Emu achievements merged from [dim]{emu_ach_path}[/dim]")
            changes = diff_achievements(steam_ach, merged)
            has_changes = print_diff_table(changes)
        else:
            console.print("[yellow]⚠[/yellow] No emu data found - building `achievements.json` file from Steam data")
        
        # --- 3. BACKUPS & FILE WRITING ---
        with Status("[cyan]Securing backups and writing files...[/cyan]", console=console):
            if not is_fallback and emu_ach is not None and has_changes:
                backup_file(steam_bin_path)
                backup_file(emu_ach_path)
            elif is_fallback:
                if steam_schema.exists():
                    backup_file(steam_schema)
                shutil.copyfile(emu_schema_path / f"UserGameStatsSchema_{appid}.bin", steam_schema)

            steam_bin_path.parent.mkdir(parents=True, exist_ok=True)
            write_bin(steam_bin_path, steam_bin)

            emu_ach_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(emu_ach_path, merged)

        console.print(f"[green]✓[/green] Bin updated: [dim]{steam_bin_path}[/dim]")
        console.print(f"[green]✓[/green] Emu json updated: [dim]{emu_ach_path}[/dim]")

        earned_total = sum(1 for a in merged.values() if a.get("earned"))
        console.print(f"\n[bold]Final Count:[/bold] {earned_total}/{len(merged)} unlocked")
        console.rule("[dim]Done[/dim]")
