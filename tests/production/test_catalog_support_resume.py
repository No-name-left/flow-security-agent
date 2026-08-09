from __future__ import annotations

from pathlib import Path

from flowsec.production.adapters import AdapterResult
from flowsec.production.config import load_production_config
from flowsec.production.freeze import (
    _load_checkpoint,
    _save_checkpoint,
    _support_manifests,
)
from flowsec.production.manifests import build_support_entry
from flowsec.production.readiness import build_class_role_support_gate
from flowsec.production.readiness import validate_current_run_identity
from flowsec.production.schema import canonical_json, content_hash
from flowsec.production.sensitivity import build_evaluation_clean_variants
from flowsec.production.storage import CATALOG_COLUMNS, ProductionCatalog


def _row(index: int, *, label: str = "Novel", split: str = "test") -> dict[str, object]:
    values: dict[str, object] = {
        "sample_id": f"fs1_{index:040d}",
        "dataset": "Edge-IIoTset",
        "dataset_version": "v1",
        "capture_id": "capture",
        "source_hash": "a" * 64,
        "source_file": "source.pcap",
        "timestamp_start": float(index),
        "timestamp_end": float(index) + 0.1,
        "raw_initiator_ip": f"10.0.0.{index % 250 + 1}",
        "raw_responder_ip": "10.1.0.1",
        "raw_initiator_port": 1000 + index,
        "raw_responder_port": 80,
        "l3_protocol": "IPv4",
        "l4_protocol": "TCP",
        "first_frame": index,
        "last_frame": index,
        "fine_label": label,
        "coarse_label": "NovelParent",
        "base_split": split,
        "packet_sequence_json": canonical_json([{"packet_length": index + 40}]),
        "session_summary_json": canonical_json(
            {
                "duration": 0.1,
                "initiator_packets": 1,
                "responder_packets": 0,
                "initiator_bytes": index + 40,
                "responder_bytes": 0,
                "packet_length_stats": {"min": index + 40, "max": index + 40, "mean": index + 40, "std": 0},
                "iat_stats": {"min": 0, "max": 0, "mean": 0, "std": 0},
                "handshake_state": "INCOMPLETE_HANDSHAKE",
                "service_category": "HTTP",
                "service_category_source": "iana_port_category_map_v1",
            }
        ),
        "capabilities_json": "[]",
        "missing_fields_json": "[]",
        "anomaly_ids_json": "[]",
        "original_label": label,
        "evidence_signature": f"e{index}",
        "exact_signature": f"x{index}",
        "reverse_signature": f"r{index}",
        "near_signature": f"n{index}",
        "source_identity_hash": f"s{index}",
        "destination_identity_hash": "d",
        "communication_pair_hash": f"p{index}",
        "source_verified": 1,
        "retained": 1,
        "exclusion_reason": "",
    }
    assert set(values) == set(CATALOG_COLUMNS)
    return values


def test_support_query_is_disjoint_and_nested(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records(_row(index) for index in range(1200))
        value = build_support_entry(
            catalog,
            dataset="Edge-IIoTset",
            label_column="fine_label",
            label="Novel",
            split="test",
            seed=20260809,
            shots=[1, 5, 10],
            query_cap=100,
        )
        one = set(value["1_shot"]["support_sample_ids"])
        five = set(value["5_shot"]["support_sample_ids"])
        ten = set(value["10_shot"]["support_sample_ids"])
        query = set(value["query_sample_ids"])
        assert one <= five <= ten
        assert not ten & query
        assert len(query) == 100
    finally:
        catalog.close()


def test_support_falls_back_from_near_diversity_without_exact_duplicates(
    tmp_path: Path,
) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        rows = [_row(index) for index in range(40)]
        for row in rows:
            row["near_signature"] = "same-near-group"
        catalog.insert_records(rows)
        value = build_support_entry(
            catalog,
            dataset="Edge-IIoTset",
            label_column="fine_label",
            label="Novel",
            split="test",
            seed=20260809,
            shots=[1, 5, 10],
            query_cap=20,
        )
        support = set(value["10_shot"]["support_sample_ids"])
        query = set(value["query_sample_ids"])
        assert value["10_shot"]["status"] == "READY"
        assert len(support) == 10
        assert len(query) == 20
        assert not support & query
        assert value["support_query_exact_duplicate"] == 0
        assert value["support_query_reverse_duplicate"] == 0
        assert value["support_near_duplicate_count"] == 9
        assert value["support_query_near_duplicate"] == 20
    finally:
        catalog.close()


def test_support_capacity_is_applied_after_exact_evidence_diversity(
    tmp_path: Path,
) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        rows = [_row(index) for index in range(5020)]
        for row in rows[:5000]:
            row["evidence_signature"] = "high-frequency-view"
        catalog.insert_records(rows)
        value = build_support_entry(
            catalog,
            dataset="Edge-IIoTset",
            label_column="fine_label",
            label="Novel",
            split="test",
            seed=20260809,
            shots=[1, 5, 10],
            query_cap=5,
        )

        assert value["available_unique_candidates"] == 21
        assert value["10_shot"]["status"] == "READY"
        assert value["query_count"] == 5
    finally:
        catalog.close()


def test_iot_support_manifest_uses_formal_coarse_u_final_label(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        rows = [_row(index, label="Attack", split="unknown_final") for index in range(30)]
        for row in rows:
            row["dataset"] = "IoT-23"
            row["coarse_label"] = "Exploitation"
        catalog.insert_records(rows)
        config = load_production_config(Path("configs/data/production_freeze_v1.yaml"))

        _, iot = _support_manifests(config, catalog, {})
        classes = iot["presets"]["iot23_external_validation_v1"]["classes"]

        assert iot["task_label_level"] == "coarse_label"
        assert iot["native_fine_labels"] == ["Attack"]
        assert set(classes) == {"Exploitation"}
        assert classes["Exploitation"]["label"] == "Exploitation"
        assert classes["Exploitation"]["5_shot"]["status"] == "READY"
    finally:
        catalog.close()


def test_distinct_backend_sessions_with_identical_model_view_are_retained(
    tmp_path: Path,
) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        train = _row(1, label="ClassA", split="train")
        test = _row(2, label="ClassA", split="test")
        train["evidence_signature"] = test["evidence_signature"] = "same-view"
        catalog.insert_records([train, test])

        result = catalog.apply_identity_deduplication()

        assert catalog.scalar("SELECT COUNT(*) FROM records WHERE retained=1") == 2
        assert result["identity_duplicate_count"] == 0
        assert result["exact_model_view_collision_groups"] == 1
    finally:
        catalog.close()


def test_same_backend_identity_repeated_twice_retains_exactly_one(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        first = _row(1, label="ClassA", split="train")
        repeated = dict(first)
        catalog.insert_records([first, repeated])

        result = catalog.apply_identity_deduplication()
        states = catalog.query(
            "SELECT retained,exclusion_reason FROM records ORDER BY record_id"
        )

        assert result["identity_duplicate_groups"] == 1
        assert result["identity_duplicate_count"] == 1
        assert states == [(1, ""), (0, "identity_duplicate")]
    finally:
        catalog.close()


def test_same_backend_identity_with_conflicting_labels_is_quarantined(
    tmp_path: Path,
) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        first = _row(1, label="ClassA", split="train")
        conflict = dict(first)
        conflict["fine_label"] = "ClassB"
        conflict["coarse_label"] = "OtherParent"
        catalog.insert_records([first, conflict])

        result = catalog.apply_identity_deduplication()
        rows = catalog.query(
            "SELECT retained,exclusion_reason FROM records ORDER BY record_id"
        )

        assert result["identity_label_conflict_groups"] == 1
        assert result["identity_label_conflict_count"] == 2
        assert rows == [
            (0, "identity_label_conflict"),
            (0, "identity_label_conflict"),
        ]
    finally:
        catalog.close()


def test_distinct_identities_with_same_view_and_different_labels_are_retained(
    tmp_path: Path,
) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        first = _row(1, label="ClassA", split="validation")
        second = _row(2, label="ClassB", split="test")
        second["coarse_label"] = "OtherParent"
        first["evidence_signature"] = second["evidence_signature"] = "ambiguous-view"
        catalog.insert_records([first, second])

        result = catalog.apply_identity_deduplication()

        assert catalog.scalar("SELECT COUNT(*) FROM records WHERE retained=1") == 2
        assert result["identity_label_conflict_count"] == 0
        assert result["view_label_collision_groups"] == 1
        assert result["view_label_collision_count"] == 2
    finally:
        catalog.close()


def test_exact_and_near_eval_clean_leave_training_unchanged(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        rows = [
            _row(1, split="train"),
            _row(2, split="train"),
            _row(3, split="validation"),
            _row(4, split="validation"),
            _row(5, split="validation"),
            _row(6, split="test"),
            _row(7, split="test"),
        ]
        signatures = [
            ("exact-a", "near-a"),
            ("exact-train-only", "near-train"),
            ("exact-a", "near-x"),
            ("exact-b", "near-train"),
            ("exact-c", "near-c"),
            ("exact-c", "near-y"),
            ("exact-d", "near-c"),
        ]
        for row, (exact_view, near) in zip(rows, signatures):
            row["evidence_signature"] = exact_view
            row["near_signature"] = near
        catalog.insert_records(rows)
        catalog.apply_identity_deduplication()

        manifest = build_evaluation_clean_variants(
            catalog=catalog,
            output_root=tmp_path / "assets",
            processing={"parquet_compression": "zstd", "parquet_shard_rows": 2},
        )

        exact = manifest["variants"]["EXACT_EVAL_CLEAN"]["counts"]["Edge-IIoTset"]
        near = manifest["variants"]["NEAR_EVAL_CLEAN"]["counts"]["Edge-IIoTset"]
        assert exact["primary"] == {"train": 2, "validation": 3, "test": 2}
        assert exact["excluded"] == {"train": 0, "validation": 1, "test": 1}
        assert exact["effective"] == {"train": 2, "validation": 2, "test": 1}
        assert near["excluded"] == {"train": 0, "validation": 1, "test": 1}
        assert near["effective"] == {"train": 2, "validation": 2, "test": 1}
        assert exact["train_unchanged"] is True
        assert near["train_unchanged"] is True
        assert manifest["superseded_variant"]["SUPERSEDED_BEFORE_ANY_MODEL_RUN"] is True
    finally:
        catalog.close()


def _ready_support_entry(index: int = 900) -> dict[str, object]:
    support_ids = [f"fs1_{index + offset:040d}" for offset in range(10)]
    value: dict[str, object] = {
        "shots_requested": [1, 5, 10],
        "query_sample_ids": [f"fs1_{index + 10:040d}"],
        "query_count": 1,
        "query_cap_requested": 1,
        "support_query_overlap": 0,
        "support_query_exact_duplicate": 0,
        "support_query_reverse_duplicate": 0,
    }
    for shot in (1, 5, 10):
        value[f"{shot}_shot"] = {
            "status": "READY",
            "support_sample_ids": support_ids[:shot],
            "support_count": shot,
        }
    return value


def _edge_training(
    *,
    known: list[str] | None = None,
    udev: list[str] | None = None,
    ufinal: list[str] | None = None,
) -> dict[str, object]:
    known = known or ["Known"]
    udev = udev or ["Dev"]
    ufinal = ufinal or ["Final"]

    def asset(
        role: str,
        split: str,
        labels: list[str],
        ku_role: str,
        development_visible: bool,
        allowed_labels: list[str],
    ) -> dict[str, object]:
        return {
            "preset": "P",
            "role": role,
            "split": split,
            "sample_ids": {
                "dataset": "Edge-IIoTset",
                "filter": {"split": split, "fine_label_in": labels},
            },
            "allowed_labels": allowed_labels,
            "ku_role": ku_role,
            "development_visible": development_visible,
        }

    return {
        "dataset": "Edge-IIoTset",
        "assets": [
            asset("sft_train", "train", known, "K_known", True, known),
            asset("sft_validation", "validation", known, "K_known", True, known),
            asset("closed_test", "test", known, "K_known", False, known),
            asset("unknown_development", "validation", udev, "U_dev", True, []),
            asset("final_unknown", "test", ufinal, "U_final", False, []),
        ],
    }


def _iot_training() -> dict[str, object]:
    known = ["Benign", "CommandAndControl"]

    def asset(
        role: str,
        split: str,
        labels: list[str],
        ku_role: str,
        development_visible: bool,
        allowed_labels: list[str],
    ) -> dict[str, object]:
        return {
            "role": role,
            "split": split,
            "sample_ids": {
                "dataset": "IoT-23",
                "filter": {"split": split, "coarse_label_in": labels},
            },
            "allowed_labels": allowed_labels,
            "ku_role": ku_role,
            "development_visible": development_visible,
        }

    return {
        "dataset": "IoT-23",
        "task_label_level": "coarse_label",
        "assets": [
            asset("sft_train", "train", known, "K_known", True, known),
            asset("sft_validation", "validation", known, "K_known", True, known),
            asset("scenario_held_closed_test", "test", known, "K_known", False, known),
            asset("unknown_development", "unknown_dev", ["Reconnaissance"], "U_dev", True, []),
            asset("final_unknown", "unknown_final", ["Exploitation"], "U_final", False, []),
        ],
    }


def _insert_iot_gate_rows(catalog: ProductionCatalog, start: int = 100) -> None:
    rows = []
    index = start
    for label in ("Benign", "CommandAndControl"):
        for split in ("train", "validation", "test"):
            row = _row(index, label=label, split=split)
            row["dataset"] = "IoT-23"
            row["coarse_label"] = label
            rows.append(row)
            index += 1
    for label, split in (("Reconnaissance", "unknown_dev"), ("Exploitation", "unknown_final")):
        row = _row(index, label=label, split=split)
        row["dataset"] = "IoT-23"
        row["coarse_label"] = label
        rows.append(row)
        index += 1
    catalog.insert_records(rows)


def _iot_gate_inputs() -> tuple[dict[str, object], dict[str, object]]:
    preset: dict[str, object] = {
        "id": "iot",
        "k_known": ["Benign", "CommandAndControl"],
        "u_dev": ["Reconnaissance"],
        "u_final": ["Exploitation"],
    }
    support: dict[str, object] = {
        "task_label_level": "coarse_label",
        "presets": {"iot": {"classes": {"Exploitation": _ready_support_entry(950)}}}
    }
    return preset, support


def test_k_known_missing_train_fails_readiness(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records(
            [
                _row(1, label="Known", split="validation"),
                _row(2, label="Known", split="test"),
                _row(3, label="Dev", split="validation"),
                _row(4, label="Final", split="test"),
            ]
        )
        _insert_iot_gate_rows(catalog)
        iot_preset, iot_support = _iot_gate_inputs()
        gate = build_class_role_support_gate(
            catalog=catalog,
            edge_dataset="Edge-IIoTset",
            edge_presets={"P": {"K_known": ["Known"], "U_dev": ["Dev"], "U_final": ["Final"]}},
            edge_support={"presets": {"P": {"classes": {"Final": _ready_support_entry()}}}},
            edge_training=_edge_training(),
            iot_dataset="IoT-23",
            iot_preset=iot_preset,
            iot_support=iot_support,
            iot_training=_iot_training(),
        )

        assert gate["CLASS_ROLE_SUPPORT_GATE"] == "FAIL"
        assert any(item["code"] == "K_KNOWN_SUPPORT_FAIL" for item in gate["failures"])
    finally:
        catalog.close()


def test_u_final_insufficient_support_query_fails_variant_not_base(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records(
            [
                _row(1, label="Known", split="train"),
                _row(2, label="Known", split="validation"),
                _row(3, label="Known", split="test"),
                _row(4, label="Dev", split="validation"),
                _row(5, label="Final", split="test"),
            ]
        )
        _insert_iot_gate_rows(catalog)
        iot_preset, iot_support = _iot_gate_inputs()
        insufficient = _ready_support_entry()
        insufficient["1_shot"] = {
            "status": "INSUFFICIENT_SUPPORT",
            "support_sample_ids": [],
            "support_count": 0,
        }
        gate = build_class_role_support_gate(
            catalog=catalog,
            edge_dataset="Edge-IIoTset",
            edge_presets={"P": {"K_known": ["Known"], "U_dev": ["Dev"], "U_final": ["Final"]}},
            edge_support={"presets": {"P": {"classes": {"Final": insufficient}}}},
            edge_training=_edge_training(),
            iot_dataset="IoT-23",
            iot_preset=iot_preset,
            iot_support=iot_support,
            iot_training=_iot_training(),
        )

        assert gate["CLASS_ROLE_SUPPORT_GATE"] == "PASS"
        assert gate["BASE_PRODUCTION_READY"] is True
        assert gate["FEW_SHOT_VARIANT_READY"] is False
        assert any(item["code"] == "FEW_SHOT_VARIANT_NOT_READY" for item in gate["variant_failures"])
    finally:
        catalog.close()


def _passing_gate_inputs(catalog: ProductionCatalog) -> dict[str, object]:
    _insert_iot_gate_rows(catalog)
    iot_preset, iot_support = _iot_gate_inputs()
    return {
        "catalog": catalog,
        "edge_dataset": "Edge-IIoTset",
        "edge_presets": {"P": {"K_known": ["Known"], "U_dev": ["Dev"], "U_final": ["Final"]}},
        "edge_support": {"presets": {"P": {"classes": {"Final": _ready_support_entry()}}}},
        "edge_training": _edge_training(),
        "iot_dataset": "IoT-23",
        "iot_preset": iot_preset,
        "iot_support": iot_support,
        "iot_training": _iot_training(),
    }


def test_edge_missing_per_class_validation_is_reported_not_base_blocker(
    tmp_path: Path,
) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records(
            [
                _row(1, label="Known", split="train"),
                _row(2, label="Known", split="test"),
                _row(3, label="Dev", split="validation"),
                _row(4, label="Final", split="test"),
            ]
        )
        gate = build_class_role_support_gate(**_passing_gate_inputs(catalog))

        assert gate["CLASS_ROLE_SUPPORT_GATE"] == "PASS"
        limitation = next(
            row for row in gate["class_role_matrix"]
            if row["dataset"] == "Edge-IIoTset"
            and row["class"] == "Known"
            and row["physical_split"] == "validation"
        )
        assert limitation["status"] == "LIMITATION"
        assert limitation["hard_for_base"] is False
    finally:
        catalog.close()


def test_u_final_physical_train_presence_is_not_logical_leak(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records(
            [
                _row(1, label="Known", split="train"),
                _row(2, label="Known", split="validation"),
                _row(3, label="Known", split="test"),
                _row(4, label="Dev", split="validation"),
                _row(5, label="Final", split="train"),
                _row(6, label="Final", split="test"),
            ]
        )
        gate = build_class_role_support_gate(**_passing_gate_inputs(catalog))

        assert gate["CLASS_ROLE_SUPPORT_GATE"] == "PASS"
        assert gate["edge"]["P"]["development_isolation"] == "PASS"
    finally:
        catalog.close()


def test_u_final_logical_training_visibility_fails_gate(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records(
            [
                _row(1, label="Known", split="train"),
                _row(2, label="Known", split="validation"),
                _row(3, label="Known", split="test"),
                _row(4, label="Dev", split="validation"),
                _row(5, label="Final", split="test"),
            ]
        )
        inputs = _passing_gate_inputs(catalog)
        training = inputs["edge_training"]
        assert isinstance(training, dict)
        train_asset = next(
            asset for asset in training["assets"] if asset["role"] == "sft_train"
        )
        train_asset["sample_ids"]["filter"]["fine_label_in"].append("Final")
        inputs["edge_training"] = training
        gate = build_class_role_support_gate(**inputs)

        assert gate["CLASS_ROLE_SUPPORT_GATE"] == "FAIL"
        assert any(item["code"] == "U_FINAL_DEVELOPMENT_LEAK" for item in gate["failures"])
    finally:
        catalog.close()


def test_iot_raw_fine_label_cannot_replace_formal_coarse_label(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records(
            [
                _row(1, label="Known", split="train"),
                _row(2, label="Known", split="validation"),
                _row(3, label="Known", split="test"),
                _row(4, label="Dev", split="validation"),
                _row(5, label="Final", split="test"),
            ]
        )
        inputs = _passing_gate_inputs(catalog)
        training = inputs["iot_training"]
        support = inputs["iot_support"]
        assert isinstance(training, dict) and isinstance(support, dict)
        training["task_label_level"] = "fine_label"
        support["task_label_level"] = "fine_label"
        gate = build_class_role_support_gate(**inputs)

        assert gate["CLASS_ROLE_SUPPORT_GATE"] == "FAIL"
        assert any(item["code"] == "CANONICAL_LABEL_SPACE_FAIL" for item in gate["failures"])
    finally:
        catalog.close()


def test_empty_support_query_is_never_silently_variant_ready(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records(
            [
                _row(1, label="Known", split="train"),
                _row(2, label="Known", split="validation"),
                _row(3, label="Known", split="test"),
                _row(4, label="Dev", split="validation"),
                _row(5, label="Final", split="test"),
            ]
        )
        inputs = _passing_gate_inputs(catalog)
        inputs["edge_support"] = {"presets": {"P": {"classes": {"Final": {}}}}}
        gate = build_class_role_support_gate(**inputs)

        assert gate["CLASS_ROLE_SUPPORT_GATE"] == "PASS"
        assert gate["FEW_SHOT_VARIANT_READY"] is False
        variants = gate["edge"]["P"]["U_final"]["Final"]["variants"]
        assert variants["1_shot"]["status"] == "NOT_READY"
        assert variants["10_shot"]["status"] == "NOT_READY"
    finally:
        catalog.close()


def test_stale_run_manifest_is_rejected_before_small_refresh(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        catalog.insert_records([_row(1)])
        source_manifest = {"config_hash": "cfg", "files": [{"sha256": "a" * 64}]}
        completion = {
            "config_hash": "cfg",
            "source_manifest_hash": content_hash(source_manifest["files"]),
            "mode": "full",
            "selected_all": True,
        }
        statistics = {
            "mode": "full",
            "asset_counts": {"backend_records": 2, "canonical_sessions": 1},
        }

        try:
            validate_current_run_identity(
                catalog=catalog,
                config_hash="cfg",
                source_manifest=source_manifest,
                statistics=statistics,
                completion=completion,
            )
        except ValueError as exc:
            assert "STALE_RUN_MANIFEST" in str(exc)
            assert "backend_record_count" in str(exc)
        else:
            raise AssertionError("stale statistics unexpectedly passed")
    finally:
        catalog.close()


def test_checkpoint_resume_requires_matching_source_and_catalog(tmp_path: Path) -> None:
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    checkpoint = tmp_path / "checkpoint.json"
    result = AdapterResult(
        dataset="Edge-IIoTset",
        capture_id="capture",
        source_hashes={"combined": "fingerprint"},
        source_verified=True,
        records=1,
        retained_candidates=1,
        quarantined=0,
        parse={},
        label_counts={"Novel": 1},
        coarse_counts={"NovelParent": 1},
        split_counts={"test": 1},
        duration_statistics={},
        anomaly_ids=[],
    )
    try:
        catalog.insert_records([_row(1)])
        _save_checkpoint(
            checkpoint,
            config_hash="config",
            source_fingerprint="source",
            mode="sample",
            result=result,
        )
        assert _load_checkpoint(
            path=checkpoint,
            config_hash="config",
            source_fingerprint="source",
            catalog=catalog,
            dataset="Edge-IIoTset",
            capture_id="capture",
            mode="sample",
        ) is not None
        assert _load_checkpoint(
            path=checkpoint,
            config_hash="config",
            source_fingerprint="changed",
            catalog=catalog,
            dataset="Edge-IIoTset",
            capture_id="capture",
            mode="sample",
        ) is None
    finally:
        catalog.close()


def test_ku_sets_are_pairwise_disjoint_and_benign_is_known() -> None:
    from flowsec.production.config import load_production_config

    config = load_production_config(Path("configs/data/production_freeze_v1.yaml"))
    labels = set(config.edge["coarse_mapping"])
    for preset in config.edge["known_unknown_presets"].values():
        udev, ufinal = set(preset["u_dev"]), set(preset["u_final"])
        known = labels - udev - ufinal
        assert "Normal" in known
        assert not (known & udev or known & ufinal or udev & ufinal)
