# TextForge v1.0.0

Smart text and regex processor. Zero external dependencies. Python 3.6+.

## Commands

| Command | What it does |
|---------|-------------|
| `find` | Search files for regex patterns with context lines |
| `replace` | Find and replace with regex, capture groups, dry-run, backup |
| `extract` | Pull patterns out as CSV, JSON, list, or table |
| `count` | Count occurrences across files, per-file breakdown |
| `split` | Split a file by delimiter, regex, or blank lines |
| `join` | Join multiple files into one |
| `stats` | Word/line/char counts, readability stats, top words |
| `summary` | Quick file overview |

## Usage

```bash
# Search for TODOs with 2 lines of context
python3 textforge.py find "TODO|FIXME" src/ --context 2

# Dry-run replace to preview changes
python3 textforge.py replace "old_api" "new_api" *.py --dry-run

# Extract all URLs from log files into CSV
python3 textforge.py extract "https?://\S+" logs/ --format csv

# Count errors, warnings, and fatals per file
python3 textforge.py count "error" "warn" "fatal" logs/ --per-file

# Text statistics with top 10 words
python3 textforge.py stats README.md --top 10

# Split a file by delimiter
python3 textforge.py split data.txt --delimiter='---' --skip-empty

# Join files back together
python3 textforge.py join part_*.txt -o combined.txt -s=$'\n---\n'
```

## Install

No install needed. Copy `textforge.py` anywhere and run:

```bash
python3 /path/to/textforge.py find "pattern" files/
```

Or add to your PATH:

```bash
chmod +x textforge.py
sudo ln -s $(pwd)/textforge.py /usr/local/bin/textforge
```

## Requirements

- Python 3.6+ (uses only stdlib: `re`, `csv`, `json`, `argparse`, `pathlib`, `collections`)
- Zero external dependencies

## License

MIT
