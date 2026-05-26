# NetPulse vs ARTEMIS head-to-head plan

A reproducible apples-to-apples comparison against ARTEMIS
(FORTH-ICS-INSPIRE/artemis) on the same labeled-incident
corpus NetPulse ships. ARTEMIS is the canonical academic
prior art for AS-self-monitoring BGP-hijack detection, so a
public side-by-side is the strongest credibility signal we
can produce.

## Why ARTEMIS

- Same problem space (BGP hijack detection by an operator
  watching their own prefixes).
- Open-source (BSD-3), still maintained, well-documented
  config format.
- Uses BGPStream / RIPE RIS / RouteViews exactly the way
  NetPulse does, so feeding both tools the same archive is
  meaningful.

ARTEMIS' default mode is **passive monitoring** of an
operator's own prefixes against a YAML rule set declaring
the legitimate origin + neighbor for each. It fires on:

- Type-0: unauthorized origin AS (MOAS-shape).
- Type-1: unauthorized first hop after origin (path leak).
- Type-N: longer-prefix not declared in rules
  (sub-prefix hijack).
- Type-U: unverified rules / unknown shape.

NetPulse's `SubPrefixHijackDetector` handles Type-0 + Type-N
in one detector; `RouteLeakDetector` /
`CustomerConeLeakDetector` handle Type-1. The categorical
mapping makes the comparison fair.

## Methodology

For each labeled incident in `data/incidents/*.json`:

1. **Build an ARTEMIS config** that declares the victim
   ASN's legitimate prefixes + origin from
   `<incident>_baseline.duckdb`. Output:
   `docs/artemis/configs/<incident>.yaml`.
2. **Replay the same MRT data** through ARTEMIS:
   - Mount `data/<incident>.duckdb`'s underlying MRT
     dumps into the ARTEMIS `bgpstreamhist` directory
     (re-export to MRT first; ARTEMIS can't read DuckDB).
   - Start the ARTEMIS docker-compose stack.
   - Load the config; wait for the detection-process to
     finish replay.
   - Pull `view_hijacks` from ARTEMIS' Postgres.
3. **Score the same incident** through NetPulse via
   `scripts/run_corpus_benchmark.py` (already produces
   `docs/corpus_benchmark.json`).
4. **Compare**: per-incident outcome (`TP/FN`), per-tool
   alert counts, latency from documented onset to first
   alert.

## Reproduce locally

Prerequisites:

- Docker Desktop running (the daemon must be reachable
  at the default socket).
- ~6 GB RAM free; ARTEMIS' compose stack starts ~12
  containers including Kafka + Postgres + RabbitMQ.

### One-time setup

```sh
# 1. Pull ARTEMIS
git clone https://github.com/FORTH-ICS-INSPIRE/artemis ../artemis
cd ../artemis
cp .env.example .env

# 2. Bring up the stack
docker compose up -d
docker compose ps   # confirm all containers are healthy

# 3. Web UI at https://localhost:8443/ (self-signed cert).
```

### Per-incident comparison

From the NetPulse repo root:

```sh
# 1. Export an ARTEMIS config from the NetPulse incident.
uv run python scripts/artemis_export_config.py \
    data/incidents/youtube_2008.json \
    docs/artemis/configs/youtube_2008.yaml

# 2. Re-export the MRT for ARTEMIS' bgpstreamhist replay.
#    (NetPulse stores BGP records in DuckDB; ARTEMIS
#    expects the underlying MRT bz2 dumps in a directory.)
uv run python scripts/artemis_export_mrt.py \
    data/incidents/youtube_2008.json \
    ../artemis/local_configs/bgpstreamhist/

# 3. Reload ARTEMIS' config (via web UI or REST API).
# 4. Trigger replay (web UI -> "Restart processes").
# 5. Once detection finishes, pull alerts:
uv run python scripts/artemis_compare.py \
    --incident data/incidents/youtube_2008.json \
    --artemis-url https://localhost:8443 \
    --artemis-token "$(cat ../artemis/.env | grep API_TOKEN | cut -d= -f2)" \
    --out docs/artemis/results/youtube_2008.json
```

The comparison report writes a JSON shaped like:

```json
{
  "incident_id": "youtube_2008",
  "netpulse": {
    "fired": true,
    "first_alert_us": 1203882477000000,
    "latency_from_onset_us": 0,
    "on_target_alerts": 1
  },
  "artemis": {
    "fired": true,
    "first_alert_us": 1203882477000000,
    "latency_from_onset_us": 0,
    "on_target_alerts": 14,
    "hijack_type": "S|0|-|-"
  }
}
```

`scripts/artemis_aggregate.py` rolls these up into a
single `docs/artemis-comparison.md` table:

| Incident                | NetPulse | ARTEMIS | NetPulse latency | ARTEMIS latency |
|-------------------------|----------|---------|------------------|-----------------|
| youtube_2008   | TP       | TP      | 0 µs             | 0 µs            |
| indosat_2014            | TP       | TP      | ...              | ...             |
| google_ntt_leak_2017    | TP       | ?       | ...              | ...             |
| mainone_google_leak_2018| TP       | ?       | ...              | ...             |
| myetherwallet_2018      | TP       | TP      | ...              | ...             |

Expected outcome: both tools detect the sub-prefix hijacks
(YouTube, MyEtherWallet, the sub-prefix portion of Indosat);
NetPulse additionally catches the route-leak cases via
`customer_cone_leak` while ARTEMIS' Type-1 logic may need
the relationship file installed. The point of the exercise
is to surface where the two diverge -- both will likely
agree on the easy cases and disagree on at least one of
the leaks.

## Open questions for the actual run

1. **Latency comparison fairness.** ARTEMIS' "first alert"
   includes its Kafka publish + DB write hop; NetPulse's
   `stream-latency` measures the detector's internal
   evaluation only. Either normalize to "first qualifying
   record" timestamp (both can produce that) or report both.
2. **Hijack type label.** ARTEMIS' `S|0|-|-` notation
   (sub-prefix, Type-0 origin, neighbor n/a, mitigation n/a)
   doesn't map 1:1 to NetPulse's `subprefix_hijack` /
   `route_leak`. The comparison table should include both
   tools' native labels rather than forcing a translation.
3. **False-positive count.** ARTEMIS suppresses alerts
   via `autoignore`; NetPulse's `--unauth-only` cuts
   noise differently. Document both modes' settings in
   the comparison output.
