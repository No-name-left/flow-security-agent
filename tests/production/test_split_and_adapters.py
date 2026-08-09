from __future__ import annotations

from pathlib import Path

from flowsec.production.adapters import iot_labels, parse_zeek_log
from flowsec.production.config import load_production_config
from flowsec.production.core import choose_gap_seconds, chronological_split, sha256_file


CONFIG = Path("configs/data/production_freeze_v1.yaml")


def test_chronological_split_excludes_gap_and_boundary_crossers() -> None:
    assert chronological_split(0, 60, 0, 100, 10) == ("train", None)
    assert chronological_split(66, 72, 0, 100, 10)[0] == "quarantine"
    assert chronological_split(76, 79, 0, 100, 10) == ("validation", None)
    assert chronological_split(91, 95, 0, 100, 10) == ("test", None)


def test_gap_rule_is_model_independent_and_records_usability_clipping() -> None:
    value = choose_gap_seconds(
        capture_span=100,
        session_durations=[0.1, 0.2, 50],
        fixed_safety_seconds=5,
        long_session_quantile=0.999,
        max_gap_fraction=0.02,
    )
    assert value["requested_gap_seconds"] >= 5
    assert value["effective_gap_seconds"] == 2
    assert value["clipped_for_split_usability"] is True


def test_iot_adapter_accepts_both_detailed_label_spellings(tmp_path: Path) -> None:
    content = (
        "#separator \\x09\n"
        "#fields ts uid id.orig_h id.orig_p id.resp_h id.resp_p proto service duration "
        "orig_bytes resp_bytes conn_state local_orig local_resp missed_bytes history "
        "orig_pkts orig_ip_bytes resp_pkts resp_ip_bytes label det_label\n"
        "1.0 x 10.0.0.1 1 10.0.0.2 2 tcp - 1 1 1 S0 - - 0 S 1 41 1 41 Malicious Attack\n"
    )
    path = tmp_path / "det.log"
    path.write_text(content, encoding="utf-8")
    rows = list(parse_zeek_log(path))
    assert rows[0][1]["det_label"] == "Attack"
    config = load_production_config(CONFIG).iot23
    assert iot_labels(config, "Malicious", rows[0][1]["det_label"]) == (
        "Attack",
        "Exploitation",
    )


def test_somfy_and_capture42_limitations_remain_frozen() -> None:
    scenarios = {
        item["id"]: item for item in load_production_config(CONFIG).iot23["scenarios"]
    }
    assert scenarios["CTU-Honeypot-Capture-7-1-Somfy-01"]["anomaly"] == (
        "iot23_somfy_strict_match_limitation"
    )
    assert scenarios["CTU-IoT-Malware-Capture-42-1"]["role"] == "unknown_probe"
    assert scenarios["CTU-IoT-Malware-Capture-42-1"]["anomaly"] == (
        "iot23_capture42_truncated_tail"
    )


def test_source_hash_mismatch_is_detectable(tmp_path: Path) -> None:
    path = tmp_path / "source.bin"
    path.write_bytes(b"official")
    expected = sha256_file(path)
    path.write_bytes(b"changed")
    assert sha256_file(path) != expected
