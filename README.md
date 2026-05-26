# UserGameStats-to-JSON

A simple utility for synchronizing Steam achievement data with emulator achievement files.

The project reads Steam `UserGameStats` data, converts achievements to JSON, merges emulator progress, and writes updated Steam `.bin` and emulator JSON files.

## Features

- Extract Steam achievement state from `UserGameStats` binaries
- Merge Steam achievements with emulator achievement progress
- Preserve stat-based achievement consistency during merges
- Create backups for existing `.bin` and emulator achievement files
- Export intermediate JSON files for inspection

## Requirements

- Python 3.11+ (recommended)
- `vdf`
- `rich`
- `ruff` (optional for linting)

Install dependencies from `requirements.txt`:

```bash
python -m pip install -r requirements.txt
```

## Setup

1. Copy or generate `config.ini`.
2. Set the Steam stats path, emulator save path, emulator schema backup path, and Steam user ID.

Example `config.ini`:

```ini
[paths]
steam_path = C:\Program Files (x86)\Steam\appcache\stats
emu_path = %APPDATA%\GSE Saves
emu_schema_path = C:\path\to\generate_emu_config\backup

[user]
userid = 000000000 # Steam32 ID
```

If `config.ini` is missing, `main.py` will create a default file and prompt you to fill it in.

## Usage

Run the main sync tool from the project root. You can pass one or more AppIDs directly, or auto-detect them from your Steam or emulator folders.

```bash
python main.py 2215200
python main.py 2215200 1091500
python main.py --from stats
python main.py --from saves
python main.py --local 2215200
```

### CLI arguments

- `AppID` — one or more explicit Steam AppIDs to process.
- `--from stats` — auto-detect AppIDs from Steam `UserGameStatsSchema_*.bin` files.
- `--from saves` — auto-detect AppIDs from emulator save subfolders.
- `--local` — load from local `/stats` and `/saves` paths.

### Output files

- `achievements.json` — extracted Steam achievement data
- `merged_achievements.json` — merged achievement state
- `bits.json` — internal debug mapping of achievement bit indices
- `data.json` — parsed UserGameStats_{appid}.bin
- `schema.json` — parsed UserGameStatsSchema_{userid}_{appid}.bin
- Steam `UserGameStats_<userid>_<appid>.bin` — updated binary written back to Steam stats path
- emulator `achievements.json` — updated emulator achievement JSON

## Project Files

- `main.py` — primary sync workflow
- `bin_to_json.py` — Steam binary to JSON extraction
- `json_to_bin.py` — merge and apply achievement updates
- `parse_bin.py` — inspect a single Steam `UserGameStats` `.bin` file and export JSON
- `utils.py` — shared helpers for JSON/binary I/O and Steam schema parsing
- `requirements.txt` — Python dependencies

## Notes

- Always close Steam before modifying Steam binary files.
- Backups are created automatically for existing Steam and emulator files.
- If Steam is running, the tool detects it and forces Steam to close before updating files.
- This tool is designed for managing achievement sync between Steam game stats and compatible emulator achievement storage.
