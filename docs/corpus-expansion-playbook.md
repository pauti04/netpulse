# Corpus expansion playbook

Each labeled incident in `data/incidents/` requires a working
`(store + baseline + JSON)` triple where the expected detector
actually fires on the recorded data. This page records the
recipe and the failure modes we hit while moving the corpus
from N=4 to N=5 (Indosat 2014). Future expansions should start
here.

## TL;DR recipe

1. **Read the primary source first.** Confirm exact UTC onset
   time, attacker AS, victim prefix(es), and the duration of
   propagation. The cited URL must be the source you actually
   used.
2. **Pick the collector.** RIPE RIS rrc00 sees globally-
   propagated events. For regional events, pick a collector
   that peers with the affected ASes — see the collector
   geography table below.
3. **Fetch with a tight filter.** Always use a libBGPStream
   filter; without one even a 5-minute window pulls
   100k-500k unrelated records and takes minutes per fetch.
   See "Filter syntax" below for the exact form.
4. **Sanity-check the data** before writing the JSON. The
   smoke test in `scripts/run_corpus_benchmark.py` is the
   bar: alert count > 0 with the expected detector.
5. **Hand-curate the baseline.** Verify legitimate origins
   against an RRC RIB snapshot taken 30-90 minutes BEFORE
   the incident onset. Place the file at
   `data/baselines/<incident>_baseline.duckdb` via a small
   seed script in `scripts/seed_<incident>_baseline.py`.
6. **Write the JSON.** `bgp_store_path: "../<incident>.duckdb"`
   resolves to `data/<incident>.duckdb`. The DuckDB store
   itself stays gitignored; contributors reproduce via the
   ingest command in `notes`.

## Filter syntax — the trap

libBGPStream's filter parser is **fussy about quotes**. The
filter expression has to be exactly what its grammar expects.
The proven forms:

| Form                          | Use when                                  | Example                              |
|-------------------------------|-------------------------------------------|--------------------------------------|
| `prefix any X`                | Match X, less-specifics, more-specifics   | `prefix any 1.1.1.0/24`              |
| `prefix exact X`              | Match X exactly                           | `prefix exact 208.65.153.0/24`       |
| `path "_<regex>$"`            | Paths originating at AS                   | `path "_4761$"`                      |
| `path "_<regex>_<regex>"`     | Paths containing an AS pair               | `path "_15169_4713"`                 |

**Critical:** the regex on `path` filters must be in **double
quotes**, not single quotes. Pass via shell with single
quotes around the whole `--filter` argument:

```sh
--filter 'path "_4761$"'        # correct
--filter "path '_4761$'"        # WRONG -- libBGPStream returns 0 records
```

`peer-asn N` is **not** a valid filter token in this version
of libBGPStream. Don't try it.

## Collector geography

When the global collectors (rrc00, route-views2) return zero
records, it's almost always a regional propagation issue.
Pick the right collector:

| Region              | RIPE RIS       | RouteViews                        |
|---------------------|----------------|-----------------------------------|
| Global / multi-RIR  | rrc00          | route-views2, route-views.routeviews |
| Europe              | rrc01, rrc04, rrc05, rrc12, rrc13 | route-views.linx, route-views.amsix |
| Americas            | rrc14, rrc15   | route-views2, route-views4, route-views.eqix, route-views.ny |
| Brazil              | rrc15 (São Paulo) | route-views.rio, route-views.fortaleza |
| Asia-Pacific        | rrc23, rrc10   | route-views.sg, route-views.perth, route-views.wide |
| Middle East / India | rrc22          | route-views.uaeix                 |
| Africa              | rrc19          | route-views.napafrica             |

Don't pick a collector that's geographically far from the
attacker AS and expect to see short-lived hijacks. The
Cloudflare 2024-06-27 hijack (AS267613, Brazil) was visible
only on Brazilian/LatAm peers. The Twitter 2022-03-28 hijack
similarly didn't propagate globally.

## Prefix-length filter limits

RIS collectors **filter prefixes longer than /24** by
default. If the hijack was a /25 or /32 host route (e.g.
Cloudflare 2024 used `1.1.1.1/32`), it will be invisible in
the archive even on a properly-peering collector.

Check the primary source for the announced prefix length
before committing to an incident. A /32-shape hijack needs
a different detection story (active probe, traceroute
divergence), not BGP archive analysis.

## Hijack-vs-leak shape

Incidents fall into roughly four shapes that map to
different `expected_detectors`:

| Shape                     | Detector                | Notable case          |
|---------------------------|-------------------------|-----------------------|
| Same-prefix re-announce   | `subprefix_hijack` Case 1 | Indosat 2014          |
| More-specific hijack      | `subprefix_hijack` Case 2 | YouTube /24 2008      |
| Type-1 path leak          | `route_leak`            | MainOne 2018          |
| Cone-violation leak       | `customer_cone_leak`    | Google/NTT 2017       |
| Origin de-aggregation     | (no detector ships yet) | Telekom Malaysia 2015 |

The Telekom Malaysia 2015 case is instructive: AS4788
massively re-announced its OWN /16s as /23 more-specifics
through its upstream Level3 (AS3549). The propagation was
the leak; the origins were legitimate. None of NetPulse's
shipped detectors fires cleanly on this shape -- it would
need an origin-deaggregation detector that we don't have
yet. Document as `verified: false` with a notes
explanation, or skip until that detector lands.

## Baseline construction — the verification anchor

The baseline is the single biggest determinant of whether the
detector fires cleanly. Two rules:

1. **Verify every (prefix, origin) pair against a real RRC RIB
   snapshot** taken before the incident (30-90 minutes
   before). Use `--record-type ribs` and `prefix any <supernet>`.
   The legitimate origins are whatever the RIB reports for the
   prefixes in question.
2. **Cover both detector shapes if possible.** If the hijack has
   both same-prefix and sub-prefix instances, include a mix of
   exact-prefix entries (for Case 1) and supernets (for Case 2).
   Indosat 2014 was the first labeled incident to exercise both
   branches in a single case.

When in doubt about a legitimate origin, fetch the RIB. Don't
guess; the corpus rule is "no fabricated data, ever."

## After landing an incident

1. Run `uv run python scripts/run_corpus_benchmark.py`. The new
   row must show `TP` with `on_target > 0`.
2. Re-render `docs/img/corpus_matrix.svg` via
   `uv run --extra viz python scripts/plot_corpus_matrix.py`.
3. Update three places: PROJECT.md (corpus count), README.md
   (headline), CHANGELOG.md ([unreleased]).
4. Commit + push. The DuckDB stores stay local; the JSON +
   baseline + seed script are what travels.
