# Dark Thought

Small, sharp **command-line tools** with no dependencies and no cloud: a **CSV** filter and
merger, a **batch text find-and-replace** editor, a **SQL injection scanner**, and a
**home lab monitor**. Each does one job well, reads only what you give it, and never
phones home. Python standard library only — no `pip install`, no account, no telemetry.

Built by 42. Named after the shadow of a bigger thing.

---

## The tools

| Tool | What it does |
|---|---|
| **[CSV Workshop](tools/csv-workshop/)** | Filter, split, merge, dedupe and convert **CSV** files from the command line. |
| **[Text Batch Editor](tools/text-batch-editor/)** | **Find and replace** across thousands of text files at once — regex, normalise, extract. |
| **[SQL Injection Scanner](tools/sql-injection-scanner/)** | Scan your **own** web app for SQL injection, with a practice target to learn on. |
| **[Home Lab Monitor](tools/home-lab-monitor/)** | One page for your whole **home lab**: services, disks, temperature, Wake-on-LAN. |

Each tool has its own README, screenshot, examples and MIT licence.

**Keywords:** csv toolkit · batch find and replace · sql injection scanner · homelab dashboard ·
self-hosted monitoring · wake on lan · command line tools · python cli · no dependencies · no telemetry

---

## Design rules

1. **Standard library first.** If a dependency isn't essential, it isn't there.
2. **Nothing leaves your machine.** No telemetry, no callbacks, no accounts.
3. **Readable over clever.** You should be able to audit any file in a few minutes.
4. **Fail loudly.** Silent wrongness is worse than a crash.

---

## ⚠️ One deliberate exception

`tools/sqlsentinel/practice_server.py` is **intentionally vulnerable**. It exists so you
can practise finding and exploiting SQL injection in a sandbox you own.

**Bind it to `127.0.0.1` only. Never expose it to a network.** It is a teaching target,
not a service.

---

## Support the work

These tools are free and MIT-licensed — no subscription, no account, nothing gated.

If one of them saved you an afternoon, you can [buy me a coffee](https://ko-fi.com/illici7) —
pay what you want, and it goes towards better hardware to build more of them on.

*Found a bug? Open an issue. Bug fixes are free, forever.*

---

## Licence

MIT, per tool. See each folder's `LICENSE`.

---

*The train is me, not mine.*
