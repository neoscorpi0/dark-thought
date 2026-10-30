# Dark Thought · HomePulse

**One phone-friendly page for your whole home lab:** live camera wall, which computers
and network gear are online, optional per-host stats over SSH, and one-tap shutdown /
Wake-on-LAN. Self-hosted, no cloud, no accounts.

by **Dark Thought** (42) — https://deepthought-42.github.io

---

## Why

You have cameras scattered across apps, a router with its own login, PCs you have to
SSH into to check, and no single place that answers "is everything still up, and can I
shut the gaming rig down from the couch?" HomePulse is that one page.

## Features

- **Live camera wall** — RTSP cameras transcoded to MJPEG in the browser (ffmpeg). Any
  IP cam Blue Iris / Synology / Reolink / Hikvision / generic ONVIF understands.
- **Hosts panel** — ping every machine, optional SSH stats (uptime, RAM, disk),
  cross-platform (Linux + Windows), and **Power off** buttons (with a confirm).
- **Wake-on-LAN** — wake a sleeping machine with one tap.
- **Network panel** — routers/switches online + latency, each with an **Open admin** link.
- **Password login** + year-long cookie, built for a phone (Add to Home Screen).
- **Config-driven** — one `config.json`; the same build runs on anybody's PC.

## Install

```bash
pip install flask waitress
# ffmpeg must be on PATH (for cameras)
cp config.example.json config.json     # edit it
python homepulse.py                    # http://<this-pc>:5085
```

### Windows (easy)
1. Install Python 3.9+ and ffmpeg (`winget install Gyan.FFmpeg`).
2. `pip install flask waitress`
3. Edit `config.json`, then `python homepulse.py`.
   (Optional: a `.exe` build is provided in the repo releases.)

## Config

Everything lives in `config.json`:

| Key | What |
|---|---|
| `password` | Login password (or set env `HOMEPULSE_PASSWORD`) |
| `port` | Listen port (default 5085) |
| `cameras[]` | `id`, `name`, `ip`, `port`, `url` (RTSP), `scale` |
| `hosts[]` | `id`, `name`, `ip`, `os` (linux/windows), `ssh`, `shutdown`, `mac`, `warn` |
| `network[]` | `name`, `sub`, `ip`, `url` |

See `config.example.json` for a full sample.

## Access from outside your network

Put it behind **Tailscale** (free): install Tailscale on the host and your phone, then
browse to `http://<host-name>:5085` from anywhere. No port-forwarding, no exposed router.

## Security notes

- Keep it on your LAN/Tailnet — do not port-forward it to the internet.
- The password protects shutdown/WOL actions; use a strong one.

## License

MIT (see `LICENSE`). Build it into something useful.
