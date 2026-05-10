# Contributing to NetPulse

Thanks for considering a patch. The project's stated goal is **honest
evaluation** of detector ideas against real Internet routing data, so
the bar for additions is "is this reproducible against archive data,
and does it produce a useful number?"

## Local setup

```sh
git clone https://github.com/pauti04/netpulse && cd netpulse
uv sync                  # core deps only; no native libraries needed
make test                # pytest
make ci                  # ruff + ruff format --check + mypy strict + pytest
```

For BGP ingestion you also need the native `libBGPStream` library and
the optional `[bgp]` extra:

```sh
brew install bgpstream                  # macOS
# Linux: see https://bgpstream.caida.org/docs/install
CFLAGS="-I$(brew --prefix)/include" \
LDFLAGS="-L$(brew --prefix)/lib" \
    uv sync --extra bgp
```

For chart regeneration: `uv sync --extra viz` (matplotlib).

## Code style

- Python 3.11+, no untyped functions in `src/netpulse`.
- `mypy --strict` over `src/netpulse` must pass; tests are exempt.
- `ruff check` and `ruff format --check` must pass — `make ci` runs both.
- Standard library and dataclasses for internal types; `pydantic` only
  at API/CLI boundaries (see `src/netpulse/api/app.py`).
- Timestamps are **microseconds since the Unix epoch, UTC** everywhere.
  Convert at module boundaries only.

## How to add a new detector

A detector is a class that subclasses
`netpulse.detectors.base.DetectorBase[F]` for some feature-window type
`F`, sets a class-level `name`, and implements `score(features) ->
list[Alert]` as a pure function. See `src/netpulse/detectors/moas.py`
for the simplest worked example, or `subprefix.py` for one with an
external baseline.

Walkthrough: [`docs/examples/adding_a_detector.md`](docs/examples/adding_a_detector.md).

Every new detector needs:

1. A test (synthetic feature window in / asserted alert out).
2. A short docstring explaining the signal it watches and what it
   intentionally does *not* try to detect.
3. If it consumes external data (a baseline, an AS-relationship map,
   etc.) the loader for that data must live alongside the detector
   and be wired through the CLI.

## How to add a new labeled incident

1. Read primary sources end-to-end (RIPE writeups, peer-reviewed
   papers, operator postmortems). **Do not** submit incidents based on
   secondary blogs, AI-generated lists, or the model's training data.
   See [`data/incidents/_README.md`](data/incidents/_README.md) for the
   hard rule and citation requirements.
2. Pull a focused window of real archive data (using
   `--filter "prefix any <supernet>"` keeps it fast).
3. Identify `onset_iso` from the **data**, not from secondary
   reporting. Match the documented public onset to the second.
4. Draft `data/incidents/<your_id>.json` and ensure the harness picks
   the right detectors (`expected_detectors`).
5. Run `netpulse benchmark replay` with the new fixture; if it fires,
   include the alert count + latency in your PR description.

## Tests

- New code under `src/netpulse/` always has a corresponding test in
  `tests/`.
- Integration tests that hit live external services (RIS, Atlas) are
  marked `@pytest.mark.integration` and excluded from the default test
  run; CI does not run them.

## Commit messages

Conventional-ish prefixes (`feat:`, `fix:`, `docs:`, `refactor:`,
`test:`, `ci:`, `deploy:`) help readability of `git log`. Body should
explain *why*, not what.

## Reporting bugs / asking questions

Open a GitHub issue with:

- What you ran (the exact command).
- What you expected.
- What you saw.
- The version (`uv run netpulse --version` once that lands; until
  then, the commit SHA).
