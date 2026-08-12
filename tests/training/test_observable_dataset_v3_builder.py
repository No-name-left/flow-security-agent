from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from flowsec.training.contracts import SANITIZED_PAYLOAD_VERSION
from flowsec.training.evidence_v2 import (
    PACKET_ALIGNED_PAYLOAD_V2_VERSION,
    BasicEvidenceV2,
    RelationEvidenceV2,
)


def _load_builder():
    path = Path("tools/build_observable_dataset_v3.py")
    spec = importlib.util.spec_from_file_location("observable_dataset_v3_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder()
SESSION_ID = "fs1_" + "a" * 40


def _raw_contract_row() -> dict[str, object]:
    return {
        "sample_id": SESSION_ID,
        "session_summary_json": json.dumps(
            {
                "duration": 1.0,
                "bidirectional_packet_count": 2,
                "bidirectional_byte_count": 180,
                "initiator_packet_count": 1,
                "responder_packet_count": 1,
                "initiator_byte_count": 100,
                "responder_byte_count": 80,
                "packet_length_statistics": {
                    "count": 2, "min": 80.0, "max": 100.0, "mean": 90.0, "std": 10.0
                },
                "iat_statistics": {
                    "count": 1, "min": 0.25, "max": 0.25, "mean": 0.25, "std": 0.0
                },
                "tcp_handshake_state": "ESTABLISHED_OR_BIDIRECTIONAL",
                "application_protocols": ["http"],
            }
        ),
        "first_8_packets_json": json.dumps(
            [
                {"packet_index": 1, "direction": "initiator_to_responder", "relative_time": 0.0, "relative_iat": 0.0, "packet_length": 100, "l3_protocol": "IPv4", "l4_protocol": "TCP", "tcp_flags": 2},
                {"packet_index": 2, "direction": "responder_to_initiator", "relative_time": 0.25, "relative_iat": 0.25, "packet_length": 80, "l3_protocol": "IPv4", "l4_protocol": "TCP", "tcp_flags": 18},
            ]
        ),
        "basic_application_observations_json": json.dumps(
            [{"kind": "http", "method": "POST", "uri_shape": "/login"}]
        ),
        "basic_payload_json": json.dumps(["<credential_param>"]),
    }


def _payload_rows() -> list[dict[str, object]]:
    common = {
        "schema_version": PACKET_ALIGNED_PAYLOAD_V2_VERSION,
        "session_id": SESSION_ID,
        "protocol": "TCP",
        "sanitization_version": SANITIZED_PAYLOAD_VERSION,
    }
    return [
        {**common, "packet_index": 1, "direction": "initiator_to_responder", "relative_time": 0.0, "payload_present": True, "payload_length": 12, "sanitized_payload": "<credential_param>", "frame_number_backend_only": 10},
        {**common, "packet_index": 2, "direction": "responder_to_initiator", "relative_time": 0.25, "payload_present": False, "payload_length": 0, "sanitized_payload": None, "frame_number_backend_only": 11},
    ]


def test_basic_builder_uses_explicit_one_to_one_packet_payload_alignment() -> None:
    basic = BUILDER._basic_contract(_raw_contract_row(), _payload_rows())
    assert isinstance(basic, BasicEvidenceV2)
    assert [item.packet_index for item in basic.packet_aligned_payload] == [1, 2]
    assert basic.cheap_application_metadata.credential_field_presence is True
    assert len(BUILDER._label_free_near_signature(basic)) == 64

    broken = _payload_rows()
    broken[1] = {**broken[1], "relative_time": 0.5}
    with pytest.raises(ValueError, match="does not match"):
        BUILDER._basic_contract(_raw_contract_row(), broken)


def _relation_row(sample_id: str, timestamp: float) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "split": "train",
        "capture_id_backend_only": "Attack_MITM",
        "timestamp_start": timestamp,
        "raw_initiator_ip": "10.0.0.1",
        "raw_responder_ip": "10.0.0.2",
    }


def test_relation_builder_is_strict_past_endpoint_linked_and_split_local() -> None:
    rows = [_relation_row("early", 80.0), _relation_row("late", 100.0)]
    events = [
        {"timestamp": 80.0, "frame_number_backend_only": 1, "source_ip": "10.0.0.1", "source_mac": "aa", "target_ip": "10.0.0.2"},
        {"timestamp": 90.0, "frame_number_backend_only": 2, "source_ip": "10.0.0.1", "source_mac": "bb", "target_ip": "10.0.0.2"},
        {"timestamp": 110.0, "frame_number_backend_only": 3, "source_ip": "10.0.0.2", "source_mac": "bb", "target_ip": "10.0.0.1"},
    ]
    result = BUILDER._relation_evidence(rows, events, [])
    assert result["early"]["target_endpoint_linked"] is False
    assert result["late"]["arp_ip_multiple_macs"] is True
    assert result["late"]["contexts"]["10"]["past_only"] is True
    RelationEvidenceV2.model_validate(
        {key: value for key, value in result["late"]["contexts"]["10"].items() if key != "anomaly_types"}
    )

    cross_split = [dict(rows[0]), {**rows[1], "split": "validation"}]
    with pytest.raises(ValueError, match="one split"):
        BUILDER._relation_evidence(cross_split, events, [])


def test_corrupt_tail_is_accepted_only_after_every_locator(tmp_path: Path) -> None:
    stderr_path = tmp_path / "tshark.stderr.log"
    stderr_path.write_text(
        "tshark: file appears to be damaged or corrupt.\n"
        "(pcap: File has 136146411-byte packet, bigger than maximum of 262144)\n",
        encoding="utf-8",
    )
    error = RuntimeError("tshark failed")

    accepted = BUILDER._verified_corrupt_tail_limitation(
        error=error,
        stderr_path=stderr_path,
        packet_limit=None,
        max_frame_seen=265827,
        max_locator_frame=265827,
    )
    assert accepted is not None
    assert accepted["all_production_locators_covered"] is True

    assert BUILDER._verified_corrupt_tail_limitation(
        error=error,
        stderr_path=stderr_path,
        packet_limit=None,
        max_frame_seen=265826,
        max_locator_frame=265827,
    ) is None
    assert BUILDER._verified_corrupt_tail_limitation(
        error=error,
        stderr_path=stderr_path,
        packet_limit=100,
        max_frame_seen=265827,
        max_locator_frame=265827,
    ) is None

    stderr_path.write_text("tshark: permission denied\n", encoding="utf-8")
    assert BUILDER._verified_corrupt_tail_limitation(
        error=error,
        stderr_path=stderr_path,
        packet_limit=None,
        max_frame_seen=265827,
        max_locator_frame=265827,
    ) is None
