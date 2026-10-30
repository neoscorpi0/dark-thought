# CSVFlow — Smart CSV Processor

A self-contained CLI tool for filtering, transforming, merging, and analyzing CSV and JSON data files. Zero external dependencies — just Python 3.

## Quick Start

```bash
# See what's in a file
python3 csvflow.py info sales.csv

# Filter rows
python3 csvflow.py filter sales.csv --where "region=North" --where "amount>1000" -o filtered.csv

# Select and rename columns
python3 csvflow.py select data.csv --columns "name,email" --rename "name:Full Name" -o selected.csv

# Sort
python3 csvflow.py sort data.csv --by "date:desc" --by "amount:asc" -o sorted.csv

# Remove duplicates
python3 csvflow.py dedupe data.csv --on "email" -o unique.csv

# Merge files
python3 csvflow.py merge file1.csv file2.csv file3.csv -o combined.csv

# Transform columns
python3 csvflow.py transform data.csv --op "name:upper" --op "price:float" --op "notes:fill:N/A" -o clean.csv

# Export to JSON
python3 csvflow.py export data.csv -o data.json --format json

# Clean messy CSVs (BOM, whitespace, empty lines)
python3 csvflow.py clean messy.csv -o clean.csv

# Summary statistics
python3 csvflow.py stats sales.csv
```

## Commands

| Command | Description | Example |
|---------|-------------|---------|
| `info` | File structure, row count, column types, null counts | `csvflow.py info data.csv` |
| `filter` | Keep rows matching conditions | `csvflow.py filter data.csv --where "age>25"` |
| `select` | Choose/rename columns | `csvflow.py select data.csv --columns "a,b,c"` |
| `sort` | Sort by column(s) | `csvflow.py sort data.csv --by "name:asc"` |
| `dedupe` | Remove duplicate rows | `csvflow.py dedupe data.csv --on "id"` |
| `merge` | Combine multiple files | `csvflow.py merge a.csv b.csv -o out.csv` |
| `transform` | Apply column operations | `csvflow.py transform data.csv --op "name:upper"` |
| `export` | Convert CSV ↔ JSON | `csvflow.py export data.csv -o data.json` |
| `clean` | Auto-fix encoding, BOM, whitespace | `csvflow.py clean messy.csv -o clean.csv` |
| `stats` | Numeric summary statistics | `csvflow.py stats data.csv` |

## Filter Conditions

```bash
--where "column=value"      # Exact match
--where "column>100"        # Greater than
--where "column<50"         # Less than
--where "column>=100"       # Greater or equal
--where "column<=50"        # Less or equal
--where "column!=value"     # Not equal
--where "column~regex"      # Regex match
```

Multiple conditions are ANDed together.

## Transform Operations

```bash
--op "column:upper"         # Uppercase
--op "column:lower"         # Lowercase
--op "column:strip"         # Trim whitespace
--op "column:title"         # Title Case
--op "column:int"           # Convert to integer
--op "column:float"         # Convert to float
--op "column:fill:value"    # Fill empty cells
--op "column:prefix:text"   # Add prefix
--op "column:suffix:text"   # Add suffix
--op "column:regex:pat:rep" # Regex replace
```

## Features

- **Auto-detection**: Encoding and delimiter detected automatically
- **Zero dependencies**: Pure Python 3 standard library
- **Cross-platform**: Works on Windows, macOS, Linux
- **Large files**: Handles files up to available memory
- **Clean output**: Proper quoting, UTF-8 encoding

## Requirements

- Python 3.6 or later
- No external packages needed

## License

MIT License — use it however you like.

## Author

Built by Deep Thought (42).
