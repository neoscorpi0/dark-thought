#!/usr/bin/env python3
"""
HomePulse — cameras, hosts and network on one phone-friendly page.
=================================================================
Self-hosted dashboard for a home / lab / small office:
  * live camera wall (RTSP -> MJPEG in the browser)
  * which computers & network gear are online (ping + optional SSH stats)
  * one-tap shutdown + Wake-on-LAN
  * password login, "known devices", installable as a phone app (PWA)

Everything is driven by config.json so the SAME build runs on anybody's PC.
No cloud, no accounts. MIT licensed. Made by 42 — https://deepthought-42.github.io

Quick start:
    pip install flask waitress pillow
    python homepulse.py            # first run creates config.json from the example
    # edit config.json, then restart.  Serves on http://0.0.0.0:5085

ffmpeg must be on PATH for camera streaming.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shlex
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, request,
                   render_template_string)

APP_VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
EXAMPLE_CONFIG = HERE / "config.example.json"
KNOWN_PATH = HERE / "known-devices.json"

CFG: dict = {}
TOKEN = ""
KNOWN_MAX = 3
_state = {"ts": 0, "data": {}}
_lock = threading.Lock()


# --------------------------------------------------------------- config load
def write_example_config():
    """First-run convenience: drop a starter config.json next to the script."""
    if EXAMPLE_CONFIG.exists():
        CONFIG_PATH.write_text(EXAMPLE_CONFIG.read_text())
    else:
        CONFIG_PATH.write_text(json.dumps({
            "title": "HomePulse", "port": 5085, "password": "change-me",
            "refresh_seconds": 12, "accent": "#4aa8ff", "known_devices_max": 3,
            "cameras": [], "hosts": [], "network": [],
        }, indent=2))


def load_config(path: Path):
    global KNOWN_MAX
    if not path.exists():
        write_example_config()
        print(f">> No config found — created {path}. Edit it, then run again.")
    cfg = json.loads(path.read_text())
    cfg.setdefault("title", "HomePulse")
    cfg.setdefault("port", 5085)
    cfg.setdefault("refresh_seconds", 12)
    cfg.setdefault("accent", "#4aa8ff")
    cfg.setdefault("known_devices_max", 3)
    cfg.setdefault("password", os.environ.get("HOMEPULSE_PASSWORD", ""))
    for k in ("cameras", "hosts", "network"):
        cfg.setdefault(k, [])
    KNOWN_MAX = int(cfg["known_devices_max"])
    return cfg


def accent_rgb():
    h = CFG.get("accent", "#4aa8ff").lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (74, 168, 255)


# ------------------------------------------------------------------- helpers
def ping_ms(ip: str, timeout: int = 1):
    if not ip:
        return None
    cmd = (["ping", "-n", "1", "-w", "1000", ip] if os.name == "nt"
           else ["ping", "-c", "1", "-W", str(timeout), ip])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        if r.returncode != 0:
            return None
        m = re.search(r"time[=<]([\d.]+)", r.stdout, re.I)
        return float(m.group(1)) if m else 0.0
    except Exception:
        return None


def tcp_open(ip: str, port: int, timeout: float = 1.2) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def ssh_run(target: str, remote: str, timeout: int = 8):
    try:
        return subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
             "-o", "StrictHostKeyChecking=no", *shlex.split(target), remote],
            capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def wol(mac: str, broadcast: str = "255.255.255.255", port: int = 9):
    try:
        mac_b = bytes.fromhex(re.sub(r"[^0-9a-fA-F]", "", mac))
        packet = b"\xff" * 6 + mac_b * 16
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, (broadcast, port))
        s.close()
        return True
    except Exception:
        return False


# ------------------------------------------------------------- known devices
def load_known():
    try:
        return json.loads(KNOWN_PATH.read_text())
    except Exception:
        return []


def save_known(devs):
    try:
        KNOWN_PATH.write_text(json.dumps(devs[:KNOWN_MAX], indent=1))
    except Exception:
        pass


def device_label(ua: str) -> str:
    ua = ua or ""
    osname = ("iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else
              "Android" if "Android" in ua else "Windows PC" if "Windows" in ua else
              "Mac" if "Macintosh" in ua else "Linux PC" if "Linux" in ua else "device")
    browser = ("Edge" if "Edg" in ua else "Chrome" if "Chrome" in ua else
               "Firefox" if "Firefox" in ua else
               "Safari" if "Safari" in ua and "Chrome" not in ua else "browser")
    return f"{browser} on {osname}"


def remember_device():
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or request.remote_addr or "?")
    ua = request.headers.get("User-Agent", "")
    did = hashlib.sha1(f"{ip}|{ua}".encode()).hexdigest()[:10]
    devs = [d for d in load_known() if d.get("id") != did]
    devs.insert(0, {"id": did, "label": device_label(ua), "ip": ip,
                    "last_seen": datetime.now().strftime("%d %b %H:%M")})
    save_known(devs)


# ---------------------------------------------------------------- app icon
_ICON_CACHE = {}


def make_icon(size: int):
    if size in _ICON_CACHE:
        return _ICON_CACHE[size]
    from PIL import Image, ImageDraw
    S = size
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGB", (1, S))
    top, bot = (17, 26, 42), (9, 13, 20)
    for y in range(S):
        t = y / (S - 1)
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bot)))
    grad = grad.resize((S, S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * .22), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    acc = accent_rgb() + (255,)
    bg = (10, 15, 24, 255)
    d.polygon([(S*.20, S*.50), (S*.50, S*.26), (S*.80, S*.50)], fill=acc)
    d.rectangle([S*.265, S*.48, S*.735, S*.78], fill=acc)
    cx, cy, r = S*.50, S*.615, S*.115
    d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=bg)
    d.ellipse([cx-r*.62, cy-r*.62, cx+r*.62, cy+r*.62], outline=acc, width=max(2, int(S*.018)))
    d.ellipse([cx-r*.24, cy-r*.24, cx+r*.24, cy+r*.24], fill=acc)
    d.ellipse([cx-r*.05, cy-r*.34, cx+r*.10, cy-r*.15], fill=(255, 255, 255, 230))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    _ICON_CACHE[size] = buf.getvalue()
    return _ICON_CACHE[size]


SW_JS = ("self.addEventListener('install',e=>self.skipWaiting());"
         "self.addEventListener('activate',e=>self.clients.claim());"
         "self.addEventListener('fetch',e=>{});")


# ------------------------------------------------------------------- state
def host_stats(h):
    ssh = h.get("ssh")
    if not ssh:
        return {}
    if h.get("os", "linux") == "linux":
        r = ssh_run(ssh, "uptime -p 2>/dev/null; nproc; free -m | awk 'NR==2{print $3\"/\"$2}'; df -h / | awk 'NR==2{print $5}'", 10)
        if not r or r.returncode != 0:
            return {}
        ln = [x for x in r.stdout.strip().splitlines() if x.strip()]
        out = {}
        if ln: out["uptime"] = ln[0].replace("up ", "")
        if len(ln) > 2: out["mem_mb"] = ln[2]
        if len(ln) > 3: out["disk"] = ln[3]
        return out
    if h.get("os") == "windows":
        r = ssh_run(ssh, "powershell -NoProfile -Command \"$o=Get-CimInstance Win32_OperatingSystem;"
                         "$u=(Get-Date)-$o.LastBootUpTime;"
                         "Write-Output ('up {0}d {1}h' -f $u.Days,$u.Hours);"
                         "Write-Output ('mem {0:N0}/{1:N0} MB' -f (($o.TotalVisibleMemorySize-$o.FreePhysicalMemory)/1024),($o.TotalVisibleMemorySize/1024))\"", 12)
        if not r or r.returncode != 0:
            return {}
        out = {}
        for x in r.stdout.splitlines():
            x = x.strip()
            if x.startswith("up "): out["uptime"] = x[3:]
            elif x.startswith("mem "): out["mem_mb"] = x[4:].replace(" MB", "")
        return out
    return {}


def sample_state():
    cams = [{"id": c["id"], "name": c.get("name", c["id"]),
             "online": tcp_open(c["ip"], c.get("port", 554))} for c in CFG["cameras"]]
    hosts = []
    for h in CFG["hosts"]:
        ms = ping_ms(h["ip"])
        e = {"id": h["id"], "name": h.get("name", h["id"]), "os": h.get("os", "linux"),
             "online": ms is not None, "ping_ms": round(ms, 1) if ms is not None else None,
             "shutdown": bool(h.get("shutdown")), "wol": bool(h.get("mac")), "warn": h.get("warn", "")}
        if e["online"]:
            e["stats"] = host_stats(h)
        hosts.append(e)
    net = []
    for n in CFG["network"]:
        ms = ping_ms(n["ip"])
        net.append({"name": n.get("name", n["ip"]), "sub": n.get("sub", ""), "ip": n["ip"],
                    "url": n.get("url"), "online": ms is not None,
                    "ping_ms": round(ms, 1) if ms is not None else None})
    return {"now": datetime.now().strftime("%a %d %b %H:%M:%S"),
            "cameras": cams, "hosts": hosts, "network": net, "devices": load_known()}


def refresher():
    while True:
        try:
            data = sample_state()
            with _lock:
                _state.update(ts=time.time(), data=data)
        except Exception as e:
            with _lock:
                _state["data"] = {"error": str(e)}
        time.sleep(CFG.get("refresh_seconds", 12))


# ------------------------------------------------------------------ actions
def do_action(h, action):
    if action == "shutdown":
        remote = "shutdown /s /f /t 0" if h.get("os") == "windows" else "sudo shutdown -h now"
        r = ssh_run(h["ssh"], remote, 10)
        if r and r.returncode == 0:
            return True, "sent"
        return False, (r.stderr.strip()[:200] if r else "ssh failed")
    if action == "wake":
        return (True, "magic packet sent") if wol(h["mac"]) else (False, "wol failed")
    return False, "unknown action"


# -------------------------------------------------------------------- flask
app = Flask(__name__)


def authed():
    if not TOKEN:
        return True
    return (request.args.get("k") or request.cookies.get("pk")) == TOKEN


def head_tags():
    return (f'<meta name="theme-color" content="{CFG.get("accent", "#4aa8ff")}">'
            '<meta name="apple-mobile-web-app-capable" content="yes">'
            '<meta name="mobile-web-app-capable" content="yes">'
            f'<meta name="apple-mobile-web-app-title" content="{CFG["title"]}">'
            '<link rel="manifest" href="/manifest.webmanifest">'
            '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
            '<link rel="icon" href="/icon-192.png">')


LOGIN = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
""" + "{{HEAD}}" + r"""
<title>{{TITLE}}</title><style>
:root{--bg:#0b0f14;--card:#141a22;--fg:#e8eef5;--dim:#8394a6;--accent:#4aa8ff;--bad:#ff5470}
body{margin:0;background:var(--bg);color:var(--fg);font:16px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:20px}
.box{background:var(--card);border:1px solid #ffffff14;border-radius:16px;padding:24px;width:100%;max-width:340px;text-align:center}
input{width:100%;padding:14px;font-size:18px;text-align:center;border-radius:11px;border:1px solid #ffffff22;background:#0b0f14;color:var(--fg);margin-bottom:12px}
button{width:100%;padding:14px;font-size:16px;font-weight:700;border:0;border-radius:11px;background:var(--accent);color:#04121f}
.err{color:var(--bad);font-size:13px;margin-bottom:12px}h1{font-size:18px;margin:0 0 6px}p{color:var(--dim);font-size:13px;margin:0 0 16px}
</style></head><body><form class="box" method="post" action="/auth">
<h1>{{TITLE}}</h1><p>Enter password to continue</p>{{ERR}}
<input name="key" type="password" autofocus placeholder="password"><button>Unlock</button>
</form></body></html>"""


def login_html(err=""):
    e = f'<div class="err">{err}</div>' if err else ""
    return (LOGIN.replace("{{HEAD}}", head_tags()).replace("{{TITLE}}", CFG["title"])
            .replace("{{ERR}}", e))


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
""" + "{{HEAD}}" + r"""
<title>{{TITLE}}</title><style>
:root{--bg:#0b0f14;--card:#141a22;--fg:#e8eef5;--dim:#8394a6;--ok:#38d39f;--bad:#ff5470;--accent:#4aa8ff}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:12px 12px 40px}
h1{font-size:17px;margin:4px 0 2px;display:flex;gap:8px;align-items:center}
h1 .dot{width:9px;height:9px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok)}
.sub{color:var(--dim);font-size:12px;margin-bottom:12px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin:20px 2px 8px}
.grid{display:grid;gap:10px}.cams{grid-template-columns:repeat(2,1fr)}
@media(min-width:760px){.cams{grid-template-columns:repeat(4,1fr)}.cards{grid-template-columns:1fr 1fr}}
.cam{background:var(--card);border-radius:12px;overflow:hidden;position:relative;border:1px solid #ffffff10}
.cam img{width:100%;display:block;aspect-ratio:4/3;object-fit:cover;background:#000}
.cam .lbl{position:absolute;left:0;right:0;bottom:0;padding:6px 8px;font-size:12px;background:linear-gradient(transparent,#000b);display:flex;justify-content:space-between}
.cam .st{width:8px;height:8px;border-radius:50%;background:var(--ok)}.cam.off .st{background:var(--bad)}.cam.off img{opacity:.25}
.card{background:var(--card);border-radius:12px;padding:12px;border:1px solid #ffffff10}
.row{display:flex;justify-content:space-between;align-items:center;gap:10px}
.name{font-weight:600}.meta{color:var(--dim);font-size:12px;margin-top:2px}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid #ffffff18}
.up{color:var(--ok);border-color:#38d39f55;background:#38d39f12}.down{color:var(--bad);border-color:#ff547055;background:#ff547012}
.btn{margin-top:10px;width:100%;padding:10px;border-radius:10px;border:1px solid #ff547055;background:#ff547018;color:#ff8fa0;font-weight:600;font-size:14px}
.btn.wake{border-color:#38d39f55;background:#38d39f12;color:#7fe9c4}
.btn[disabled]{opacity:.35;border-color:#ffffff10;background:#ffffff08;color:var(--dim)}
.openlink{display:inline-block;margin-top:10px;font-size:13px;color:var(--accent);text-decoration:none;border:1px solid #4aa8ff44;background:#4aa8ff12;padding:7px 12px;border-radius:9px}
.toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:#1b232e;border:1px solid #ffffff22;padding:10px 16px;border-radius:12px;opacity:0;transition:.3s;pointer-events:none;z-index:50}
.toast.show{opacity:1}
</style></head><body>
<h1><span class="dot"></span> {{TITLE}}</h1><div class="sub" id="clock">loading…</div>
<h2>Cameras · live</h2><div class="grid cams" id="cams"></div>
<h2>Hosts</h2><div class="grid cards" id="hosts"></div>
<h2>Network</h2><div class="grid cards" id="network"></div>
<h2>Known devices</h2><div class="grid cards" id="devices"></div>
<div class="toast" id="toast"></div>
<script>
const K=new URLSearchParams(location.search).get('k')||(document.cookie.split('; ').find(x=>x.startsWith('pk='))||'').split('=')[1]||'';
function q(u){return K?u+(u.includes('?')?'&':'?')+'k='+K:u;}
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200);}
function renderCams(cs){const e=document.getElementById('cams');e.innerHTML='';cs.forEach(c=>{const d=document.createElement('div');d.className='cam'+(c.online?'':' off');d.innerHTML=`<img src="${q('/cam/'+c.id+'/stream')}"><div class="lbl"><span>${c.name}</span><span class="st"></span></div>`;e.appendChild(d);});}
function renderHosts(hs){const e=document.getElementById('hosts');e.innerHTML='';hs.forEach(h=>{const s=h.stats||{};let m=[h.os];if(h.ping_ms!==null)m.push(h.ping_ms+' ms');if(s.uptime)m.push('up '+s.uptime);if(s.mem_mb)m.push('RAM '+s.mem_mb+' MB');if(s.disk)m.push('disk '+s.disk);const d=document.createElement('div');d.className='card';d.innerHTML=`<div class="row"><div><div class="name">${h.name}</div><div class="meta">${m.join(' · ')}</div></div><span class="badge ${h.online?'up':'down'}">${h.online?'online':'offline'}</span></div>`;if(h.wol&&!h.online){const b=document.createElement('button');b.className='btn wake';b.textContent='Wake (WOL)';b.onclick=()=>act('wake',h.id,'Wake '+h.name+'?');d.appendChild(b);}if(h.shutdown){const b=document.createElement('button');b.className='btn';b.textContent='Power off';b.disabled=!h.online;b.onclick=()=>act('shutdown',h.id,(h.warn?h.warn+'\n\n':'')+'Power OFF '+h.name+'?');d.appendChild(b);}e.appendChild(d);});}
function renderNet(ns){const e=document.getElementById('network');e.innerHTML='';ns.forEach(n=>{const d=document.createElement('div');d.className='card';d.innerHTML=`<div class="row"><div><div class="name">${n.name}</div><div class="meta">${n.sub?n.sub+' · ':''}${n.ip}${n.ping_ms!==null?' · '+n.ping_ms+' ms':''}</div></div><span class="badge ${n.online?'up':'down'}">${n.online?'online':'offline'}</span></div>`+((n.url&&n.online)?`<a class="openlink" href="${n.url}" target="_blank" rel="noopener">Open admin ↗</a>`:'');e.appendChild(d);});}
function renderDevices(ds){const e=document.getElementById('devices');e.innerHTML='';(ds||[]).forEach(d=>{const c=document.createElement('div');c.className='card';c.innerHTML=`<div class="row"><div><div class="name">${d.label}</div><div class="meta">${d.ip} · last ${d.last_seen}</div></div><span class="badge up">known</span></div>`;e.appendChild(c);});if(!(ds||[]).length)e.innerHTML='<div class="card"><div class="meta">No devices yet.</div></div>';}
async function act(a,id,m){if(!confirm(m))return;try{const r=await fetch(q('/api/action'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a,target:id,confirm:'yes'})});const j=await r.json();toast(j.ok?a+' sent':'Failed: '+(j.msg||'?'));}catch(e){toast('Error');}setTimeout(poll,1500);}
async function poll(){try{const r=await fetch(q('/api/state'));const s=await r.json();document.getElementById('clock').textContent='Updated '+s.now;renderCams(s.cameras);renderHosts(s.hosts);renderNet(s.network);renderDevices(s.devices);}catch(e){document.getElementById('clock').textContent='offline — retrying…';}}
if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
poll();setInterval(poll,10000);
</script></body></html>"""


@app.route("/")
def index():
    if request.args.get("k") == TOKEN and TOKEN:
        r = redirect("/")
        r.set_cookie("pk", TOKEN, max_age=31536000, samesite="Lax")
        return r
    if not authed():
        return Response(login_html(), mimetype="text/html"), 200
    remember_device()
    return render_template_string(PAGE.replace("{{HEAD}}", head_tags()).replace("{{TITLE}}", CFG["title"]))


@app.route("/auth", methods=["POST"])
def auth():
    if (request.form.get("key") or "").strip() == TOKEN:
        r = redirect("/")
        r.set_cookie("pk", TOKEN, max_age=31536000, samesite="Lax")
        return r
    return Response(login_html("Wrong password — try again."), mimetype="text/html"), 401


@app.route("/icon-<int:size>.png")
def icon(size):
    if size not in (180, 192, 512):
        abort(404)
    return Response(make_icon(size), mimetype="image/png")


@app.route("/apple-touch-icon.png")
def apple_icon():
    return Response(make_icon(180), mimetype="image/png")


@app.route("/manifest.webmanifest")
def manifest():
    return jsonify({
        "name": CFG["title"], "short_name": CFG["title"][:12],
        "description": "Cameras, hosts and network on one page.",
        "start_url": "/", "display": "standalone",
        "background_color": "#0b0f14", "theme_color": CFG.get("accent", "#0b0f14"),
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    })


@app.route("/sw.js")
def sw():
    return Response(SW_JS, mimetype="application/javascript")


@app.route("/cam/<cid>/stream")
def cam_stream(cid):
    if not authed():
        abort(401)
    c = next((x for x in CFG["cameras"] if x["id"] == cid), None)
    if not c:
        abort(404)

    def gen():
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
               "-fflags", "nobuffer", "-flags", "low_delay",
               "-probesize", "32", "-analyzeduration", "0",
               "-rtsp_transport", "tcp",
               "-i", c["url"], "-an", "-vf", f"scale={c.get('scale', 720)}:-2", "-r", "6",
               "-q:v", "7", "-f", "mpjpeg", "-boundary_tag", "ffmpeg", "-"]
        while True:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                while True:
                    chunk = p.stdout.read(4096)
                    if not chunk:
                        break
                    yield chunk
            except Exception:
                pass
            finally:
                try: p.kill()
                except Exception: pass
            time.sleep(1)

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=ffmpeg")


@app.route("/api/state")
def api_state():
    if not authed():
        abort(401)
    with _lock:
        return jsonify(dict(_state["data"]))


@app.route("/api/action", methods=["POST"])
def api_action():
    if not authed():
        abort(401)
    b = request.get_json(silent=True) or {}
    if b.get("confirm") != "yes":
        return jsonify({"ok": False, "msg": "no confirm"}), 400
    h = next((x for x in CFG["hosts"] if x["id"] == b.get("target")), None)
    if not h:
        return jsonify({"ok": False, "msg": "unknown target"}), 404
    if b.get("action") == "shutdown" and not h.get("shutdown"):
        return jsonify({"ok": False, "msg": "shutdown not allowed"}), 403
    if b.get("action") == "wake" and not h.get("mac"):
        return jsonify({"ok": False, "msg": "no MAC configured"}), 403
    ok, msg = do_action(h, b.get("action"))
    return jsonify({"ok": ok, "msg": msg})


def main():
    global CFG, TOKEN
    ap = argparse.ArgumentParser(description="HomePulse dashboard")
    ap.add_argument("--config", default=str(CONFIG_PATH))
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--no-auth", action="store_true")
    ap.add_argument("--example", action="store_true", help="write config.json from the example and exit")
    args = ap.parse_args()
    if args.example:
        write_example_config()
        print(f">> wrote {CONFIG_PATH}")
        return
    CFG = load_config(Path(args.config))
    TOKEN = "" if args.no_auth else (args.password or CFG["password"] or
                                     os.environ.get("HOMEPULSE_PASSWORD", ""))
    threading.Thread(target=refresher, daemon=True).start()
    port = args.port or CFG["port"]
    print(f"HomePulse v{APP_VERSION} — {CFG['title']} on :{port} (auth={'off' if not TOKEN else 'password'})")
    from waitress import serve
    serve(app, host="0.0.0.0", port=port, threads=12)


if __name__ == "__main__":
    main()
