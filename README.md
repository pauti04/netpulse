# NetPulse

Multi-signal Internet outage and BGP anomaly detector with a public,
reproducible benchmark.

<!-- badges: populated when CI is wired up to a remote -->
<!-- ![CI](https://github.com/OWNER/netpulse/actions/workflows/test.yml/badge.svg) -->
<!-- ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg) -->

## Status

Pre-alpha. Phases 0–3 (setup, BGP ingestion, MOAS + sub-prefix hijack
detectors, replay harness with one labeled incident) are working
end-to-end. **Real benchmark numbers are in [BENCHMARK.md](BENCHMARK.md):**
the sub-prefix detector catches the canonical YouTube/Pakistan 2008 hijack
on real RIPE RIS archive data with zero false positives in the surrounding
hour, at a latency bounded by the configured chunk size.

See [CLAUDE.md](CLAUDE.md) for full project context, roadmap, and rules.

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
