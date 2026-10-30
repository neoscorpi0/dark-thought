# Dark Thought

Small, sharp tools with no dependencies and no cloud. Each one does a single job well,
reads only what you give it, and never phones home.

Built by 42. Named after the shadow of a bigger thing.

---

## The tools

| Tool | What it does |
|---|---|
| **[csvflow](sellable-tool-001/)** | Clean, split, merge, dedupe and convert CSV files from the command line. No pandas, no surprises. |
| **[textforge](sellable-tool-002/)** | Batch text processing: normalise, dedupe, extract, rewrite line patterns across whole folders. |
| **[sql_scanner](sellable-tool-003/)** | Static SQL-injection hunter for your own code, plus an **intentionally vulnerable practice server** to train against. |
| **[homepulse](sellable-tool-004-homepulse/)** | A tiny always-on health check for your own machines: services, disk, temperature, and a notification when something changes. |

Each folder has its own README, examples and licence.

---

## Design rules

1. **Standard library first.** If a dependency isn't essential, it isn't there.
2. **Nothing leaves your machine.** No telemetry, no callbacks, no accounts.
3. **Readable over clever.** You should be able to audit any file in a few minutes.
4. **Fail loudly.** Silent wrongness is worse than a crash.

---

## ⚠️ One deliberate exception

`sellable-tool-003/practice_server.py` is **intentionally vulnerable**. It exists so you
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
