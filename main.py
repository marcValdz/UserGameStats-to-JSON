import argparse
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

from rich.status import Status
from rich.table import Table

from utils import console, read_json, write_json, write_bin, load_steam_stats
from bin_to_json import extract_achievements
from json_to_bin import merge_achievements, apply_achievements
from config import load_config


def diff_achievements(steam, merged_ach):
    """Return list of (name, old, new) for achievements that changed state."""
    changes = []
    for name, new in merged_ach.items():
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


def get_appids(source, stats_path, saves_path):
    if source == "stats":
        appids = [f.name.split(".")[0].split("_")[1] for f in stats_path.iterdir() if (f.is_file() and f.name.startswith("UserGameStatsSchema_") and f.suffix == ".bin")]
        console.print(f"[green]✓[/green] Auto-detected {len(appids)} AppIDs from Steam folder")
        return appids
    elif source == "saves":
        appids = [d.name for d in saves_path.iterdir() if d.is_dir()]
        console.print(f"[green]✓[/green] Auto-detected {len(appids)} AppIDs from Emu folder")
        return appids
    return []


if __name__ == "__main__":
    ensure_steam_closed()

    parser = argparse.ArgumentParser()
    parser.add_argument("appids", nargs="*", help="Explicit AppIDs")
    parser.add_argument("--from", dest="source", choices=["stats", "saves"], help="Auto-detect AppIDs")
    parser.add_argument("--local", action="store_true", help="Use default_* paths from config")
    args = parser.parse_args()

    console.rule("[bold cyan]Steam ↔ Emu Achievement Sync[/bold cyan]")

    cfg = load_config(local=args.local)

    userid = cfg["userid"]
    stats_path = cfg["stats_path"]
    saves_path = cfg["saves_path"]

    if args.appids:
        appids = args.appids
    elif args.source:
        appids = get_appids(args.source, stats_path, saves_path)
    else:
        parser.error("Provide AppIDs or use --from stats|saves")

    for appid in appids:
        # --- 1. SETUP PATHS ---
        emu_ach_path = saves_path / appid / "achievements.json"
        emu_schema_path = cfg["emu_schema_path"] / appid

        steam_bin_path = stats_path / f"UserGameStats_{userid}_{appid}.bin"
        steam_schema_path = stats_path / f"UserGameStatsSchema_{appid}.bin"

        # --- 2. DATA LOADING & PROCESSING ---
        with Status(f"[cyan]Processing AppID {appid}...[/cyan]", console=console):
            schema, data, is_fallback = load_steam_stats(stats_path, userid, appid, emu_schema_path)
            steam_ach = extract_achievements(schema, data)

            try:
                emu_ach = read_json(emu_ach_path)
                merged_ach = merge_achievements(base=steam_ach, patch=emu_ach, schema=schema)
            except FileNotFoundError:
                emu_ach = None
                merged_ach = steam_ach

            steam_bin = apply_achievements(merged_ach, schema, data)

        has_changes = False

        console.print(f"[green]✓[/green] Steam data loaded ({len(steam_ach)} achievements found)")
        if is_fallback:
            console.print("[yellow]⚠[/yellow] Local Steam data missing. Generating fresh Steam .bin using your emulator history")
        elif emu_ach is not None:
            console.print(f"[green]✓[/green] Emu achievements merged from [dim]{emu_ach_path}[/dim]")
            changes = diff_achievements(steam_ach, merged_ach)
            has_changes = print_diff_table(changes)
        else:
            console.print("[yellow]⚠[/yellow] No emu data found - building `achievements.json` file from Steam data")

        # --- 3. BACKUPS & FILE WRITING ---
        with Status("[cyan]Securing backups and writing files...[/cyan]", console=console):
            if not is_fallback and emu_ach is not None and has_changes:
                backup_file(steam_bin_path)
                backup_file(emu_ach_path)
            elif is_fallback:
                if steam_schema_path.exists():
                    backup_file(steam_schema_path)
                steam_schema_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(emu_schema_path / f"UserGameStatsSchema_{appid}.bin", steam_schema_path)

            steam_bin_path.parent.mkdir(parents=True, exist_ok=True)
            write_bin(steam_bin_path, steam_bin)

            emu_ach_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(emu_ach_path, merged_ach)

        console.print(f"[green]✓[/green] Bin updated: [dim]{steam_bin_path}[/dim]")
        console.print(f"[green]✓[/green] Emu json updated: [dim]{emu_ach_path}[/dim]")

        earned_total = sum(1 for a in merged_ach.values() if a.get("earned"))
        console.print(f"\n[bold]Final Count:[/bold] {earned_total}/{len(merged_ach)} unlocked")
        console.rule("[dim]Done[/dim]")
    console.save_text("session.log")
