# Tweet thread draft

Eight tweets, written to fit 280 chars each (counts kept loose; trim
before posting). The thread leads with the headline, walks through
methodology, lands on the live deployment.

## Thread

**1/**

I shipped NetPulse — an open BGP anomaly detector evaluated against a
reproducible benchmark of labeled historical incidents.

4 / 4 detected. 0 GAP. 0 FN. Streaming-mode latency 0 µs on
the labeled sub-prefix hijacks.

GitHub: https://github.com/pauti04/netpulse

**2/**

Most open BGP-detection writeups have a methodology problem: the algos
are published, but the data and configs that produced the numbers
aren't easily re-runnable.

NetPulse is opinionated about that. Every claim has a re-run command
in the repo.

**3/**

The corpus is 4 incidents from primary sources only — RIPE NCC,
Cloudflare, BGPmon, ISC. The repo has a HARD rule against fabricated
incident data. Methodology has 3 buckets (TP / FN / GAP) so a missing
*input* isn't labeled as an algorithm miss.

**3a/**

The Google 2017 leak is the worked example for *why* methodology
matters. Standard valley-free check abstains because CAIDA 2017-08
has the AS15169↔AS4713 pair as `unknown`. Customer-cone-aware variant
catches it: NTT OCN is not in Google's 2017 cone (10 ASes). 123,749
alerts.

**4/**

Latency, reported two ways on the same archive:

- chunk-bounded (`--chunk 1m`): 3.0 s
- per-record streaming: **0 µs from documented onset**

The first qualifying update in the public RIS archive IS the onset
record. Honest streaming latency, not vapor.

**5/**

FPR survey: 4 hours of real RRC00 data around the YouTube hijack +
the hijack hour itself. 13,961 distinct prefixes. The sub-prefix
detector emits 1 alert across the whole 5 hours — in the right hour.

Detector runs against a real RIB-derived baseline, not a hand row.

**6/**

Multi-signal fusion on the 2018 MainOne→Google leak:

BGP route-leak detector (1,985 alerts on the actual leak shape using
the time-aligned CAIDA snapshot)
×
Atlas median RTT jumps 1.31× above baseline (38.0 → 49.9 ms)

= 1 fused critical alert.

**7/**

Performance fact I'm proud of: RPKI origin validation against 859k
VRPs runs at 43 µs / call — ~23k calls / sec. That's a 500× speedup
from longest-prefix-match indexing vs a linear scan over covering
networks. RFC 6811 §2 correctness preserved.

**8/**

Live HTTP surface: https://netpulse-pauti.fly.dev/health

```
curl -X POST https://netpulse-pauti.fly.dev/detect/bgp \
  -H 'Content-Type: application/json' \
  -d '{"start_iso":"2008-02-24T18:45:00Z","duration_s":300}'
```

Full writeup: docs/paper.md
MIT. Python 3.11. DuckDB + libBGPStream.
