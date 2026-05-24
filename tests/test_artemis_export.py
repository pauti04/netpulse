"""Smoke tests for the ARTEMIS comparison scaffolding.

We don't run ARTEMIS itself in CI -- that needs Docker -- but we can
check that the config exporter emits structurally valid YAML for any
incident in the corpus, and that the comparison runner handles
NetPulse-only / ARTEMIS-only / both-present cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"

# Make the script importable as a module without installing it.
sys.path.insert(0, str(SCRIPTS))

import artemis_compare  # noqa: E402
import artemis_export_config  # noqa: E402

# ----- Config exporter -----


@pytest.fixture
def youtube_incident_path() -> Path:
    p = REPO_ROOT / "data" / "incidents" / "youtube_pakistan_2008.json"
    if not p.exists():
        pytest.skip("youtube incident not present in this checkout")
    return p


@pytest.fixture
def indosat_incident_path() -> Path:
    p = REPO_ROOT / "data" / "incidents" / "indosat_2014.json"
    if not p.exists():
        pytest.skip("indosat incident not present in this checkout")
    return p


def test_export_emits_valid_yaml(youtube_incident_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "youtube.yaml"
    artemis_export_config.export(youtube_incident_path, out)
    blob = yaml.safe_load(out.read_text())
    assert "prefixes" in blob
    assert "asns" in blob
    assert "rules" in blob
    # Every rule must have prefixes + origin_asns.
    for rule in blob["rules"]:
        assert "prefixes" in rule
        assert "origin_asns" in rule
        assert isinstance(rule["prefixes"], list) and rule["prefixes"]
        assert isinstance(rule["origin_asns"], list) and rule["origin_asns"]


def test_export_indosat_includes_all_baseline_origins(
    indosat_incident_path: Path, tmp_path: Path
) -> None:
    out = tmp_path / "indosat.yaml"
    artemis_export_config.export(indosat_incident_path, out)
    blob = yaml.safe_load(out.read_text())
    # Indosat baseline carries three legitimate origins:
    # 45305, 45348, 45454. All three should be declared.
    asns = blob["asns"]
    assert set(asns.keys()) == {"as45305", "as45348", "as45454"}


def test_export_rejects_missing_baseline(tmp_path: Path) -> None:
    fake = tmp_path / "no_baseline.json"
    fake.write_text(
        json.dumps(
            {
                "id": "x",
                "name": "x",
                "kind": "hijack",
                "start_iso": "2024-01-01T00:00:00Z",
                "end_iso": "2024-01-01T01:00:00Z",
                "expected_detectors": ["subprefix_hijack"],
                "source_url": "https://example.com",
                "prefix": None,
                "attacker_asn": 0,
                "victim_asn": 0,
                "notes": "test",
                "verified": False,
            }
        )
    )
    with pytest.raises(SystemExit):
        artemis_export_config.export(fake, tmp_path / "out.yaml")


# ----- Comparison runner -----


def test_compare_handles_netpulse_only(tmp_path: Path) -> None:
    netpulse_path = tmp_path / "corpus.json"
    netpulse_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "incident_id": "youtube_pakistan_2008",
                        "outcome": "TP",
                        "on_target_alerts": 1,
                        "other_alerts": 0,
                    }
                ]
            }
        )
    )
    rows = artemis_compare.compare(netpulse_path, [])
    assert len(rows) == 1
    r = rows[0]
    assert r.incident_id == "youtube_pakistan_2008"
    assert r.netpulse_outcome == "TP"
    assert r.artemis_fired is False
    assert r.artemis_alerts == 0
    assert "no ARTEMIS replay" in r.notes


def test_compare_handles_artemis_only(tmp_path: Path) -> None:
    netpulse_path = tmp_path / "corpus.json"
    netpulse_path.write_text(json.dumps({"results": []}))
    artemis_path = tmp_path / "extra_2024.json"
    artemis_path.write_text(json.dumps([{"hijack_type": "S|0|-|-"}, {"hijack_type": "E|0|-|-"}]))
    rows = artemis_compare.compare(netpulse_path, [artemis_path])
    assert len(rows) == 1
    r = rows[0]
    assert r.netpulse_outcome == "MISSING"
    assert r.artemis_fired is True
    assert r.artemis_alerts == 2
    assert set(r.artemis_hijack_types) == {"S|0|-|-", "E|0|-|-"}


def test_compare_handles_both_present(tmp_path: Path) -> None:
    netpulse_path = tmp_path / "corpus.json"
    netpulse_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "incident_id": "indosat_2014",
                        "outcome": "TP",
                        "on_target_alerts": 19,
                        "other_alerts": 0,
                    }
                ]
            }
        )
    )
    artemis_path = tmp_path / "indosat_2014.json"
    artemis_path.write_text(json.dumps([{"hijack_type": "E|0|-|-"}]))
    rows = artemis_compare.compare(netpulse_path, [artemis_path])
    r = rows[0]
    assert r.incident_id == "indosat_2014"
    assert r.netpulse_outcome == "TP"
    assert r.netpulse_on_target == 19
    assert r.artemis_fired is True
    assert r.artemis_alerts == 1
    assert r.notes == ""
