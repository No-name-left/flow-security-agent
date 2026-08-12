from __future__ import annotations

import pytest

from flowsec.training.capture_wide_signal import (
    classify_session_signal,
    interval_profile,
    propagation_risk,
    session_mechanism_signals,
)


def _session(*signals: str, timestamp: float = 100.0) -> dict[str, object]:
    return {"timestamp_start": timestamp, "mechanism_signals": list(signals)}


def test_interval_profile_requires_repeated_observations_for_beacon_score() -> None:
    assert interval_profile([1.0, 2.0, 3.0])["beacon_score"] == 0.0
    profile = interval_profile([1.0, 2.0, 3.0, 4.0])
    assert profile["interval_cv"] == 0.0
    assert profile["beacon_score"] == 1.0


def test_mechanism_signals_do_not_treat_generic_syn_as_command_or_auth() -> None:
    signals = session_mechanism_signals(
        {
            "packet_count": 1,
            "byte_count": 60,
            "initiator_packets": 1,
            "responder_packets": 0,
            "tcp_syn": 1,
            "tcp_synack": 0,
        }
    )
    assert {"small_flow", "incomplete_handshake"} <= signals
    assert "command_structure" not in signals
    assert "authentication_attempt" not in signals
    assert "established_exchange" not in signals


def test_password_direct_and_strict_past_only_context() -> None:
    direct = classify_session_signal(
        "Password", _session("authentication_attempt", "http_activity")
    )
    assert direct["category"] == "DIRECTLY_ATTACK_INFORMATIVE"

    anchor = _session("authentication_attempt", "http_activity", timestamp=95.0)
    contextual = classify_session_signal(
        "Password",
        _session("http_activity", timestamp=100.0),
        past_10s_same_relation=[anchor],
        past_60s_same_relation=[anchor],
    )
    assert contextual["category"] == "CONTEXTUALLY_ATTACK_INFORMATIVE"
    assert contextual["past_10s_recoverable"] is True

    generic = classify_session_signal(
        "Password", _session("http_activity", timestamp=100.0)
    )
    assert generic["category"] == "GENERIC_OR_BACKGROUND"


def test_upload_requires_write_plus_transfer_not_get_delivered_script() -> None:
    get_script = classify_session_signal(
        "Uploading", _session("http_activity", "script_content")
    )
    assert get_script["category"] == "GENERIC_OR_BACKGROUND"

    direct = classify_session_signal(
        "Uploading", _session("write_method", "file_transfer_metadata")
    )
    assert direct["category"] == "DIRECTLY_ATTACK_INFORMATIVE"


def test_backdoor_periodicity_requires_small_bidirectional_exchange() -> None:
    past = [
        _session("small_flow", "bidirectional_exchange", "established_exchange", timestamp=value)
        for value in (10.0, 20.0, 30.0)
    ]
    contextual = classify_session_signal(
        "Backdoor",
        _session("small_flow", "bidirectional_exchange", "established_exchange", timestamp=40.0),
        past_60s_same_relation=past,
        past_history_same_relation=past,
    )
    assert contextual["category"] == "CONTEXTUALLY_ATTACK_INFORMATIVE"

    syn_only = classify_session_signal(
        "Backdoor",
        _session("small_flow", "incomplete_handshake", timestamp=40.0),
        past_60s_same_relation=past,
        past_history_same_relation=past,
    )
    assert syn_only["category"] == "GENERIC_OR_BACKGROUND"


def test_backdoor_long_strict_past_history_can_exceed_formal_60s_window() -> None:
    past = [
        _session("small_flow", "established_exchange", timestamp=value)
        for value in (10.0, 70.25, 130.5)
    ]
    assessment = classify_session_signal(
        "Backdoor",
        _session("small_flow", "established_exchange", timestamp=190.75),
        past_10s_same_relation=[],
        past_60s_same_relation=[],
        past_history_same_relation=past,
    )
    assert assessment["category"] == "CONTEXTUALLY_ATTACK_INFORMATIVE"
    assert assessment["past_10s_recoverable"] is False
    assert assessment["past_60s_recoverable"] is False


def test_ransomware_does_not_inherit_from_generic_malware_signals() -> None:
    assessment = classify_session_signal(
        "Ransomware",
        _session(
            "command_structure",
            "file_transfer_metadata",
            "encrypted_application",
            "bidirectional_exchange",
        ),
    )
    assert assessment["category"] == "GENERIC_OR_BACKGROUND"


@pytest.mark.parametrize(
    ("rate", "expected"),
    [(0.0, "LOW"), (0.2, "MEDIUM"), (0.499, "MEDIUM"), (0.5, "HIGH"), (1.0, "HIGH")],
)
def test_propagation_risk_thresholds(rate: float, expected: str) -> None:
    assert propagation_risk(rate) == expected
