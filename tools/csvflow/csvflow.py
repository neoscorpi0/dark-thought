#!/usr/bin/env python3
"""
CSVFlow — Smart CSV Processor
Version 1.0.0

A self-contained CLI tool for filtering, transforming, merging, and analyzing
CSV and JSON data files. Zero external dependencies.

Usage:
    python3 csvflow.py <command> [options]

Commands:
    info        Show file structure, row count, column types, null counts
    filter      Keep rows matching conditions
    select      Choose/rename columns
    sort        Sort by column(s)
    dedupe      Remove duplicate rows
    merge       Combine multiple CSV files
    transform   Apply column operations (upper, lower, strip, fill, etc.)
    export      Convert between CSV and JSON
    clean       Auto-clean common CSV issues (encoding, blanks, BOM)
    stats       Summary statistics for numeric columns

Examples:
    python3 csvflow.py info sales.csv
    python3 csvflow.py filter sales.csv --where "region=North" --where "amount>1000"
    python3 csvflow.py select data.csv --columns "name,email" --rename "Name:Full Name"
    python3 csvflow.py sort data.csv --by "date:desc"
    python3 csvflow.py dedupe data.csv --on "email"
    python3 csvflow.py merge file1.csv file2.csv -o combined.csv
    python3 csvflow.py transform data.csv --op "price:float" --op "name:upper"
    python3 csvflow.py export data.csv -o data.json --format json
    python3 csvflow.py clean messy.csv -o clean.csv
    python3 csvflow.py stats sales.csv

Author: Deep Thought (42)
License: MIT
"""

import csv
import json
import sys
import os
import re
import io
import codecs
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

__version__ = "1.0.0"
__author__ = "Deep Thought (42)"


class CSVFlowError(Exception):
    """Base exception for CSVFlow."""
    pass


class FileReadError(CSVFlowError):
    """Could not read the input file."""
    pass


class ValidationError(CSVFlowError):
    """Invalid arguments or data."""
    pass


def detect_encoding(filepath: str) -> str:
    """Detect file encoding by trying common encodings."""
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                f.read(4096)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return 'utf-8'


def detect_delimiter(filepath: str, encoding: str) -> str:
    """Detect CSV delimiter by analyzing first few lines."""
    with open(filepath, 'r', encoding=encoding) as f:
        sample = f.read(8192)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        return dialect.delimiter
    except csv.Error:
        return ','


def read_csv(filepath: str, encoding: str = None, delimiter: str = None) -> Tuple[List[str], List[List[str]]]:
    """Read a CSV file, auto-detecting encoding and delimiter. Returns (headers, rows)."""
    if not os.path.exists(filepath):
        raise FileReadError(f"File not found: {filepath}")

    if encoding is None:
        encoding = detect_encoding(filepath)
    if delimiter is None:
        delimiter = detect_delimiter(filepath, encoding)

    with open(filepath, 'r', encoding=encoding, newline='') as f:
        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)

    if not rows:
        raise FileReadError(f"File is empty: {filepath}")

    headers = rows[0]
    data = rows[1:]
    return headers, data


def write_csv(headers: List[str], data: List[List[str]], filepath: str):
    """Write data to CSV file."""
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(data)


def write_json(headers: List[str], data: List[List[str]], filepath: str):
    """Write data to JSON file."""
    records = []
    for row in data:
        record = {}
        for i, h in enumerate(headers):
            record[h] = row[i] if i < len(row) else ""
        records.append(record)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def detect_column_type(values: List[str]) -> str:
    """Detect the likely type of a column based on its values."""
    non_empty = [v for v in values if v.strip()]
    if not non_empty:
        return "empty"

    # Check int
    try:
        for v in non_empty:
            int(v.replace(',', ''))
        return "integer"
    except ValueError:
        pass

    # Check float
    try:
        for v in non_empty:
            float(v.replace(',', ''))
        return "float"
    except ValueError:
        pass

    # Check date
    date_patterns = [
        r'\d{4}-\d{2}-\d{2}',
        r'\d{2}/\d{2}/\d{4}',
        r'\d{2}-\d{2}-\d{4}',
    ]
    for pat in date_patterns:
        if all(re.match(pat, v.strip()) for v in non_empty[:10]):
            return "date"

    # Check boolean
    bool_vals = {'true', 'false', 'yes', 'no', '1', '0', 't', 'f', 'y', 'n'}
    if all(v.strip().lower() in bool_vals for v in non_empty):
        return "boolean"

    return "text"


def parse_condition(condition: str) -> Tuple[str, str, str]:
    """Parse a condition like 'column=value' or 'column>100' into (column, op, value)."""
    ops = ['>=', '<=', '!=', '~', '>', '<', '=']
    for op in ops:
        if op in condition:
            parts = condition.split(op, 1)
            if len(parts) == 2:
                return parts[0].strip(), op, parts[1].strip()
    raise ValidationError(f"Invalid condition: {condition}. Use format: column=value, column>100, column~regex")


def match_condition(value: str, op: str, expected: str) -> bool:
    """Test if a value matches a condition."""
    if op == '=':
        return value.strip().lower() == expected.lower()
    elif op == '!=':
        return value.strip().lower() != expected.lower()
    elif op == '~':
        return bool(re.search(expected, value, re.IGNORECASE))
    elif op in ('>', '<', '>=', '<='):
        try:
            v = float(value.replace(',', ''))
            e = float(expected.replace(',', ''))
            if op == '>':
                return v > e
            elif op == '<':
                return v < e
            elif op == '>=':
                return v >= e
            elif op == '<=':
                return v <= e
        except ValueError:
            return False
    return False


# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_info(args):
    """Show file structure, row count, column types, null counts."""
    if not args:
        raise ValidationError("Usage: csvflow.py info <file.csv>")

    filepath = args[0]
    headers, data = read_csv(filepath)

    print(f"\n{'='*60}")
    print(f"  CSVFlow Info: {os.path.basename(filepath)}")
    print(f"{'='*60}")
    print(f"  Rows:    {len(data):,}")
    print(f"  Columns: {len(headers)}")
    print(f"  File:    {os.path.getsize(filepath):,} bytes")
    print()

    # Column analysis
    col_data = defaultdict(list)
    for row in data:
        for i, h in enumerate(headers):
            val = row[i] if i < len(row) else ""
            col_data[h].append(val)

    print(f"  {'Column':<20} {'Type':<10} {'Non-Null':<10} {'Nulls':<10} {'Example'}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10} {'-'*20}")

    for h in headers:
        vals = col_data[h]
        non_null = [v for v in vals if v.strip()]
        nulls = len(vals) - len(non_null)
        col_type = detect_column_type(vals)
        example = non_null[0][:20] if non_null else "(empty)"
        print(f"  {h:<20} {col_type:<10} {len(non_null):<10} {nulls:<10} {example}")

    print()


def cmd_filter(args):
    """Keep rows matching conditions."""
    if len(args) < 2:
        raise ValidationError("Usage: csvflow.py filter <file.csv> --where 'col=val' [--where 'col>100'] [-o output.csv]")

    filepath = args[0]
    conditions = []
    output = None

    i = 1
    while i < len(args):
        if args[i] == '--where' and i + 1 < len(args):
            conditions.append(args[i + 1])
            i += 2
        elif args[i] in ('-o', '--output') and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            i += 1

    if not conditions:
        raise ValidationError("At least one --where condition required")

    headers, data = read_csv(filepath)
    col_idx = {h.lower(): i for i, h in enumerate(headers)}

    filtered = []
    for row in data:
        match = True
        for cond in conditions:
            col_name, op, val = parse_condition(cond)
            idx = col_idx.get(col_name.lower())
            if idx is None:
                match = False
                break
            cell = row[idx] if idx < len(row) else ""
            if not match_condition(cell, op, val):
                match = False
                break
        if match:
            filtered.append(row)

    print(f"Filtered {len(data):,} → {len(filtered):,} rows ({len(conditions)} condition(s))")

    if output:
        write_csv(headers, filtered, output)
        print(f"Written to: {output}")
    else:
        # Print to stdout
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(filtered[:100])
        if len(filtered) > 100:
            print(f"... ({len(filtered) - 100} more rows)")


def cmd_select(args):
    """Choose/rename columns."""
    if len(args) < 2:
        raise ValidationError("Usage: csvflow.py select <file.csv> --columns 'a,b,c' [--rename 'old:new'] [-o output.csv]")

    filepath = args[0]
    columns = None
    renames = []
    output = None

    i = 1
    while i < len(args):
        if args[i] == '--columns' and i + 1 < len(args):
            columns = [c.strip() for c in args[i + 1].split(',')]
            i += 2
        elif args[i] == '--rename' and i + 1 < len(args):
            renames.append(args[i + 1])
            i += 2
        elif args[i] in ('-o', '--output') and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            i += 1

    headers, data = read_csv(filepath)

    if columns:
        col_idx = []
        new_headers = []
        for c in columns:
            found = False
            for i, h in enumerate(headers):
                if h.lower() == c.lower():
                    col_idx.append(i)
                    new_headers.append(c)
                    found = True
                    break
            if not found:
                raise ValidationError(f"Column not found: {c}")

        selected = []
        for row in data:
            selected.append([row[i] if i < len(row) else "" for i in col_idx])
        headers, data = new_headers, selected

    # Apply renames
    for rename in renames:
        if ':' not in rename:
            raise ValidationError(f"Invalid rename format: {rename}. Use old:new")
        old, new = rename.split(':', 1)
        for i, h in enumerate(headers):
            if h.lower() == old.lower():
                headers[i] = new
                break

    print(f"Selected {len(headers)} columns, {len(data):,} rows")

    if output:
        write_csv(headers, data, output)
        print(f"Written to: {output}")
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(data[:50])
        if len(data) > 50:
            print(f"... ({len(data) - 50} more rows)")


def cmd_sort(args):
    """Sort by column(s)."""
    if len(args) < 2:
        raise ValidationError("Usage: csvflow.py sort <file.csv> --by 'col:asc' [--by 'col2:desc'] [-o output.csv]")

    filepath = args[0]
    sort_keys = []
    output = None

    i = 1
    while i < len(args):
        if args[i] == '--by' and i + 1 < len(args):
            parts = args[i + 1].split(':')
            col = parts[0]
            desc = len(parts) > 1 and parts[1].lower() == 'desc'
            sort_keys.append((col, desc))
            i += 2
        elif args[i] in ('-o', '--output') and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            i += 1

    headers, data = read_csv(filepath)
    col_idx = {h.lower(): i for i, h in enumerate(headers)}

    for col, desc in reversed(sort_keys):
        idx = col_idx.get(col.lower())
        if idx is None:
            raise ValidationError(f"Column not found: {col}")

        def sort_key(row):
            val = row[idx] if idx < len(row) else ""
            # Try numeric sort
            try:
                return (0, float(val.replace(',', '')))
            except ValueError:
                return (1, val.lower())

        data.sort(key=sort_key, reverse=desc)

    print(f"Sorted {len(data):,} rows by: {', '.join(f'{c} ({'desc' if d else 'asc'})' for c, d in sort_keys)}")

    if output:
        write_csv(headers, data, output)
        print(f"Written to: {output}")
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(data[:50])
        if len(data) > 50:
            print(f"... ({len(data) - 50} more rows)")


def cmd_dedupe(args):
    """Remove duplicate rows."""
    if len(args) < 1:
        raise ValidationError("Usage: csvflow.py dedupe <file.csv> [--on 'col1,col2'] [-o output.csv]")

    filepath = args[0]
    on_cols = None
    output = None

    i = 1
    while i < len(args):
        if args[i] == '--on' and i + 1 < len(args):
            on_cols = [c.strip() for c in args[i + 1].split(',')]
            i += 2
        elif args[i] in ('-o', '--output') and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            i += 1

    headers, data = read_csv(filepath)

    if on_cols:
        col_idx = []
        for c in on_cols:
            found = False
            for j, h in enumerate(headers):
                if h.lower() == c.lower():
                    col_idx.append(j)
                    found = True
                    break
            if not found:
                raise ValidationError(f"Column not found: {c}")

        seen = set()
        unique = []
        for row in data:
            key = tuple(row[i] if i < len(row) else "" for i in col_idx)
            if key not in seen:
                seen.add(key)
                unique.append(row)
    else:
        seen = set()
        unique = []
        for row in data:
            key = tuple(row)
            if key not in seen:
                seen.add(key)
                unique.append(row)

    removed = len(data) - len(unique)
    print(f"Deduplicated: {len(data):,} → {len(unique):,} rows ({removed:,} removed)")

    if output:
        write_csv(headers, unique, output)
        print(f"Written to: {output}")
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(unique[:50])
        if len(unique) > 50:
            print(f"... ({len(unique) - 50} more rows)")


def cmd_merge(args):
    """Combine multiple CSV files."""
    if len(args) < 2:
        raise ValidationError("Usage: csvflow.py merge <file1.csv> <file2.csv> [...] [-o output.csv]")

    output = None
    files = []
    i = 0
    while i < len(args):
        if args[i] in ('-o', '--output') and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            files.append(args[i])
            i += 1

    if len(files) < 2:
        raise ValidationError("At least 2 files required for merge")

    all_headers = None
    all_data = []

    for fp in files:
        headers, data = read_csv(fp)
        if all_headers is None:
            all_headers = headers
        # Align columns
        aligned = []
        header_map = {h.lower(): i for i, h in enumerate(all_headers)}
        for row in data:
            new_row = []
            for h in all_headers:
                idx = None
                for j, rh in enumerate(headers):
                    if rh.lower() == h.lower():
                        idx = j
                        break
                new_row.append(row[idx] if idx is not None and idx < len(row) else "")
            aligned.append(new_row)
        all_data.extend(aligned)

    print(f"Merged {len(files)} files: {len(all_data):,} total rows")

    if output:
        write_csv(all_headers, all_data, output)
        print(f"Written to: {output}")
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(all_headers)
        writer.writerows(all_data[:50])
        if len(all_data) > 50:
            print(f"... ({len(all_data) - 50} more rows)")


def cmd_transform(args):
    """Apply column operations."""
    if len(args) < 2:
        raise ValidationError(
            "Usage: csvflow.py transform <file.csv> --op 'column:operation' [-o output.csv]\n"
            "Operations: upper, lower, strip, title, int, float, fill:value, prefix:text, suffix:text, regex:pattern:replace"
        )

    filepath = args[0]
    operations = []
    output = None

    i = 1
    while i < len(args):
        if args[i] == '--op' and i + 1 < len(args):
            operations.append(args[i + 1])
            i += 2
        elif args[i] in ('-o', '--output') and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            i += 1

    headers, data = read_csv(filepath)
    col_idx = {h.lower(): i for i, h in enumerate(headers)}

    for op_str in operations:
        parts = op_str.split(':')
        if len(parts) < 2:
            raise ValidationError(f"Invalid operation format: {op_str}. Use column:operation")

        col_name = parts[0]
        operation = parts[1].lower()
        op_args = parts[2:]

        idx = col_idx.get(col_name.lower())
        if idx is None:
            raise ValidationError(f"Column not found: {col_name}")

        for row in data:
            if idx >= len(row):
                continue
            val = row[idx]
            if operation == 'upper':
                row[idx] = val.upper()
            elif operation == 'lower':
                row[idx] = val.lower()
            elif operation == 'strip':
                row[idx] = val.strip()
            elif operation == 'title':
                row[idx] = val.title()
            elif operation == 'int':
                try:
                    row[idx] = str(int(float(val.replace(',', ''))))
                except ValueError:
                    row[idx] = val
            elif operation == 'float':
                try:
                    row[idx] = str(float(val.replace(',', '')))
                except ValueError:
                    row[idx] = val
            elif operation == 'fill' and op_args:
                if not val.strip():
                    row[idx] = op_args[0]
            elif operation == 'prefix' and op_args:
                row[idx] = op_args[0] + val
            elif operation == 'suffix' and op_args:
                row[idx] = val + op_args[0]
            elif operation == 'regex' and len(op_args) >= 2:
                row[idx] = re.sub(op_args[0], op_args[1], val)
            else:
                raise ValidationError(f"Unknown operation: {operation}")

    print(f"Applied {len(operations)} transformation(s) to {len(data):,} rows")

    if output:
        write_csv(headers, data, output)
        print(f"Written to: {output}")
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(data[:50])
        if len(data) > 50:
            print(f"... ({len(data) - 50} more rows)")


def cmd_export(args):
    """Convert between CSV and JSON."""
    if len(args) < 1:
        raise ValidationError("Usage: csvflow.py export <file.csv> [-o output.json] [--format json|csv]")

    filepath = args[0]
    output = None
    fmt = 'json'

    i = 1
    while i < len(args):
        if args[i] in ('-o', '--output') and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        elif args[i] == '--format' and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 2
        else:
            i += 1

    headers, data = read_csv(filepath)

    if not output:
        base = os.path.splitext(filepath)[0]
        output = f"{base}.{'json' if fmt == 'json' else 'csv'}"

    if fmt == 'json':
        write_json(headers, data, output)
    else:
        write_csv(headers, data, output)

    print(f"Exported {len(data):,} rows to {output} ({fmt})")


def cmd_clean(args):
    """Auto-clean common CSV issues."""
    if len(args) < 1:
        raise ValidationError("Usage: csvflow.py clean <file.csv> [-o output.csv]")

    filepath = args[0]
    output = None

    i = 1
    while i < len(args):
        if args[i] in ('-o', '--output') and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            i += 1

    # Detect and handle BOM
    encoding = detect_encoding(filepath)
    with open(filepath, 'r', encoding=encoding) as f:
        content = f.read()

    # Remove BOM
    if content.startswith('\ufeff'):
        content = content[1:]
        print("Removed BOM character")

    # Remove leading/trailing whitespace from all cells
    lines = content.split('\n')
    cleaned_lines = []
    changes = 0
    for line in lines:
        # Split by delimiter, clean each cell
        reader = csv.reader(io.StringIO(line))
        for row in reader:
            cleaned_row = []
            for cell in row:
                original = cell
                cell = cell.strip()
                if cell != original:
                    changes += 1
                cleaned_row.append(cell)
            # Reconstruct line
            output_io = io.StringIO()
            writer = csv.writer(output_io)
            writer.writerow(cleaned_row)
            cleaned_lines.append(output_io.getvalue().strip())

    # Remove empty lines
    non_empty = [l for l in cleaned_lines if l.strip()]
    empty_removed = len(cleaned_lines) - len(non_empty)
    if empty_removed:
        print(f"Removed {empty_removed} empty lines")

    # Parse and re-serialize to normalize
    reader = csv.reader(io.StringIO('\n'.join(non_empty)))
    rows = list(reader)
    if not rows:
        raise ValidationError("File is empty after cleaning")

    headers = rows[0]
    data = rows[1:]

    print(f"Cleaned {filepath}: {changes} cells trimmed, {empty_removed} empty lines removed")
    print(f"Result: {len(headers)} columns, {len(data):,} rows")

    if output:
        write_csv(headers, data, output)
        print(f"Written to: {output}")
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(data[:50])
        if len(data) > 50:
            print(f"... ({len(data) - 50} more rows)")


def cmd_stats(args):
    """Summary statistics for numeric columns."""
    if len(args) < 1:
        raise ValidationError("Usage: csvflow.py stats <file.csv>")

    filepath = args[0]
    headers, data = read_csv(filepath)

    print(f"\n{'='*60}")
    print(f"  CSVFlow Stats: {os.path.basename(filepath)}")
    print(f"{'='*60}")
    print(f"  Rows: {len(data):,}  |  Columns: {len(headers)}")
    print()

    for h in headers:
        col_idx = headers.index(h)
        values = [row[col_idx] for row in data if col_idx < len(row)]

        # Try numeric
        nums = []
        for v in values:
            try:
                nums.append(float(v.replace(',', '')))
            except ValueError:
                continue

        if len(nums) > len(values) * 0.5:  # More than 50% numeric
            if nums:
                nums.sort()
                n = len(nums)
                mean = sum(nums) / n
                median = nums[n // 2] if n % 2 else (nums[n // 2 - 1] + nums[n // 2]) / 2
                mn, mx = nums[0], nums[-1]
                variance = sum((x - mean) ** 2 for x in nums) / n
                std = variance ** 0.5

                print(f"  {h}")
                print(f"    Count: {n:,}  |  Mean: {mean:,.2f}  |  Median: {median:,.2f}")
                print(f"    Min: {mn:,.2f}  |  Max: {mx:,.2f}  |  Std Dev: {std:,.2f}")
                print()
        else:
            # Text column
            counter = Counter(v.strip().lower() for v in values if v.strip())
            top = counter.most_common(3)
            print(f"  {h} (text)")
            print(f"    Unique: {len(counter):,}  |  Top: {', '.join(f'{k}({v})' for k, v in top)}")
            print()


def print_help():
    """Print usage information."""
    print(__doc__)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        'info': cmd_info,
        'filter': cmd_filter,
        'select': cmd_select,
        'sort': cmd_sort,
        'dedupe': cmd_dedupe,
        'merge': cmd_merge,
        'transform': cmd_transform,
        'export': cmd_export,
        'clean': cmd_clean,
        'stats': cmd_stats,
        'help': lambda a: print_help(),
    }

    if command in ('--version', '-v'):
        print(f"CSVFlow v{__version__}")
        sys.exit(0)

    if command not in commands:
        print(f"Unknown command: {command}")
        print_help()
        sys.exit(1)

    try:
        commands[command](args)
    except CSVFlowError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


if __name__ == '__main__':
    main()
