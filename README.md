# NetPulse

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
# Install (requires uv: https://docs.astral.sh/uv/)
uv sync

# Pull one hour of BGP updates from RRC00 into a DuckDB file
uv run netpulse ingest bgp \
    --collector rrc00 \
    --start 2024-01-01T00:00:00 \
    --duration 1h \
    --out data/bgp.duckdb
```

### Native dependency: libBGPStream

`pybgpstream` is a Python wrapper around the C library `libBGPStream`, which
must be installed before `uv sync` can build the wheel.

- **macOS:** `brew install bgpstream` (in homebrew-core; pulls in `wandio` and
  `librdkafka`).
- **Linux / others:** see <https://bgpstream.caida.org/docs/install>.

If `uv sync` cannot find `bgpstream_elem.h` after installing the library,
point the build at Homebrew's prefix:

```sh
CFLAGS="-I$(brew --prefix)/include" \
LDFLAGS="-L$(brew --prefix)/lib" \
uv sync
```

## Development

```sh
make install   # uv sync, including dev deps
make lint      # ruff check + mypy
make test      # pytest (skips integration tests by default)
make ci        # what CI runs
```

## License

MIT — see [LICENSE](LICENSE).
