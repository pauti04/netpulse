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

_SEV_COLOR = {"critical": "#ff5555", "warning": "#ffb86c", "info": "#8be9fd"}


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


def _render_page(feed: DetectionFeed) -> str:
    s = feed.stats()
    dets = feed.recent(40)
    conn = (
        '<span style="color:#50fa7b">● live</span>'
        if s["connected"]
        else '<span style="color:#ff5555">● reconnecting</span>'
    )
    up = cast(int, s["uptime_seconds"])
    uptime = f"{up // 3600}h {(up % 3600) // 60}m"

    rows = []
    for d in dets:
        when = datetime.fromtimestamp(d.ts_us / 1_000_000, tz=UTC).strftime("%H:%M:%S")
        color = _SEV_COLOR.get(d.severity, "#f8f8f2")
        rows.append(
            f"<tr><td class=t>{when}</td>"
            f'<td><span class=sev style="background:{color}">{d.severity}</span></td>'
            f"<td class=d>{d.detector}</td>"
            f"<td class=e>{_esc(d.entity)}</td>"
            f"<td class=s>{_esc(d.summary)}</td></tr>"
        )
    if not rows:
        rows.append(
            "<tr><td colspan=5 class=empty>no detections yet — watching the feed…</td></tr>"
        )

    return f"""<!doctype html><html><head><meta charset=utf-8>
<title>NetPulse Live — BGP anomaly monitor</title>
<meta http-equiv=refresh content=15>
<style>
 body{{background:#1a1b26;color:#c0caf5;font:14px/1.5 ui-monospace,Menlo,monospace;margin:0;padding:24px}}
 h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#7aa2f7;margin-bottom:18px}}
 .stats{{display:flex;gap:24px;flex-wrap:wrap;margin-bottom:20px}}
 .stat{{background:#24283b;border:1px solid #2f344d;border-radius:8px;padding:10px 16px}}
 .stat .n{{font-size:22px;font-weight:700;color:#bb9af7}} .stat .l{{color:#787c99;font-size:11px;text-transform:uppercase;letter-spacing:.08em}}
 table{{width:100%;border-collapse:collapse;font-size:13px}} th{{text-align:left;color:#787c99;font-weight:600;padding:6px 10px;border-bottom:1px solid #2f344d}}
 td{{padding:6px 10px;border-bottom:1px solid #20222e;vertical-align:top}} .t{{color:#7aa2f7;white-space:nowrap}} .d{{color:#7dcfff}} .e{{color:#e0af68;white-space:nowrap}}
 .sev{{color:#1a1b26;border-radius:4px;padding:1px 7px;font-size:11px;font-weight:700}}
 .empty{{color:#565a6e;text-align:center;padding:30px}} .s{{color:#a9b1d6}}
 a{{color:#7aa2f7}} .foot{{margin-top:20px;color:#565a6e;font-size:12px}}
</style></head><body>
<h1>⚡ NetPulse Live {conn}</h1>
<div class=sub>real-time BGP anomaly monitor · tapping the RIPE RIS Live feed · auto-refreshes every 15s</div>
<div class=stats>
 <div class=stat><div class=n>{s["updates_seen"]:,}</div><div class=l>BGP updates seen</div></div>
 <div class=stat><div class=n>{s["windows_evaluated"]:,}</div><div class=l>windows evaluated</div></div>
 <div class=stat><div class=n>{s["detections_total"]:,}</div><div class=l>anomalies flagged</div></div>
 <div class=stat><div class=n>{uptime}</div><div class=l>uptime</div></div>
 <div class=stat><div class=n>{s["reconnects"]}</div><div class=l>reconnects</div></div>
</div>
<table><thead><tr><th>time (UTC)</th><th>severity</th><th>detector</th><th>entity</th><th>summary</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>
<div class=foot>NetPulse v{__version__} · <a href=https://github.com/pauti04/netpulse>github.com/pauti04/netpulse</a> · <a href=/live/recent>JSON feed</a></div>
</body></html>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
