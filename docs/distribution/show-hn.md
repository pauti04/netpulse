# Show HN draft

Drafts for an "Show HN" post on Hacker News. Keep the title under 80
chars, the body in plain prose with one or two links. Pick one — A is
the engineering-honest framing, B leads with the multi-signal angle.

## Variant A — methodology-led (recommended)

**Title:** Show HN: NetPulse – an open BGP anomaly detector with a 4-incident reproducible benchmark

**URL:** https://github.com/pauti04/netpulse

**Body:**

I built NetPulse because the open BGP-anomaly-detector world has a
real gap: the published systems are great (PHAS, Pretty Good BGP,
ARTEMIS), but very few publish a public, re-runnable benchmark on real
RIS archive data. So you can read the algorithm but you can't sit down
and run it on the YouTube/Pakistan 2008 hijack in five minutes.

NetPulse is opinionated about that part:

- 4 labeled incidents from primary sources only (RIPE NCC, Cloudflare,
  BGPmon, ISC). No fabricated incident data — that's a hard rule in the
  repo. 3 detected, 1 honest GAP (the CAIDA inferred-relationships
  snapshot for 2017-08 is missing the AS pair the leak detector needs,
  so it abstains rather than guesses).
- Two latency numbers per sub-prefix incident: chunk-bounded (3.0 s
  at `--chunk 1m`) and per-record streaming (0 µs from documented
  onset — the first qualifying record IS the onset record in the
  archive).
- A four-hour false-positive survey of real RRC00 background data
  around the YouTube hour: 0 sub-prefix alerts on the background, 1
  on the hijack. MOAS row is published too (~40 alerts/hour) because
  it's the empirical case for needing a supernet-aware detector.
- Multi-signal correlator that fires on the MainOne 2018 leak when
  the BGP route-leak detector (1,985 alerts on the actual leak shape)
  co-occurs with a 1.31× Atlas median-RTT jump on the same window.
- Live: `curl https://netpulse-pauti.fly.dev/health`.

The detector logic is textbook — RFC 6811 origin validation with
longest-prefix-match (43 µs / call against 859k VRPs), RFC 7908
valley-free check, sub-prefix supernet match. The contribution is the
end-to-end stitching plus the methodology around what counts as a
detection and what counts as a gap.

Built on DuckDB, libBGPStream, RIPE Atlas. Python 3.11, MIT.

Happy to dig into any of:
- Why I chose `GAP` as a third bucket (instead of folding it into FN)
- How the per-record streaming benchmark differs from `--chunk` mode
- What it would take to time-align CAIDA snapshots for every
  historical incident automatically

## Variant B — multi-signal-led

**Title:** Show HN: BGP + RIPE Atlas signal fusion fires on the 2018 MainOne/Google leak

**Body:**

NetPulse is an open detector that runs the route-leak check (RFC 7908
valley-free) and an Atlas RTT-jump check on the same window of real
2018-11-12 archive data. On the MainOne → Google leak:

- BGP: 1,985 leak alerts on the actual AS37282→AS15169 path shape
  using the time-aligned CAIDA 2018-11 snapshot.
- Atlas: median RTT to 8.8.8.8 jumps 1.31× above baseline (38.0 → 49.9
  ms) during the 21:12–22:30 leak window.
- Correlator binds them into one fused critical alert.

`scripts/fusion_demo.py` reproduces the whole thing from the bundled
data. Live FastAPI at netpulse-pauti.fly.dev.

The full benchmark covers 4 labeled incidents (3 TP / 1 GAP / 0 FN)
and a 4-hour FPR survey. Honest writeup at docs/paper.md.

MIT, Python 3.11, DuckDB. https://github.com/pauti04/netpulse

## Top comment seed (post yourself within the first 5 minutes)

> A note on the GAP outcome: the Google 2017 leak is the 4th
> incident in the corpus and I'm reporting it as GAP rather than FN
> on purpose. The detector logic is the same code that catches the
> 2018 MainOne case end-to-end. What's missing is the CAIDA serial-2
> snapshot for 2017-08 happening to infer the AS15169 ↔ AS4713 pair —
> when an AS pair is `unknown` in the relationships table, the
> valley-free analyzer abstains. That's a snapshot-loader change, not
> an algorithm change, and folding it into FN would overclaim a
> missing-input case as a missing-algorithm case.
