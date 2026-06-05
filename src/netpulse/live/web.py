"""Public web surface for the live monitor: a status page + JSON feed.

Reads from a shared ``DetectionFeed`` (no database between the monitor
thread and these handlers). Endpoints:

- ``GET /``            — self-refreshing HTML status page
- ``GET /live/recent`` — JSON: recent detections + live stats
- ``GET /healthz``     — liveness (always 200 while the process is up)
"""

# This module is mostly an inline HTML/CSS template; long lines are natural.
# ruff: noqa: E501
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from netpulse import __version__
from netpulse.live.feed import DetectionFeed


def build_live_app(feed: DetectionFeed) -> FastAPI:
    app = FastAPI(title="NetPulse Live", version=__version__)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/live/recent")
    def recent(limit: int = 50) -> dict[str, object]:
        return {
            "stats": feed.stats(),
            "detections": [asdict(d) for d in feed.recent(limit)],
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _render_page(feed)

    return app


def _humanize(detector: str, entity: str) -> tuple[str, str]:
    """Translate a detector + entity into a plain-language (title, explanation)."""
    if detector == "origin_deaggregation":
        return (
            "Route deaggregation burst",
            f"{entity} suddenly announced a large batch of narrow, more-specific routes. "
            "Usually a misconfiguration — but it's also how some hijacks begin.",
        )
    if detector == "moas":
        return (
            "Conflicting route origin",
            f"{entity} is being announced by several networks at once — a classic hijack "
            "signature (though it can also be legitimate multi-homing).",
        )
    if detector == "subprefix_hijack":
        return (
            "Possible sub-prefix hijack",
            f"A more-specific slice of {entity} appeared from a network not authorized to "
            "announce it — the exact pattern behind the 2008 YouTube outage.",
        )
    return (detector.replace("_", " ").title(), entity)


def _render_page(feed: DetectionFeed) -> str:
    s = feed.stats()
    dets = feed.recent(40)
    live = bool(s["connected"])
    status_pill = (
        '<span class="pill on"><span class="dot"></span>live</span>'
        if live
        else '<span class="pill off"><span class="dot"></span>reconnecting…</span>'
    )
    up = cast(int, s["uptime_seconds"])
    uptime = f"{up // 3600}h {(up % 3600) // 60:02d}m" if up >= 3600 else f"{up // 60}m {up % 60:02d}s"

    cards = []
    for d in dets:
        when = datetime.fromtimestamp(d.ts_us / 1_000_000, tz=UTC).strftime("%H:%M:%S")
        title, why = _humanize(d.detector, _esc(d.entity))
        cards.append(
            f'<div class="ev">'
            f'<div class="ev-top"><span class="sev sev-{d.severity}">{d.severity}</span>'
            f'<span class="ev-title">{title}</span>'
            f'<span class="ev-time">{when} UTC</span></div>'
            f'<div class="ev-why">{why}</div>'
            f'<div class="ev-raw">{_esc(d.summary)} <code>{d.detector}</code></div>'
            f"</div>"
        )
    if not cards:
        cards.append('<div class="empty">Watching the feed — no anomalies in the buffer yet.</div>')

    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>NetPulse — live BGP anomaly monitor</title>
<meta http-equiv=refresh content=20>
<style>
 :root{{--bg:#0d1117;--panel:#161b22;--line:#21262d;--ink:#e6edf3;--muted:#8b949e;--dim:#6e7681;--accent:#58a6ff}}
 *{{box-sizing:border-box}}
 body{{background:var(--bg);color:var(--ink);margin:0;
   font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
 .wrap{{max-width:860px;margin:0 auto;padding:40px 22px 60px}}
 .top{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
 h1{{font-size:26px;font-weight:700;margin:0;letter-spacing:-.02em}}
 .pill{{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:600;
   padding:4px 11px;border-radius:999px;text-transform:uppercase;letter-spacing:.04em}}
 .pill.on{{background:rgba(63,185,80,.15);color:#3fb950}} .pill.off{{background:rgba(248,81,73,.15);color:#f85149}}
 .dot{{width:7px;height:7px;border-radius:50%;background:currentColor;
   box-shadow:0 0 0 0 currentColor;animation:p 1.8s infinite}}
 @keyframes p{{0%{{box-shadow:0 0 0 0 rgba(63,185,80,.5)}}70%{{box-shadow:0 0 0 6px rgba(63,185,80,0)}}100%{{box-shadow:0 0 0 0 rgba(63,185,80,0)}}}}
 .lede{{color:var(--muted);font-size:15px;margin:14px 0 4px;max-width:680px}}
 .lede b{{color:var(--ink);font-weight:600}}
 .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:26px 0 8px}}
 .stat{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
 .stat .n{{font-size:26px;font-weight:700;letter-spacing:-.02em}}
 .stat .l{{color:var(--dim);font-size:12px;margin-top:2px}}
 h2{{font-size:14px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;
   margin:34px 0 6px}}
 .note{{color:var(--dim);font-size:13px;margin:0 0 16px;max-width:680px}}
 .ev{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:10px}}
 .ev-top{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
 .ev-title{{font-weight:600}} .ev-time{{margin-left:auto;color:var(--dim);font-size:13px;
   font-variant-numeric:tabular-nums}}
 .ev-why{{color:var(--muted);font-size:14px;margin-top:6px}}
 .ev-raw{{color:var(--dim);font-size:12px;margin-top:8px;
   font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
 .ev-raw code{{background:#1f2430;color:#79c0ff;padding:1px 6px;border-radius:5px;font-size:11px}}
 .sev{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
   padding:2px 9px;border-radius:6px}}
 .sev-critical{{background:rgba(248,81,73,.18);color:#ff7b72}}
 .sev-warning{{background:rgba(210,153,34,.18);color:#e3b341}}
 .sev-info{{background:rgba(88,166,255,.18);color:#79c0ff}}
 .empty{{color:var(--dim);text-align:center;padding:40px;background:var(--panel);
   border:1px solid var(--line);border-radius:10px}}
 .foot{{margin-top:34px;padding-top:18px;border-top:1px solid var(--line);color:var(--dim);font-size:13px}}
 .foot a{{color:var(--accent);text-decoration:none}} .foot a:hover{{text-decoration:underline}}
</style></head><body><div class=wrap>
<div class=top><h1>NetPulse</h1>{status_pill}</div>
<p class=lede>A <b>live monitor of the internet's routing system</b>. Networks use BGP to
announce which addresses they can reach — a protocol with no built-in security, so a
bad announcement can hijack or misroute traffic worldwide. NetPulse taps the
<b>global BGP feed in real time</b> and flags suspicious announcements as they happen.</p>
<div class=stats>
 <div class=stat><div class=n>{s["updates_seen"]:,}</div><div class=l>routing updates analyzed</div></div>
 <div class=stat><div class=n>{s["detections_total"]:,}</div><div class=l>anomalies flagged</div></div>
 <div class=stat><div class=n>{uptime}</div><div class=l>uptime this session</div></div>
 <div class=stat><div class=n>{s["reconnects"]}</div><div class=l>feed reconnects (auto-recovered)</div></div>
</div>
<h2>Live detections</h2>
<p class=note>Newest first, auto-refreshing every 20s. Most flagged events are benign —
heavy deaggregation and multi-homing are everyday occurrences — so these are
<b>candidates worth a look</b>, surfaced by the same detectors that catch 7&nbsp;of&nbsp;7
real historical attacks in NetPulse's reproducible benchmark.</p>
{"".join(cards)}
<div class=foot>Open-source — source &amp; reproducible benchmark on
<a href=https://github.com/pauti04/netpulse>GitHub</a> ·
<a href=/live/recent>raw JSON feed</a> · live data from RIPE&nbsp;RIS&nbsp;Live · NetPulse v{__version__}</div>
</div></body></html>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
