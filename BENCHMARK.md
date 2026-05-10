# Benchmark — YouTube / Pakistan 2008 hijack

The point of NetPulse is **honest evaluation against labeled historical
incidents**. This file reports the first such number: replaying the
canonical YouTube/Pakistan 2008 BGP hijack against real RIPE RIS archive
data with the detectors implemented so far.

## Headline

| Detector             | Alerts on 1h of real RRC00 data | Caught YouTube hijack? | Latency from onset |
| -------------------- | ------------------------------: | :--------------------: | -----------------: |
| `subprefix_hijack`   |                               1 |          yes           |             3.0 s  |
| `moas`               |                              10 |           no¹          |                n/a |

¹ MOAS would only fire on the YouTube hijack if the legitimate AS36561
announcement and the AS17557 hijack were observed for the *same* prefix.
They were not — this was a sub-prefix hijack (`/22` legit vs `/24` hijack),
which is why a supernet-aware detector is required.

## What happened

On 2008-02-24, AS17557 (Pakistan Telecom) announced `208.65.153.0/24`, a
more-specific of YouTube's `208.65.152.0/22` (AS36561). The announcement
propagated globally via PCCW (AS3491). Source:
<https://www.ripe.net/publications/news/youtube-hijacking-a-ripe-ncc-ris-case-study/>.

In the data we pulled from RRC00:

- First AS17557 announcement of `208.65.153.0/24` observed at the collector:
  **2008-02-24 18:47:57 UTC** (peer AS3333, as-path
  `3333 12859 6461 3491 17557`).
- 1-hour window 18:00–19:00 UTC: 51,757 announces + 4,899 withdraws across
  7,738 distinct prefixes.

## How the number was produced

Reproducible end-to-end on a fresh checkout:

```sh
# 1. Install (requires libBGPStream — see README)
make install

# 2. Pull 1h of RRC00 updates around the hijack onset (~80s, ~57k records)
uv run netpulse ingest bgp \
    --collector rrc00 \
    --start 2008-02-24T18:00:00 \
    --duration 1h \
    --out data/youtube_2008.duckdb

# 3. Seed the focused baseline (legit YouTube /22 -> AS36561, sourced
#    from the RIPE writeup cited in the incident JSON).
uv run python scripts/seed_youtube_baseline.py data/youtube_2008_baseline.duckdb

# 4. Replay the labeled incident
uv run netpulse benchmark replay \
    --incidents data/incidents \
    --store data/youtube_2008.duckdb \
    --baseline data/youtube_2008_baseline.duckdb \
    --chunk 1m
```

Output:

```
loaded baseline: 1 prefixes
youtube_pakistan_2008: DETECTED (latency=3.0s, alerts=11)
summary: 1/1 detected (rate=100.00%); mean_latency_us=3000000.0
```

The `alerts=11` count includes one true-positive sub-prefix hijack alert
plus 10 MOAS alerts on unrelated multi-origin prefixes in the same window.

## Latency model

`latency_us` is `first_chunk_end_us − onset_us`, where `first_chunk_end_us`
is the right edge of the first expanding-window chunk in which an alert
matching the incident's prefix appeared. With `--chunk 1m` and
`onset = 18:47:57Z`, the alert lands at `18:48:00Z` so latency is bounded
above by the chunk size:

| `--chunk` | Reported latency | Notes                                                      |
| --------- | ---------------: | ---------------------------------------------------------- |
| `1m`      |           3.0 s  | dominated by chunk granularity, not detector reaction time |
| `5m`      |         123.0 s  | (re-run: same first detection, coarser bound)              |

The harness's contribution to latency is therefore the chunk size; the
underlying detector evaluates a window in well under a second.

## What this benchmark is not

- **It is not a full-corpus benchmark.** Phase 3 of the project roadmap
  (see `CLAUDE.md`) calls for ~20 labeled incidents. Only YouTube/Pakistan
  is populated. The fixture schema and primary-source citation rules are
  documented in `data/incidents/_README.md`. Adding more incidents is a
  research task, not a code task.
- **The baseline is focused, not a real RIB.** A full RRC00 RIB at
  `2008-02-24T16:00:00Z` would be the proper baseline. Pulling one through
  pybgpstream takes ~15–20 minutes of pure-Python iteration in the current
  ingest path; we use `scripts/seed_youtube_baseline.py` to write the one
  prefix that matters for the YouTube case (sourced from the cited RIPE
  writeup) so the benchmark is reproducible in seconds. Optimizing the RIB
  ingest is open work.
- **No Atlas / DNS signals yet.** Multi-signal fusion (Phases 4–6) starts
  after we have real Atlas response shapes to write against.

## Pulled-data files

The DuckDB stores produced by the steps above are not committed — they are
in `.gitignore` (`data/*.duckdb`). Re-create them with the commands in
**How the number was produced**.
