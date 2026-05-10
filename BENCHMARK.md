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

![Per-hour MOAS vs sub-prefix alert counts](docs/img/fpr_per_hour.svg)

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

# 3. Real RIB-derived baseline (89 supernets in 208.65.0.0/16, ~47s with the
#    libBGPStream filter; the result is committed at data/baselines/...)
uv run netpulse ingest bgp --collector rrc00 --start 2008-02-24T16:00:00 \
    --duration 15m --record-type ribs --filter "prefix any 208.65.0.0/16" \
    --out data/baselines/yt_rib_filtered.duckdb

# 4. Per-hour detector breakdown (the table above)
uv run python scripts/run_fpr_analysis.py

# 5. Single-incident replay with latency
uv run netpulse benchmark replay \
    --incidents data/incidents \
    --store data/youtube_2008.duckdb \
    --baseline data/baselines/yt_rib_filtered.duckdb \
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
- **Bounded baseline scope.** `data/baselines/yt_rib_filtered.duckdb` is
  the **real RIB at 2008-02-24T16:00:00Z**, but only for prefixes inside
  `208.65.0.0/16` (89 supernets). A production deployment would use the
  full RIB (~270k prefixes at 2008 volumes). The native libBGPStream
  filter makes that feasible — we choose the scoped pull here because
  the question being asked is bounded: "did the YouTube prefix's
  legitimate origin get unauthorized more-specifics?"
- **No fusion yet.** The Atlas signal works in isolation
  (`src/netpulse/detectors/atlas_loss.py`, verified live against
  measurement 1001) but is not yet correlated with BGP detections in a
  single replay. RIPE Atlas launched in 2010, so the YouTube hijack
  cannot be validated against Atlas data — fusion benchmarking starts
  with a post-2010 incident.

## A real-world finding: not every documented hijack reaches public RIS

While trying to add the **2024-06-27 Cloudflare 1.1.1.1 incident** to
this benchmark, an unfiltered 15-minute pull of RRC00 around the
documented 18:51:00 UTC onset took 5+ CPU-minutes and showed no
`1.1.1.x` traffic at all. A targeted libBGPStream filter
(`prefix any 1.1.1.0/24`) finished the same 5-minute window in 30
seconds and confirmed: across **eight RIS collectors** (rrc00, rrc01,
rrc03, rrc04, rrc11, rrc14, rrc18, rrc25), zero sub-prefix
announcements of `1.1.1.0/24` appeared during the documented event,
and AS267613 itself never originated a route any of those collectors
saw. Per Cloudflare's writeup, the hijack reached "300 networks in 70
countries" but the host-route `/32` was filtered by upstreams before
reaching RIS-monitored peers — consistent with operators applying the
maximum-prefix-length recommendations in [RFC 7454][rfc7454].

**Implication for an honest benchmark:** the 2024 case is not
reproducible from public RIS data alone. A complete corpus would need
RouteViews collectors (different peers) and / or operator-direct BGP
feeds. The detector logic is unchanged; the visibility is the gap.

[rfc7454]: https://www.rfc-editor.org/rfc/rfc7454

## Faster ingest with libBGPStream filters

The `--filter` flag passes a libBGPStream filter expression through to
the C library, dropping non-matching elements before they cross into
Python. Empirically, on the 2024-06-27 18:50–19:10 UTC RRC00 window:

| Filter                            | Wall time | Records seen by Python |
| --------------------------------- | --------: | ---------------------: |
| (none, full firehose)             |    > 5min |                  > 1M  |
| `prefix any 1.1.0.0/16`           |       30s |                     58 |
| `prefix any 1.1.1.0/24`           |       30s |                      0 |

This is the bottleneck previously called out as future work; targeted
ingest is now seconds-to-minutes for narrow questions instead of
minutes-to-hours.

## Open

- **More labeled incidents from primary sources.** Schema and citation
  rules: `data/incidents/_README.md`. Candidate next: 2018-04-24
  Amazon Route 53 / MyEtherWallet (AS10297 sub-prefix hijack of
  Amazon's `205.251.192.0/18`).
- **Cross-collector evidence aggregation.** The Cloudflare/2024
  finding makes RouteViews integration concrete — a single-collector
  view systematically misses incidents that get filtered before
  reaching that collector's peers.
- **RPKI-based baselines.** The hand-curated one-row baselines work
  for individual incidents; production systems would derive the
  baseline from RPKI ROAs (RFCs 6480 / 8893).
