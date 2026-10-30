#!/usr/bin/env python3
"""
TextForge v1.0.0 — Smart Text & Regex Processor
Zero external dependencies. Python 3.6+.

Commands:
  find      Search files for patterns (regex support, context lines, colors)
  replace   Find and replace with regex, capture groups, per-file or batch
  extract   Pull patterns out and format as CSV, JSON, or plain list
  count     Count occurrences of patterns across files
  split     Split a file into multiple files by delimiter or pattern
  join      Join multiple files into one
  stats     Text statistics (words, lines, chars, readability)
  summary   Quick overview of a text file
"""

import argparse
import csv
import io
import json
import os
import re
import sys
from pathlib import Path
from collections import Counter


def read_file(path, encoding="utf-8"):
    try:
        with open(path, "r", encoding=encoding, errors="replace") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {path}: {e}", file=sys.stderr)
        return None


def write_file(path, content, encoding="utf-8"):
    try:
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing {path}: {e}", file=sys.stderr)
        return False


def resolve_files(sources, extensions=None):
    """Resolve a list of files/globs into actual file paths."""
    files = []
    for src in sources:
        p = Path(src)
        if p.is_file():
            if extensions:
                if p.suffix.lower() in extensions:
                    files.append(p)
            else:
                files.append(p)
        elif p.is_dir():
            pattern = "**/*"
            for f in p.glob(pattern):
                if f.is_file():
                    if extensions:
                        if f.suffix.lower() in extensions:
                            files.append(f)
                    else:
                        files.append(f)
        else:
            # Try as glob
            import glob as globmod
            for f in globmod.glob(src, recursive=True):
                fp = Path(f)
                if fp.is_file():
                    if extensions:
                        if fp.suffix.lower() in extensions:
                            files.append(fp)
                    else:
                        files.append(fp)
    return sorted(set(files))


# ── FIND ─────────────────────────────────────────────────────────────────────

def cmd_find(args):
    """Search files for regex patterns with context."""
    files = resolve_files(args.files)
    if not files:
        print("No files found.", file=sys.stderr)
        return 1

    pattern = re.compile(args.pattern, re.IGNORECASE if args.ignore_case else 0)
    total_matches = 0
    context_before = args.before or args.context or 0
    context_after = args.after or args.context or 0

    for filepath in files:
        content = read_file(filepath)
        if content is None:
            continue

        lines = content.splitlines()
        file_matches = []
        for i, line in enumerate(lines):
            if pattern.search(line):
                file_matches.append(i)

        if not file_matches:
            continue

        if args.count_only:
            total_matches += len(file_matches)
            if args.files and len(args.files) == 1:
                print(f"{filepath}: {len(file_matches)} matches")
            else:
                print(f"{filepath}: {len(file_matches)}")
            continue

        if args.files_only:
            print(filepath)
            total_matches += len(file_matches)
            continue

        if total_matches == 0 or (not args.files or len(args.files) > 1):
            print(f"\n--- {filepath} ---" if not args.count_only else "", end="")

        for match_idx in file_matches:
            start = max(0, match_idx - context_before)
            end = min(len(lines), match_idx + context_after + 1)

            for i in range(start, end):
                prefix = f"{filepath}:" if total_matches == 0 or (args.files and len(args.files) > 1) else ""
                line_num = i + 1
                line_content = lines[i]

                if i == match_idx and args.color:
                    # Highlight matches
                    highlighted = pattern.sub(lambda m: f"\033[1;31m{m.group()}\033[0m", line_content)
                    print(f"{prefix}{line_num}: {highlighted}")
                else:
                    print(f"{prefix}{line_num}: {line_content}")

            if context_before > 0 or context_after > 0:
                print("--")

            total_matches += 1

    if args.count_only:
        if len(args.files) != 1:
            print(f"\nTotal: {total_matches} matches")
    else:
        print(f"\n{total_matches} match(es) found.")

    return 0


# ── REPLACE ──────────────────────────────────────────────────────────────────

def cmd_replace(args):
    """Find and replace with regex support."""
    files = resolve_files(args.files)
    if not files:
        print("No files found.", file=sys.stderr)
        return 1

    flags = re.IGNORECASE if args.ignore_case else 0
    pattern = re.compile(args.pattern, flags)
    replacement = args.replacement
    dry_run = args.dry_run
    total_replacements = 0

    for filepath in files:
        content = read_file(filepath)
        if content is None:
            continue

        new_content, count = pattern.subn(replacement, content)

        if count == 0:
            continue

        total_replacements += count

        if dry_run:
            print(f"[DRY RUN] {filepath}: {count} replacement(s) would be made")
            if args.verbose:
                # Show diff-like output
                old_lines = content.splitlines()
                new_lines = new_content.splitlines()
                for i, (old, new) in enumerate(zip(old_lines, new_lines)):
                    if old != new:
                        print(f"  L{i+1} - {old}")
                        print(f"  L{i+1} + {new}")
        else:
            if args.backup:
                backup_path = filepath.with_suffix(filepath.suffix + ".bak")
                write_file(backup_path, content)

            if write_file(filepath, new_content):
                print(f"{filepath}: {count} replacement(s)")
            else:
                print(f"Failed to write {filepath}", file=sys.stderr)

    print(f"\nTotal: {total_replacements} replacement(s){' (dry run)' if dry_run else ''}")
    return 0


# ── EXTRACT ──────────────────────────────────────────────────────────────────

def cmd_extract(args):
    """Extract patterns from files and format output."""
    files = resolve_files(args.files)
    if not files:
        print("No files found.", file=sys.stderr)
        return 1

    flags = re.IGNORECASE if args.ignore_case else 0
    pattern = re.compile(args.pattern, flags)
    results = []

    for filepath in files:
        content = read_file(filepath)
        if content is None:
            continue

        if args.groups:
            for match in pattern.finditer(content):
                row = {"file": str(filepath)}
                for i, group in enumerate(args.groups):
                    try:
                        row[group] = match.group(i + 1)
                    except IndexError:
                        row[group] = match.group(0) if match.lastindex is None else ""
                results.append(row)
        else:
            for match in pattern.finditer(content):
                results.append({
                    "file": str(filepath),
                    "match": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                })

    if not results:
        print("No matches found.")
        return 0

    if args.format == "csv":
        if results:
            writer = csv.DictWriter(sys.stdout, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
    elif args.format == "json":
        print(json.dumps(results, indent=2))
    elif args.format == "list":
        for r in results:
            if "match" in r:
                print(r["match"])
            else:
                print(json.dumps(r))
    else:
        # Tabular
        if results:
            widths = {}
            for key in results[0]:
                widths[key] = max(len(key), max(len(str(r.get(key, ""))) for r in results))
            header = "  ".join(k.ljust(widths[k]) for k in results[0])
            print(header)
            print("  ".join("-" * widths[k] for k in results[0]))
            for r in results:
                print("  ".join(str(r.get(k, "")).ljust(widths[k]) for k in results[0]))

    print(f"\n{len(results)} extraction(s).")
    return 0


# ── COUNT ────────────────────────────────────────────────────────────────────

def cmd_count(args):
    """Count occurrences of patterns across files."""
    files = resolve_files(args.files)
    if not files:
        print("No files found.", file=sys.stderr)
        return 1

    flags = re.IGNORECASE if args.ignore_case else 0
    pattern = re.compile(args.pattern, flags)

    if args.per_file:
        for filepath in files:
            content = read_file(filepath)
            if content is None:
                continue
            count = len(pattern.findall(content))
            print(f"{filepath}: {count}")
    else:
        combined = Counter()
        for filepath in files:
            content = read_file(filepath)
            if content is None:
                continue
            matches = pattern.findall(content)
            combined[str(filepath)] = len(matches)

        for fpath, cnt in combined.most_common():
            if cnt > 0:
                print(f"  {fpath}: {cnt}")

        total = sum(combined.values())
        print(f"\nTotal: {total} across {len(files)} file(s)")

    return 0


# ── SPLIT ────────────────────────────────────────────────────────────────────

def cmd_split(args):
    """Split a file into multiple files by pattern or delimiter."""
    content = read_file(args.file)
    if content is None:
        return 1

    if args.delimiter:
        parts = content.split(args.delimiter)
        if args.max_parts:
            parts = parts[:args.max_parts]
    elif args.pattern:
        pattern = re.compile(args.pattern, re.MULTILINE)
        parts = pattern.split(content)
        if args.max_parts:
            parts = parts[:args.max_parts]
    else:
        # Split by blank lines
        parts = re.split(r'\n\s*\n', content)

    file_path = Path(args.file) if not isinstance(args.file, Path) else args.file
    stem = file_path.stem
    parent = file_path.parent

    for i, part in enumerate(parts):
        if not part.strip() and args.skip_empty:
            continue
        out_path = parent / f"{stem}_{i+1:03d}.txt"
        if write_file(out_path, part.strip() + "\n"):
            print(f"  {out_path}")

    print(f"Split into {len(parts)} part(s).")
    return 0


# ── JOIN ─────────────────────────────────────────────────────────────────────

def cmd_join(args):
    """Join multiple files into one."""
    files = resolve_files(args.files)
    if not files:
        print("No files found.", file=sys.stderr)
        return 1

    parts = []
    for filepath in files:
        content = read_file(filepath)
        if content is None:
            continue
        if args.separator:
            parts.append(content + args.separator)
        else:
            parts.append(content)

    output = "".join(parts)

    if args.output:
        if write_file(args.output, output):
            print(f"Joined {len(files)} file(s) -> {args.output}")
        else:
            return 1
    else:
        print(output)

    return 0


# ── STATS ────────────────────────────────────────────────────────────────────

def cmd_stats(args):
    """Text statistics."""
    files = resolve_files(args.files)
    if not files:
        print("No files found.", file=sys.stderr)
        return 1

    for filepath in files:
        content = read_file(filepath)
        if content is None:
            continue

        lines = content.splitlines()
        words = content.split()
        chars = len(content)
        chars_no_space = len(content.replace(" ", "").replace("\n", "").replace("\t", ""))

        # Word frequency
        word_freq = Counter(w.lower().strip(".,;:!?\"'()-[]{}") for w in words if len(w) > 2)

        # Sentence count (rough)
        sentences = len(re.split(r'[.!?]+', content)) - 1

        # Paragraph count
        paragraphs = len(re.split(r'\n\s*\n', content.strip()))

        # Avg word length
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)

        # Avg sentence length
        avg_sent_len = len(words) / max(sentences, 1)

        print(f"\n--- {filepath} ---")
        print(f"  Lines:           {len(lines)}")
        print(f"  Words:           {len(words)}")
        print(f"  Characters:      {chars}")
        print(f"  Characters (no whitespace): {chars_no_space}")
        print(f"  Sentences:       {sentences}")
        print(f"  Paragraphs:      {paragraphs}")
        print(f"  Avg word length: {avg_word_len:.1f} chars")
        print(f"  Avg sentence length: {avg_sent_len:.1f} words")

        if args.top:
            n = int(args.top)
            print(f"\n  Top {n} words:")
            for word, count in word_freq.most_common(n):
                print(f"    {word:20s} {count}")

    return 0


# ── SUMMARY ──────────────────────────────────────────────────────────────────

def cmd_summary(args):
    """Quick summary of a text file."""
    content = read_file(args.file)
    if content is None:
        return 1

    lines = content.splitlines()
    words = content.split()

    print(f"File: {args.file}")
    print(f"Lines: {len(lines)}, Words: {len(words)}, Chars: {len(content)}")
    print(f"First line: {lines[0][:80] if lines else '(empty)'}")
    print(f"Last line:  {lines[-1][:80] if lines else '(empty)'}")

    # Unique words
    unique = set(w.lower() for w in words)
    print(f"Unique words: {len(unique)}")

    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="textforge",
        description="TextForge v1.0.0 — Smart Text & Regex Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  textforge find "TODO|FIXME" src/ --context 2
  textforge replace "old_api" "new_api" *.py --dry-run
  textforge extract "https?://\\S+" logs/ --format csv
  textforge count "error|warn|fatal" logs/ --per-file
  textforge stats README.md --top 10
  textforge split data.txt --delimiter "---"
  textforge join chapter_*.txt --output book.txt
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # FIND
    p_find = subparsers.add_parser("find", help="Search for patterns")
    p_find.add_argument("pattern", help="Regex pattern to search for")
    p_find.add_argument("files", nargs="+", help="Files or directories to search")
    p_find.add_argument("-i", "--ignore-case", action="store_true", help="Case insensitive")
    p_find.add_argument("-c", "--context", type=int, default=0, help="Context lines before+after")
    p_find.add_argument("-B", "--before", type=int, help="Context lines before match")
    p_find.add_argument("-A", "--after", type=int, help="Context lines after match")
    p_find.add_argument("-n", "--count-only", action="store_true", help="Print match count only")
    p_find.add_argument("-l", "--files-only", action="store_true", help="Print filenames only")
    p_find.add_argument("--color", action="store_true", default=True, help="Colorize matches")

    # REPLACE
    p_replace = subparsers.add_parser("replace", help="Find and replace")
    p_replace.add_argument("pattern", help="Regex pattern to find")
    p_replace.add_argument("replacement", help="Replacement string (supports \\1, \\g<name>)")
    p_replace.add_argument("files", nargs="+", help="Files to process")
    p_replace.add_argument("-i", "--ignore-case", action="store_true", help="Case insensitive")
    p_replace.add_argument("-n", "--dry-run", action="store_true", help="Show what would change")
    p_replace.add_argument("-b", "--backup", action="store_true", help="Create .bak backup")
    p_replace.add_argument("-v", "--verbose", action="store_true", help="Show diff output")

    # EXTRACT
    p_extract = subparsers.add_parser("extract", help="Extract patterns")
    p_extract.add_argument("pattern", help="Regex pattern (use groups for structured output)")
    p_extract.add_argument("files", nargs="+", help="Files to extract from")
    p_extract.add_argument("-i", "--ignore-case", action="store_true", help="Case insensitive")
    p_extract.add_argument("-g", "--groups", nargs="+", help="Named group names for capture groups")
    p_extract.add_argument("-f", "--format", choices=["csv", "json", "list", "table"],
                          default="table", help="Output format")

    # COUNT
    p_count = subparsers.add_parser("count", help="Count occurrences")
    p_count.add_argument("pattern", help="Regex pattern to count (use | for multiple)")
    p_count.add_argument("files", nargs="+", help="Files to search")
    p_count.add_argument("-i", "--ignore-case", action="store_true", help="Case insensitive")
    p_count.add_argument("-p", "--per-file", action="store_true", help="Show per-file counts")

    # SPLIT
    p_split = subparsers.add_parser("split", help="Split file by pattern")
    p_split.add_argument("file", help="File to split")
    p_split.add_argument("-d", "--delimiter", help="String delimiter to split on")
    p_split.add_argument("-p", "--pattern", help="Regex pattern to split on")
    p_split.add_argument("-m", "--max-parts", type=int, help="Maximum number of parts")
    p_split.add_argument("--skip-empty", action="store_true", help="Skip empty parts")

    # JOIN
    p_join = subparsers.add_parser("join", help="Join files together")
    p_join.add_argument("files", nargs="+", help="Files to join")
    p_join.add_argument("-o", "--output", help="Output file (default: stdout)")
    p_join.add_argument("-s", "--separator", help="Separator between files")

    # STATS
    p_stats = subparsers.add_parser("stats", help="Text statistics")
    p_stats.add_argument("files", nargs="+", help="Files to analyze")
    p_stats.add_argument("-t", "--top", help="Show top N most frequent words")

    # SUMMARY
    p_summary = subparsers.add_parser("summary", help="Quick file summary")
    p_summary.add_argument("file", help="File to summarize")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "find": cmd_find,
        "replace": cmd_replace,
        "extract": cmd_extract,
        "count": cmd_count,
        "split": cmd_split,
        "join": cmd_join,
        "stats": cmd_stats,
        "summary": cmd_summary,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
