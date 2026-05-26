from __future__ import annotations

import json
from pathlib import Path

import pytest

from netpulse.benchmark.loader import load_incident, load_incidents


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload))


def _valid_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "test_hijack",
        "name": "Test hijack",
        "kind": "hijack",
        "start_iso": "2024-01-01T00:00:00Z",
        "end_iso": "2024-01-01T01:00:00Z",
        "expected_detectors": ["moas"],
        "source_url": "https://example.test/citation",
        "prefix": "192.0.2.0/24",
        "attacker_asn": 64600,
        "victim_asn": 64601,
        "notes": "synthetic test fixture",
        "verified": False,
    }
    base.update(overrides)
    return base


def test_load_incident_parses_iso_to_microseconds(tmp_path: Path) -> None:
    p = tmp_path / "test.json"
    _write(p, _valid_payload())

    inc = load_incident(p)

    # 2024-01-01T00:00:00Z = 1_704_067_200 epoch seconds
    assert inc.start_us == 1_704_067_200 * 1_000_000
    assert inc.end_us == 1_704_067_200 * 1_000_000 + 3600 * 1_000_000
    assert inc.kind == "hijack"
    assert inc.expected_detectors == ["moas"]


def test_load_incident_rejects_missing_field(tmp_path: Path) -> None:
    payload = _valid_payload()
    del payload["source_url"]
    p = tmp_path / "bad.json"
    _write(p, payload)

    with pytest.raises(ValueError, match="source_url"):
        load_incident(p)


def test_load_incident_rejects_bad_kind(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    _write(p, _valid_payload(kind="hurricane"))

    with pytest.raises(ValueError, match="kind"):
        load_incident(p)


def test_load_incident_rejects_inverted_window(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    _write(p, _valid_payload(end_iso="2023-12-31T23:00:00Z"))

    with pytest.raises(ValueError, match="end_iso"):
        load_incident(p)


def test_load_incidents_skips_underscore_files(tmp_path: Path) -> None:
    _write(tmp_path / "a.json", _valid_payload(id="a"))
    _write(tmp_path / "b.json", _valid_payload(id="b"))
    _write(tmp_path / "_TEMPLATE.json", _valid_payload(id="template"))

    incidents = load_incidents(tmp_path)

    assert sorted(i.id for i in incidents) == ["a", "b"]


def test_load_incidents_empty_directory(tmp_path: Path) -> None:
    assert load_incidents(tmp_path) == []


def test_youtube_fixture_loads() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    inc = load_incident(repo_root / "data" / "incidents" / "youtube_2008.json")
    assert inc.id == "youtube_2008"
    assert inc.kind == "hijack"
    assert inc.prefix == "208.65.153.0/24"
    assert inc.attacker_asn == 17557
    assert inc.victim_asn == 36561
    assert inc.verified is True
    assert inc.onset_us is not None
    # Onset must lie strictly within the search window.
    assert inc.start_us <= inc.onset_us < inc.end_us
