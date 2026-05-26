# Show HN draft

Drafts for an "Show HN" post on Hacker News. Keep the title under 80
chars, the body in plain prose with one or two links. Pick one — A is
the engineering-honest framing, B leads with the multi-signal angle.

## Variant A — methodology-led (recommended)

**Title:** Show HN: NetPulse – open BGP detector, 4/4 on labeled incidents incl. 2017 Google→NTT leak

**URL:** https://github.com/pauti04/netpulse

**Body:**

I built NetPulse because the open BGP-anomaly-detector world has a
real gap: the published systems are great (PHAS, Pretty Good BGP,
ARTEMIS), but very few publish a public, re-runnable benchmark on real
RIS archive data. So you can read the algorithm but you can't sit down
and run it on the 2008 YouTube /24 hijack in five minutes.

NetPulse is opinionated about that part:

- 4 labeled incidents from primary sources only (RIPE NCC, Cloudflare,
  BGPmon, ISC). No fabricated incident data — that's a hard rule in the
  repo. **4 / 4 detected, 0 GAP, 0 FN.** The 2017-08 Google → Verizon
  → NTT leak that the standard valley-free check abstains on (the
  AS15169↔AS4713 pair is `unknown` in CAIDA 2017-08) is caught by a
  customer-cone-aware variant: NTT OCN is not in Google's 2017
  customer cone (10 ASes), so the path step is uphill and the cone
  detector fires (123,749 alerts).
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
- Why I ship both valley-free AND customer-cone-aware leak detectors
  instead of collapsing them into one fused signal
- How the per-record streaming benchmark differs from `--chunk` mode
- Why the corpus methodology has three buckets (TP / FN / GAP) even
  though the current corpus has zero GAP

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

The full benchmark covers 4 labeled incidents (4 TP / 0 GAP / 0 FN
— the 2017 Google leak required a customer-cone-aware leak detector
that the repo ships alongside the standard valley-free one) and a
4-hour FPR survey. Honest writeup at docs/paper.md.

MIT, Python 3.11, DuckDB. https://github.com/pauti04/netpulse

## Top comment seed (post yourself within the first 5 minutes)

> A note on the corpus methodology: the third bucket is GAP, for
> cases where the detector abstains because of a missing input rather
> than an algorithm miss. The current corpus has zero GAP — Google
> 2017 was a GAP under the standard valley-free check (the
> AS15169↔AS4713 pair is `unknown` in CAIDA 2017-08, so the check
> abstains) but the customer-cone-aware variant catches it: 4713 is
> not in cone(15169), step 5 is uphill following the downhill at
> step 4, alert fires. Keeping both detectors (rather than collapsing
> into one) preserves the audit shape: valley-free's evidence is a
> per-pair direction sequence; the cone variant's evidence is cone
> membership. Different things to look at when debugging an alert.
