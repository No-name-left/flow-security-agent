from __future__ import annotations

import json

import pytest

from flowsec.production.guards import (
    AssetAccessPolicy,
    FinalUnknownAccessError,
    project_label_schema,
)
from flowsec.production.loader import ProductionAssetLoader
from flowsec.production.schema import (
    CANONICAL_SCHEMA_VERSION,
    PROHIBITED_MODEL_FIELDS,
    initial_model_view,
    model_view_violations,
    stable_sample_id,
)


def test_canonical_schema_version_is_frozen() -> None:
    assert CANONICAL_SCHEMA_VERSION == "canonical_session_record_v1"


def test_stable_sample_id_is_path_independent_and_order_stable() -> None:
    values = dict(
        dataset_version="dataset-v1",
        source_content_hash="a" * 64,
        canonical_session_identity=("IPv4", "TCP", ("10.0.0.1", 1), ("10.0.0.2", 2)),
        start_microseconds=123456,
        deterministic_ordinal=7,
    )
    first = stable_sample_id(**values)
    second = stable_sample_id(**values)
    assert first == second
    assert "10.0.0" not in first
    assert len(first) == 44


def test_primary_projection_has_no_prohibited_keys_or_raw_identity() -> None:
    summary = {
        "duration": 1.0,
        "initiator_packets": 1,
        "responder_packets": 1,
        "initiator_bytes": 64,
        "responder_bytes": 64,
        "packet_length_stats": {"min": 64, "max": 64, "mean": 64, "std": 0},
        "iat_stats": {"min": 1, "max": 1, "mean": 1, "std": 0},
        "handshake_state": "ESTABLISHED_OPEN",
        "service_category": "HTTP",
        "service_category_source": "iana_port_category_map_v1",
    }
    view = initial_model_view(
        label_schema_id="synthetic_v1",
        packets=[
            {
                "direction": "initiator_to_responder",
                "packet_length": 64,
                "relative_iat": 0.0,
                "l3_protocol": "IPv4",
                "l4_protocol": "TCP",
                "tcp_flags": 2,
            }
        ],
        summary=summary,
        capabilities=["temporal_context"],
        missing_fields=["application_evidence"],
    )
    assert model_view_violations(view, ["192.0.2.1", "198.51.100.2"]) == []
    serialized = json.dumps(view)
    assert "service_category" not in serialized
    assert not any(field in serialized for field in PROHIBITED_MODEL_FIELDS)


def test_u_final_loader_and_label_descriptions_are_guarded() -> None:
    manifest = {
        "assets": [
            {"role": "sft_train", "ku_role": "K_known"},
            {"role": "final_unknown", "ku_role": "U_final"},
        ]
    }
    loader = ProductionAssetLoader(manifest, AssetAccessPolicy())
    assert loader.resolve("sft_train")["ku_role"] == "K_known"
    with pytest.raises(FinalUnknownAccessError):
        loader.resolve("final_unknown")
    schema = {
        "fine_labels": ["Known", "SecretFinal"],
        "label_descriptions": {"Known": "visible", "SecretFinal": "hidden"},
    }
    projected = project_label_schema(
        schema,
        allowed_labels=["Known", "SecretFinal"],
        final_unknown_labels=["SecretFinal"],
        policy=AssetAccessPolicy(),
    )
    assert "SecretFinal" not in projected["label_descriptions"]


def test_support_labels_require_support_phase_unlock() -> None:
    with pytest.raises(FinalUnknownAccessError):
        AssetAccessPolicy(phase="support").assert_role_allowed("U_final_support")
    AssetAccessPolicy(
        phase="support",
        exclude_final_unknown=False,
        support_labels_unlocked=True,
    ).assert_role_allowed("U_final_support")
