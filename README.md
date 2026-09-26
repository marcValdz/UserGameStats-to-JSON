# UserGameStats-to-JSON

Syncs achievements both ways between Steam's local stats cache (`Steam\appcache\stats`) and Goldberg / GSE emulator saves (`achievements.json`).

## How it works

For each AppID the tool:

1. Reads the Steam schema `UserGameStatsSchema_<appid>.bin` and your stats `UserGameStats_<userid>_<appid>.bin` from the Steam stats folder. If Steam has no schema for the app, it uses `<emu_schema_path>/<appid>/UserGameStatsSchema_<appid>.bin` instead and copies it into the Steam folder.
2. Reads the emulator save `<saves_path>/<appid>/achievements.json`, if there is one.
3. Merges both sides:
   - An achievement earned on either side is earned. Merging never removes an unlock.
   - The unlock time is the earliest one either side recorded.
   - Achievements driven by a stat share that stat: earning a higher tier earns the lower ones, and progress is the highest either side reached.
4. Writes the result back to both sides:
   - Steam stats are only ever raised, never lowered. Stats and groups that don't change are left exactly as they were.
   - A file whose content wouldn't change is not written. A file that does change is backed up first (see [Backups](#backups)).

Steam treats the stats folder as a local cache and may replace it with the values from its servers. Achievements show in the Steam client until then; run the sync again to restore them. Steam must be closed while the files are written, because it saves its in-memory cache when it exits.

## Requirements

- Python 3.11+

```bash
python -m pip install -r requirements.txt
```

## Setup

Run the tool once from the project folder. It creates `config.ini` and exits; fill it in and run it again.

```ini
[paths]
stats_path = C:\Program Files (x86)\Steam\appcache\stats
saves_path = %APPDATA%\GSE Saves
emu_schema_path = C:\path\to\generate_emu_config\backup

[user]
userid = 000000000
```

| Key | Meaning |
|---|---|
| `stats_path` | Steam's stats cache folder. Must exist. |
| `saves_path` | Emulator saves folder, containing one folder per AppID. Must exist. |
| `emu_schema_path` | Optional. Folder with `<appid>/UserGameStatsSchema_<appid>.bin` files (e.g. from generate_emu_config), used only for apps Steam has no schema for. |
| `userid` | Your Steam32 account ID, the number in `UserGameStats_<userid>_<appid>.bin`. The tool refuses to run with the template's `0`, and warns if `stats_path` has no files for this ID. |

Environment variables such as `%APPDATA%` are expanded. Don't put comments on the same line as a value; `configparser` would read them as part of the value.

## Usage

Run from the project folder (`config.ini` and `session.log` live there).

```bash
python main.py <appid> [<appid> ...]
python main.py --from stats
python main.py --from saves
python main.py --local <appid>
```

| Argument | Effect |
|---|---|
| `<appid> ...` | Sync these AppIDs. |
| `--from stats` | Sync every app with a `UserGameStatsSchema_<appid>.bin` in `stats_path`. |
| `--from saves` | Sync every numeric folder in `saves_path`. |
| `--local` | Use the `stats/` and `saves/` folders in the project folder instead of the configured paths, e.g. to try a sync on copies. Steam is not closed. |

- On Windows, Steam is force-closed right before syncing, once the arguments and `config.ini` have been checked. `--help` and invalid arguments never close it.
- Each AppID is synced on its own. If one fails (for example, no schema anywhere), the error is shown and the others still sync.
- For each app the tool prints what changes on each side (`Steam ← Emu`, `Emu ← Steam`), listed by the achievements' display names and including unlock times moved to an earlier date, and the final unlock count.
- The console output of every run is saved to `session.log`, replacing the previous one.

### Backups

Before a file is replaced, a copy is saved next to it as `<file>.<HH-MM-SS_MM-DD-YYYY>.bak`, e.g. `achievements.json.14-03-34_06-02-2026.bak`. Files that don't change get no backup, so re-running a sync that's already done creates nothing.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Every AppID synced. |
| `1` | `config.ini` was just created, a configured path doesn't exist, or at least one AppID failed (listed at the end). |
| `2` | Invalid arguments. |

## Standalone scripts

These work on files in the current folder and never touch Steam's folder or the emulator saves.

| Script | What it does |
|---|---|
| `parse_bin.py` | Asks for a `.bin` path and dumps it as JSON: `schema.json` for a `UserGameStatsSchema_*.bin`, otherwise `data.json`. |
| `bin_to_json.py` | Asks for an AppID and writes that app's Steam achievements to `achievements.json`. |
| `json_to_bin.py` | Asks for an AppID, merges `achievements.json` (from `bin_to_json.py`) with the emulator save, and writes `merged_achievements.json` and `UserGameStats_<userid>_<appid>.bin`. |

## Project files

| File | Purpose |
|---|---|
| `main.py` | The sync workflow and command line. |
| `bin_to_json.py` | Reads Steam achievement state from the `.bin` files. |
| `json_to_bin.py` | Merges both sides and applies the result to the Steam data. |
| `parse_bin.py` | Dumps a single `.bin` file as JSON. |
| `config.py` | Creates and loads `config.ini`. |
| `utils.py` | Shared helpers: JSON and binary VDF I/O, schema parsing. |
| `tests/` | The test suite. |

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
ruff check .
ruff format --check .
```

- Tests describe the expected behavior. They run in temporary folders, never touch real Steam or emulator files, and never close Steam.
- `ruff` handles linting and formatting (config in `pyproject.toml`).
- Files use LF line endings (enforced by `.gitattributes`).
