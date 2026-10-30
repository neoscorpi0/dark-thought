#!/usr/bin/env python3
"""
SQLi Practice Server v1.0.0 — Deliberately Vulnerable Web App for Learning
Run this locally and practice SQL injection techniques against it.

Endpoints:
    GET  /                — Home page with links
    GET  /products        — Product listing (SQLi-vulnerable search)
    GET  /login           — Login form (SQLi-vulnerable auth)
    GET  /users           — User profile by ID (SQLi-vulnerable)
    GET  /api/search      — JSON search endpoint (blind SQLi)
    GET  /api/union       — UNION-based injection practice
    POST /api/login       — Auth endpoint (SQLi-vulnerable)

WARNING: This app is INTENTIONALLY vulnerable. Never expose to the internet.
Author: 42 (Deep Thought) | License: MIT | Version: 1.0.0
"""

import json
import hashlib
import secrets
import sqlite3
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

__version__ = "1.0.0"
DB_PATH = Path(__file__).parent / "practice.db"

# ─── Database Setup ──────────────────────────────────────────────────────────────

def init_db():
    """Create the practice database with sample data."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS products")
    c.execute("DROP TABLE IF EXISTS users")
    c.execute("DROP TABLE IF EXISTS secrets")

    c.execute("""CREATE TABLE products (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        price REAL NOT NULL,
        stock INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        api_key TEXT
    )""")

    c.execute("""CREATE TABLE secrets (
        id INTEGER PRIMARY KEY,
        flag TEXT NOT NULL,
        hint TEXT
    )""")

    # Sample products
    products = [
        (1, "Wireless Mouse", "Electronics", 29.99, 150),
        (2, "Mechanical Keyboard", "Electronics", 89.99, 75),
        (3, "USB-C Hub", "Electronics", 45.00, 200),
        (4, "Monitor Stand", "Accessories", 35.00, 100),
        (5, "Webcam HD", "Electronics", 59.99, 60),
        (6, "Desk Lamp", "Lighting", 25.00, 120),
        (7, "Cable Management Kit", "Accessories", 15.00, 300),
        (8, "Ergonomic Chair", "Furniture", 299.99, 20),
        (9, "Laptop Stand", "Accessories", 49.99, 85),
        (10, "Noise Cancelling Headphones", "Electronics", 199.99, 40),
    ]
    c.executemany("INSERT INTO products VALUES (?,?,?,?,?)", products)

    # Sample users
    users = [
        (1, "admin", hashlib.sha256("admin123".encode()).hexdigest(), "admin@practice.local", "admin", "sk-admin-" + secrets.token_hex(16)),
        (2, "user1", hashlib.sha256("password1".encode()).hexdigest(), "user1@practice.local", "user", "sk-user-" + secrets.token_hex(16)),
        (3, "user2", hashlib.sha256("letmein".encode()).hexdigest(), "user2@practice.local", "user", "sk-user-" + secrets.token_hex(16)),
        (4, "test", hashlib.sha256("test123".encode()).hexdigest(), "test@practice.local", "test", "sk-test-" + secrets.token_hex(16)),
    ]
    c.executemany("INSERT INTO users VALUES (?,?,?,?,?,?)", users)

    # Hidden flags (extractable via SQLi)
    flags = [
        (1, "FLAG{sql_injection_101掌握了}", "Basic error-based injection"),
        (2, "FLAG{union_select_all_the_things}", "UNION-based extraction"),
        (3, "FLAG{blind_but_not_invisible}", "Boolean-based blind injection"),
        (4, "FLAG{time_will_reveal_all}", "Time-based blind injection"),
        (5, "FLAG{admin_password_is_admin123}", "Auth bypass via injection"),
    ]
    c.executemany("INSERT INTO secrets VALUES (?, ?, ?)", flags)

    conn.commit()
    conn.close()
    print(f"  Database initialized: {DB_PATH}")


# ─── HTML Templates ──────────────────────────────────────────────────────────────

HTML_LAYOUT = """<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{ font-family: monospace; background: #1a1a2e; color: #e0e0e0; margin: 40px; }}
        h1 {{ color: #00ff88; }}
        h2 {{ color: #00aaff; }}
        a {{ color: #ff6b9d; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        input, button {{ font-family: monospace; padding: 8px; margin: 4px; background: #16213e; color: #e0e0e0; border: 1px solid #0f3460; }}
        button {{ background: #0f3460; cursor: pointer; }}
        button:hover {{ background: #1a508b; }}
        table {{ border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #0f3460; padding: 8px 16px; text-align: left; }}
        th {{ background: #16213e; }}
        .flag {{ color: #ff0088; font-weight: bold; }}
        .nav {{ margin: 20px 0; padding: 10px; background: #16213e; }}
        code {{ background: #16213e; padding: 2px 6px; }}
        pre {{ background: #16213e; padding: 16px; overflow-x: auto; }}
    </style>
</head>
<body>
{content}
<div class="nav">
    <a href="/">Home</a> |
    <a href="/products">Products</a> |
    <a href="/login">Login</a> |
    <a href="/users?id=1">Users</a> |
    <a href="/api/search?q=test">API Search</a> |
    <a href="/api/union?table=products">API UNION</a>
</div>
<hr>
<small>SQLi Practice Server v{version} — INTENTIONALLY VULNERABLE</small>
</body>
</html>"""

HOME_CONTENT = """
<h1>SQLi Practice Server</h1>
<p>Welcome to the deliberately vulnerable practice server.</p>
<h2>Endpoints</h2>
<table>
<tr><th>Endpoint</th><th>Method</th><th>Vulnerability</th><th>Technique</th></tr>
<tr><td><a href="/products?category=Electronics">/products?category=X</a></td><td>GET</td><td>Error-based</td><td>SQL error messages leak data</td></tr>
<tr><td><a href="/users?id=1">/users?id=1</a></td><td>GET</td><td>UNION-based</td><td>Extract via UNION SELECT</td></tr>
<tr><td><a href="/api/search?q=test">/api/search?q=X</a></td><td>GET</td><td>Boolean blind</td><td>True/false response differences</td></tr>
<tr><td><a href="/api/union?table=products">/api/union?table=X</a></td><td>GET</td><td>UNION-based (JSON)</td><td>Extract tables as JSON</td></tr>
<tr><td><a href="/login">/login</a></td><td>GET/POST</td><td>Auth bypass</td><td>Log in as admin without password</td></tr>
</table>
<h2>Your Mission</h2>
<ol>
<li><span class="flag">FLAG 1</span>: Extract the hidden flags from the <code>secrets</code> table</li>
<li><span class="flag">FLAG 2</span>: Log in as admin without knowing the password</li>
<li><span class="flag">FLAG 3</span>: Extract all usernames and password hashes</li>
<li><span class="flag">BONUS</span>: Use blind injection to extract data character by character</li>
</ol>
<h2>Hints</h2>
<pre>
-- Start with a single quote to break out:
'

-- Test for error-based:
' OR '1'='1

-- UNION-based (find column count first):
' UNION SELECT NULL,NULL,NULL--

-- Boolean blind:
' OR 1=1--
' OR 1=2--

-- Time blind:
' OR SLEEP(5)--
</pre>
"""

PRODUCTS_CONTENT = """
<h1>Products</h1>
<form method="GET" action="/products">
    <input type="text" name="category" placeholder="Search category..." value="{query}">
    <button type="submit">Search</button>
</form>
{results}
"""

LOGIN_CONTENT = """
<h1>Login</h1>
<form method="POST" action="/api/login">
    <div>
        <label>Username:</label><br>
        <input type="text" name="username" placeholder="admin">
    </div>
    <div>
        <label>Password:</label><br>
        <input type="password" name="password" placeholder="password">
    </div>
    <br>
    <button type="submit">Login</button>
</form>
{message}
"""


# ─── Request Handler ─────────────────────────────────────────────────────────────

class SQLiHandler(BaseHTTPRequestHandler):
    """Deliberately vulnerable HTTP handler for SQLi practice."""

    def _send(self, code, content, content_type="text/html"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Powered-By", "SQLite/3.x")  # intentional info leak
        self.end_headers()
        self.wfile.write(content.encode() if isinstance(content, str) else content)

    def _render(self, title, content):
        return HTML_LAYOUT.format(title=title, content=content, version=__version__)

    def _get_params(self):
        parsed = urlparse(self.path)
        return parse_qs(parsed.query)

    def _get_post_data(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return parse_qs(self.rfile.read(length).decode())
        return {}

    def _query(self, sql, params=()):
        """Execute SQL — INTENTIONALLY VULNERABLE (string formatting)."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # VULNERABLE: direct string formatting (this is the whole point)
        c.execute(sql, params)
        results = [dict(row) for row in c.fetchall()]
        conn.close()
        return results

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = {k: v[0] for k, v in self._get_params().items()}

        if path == "/" or path == "":
            self._send(200, self._render("SQLi Practice", HOME_CONTENT))

        elif path == "/products":
            query = params.get("category", "")
            # VULNERABLE: direct string concatenation
            if query:
                sql = f"SELECT * FROM products WHERE category = '{query}'"
                try:
                    results = self._query(sql)
                    rows = "".join(
                        f"<tr><td>{r['id']}</td><td>{r['name']}</td><td>{r['category']}</td>"
                        f"<td>${r['price']:.2f}</td><td>{r['stock']}</td></tr>"
                        for r in results
                    )
                    table = f"<table><tr><th>ID</th><th>Name</th><th>Category</th><th>Price</th><th>Stock</th></tr>{rows}</table>"
                    count = f"<p>{len(results)} product(s) found</p>"
                except Exception as e:
                    # VULNERABLE: error messages leaked to user
                    table = f"<pre style='color: red;'>SQL Error: {e}</pre>"
                    count = ""
            else:
                results = self._query("SELECT * FROM products")
                rows = "".join(
                    f"<tr><td>{r['id']}</td><td>{r['name']}</td><td>{r['category']}</td>"
                    f"<td>${r['price']:.2f}</td><td>{r['stock']}</td></tr>"
                    for r in results
                )
                table = f"<table><tr><th>ID</th><th>Name</th><th>Category</th><th>Price</th><th>Stock</th></tr>{rows}</table>"
                count = f"<p>{len(results)} product(s) total</p>"

            content = PRODUCTS_CONTENT.format(query=query, results=count + table)
            self._send(200, self._render("Products", content))

        elif path == "/users":
            uid = params.get("id", "1")
            # VULNERABLE: direct string concatenation
            sql = f"SELECT id, username, email, role, api_key FROM users WHERE id = '{uid}'"
            try:
                results = self._query(sql)
                if results:
                    rows = "".join(
                        f"<tr><td>{r['id']}</td><td>{r['username']}</td>"
                        f"<td>{r['email']}</td><td>{r['role']}</td>"
                        f"<td><code>{r['api_key']}</code></td></tr>"
                        for r in results
                    )
                    table = f"<table><tr><th>ID</th><th>Username</th><th>Email</th><th>Role</th><th>API Key</th></tr>{rows}</table>"
                else:
                    table = "<p>No user found.</p>"
            except Exception as e:
                table = f"<pre style='color: red;'>SQL Error: {e}</pre>"

            content = f"<h1>User Profile</h1><form method='GET' action='/users'><input type='text' name='id' value='{uid}'><button>Search</button></form>{table}"
            self._send(200, self._render("Users", content))

        elif path == "/login":
            content = LOGIN_CONTENT.format(message="")
            self._send(200, self._render("Login", content))

        elif path == "/api/search":
            q = params.get("q", "")
            # VULNERABLE: blind SQLi (no errors shown, but response differs)
            if q:
                sql = f"SELECT id, name, category FROM products WHERE name LIKE '%{q}%'"
                try:
                    results = self._query(sql)
                    # Always returns JSON (blind: true/false = different result counts)
                    self._send(200, json.dumps({"count": len(results), "results": results}), "application/json")
                except Exception:
                    # Blind: return error but don't leak SQL details
                    self._send(200, json.dumps({"count": 0, "results": [], "error": "query failed"}), "application/json")
            else:
                results = self._query("SELECT id, name, category FROM products LIMIT 5")
                self._send(200, json.dumps({"count": len(results), "results": results, "hint": "Use ?q= to search"}), "application/json")

        elif path == "/api/union":
            # VULNERABLE: UNION-based (table name directly concatenated)
            table = params.get("table", "products")
            sql = f"SELECT * FROM {table}"
            try:
                results = self._query(sql)
                self._send(200, json.dumps({"table": table, "rows": len(results), "data": results}, indent=2), "application/json")
            except Exception as e:
                self._send(200, json.dumps({"error": str(e), "table": table}), "application/json")

        elif path == "/api/secrets":
            # Hidden endpoint — not linked, must be discovered
            sql = "SELECT * FROM secrets"
            results = self._query(sql)
            self._send(200, json.dumps(results, indent=2), "application/json")

        else:
            self._send(404, self._render("404", "<h1>Not Found</h1>"))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/login":
            data = self._get_post_data()
            username = data.get("username", [""])[0]
            password = data.get("password", [""])[0]

            # VULNERABLE: direct string concatenation in auth query
            pw_hash = hashlib.sha256(password.encode()).hexdigest() if password else ""
            sql = f"SELECT * FROM users WHERE username = '{username}' AND password = '{pw_hash}'"

            try:
                results = self._query(sql)
                if results:
                    user = results[0]
                    content = self._render("Login Success", f"""
                        <h1>Login Successful!</h1>
                        <p>Welcome, <strong>{user['username']}</strong> ({user['role']})</p>
                        <p>Email: {user['email']}</p>
                        <p>API Key: <code>{user['api_key']}</code></p>
                        <p class="flag">FLAG{{admin_password_is_admin123}}</p>
                    """)
                    self._send(200, content)
                else:
                    content = self._render("Login Failed", LOGIN_CONTENT.format(
                        message="<p style='color: red;'>Invalid username or password.</p>"
                    ))
                    self._send(200, content)
            except Exception as e:
                content = self._render("Login Error", LOGIN_CONTENT.format(
                    message=f"<pre style='color: red;'>SQL Error: {e}</pre>"
                ))
                self._send(200, content)

        else:
            self._send(404, self._render("404", "<h1>Not Found</h1>"))

    def log_message(self, format, *args):
        """Custom log format."""
        print(f"  [{self.log_date_time_string()}] {args[0]}")


# ─── Main ────────────────────────────────────────────────────────────────────────

def main():
    port = 8888
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    print(f"\n{'='*50}")
    print(f"  SQLi Practice Server v{__version__}")
    print(f"  INTENTIONALLY VULNERABLE — do not expose to internet")
    print(f"{'='*50}\n")

    init_db()

    server = HTTPServer(("127.0.0.1", port), SQLiHandler)
    print(f"  Listening on http://127.0.0.1:{port}")
    print(f"  Endpoints:")
    print(f"    GET  /products?category=X    (error-based)")
    print(f"    GET  /users?id=X             (UNION-based)")
    print(f"    GET  /api/search?q=X         (boolean blind)")
    print(f"    GET  /api/union?table=X      (UNION JSON)")
    print(f"    POST /api/login              (auth bypass)")
    print(f"    GET  /api/secrets            (hidden — find it!)")
    print(f"\n  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
