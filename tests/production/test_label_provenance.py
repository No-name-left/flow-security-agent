from __future__ import annotations

from pathlib import Path

from flowsec.production.adapters import iot_labels
from flowsec.production.config import load_production_config
from flowsec.production.core import sha256_file
from flowsec.production.label_provenance import (
    CAPTURE_FAILURE,
    CAPTURE_FALLBACK_METHOD,
    CONFLICT_METHOD,
    DIRECT_EVIDENCE_POLICY,
    UNMATCHED_METHOD,
    assign_session_label,
    validate_edge_capture_provenance,
)


CONFIG = Path("configs/data/production_freeze_v1.yaml")


def _sources(tmp_path: Path, labels: list[tuple[str, str]]) -> tuple[Path, Path]:
    pcap = tmp_path / "capture.pcap"
    pcap.write_bytes(b"immutable-pcap-content")
    companion = tmp_path / "capture.csv"
    lines = ["frame.time,ip.src_host,ip.dst_host,Attack_label,Attack_type"]
    lines.extend(
        f"2021 00:00:0{index}.000000,10.0.0.1,10.0.0.2,{binary},{label}"
        for index, (binary, label) in enumerate(labels)
    )
    companion.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pcap, companion


def _validate(
    tmp_path: Path,
    labels: list[tuple[str, str]],
    *,
    expected_label: str = "Backdoor",
) -> dict[str, object]:
    pcap, companion = _sources(tmp_path, labels)
    return validate_edge_capture_provenance(
        capture_id="Attack_Backdoor",
        pcap_path=pcap,
        companion_csv_path=companion,
        expected_label=expected_label,
        expected_pcap_sha256=sha256_file(pcap),
        expected_companion_csv_sha256=sha256_file(companion),
        official_archive_verified=True,
        packet_count=len(labels),
    )


def test_pure_companion_and_matching_expected_label_pass(tmp_path: Path) -> None:
    provenance = _validate(tmp_path, [("1", "Backdoor"), ("1", "Backdoor")])
    assert provenance["status"] == "PASS"
    assert provenance["csv_label_purity"] == 1.0
    assert provenance["csv_observed_labels"] == [
        {"Attack_label": "1", "Attack_type": "Backdoor"}
    ]


def test_two_companion_labels_fail_capture_provenance(tmp_path: Path) -> None:
    provenance = _validate(tmp_path, [("1", "Backdoor"), ("1", "Password")])
    assert provenance["status"] == CAPTURE_FAILURE
    assert "companion_csv_not_single_label" in provenance["failure_reasons"]


def test_expected_capture_label_mismatch_fails(tmp_path: Path) -> None:
    provenance = _validate(
        tmp_path, [("1", "Password"), ("1", "Password")]
    )
    assert provenance["status"] == CAPTURE_FAILURE
    assert "expected_capture_label_mismatch" in provenance["failure_reasons"]


def test_unanimous_direct_evidence_assigns_direct_label(tmp_path: Path) -> None:
    provenance = _validate(tmp_path, [("1", "Backdoor")])
    decision = assign_session_label(
        expected_label="Backdoor",
        capture_provenance=provenance,
        direct_labels=["Backdoor", "Backdoor"],
        session_capture_id="Attack_Backdoor",
    )
    assert decision["assigned_label"] == "Backdoor"
    assert decision["direct_evidence_count"] == 2
    assert decision["label_assignment_method"] == DIRECT_EVIDENCE_POLICY
    assert decision["quarantined"] is False


def test_conflicting_direct_evidence_is_quarantined(tmp_path: Path) -> None:
    provenance = _validate(tmp_path, [("1", "Backdoor")])
    decision = assign_session_label(
        expected_label="Backdoor",
        capture_provenance=provenance,
        direct_labels=["Backdoor", "Password"],
        session_capture_id="Attack_Backdoor",
    )
    assert decision["assigned_label"] is None
    assert decision["label_assignment_method"] == CONFLICT_METHOD
    assert decision["quarantined"] is True


def test_zero_direct_evidence_uses_verified_capture_fallback(tmp_path: Path) -> None:
    provenance = _validate(tmp_path, [("1", "Backdoor")])
    decision = assign_session_label(
        expected_label="Backdoor",
        capture_provenance=provenance,
        direct_labels=[],
        session_capture_id="Attack_Backdoor",
    )
    assert decision["assigned_label"] == "Backdoor"
    assert decision["label_assignment_method"] == CAPTURE_FALLBACK_METHOD
    assert decision["quarantined"] is False


def test_zero_direct_evidence_with_unverified_capture_is_quarantined(
    tmp_path: Path,
) -> None:
    provenance = _validate(tmp_path, [("1", "Backdoor"), ("1", "Password")])
    decision = assign_session_label(
        expected_label="Backdoor",
        capture_provenance=provenance,
        direct_labels=[],
        session_capture_id="Attack_Backdoor",
    )
    assert decision["assigned_label"] is None
    assert decision["label_assignment_method"] == UNMATCHED_METHOD
    assert decision["quarantined"] is True


def test_session_cannot_cross_capture(tmp_path: Path) -> None:
    provenance = _validate(tmp_path, [("1", "Backdoor")])
    decision = assign_session_label(
        expected_label="Backdoor",
        capture_provenance=provenance,
        direct_labels=[],
        session_capture_id="Attack_Password",
    )
    assert decision["quarantined"] is True
    assert decision["reason"] == "session_capture_mismatch"


def test_yaml_label_alone_cannot_bypass_provenance_guard() -> None:
    decision = assign_session_label(
        expected_label="Backdoor",
        capture_provenance=None,
        direct_labels=[],
        session_capture_id="Attack_Backdoor",
    )
    assert decision["assigned_label"] is None
    assert decision["label_assignment_method"] == UNMATCHED_METHOD
    assert decision["quarantined"] is True


def test_iot_adapter_label_behavior_is_unchanged() -> None:
    config = load_production_config(CONFIG).iot23
    assert iot_labels(config, "Benign", "-") == ("Benign", "Benign")
    assert iot_labels(config, "Malicious", "Attack") == (
        "Attack",
        "Exploitation",
    )
