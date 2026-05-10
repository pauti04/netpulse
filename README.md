# NetPulse

[![CI](https://github.com/pauti04/netpulse/actions/workflows/test.yml/badge.svg)](https://github.com/pauti04/netpulse/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Multi-signal Internet outage and BGP anomaly detector with a public,
reproducible benchmark.

The differentiator is honest evaluation: detector latency and
precision/recall reported against labeled historical incidents pulled
from the real RIPE RIS archive, not against synthetic fixtures.

## Headline result

The supernet-aware sub-prefix hijack detector catches the canonical
**YouTube / Pakistan Telecom 2008 hijack** on real RRC00 archive data:

| Metric                                | Value     |
| ------------------------------------- | --------- |
| Incidents detected                    | 1 / 1     |
| Latency from documented onset         | **3.0 s** at 1-minute replay chunks |
| False positives in surrounding hour   | 0         |

Full methodology, reproduction commands, and a write-up of why MOAS
doesn't catch this case: [BENCHMARK.md](BENCHMARK.md) and
[docs/why-subprefix.md](docs/why-subprefix.md).

## Status

Pre-alpha; phases 0–3 of the roadmap in [CLAUDE.md](CLAUDE.md) are
working end-to-end (setup, BGP ingestion, MOAS + sub-prefix hijack
detectors, replay harness with one labeled incident). Phases 4+ (RIPE
Atlas, DNS, multi-signal fusion, dashboard) are not yet started.

## Quickstart

```sh
# Install core deps (no native libraries needed)
uv sync

# Pull one hour of BGP updates from RRC00 into a DuckDB file
# (requires the optional [bgp] extra and libBGPStream — see below)
uv sync --extra bgp
uv run netpulse ingest bgp \
    --collector rrc00 \
    --start 2024-01-01T00:00:00 \
    --duration 1h \
    --out data/bgp.duckdb
```

### BGP ingestion — optional extra

`pybgpstream` is a Python wrapper around the C library `libBGPStream` and is
not in the default install. Detection, replay, and the test suite work
without it; only `netpulse ingest bgp` needs it.

- **macOS:** `brew install bgpstream` (homebrew-core; pulls in `wandio` and
  `librdkafka`), then:
  ```sh
  CFLAGS="-I$(brew --prefix)/include" \
  LDFLAGS="-L$(brew --prefix)/lib" \
  uv sync --extra bgp
  ```
- **Linux / others:** see <https://bgpstream.caida.org/docs/install>, then
  `uv sync --extra bgp`.

## Development

```sh
make install   # uv sync, including dev deps
make lint      # ruff check + mypy
make test      # pytest (skips integration tests by default)
make ci        # what CI runs
```

## License

MIT — see [LICENSE](LICENSE).
