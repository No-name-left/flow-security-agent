from __future__ import annotations

from pathlib import Path

from flowsec.production.schema import canonical_json
from flowsec.production.split_revision import (
    Boundary,
    PHASE_A_POLICY_ORDER,
    SPLIT_POLICY_ID,
    assign_constrained_split,
    audit_phase_a_split_candidates,
    build_paper_readiness,
    build_sft_candidate_manifests,
    choose_constrained_boundary,
    install_revision_overlay,
    paper_support_status,
)
from flowsec.production.storage import CATALOG_COLUMNS, ProductionCatalog


def _row(
    index: int,
    *,
    label: str = "ClassA",
    split: str = "train",
    capture: str = "capture-a",
) -> dict[str, object]:
    row: dict[str, object] = {
        "sample_id": f"fs1_revision_{index:040d}",
        "dataset": "Edge-IIoTset",
        "dataset_version": "v1",
        "capture_id": capture,
        "source_hash": "a" * 64,
        "source_file": "source.pcap",
        "timestamp_start": float(index),
        "timestamp_end": float(index) + 0.25,
        "raw_initiator_ip": "10.0.0.1",
        "raw_responder_ip": "10.0.0.2",
        "raw_initiator_port": 1000,
        "raw_responder_port": 80,
        "l3_protocol": "IPv4",
        "l4_protocol": "TCP",
        "first_frame": index,
        "last_frame": index,
        "fine_label": label,
        "coarse_label": "ParentA",
        "base_split": split,
        "packet_sequence_json": canonical_json([{"packet_length": 40 + index}]),
        "session_summary_json": canonical_json({"duration": 0.25}),
        "capabilities_json": "[]",
        "missing_fields_json": "[]",
        "anomaly_ids_json": "[]",
        "original_label": label,
        "evidence_signature": f"exact-{index % 80}",
        "exact_signature": f"backend-{index}",
        "reverse_signature": f"reverse-{index}",
        "near_signature": f"near-{index % 40}",
        "source_identity_hash": f"source-{index}",
        "destination_identity_hash": "destination",
        "communication_pair_hash": f"pair-{index}",
        "source_verified": 1,
        "retained": 1,
        "exclusion_reason": "",
    }
    assert set(row) == set(CATALOG_COLUMNS)
    return row


def test_paper_support_status_thresholds() -> None:
    assert paper_support_status(0) == "ZERO"
    assert paper_support_status(1) == "CRITICAL_LOW"
    assert paper_support_status(29) == "CRITICAL_LOW"
    assert paper_support_status(30) == "LOW"
    assert paper_support_status(99) == "LOW"
    assert paper_support_status(100) == "ADEQUATE"


def test_constrained_split_quarantines_crossing_and_local_embargo() -> None:
    common = {
        "first_boundary": 70.0,
        "second_boundary": 85.0,
        "local_embargo_seconds": 5.0,
    }
    assert assign_constrained_split(
        timestamp_start=0.0, timestamp_end=67.5, **common
    ) == ("train", "")
    assert assign_constrained_split(
        timestamp_start=67.0, timestamp_end=71.0, **common
    )[0] == "quarantine"
    assert assign_constrained_split(
        timestamp_start=72.5, timestamp_end=82.5, **common
    ) == ("validation", "")
    assert assign_constrained_split(
        timestamp_start=87.5, timestamp_end=90.0, **common
    ) == ("test", "")


def test_boundary_search_is_deterministic_and_session_complete() -> None:
    rows = [
        (float(index), float(index) + (10.0 if index in {70, 85} else 0.1), f"e{index}", f"n{index % 40}")
        for index in range(200)
    ]
    first = choose_constrained_boundary(
        capture_id="capture", fine_label="ClassA", rows=rows
    )
    second = choose_constrained_boundary(
        capture_id="capture", fine_label="ClassA", rows=list(reversed(rows))
    )
    assert first == second
    assert first.first_timestamp < first.second_timestamp
    for start, end, _, _ in rows:
        split, _ = assign_constrained_split(
            timestamp_start=start,
            timestamp_end=end,
            first_boundary=first.first_timestamp,
            second_boundary=first.second_timestamp,
            local_embargo_seconds=first.local_embargo_seconds,
        )
        assert split in {"train", "validation", "test", "quarantine"}


def test_overlay_changes_only_split_fields_and_preserves_main_catalog(
    tmp_path: Path,
) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records(_row(index) for index in range(200))
        original = catalog.query(
            "SELECT sample_id,base_split,retained FROM main.records ORDER BY sample_id"
        )
        boundary = Boundary(
            capture_id="capture-a",
            fine_label="ClassA",
            first_timestamp=70.0,
            second_timestamp=85.0,
            first_anchor_fraction=0.70,
            second_anchor_fraction=0.85,
            local_embargo_seconds=5.0,
            source_session_count=200,
            search_applied=False,
        )
        manifest = install_revision_overlay(
            catalog,
            dataset="Edge-IIoTset",
            boundaries={"capture-a": boundary},
            assignment_root=None,
        )
        revised = catalog.query(
            "SELECT sample_id,base_split,retained FROM records ORDER BY sample_id"
        )
        main_after = catalog.query(
            "SELECT sample_id,base_split,retained FROM main.records ORDER BY sample_id"
        )

        assert manifest["policy"] == SPLIT_POLICY_ID
        assert [row[0] for row in revised] == [row[0] for row in original]
        assert revised != original
        assert main_after == original
        assert catalog.scalar(
            "SELECT COUNT(*)-COUNT(DISTINCT sample_id) FROM records"
        ) == 0
    finally:
        catalog.close()


def test_paper_gate_and_sft_candidates_use_known_train_only(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        rows = []
        for index in range(360):
            split = "train" if index < 160 else "validation" if index < 260 else "test"
            rows.append(_row(index, split=split))
        for index in range(360, 390):
            rows.append(_row(index, label="UnknownDev", split="validation"))
        for index in range(390, 420):
            rows.append(_row(index, label="UnknownFinal", split="test"))
        catalog.insert_records(rows)
        presets = {
            "Near": {
                "K_known": ["ClassA"],
                "U_dev": ["UnknownDev"],
                "U_final": ["UnknownFinal"],
            }
        }
        paper = build_paper_readiness(
            catalog=catalog, dataset="Edge-IIoTset", edge_presets=presets
        )
        sft = build_sft_candidate_manifests(
            catalog=catalog,
            dataset="Edge-IIoTset",
            edge_presets=presets,
            output_root=None,
            selected_plan="PLAN_B",
        )

        assert paper["PAPER_EVALUATION_READINESS_GATE"] == "FAIL"
        selected = sft["plans"]["Near"]["PLAN_B"]
        assert selected["classes"][0]["class"] == "ClassA"
        assert selected["classes"][0]["raw_train_sessions"] == 160
        assert selected["duplicate_sample_ids"] == 0
        assert {item["class"] for item in selected["classes"]} == {"ClassA"}
    finally:
        catalog.close()



def test_phase_a_candidate_audit_is_read_only_and_complete(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        rows = []
        for index in range(200):
            split = "train" if index < 120 else "validation" if index < 160 else "test"
            rows.append(_row(index, split=split))
        catalog.insert_records(rows)
        before = catalog.query(
            "SELECT sample_id,base_split,retained FROM main.records ORDER BY sample_id"
        )
        selected = {
            "capture-a": Boundary(
                capture_id="capture-a",
                fine_label="ClassA",
                first_timestamp=140.0,
                second_timestamp=170.0,
                first_anchor_fraction=0.70,
                second_anchor_fraction=0.85,
                local_embargo_seconds=5.0,
                source_session_count=200,
                search_applied=False,
            )
        }
        report = audit_phase_a_split_candidates(
            catalog=catalog,
            dataset="Edge-IIoTset",
            selected_boundaries=selected,
        )
        after = catalog.query(
            "SELECT sample_id,base_split,retained FROM main.records ORDER BY sample_id"
        )

        assert report["audit_mode"] == "READ_ONLY_SINGLE_PASS_NO_ASSET_REBUILD"
        assert report["candidate_order"] == list(PHASE_A_POLICY_ORDER)
        assert report["source_rows"] == 200
        assert set(report["candidates"]) == set(PHASE_A_POLICY_ORDER)
        assert all(
            value["identity_cross_split_leakage"] == 0
            for value in report["candidates"].values()
        )
        assert before == after
    finally:
        catalog.close()
