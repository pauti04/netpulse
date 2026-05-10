# Benchmark — BGP detectors on real RIPE RIS archive data

The point of NetPulse is **honest evaluation against labeled historical
incidents**. This file reports what the detectors do on real RRC00 traffic:
one hour containing the 2008-02-24 YouTube/Pakistan hijack and four
background hours either side of it for false-positive analysis.

## Headline

| Detector             | Hour with hijack | Background (4 hours, 13,961 prefixes) | Verdict |
| -------------------- | ---------------: | ------------------------------------: | :------ |
| `subprefix_hijack`   |  **1 alert** (the hijack) |                            **0 alerts** | TPR = 1/1, FPR = 0 over the surveyed window |
| `moas`               |          10 alerts |  ~40 alerts/hour mean (variance 10–145) | Noise floor; flags multi-origin prefixes regardless of hijack |

The MOAS row is not "wrong" — same-prefix multi-origin events do happen
constantly (anycast services, multi-homed customers). The point is that
they're not, on their own, hijack signals; the canonical YouTube case is
in fact a *sub-prefix* hijack, which is why a supernet-aware detector is
required. See [`docs/why-subprefix.md`](docs/why-subprefix.md) for the
walkthrough.

![YouTube/Pakistan hijack onset at RRC00](docs/img/youtube_2008_onset.svg)

## Per-hour table

```
window                                        ann     wd    pfxs  moas  sub
2008-02-23 00:00 UTC (background)           43,385  5,665  3,660    14    0
2008-02-24 06:00 UTC (background)           55,067  7,042  2,840   145    0
2008-02-24 12:00 UTC (background)           49,682  6,673  2,924    16    0
2008-02-24 18:00 UTC (HIJACK)               51,757  4,899  7,738    10    1
2008-02-25 00:00 UTC (background)           42,272  4,203  4,537    13    0
TOTAL                                      242,163 28,482 21,699   198    1
```

The sole sub-prefix alert across these 5 hours, fired in the hijack window:

```
[critical] subprefix_hijack :: 208.65.153.0/24 :: more-specific of
208.65.152.0/22 (legit origins [36561]) announced from unauthorized
origin(s) [17557]
```

## What "the hijack" actually was

On 2008-02-24, AS17557 (Pakistan Telecom) announced `208.65.153.0/24`, a
more-specific of YouTube's `208.65.152.0/22` (AS36561), propagating
globally via PCCW (AS3491). Source:
<https://www.ripe.net/publications/news/youtube-hijacking-a-ripe-ncc-ris-case-study/>.

In the data:

- First AS17557 announcement of `208.65.153.0/24` observed at RRC00:
  **2008-02-24 18:47:57 UTC** (peer AS3333, as-path
  `3333 12859 6461 3491 17557`).
- The chart above shows announces-per-second around the onset, the
  hijacking AS in red, all other prefixes in grey.

## Reproducing

```sh
# 0. Native lib (macOS)
brew install bgpstream

# 1. Install with the BGP extra
CFLAGS="-I$(brew --prefix)/include" \
LDFLAGS="-L$(brew --prefix)/lib" \
    uv sync --extra bgp

# 2. Pull the 5 hours (~6 minutes total at 2008 RRC00 volumes)
mkdir -p data/fpr
uv run netpulse ingest bgp --collector rrc00 --start 2008-02-24T18:00:00 \
    --duration 1h --out data/youtube_2008.duckdb
for s in 2008-02-23T00:00:00 2008-02-24T06:00:00 \
         2008-02-24T12:00:00 2008-02-25T00:00:00; do
    uv run netpulse ingest bgp --collector rrc00 --start "$s" \
        --duration 1h --out data/fpr/fpr_${s//[:-]/_}.duckdb
done

# 3. Seed the focused baseline
uv run python scripts/seed_youtube_baseline.py data/youtube_2008_baseline.duckdb

# 4. Per-hour detector breakdown (the table above)
uv run python scripts/run_fpr_analysis.py

# 5. Single-incident replay with latency
uv run netpulse benchmark replay \
    --incidents data/incidents \
    --store data/youtube_2008.duckdb \
    --baseline data/youtube_2008_baseline.duckdb \
    --chunk 1m
```

For a one-command preview that does NOT require libBGPStream:

```sh
uv sync && uv run netpulse demo
```

## Latency

Latency in the replay harness is the time from documented event onset
(`onset_iso` in the incident JSON) to the right edge of the first
expanding-window chunk in which the detector fires. With `--chunk 1m`
and the YouTube onset at `2008-02-24 18:47:57Z`, the alert lands at
`18:48:00Z` — so the **reported latency (3.0 s) is bounded by the chunk
size, not by detector reaction time.** A streaming implementation
(see "Open: streaming detection") would emit the alert on the *first*
qualifying update; in this pull that update is the one at 18:47:57 itself,
and detector evaluation is well under one millisecond.

| `--chunk` | Reported latency |
| --------- | ---------------: |
| `5s`      |             3.0s |
| `1m`      |             3.0s |
| `5m`      |           123.0s |

## What this benchmark is not

- **One labeled incident.** The fixture set in `data/incidents/` has
  `youtube_pakistan_2008.json` only. Schema and primary-source citation
  rules: `data/incidents/_README.md`. Adding more is research, not code.
- **Focused, not RIB-derived, baseline.** `scripts/seed_youtube_baseline.py`
  writes a single (prefix, ASN) row sourced from the cited RIPE writeup
  rather than ingesting a full `record_type=ribs` snapshot from RRC00 at
  16:00 UTC; the ingest path is the same one that takes minutes per RIB
  and is why we use a focused baseline here.
- **No fusion yet.** The Atlas signal works in isolation
  (`src/netpulse/detectors/atlas_loss.py`, verified live against
  measurement 1001) but is not yet correlated with BGP detections in a
  single replay. RIPE Atlas launched in 2010, so the YouTube hijack
  cannot be validated against Atlas data — fusion benchmarking starts
  with a post-2010 incident.

## Open

- **Next incident** — 2018-04-24 Amazon Route 53 / MyEtherWallet hijack
  (AS10297 announced `/24` more-specifics inside Amazon's
  `205.251.192.0/18`; primary source:
  <https://blog.cloudflare.com/bgp-leaks-and-crypto-currencies/>). The
  detector and harness already handle this shape; the limiter is the
  ingest-path bottleneck on 2018-volume multi-hop RRC00 updates, which
  also blocks full-RIB ingestion.
- **Streaming detection** — `netpulse stream` against the RIS Live
  WebSocket would tighten reported latency from "chunk size" to
  "first-qualifying-update arrival."
- **Faster ingest path** — pybgpstream's pure-Python iteration is the
  bottleneck. Filtering inside libBGPStream (its native filter language)
  could give 100×+ speedups and unlock both larger backgrounds and the
  full RIB baseline.
