# Benchmark incident dataset

Each `*.json` file in this directory describes one labeled historical
incident the replay harness scores detectors against. Files whose names
begin with `_` (this README, `_TEMPLATE.json`) are skipped by the loader.

## Hard rule

**Every field must be backed by a primary source cited in `source_url`.**
Do not invent timestamps, AS numbers, prefixes, or incident details. When a
detail cannot be verified, leave the field absent and set `"verified":
false` with a note describing what still needs confirmation.

The repository ships exactly one populated example (`youtube_pakistan_2008.json`)
because that's the most extensively documented public BGP hijack. Adding a
new incident is a deliberate research task — read the primary sources and
fill in the schema yourself. Generated lists of "famous BGP incidents" are
explicitly disallowed.

## Schema

```json
{
  "id": "short_snake_case_id",
  "name": "Human-readable name",
  "kind": "hijack | leak | outage",
  "start_iso": "YYYY-MM-DDTHH:MM:SSZ",
  "end_iso":   "YYYY-MM-DDTHH:MM:SSZ",
  "expected_detectors": ["moas", "..."],
  "source_url": "https://primary.source/citation",
  "prefix": "1.2.3.0/24",
  "attacker_asn": 12345,
  "victim_asn": 67890,
  "notes": "free text — explain timing precision, scope, and anything not directly verifiable",
  "verified": false
}
```

`prefix`, `attacker_asn`, and `victim_asn` are all optional (e.g., outages
may have no single attacker). `expected_detectors` lists which detector
names a faithful replay should fire — empty is allowed if no detector in
the project is yet expected to catch the incident.

## Adding an incident

1. Read primary sources end-to-end (RIPE writeups, peer-reviewed papers,
   operator postmortems). Mailing-list threads alone are not enough.
2. Copy `_TEMPLATE.json`, fill in only what the source documents.
3. Cite the source in `source_url`. Multiple sources go in `notes`.
4. Set `verified: true` only when every field is directly supported by the
   citation — including time precision.
5. Open a PR with the source and your reasoning in the description.
