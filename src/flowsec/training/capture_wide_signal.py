from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from statistics import fmean, pstdev
from typing import Any


CAPTURE_WIDE_AUDIT_VERSION = "CAPTURE_WIDE_ATTACK_SIGNAL_AUDIT_V1"

SESSION_CATEGORIES = frozenset(
    {
        "DIRECTLY_ATTACK_INFORMATIVE",
        "CONTEXTUALLY_ATTACK_INFORMATIVE",
        "GENERIC_OR_BACKGROUND",
    }
)

TARGET_CLASSES = (
    "Backdoor",
    "Password",
    "Uploading",
    "Ransomware",
)


def interval_profile(timestamps: Iterable[float]) -> dict[str, float | int | None]:
    """Summarize recurrence without using a label or capture identity.

    Timestamps must already be restricted to the legal observation scope.  The
    returned beacon score is descriptive only; it is not sufficient without a
    real bidirectional application exchange.
    """

    values = sorted(float(value) for value in timestamps)
    intervals = [right - left for left, right in zip(values, values[1:]) if right > left]
    if not intervals:
        return {
            "timestamp_count": len(values),
            "interval_count": 0,
            "interval_mean_seconds": None,
            "interval_cv": None,
            "beacon_score": 0.0,
        }
    mean = fmean(intervals)
    cv = pstdev(intervals) / mean if mean > 0 and len(intervals) > 1 else 0.0
    return {
        "timestamp_count": len(values),
        "interval_count": len(intervals),
        "interval_mean_seconds": mean,
        "interval_cv": cv,
        "beacon_score": max(0.0, min(1.0, 1.0 - cv)) if len(intervals) >= 3 else 0.0,
    }


def directional_profile(
    initiator_bytes: int,
    responder_bytes: int,
) -> dict[str, float | int]:
    total = max(0, int(initiator_bytes)) + max(0, int(responder_bytes))
    asymmetry = abs(int(initiator_bytes) - int(responder_bytes)) / total if total else 0.0
    return {
        "initiator_bytes": int(initiator_bytes),
        "responder_bytes": int(responder_bytes),
        "byte_asymmetry": asymmetry,
        "client_to_server_fraction": int(initiator_bytes) / total if total else 0.0,
    }


def session_mechanism_signals(session: Mapping[str, Any]) -> frozenset[str]:
    """Extract mechanism/protocol signals from one label-free session row."""

    payload = set(session.get("payload_semantics") or ())
    application = set(session.get("application_semantics") or ())
    methods = {str(value).upper() for value in session.get("http_methods") or ()}
    statuses = {str(value) for value in session.get("http_statuses") or ()}
    content_types = {str(value).casefold() for value in session.get("content_types") or ()}
    uri_shapes = {str(value).casefold() for value in session.get("uri_shapes") or ()}
    ftp_commands = {str(value).upper() for value in session.get("ftp_commands") or ()}

    signals: set[str] = set(payload) | set(application)
    if methods or "http" in application:
        signals.add("http_activity")
    if statuses & {"401", "403"}:
        signals.add("authentication_failure")
    if statuses & {"200", "201", "202", "204", "302", "303"}:
        signals.add("application_success_response")
    if "credential_structure" in payload:
        signals.add("authentication_attempt")
    if methods & {"POST", "PUT", "PATCH"}:
        signals.add("write_method")
    if any("multipart/form-data" in value for value in content_types):
        signals.add("file_transfer_metadata")
    if ftp_commands & {"STOR", "STOU", "APPE"}:
        signals.update({"file_transfer_metadata", "write_method", "ftp_upload"})
    if ftp_commands & {"RETR"}:
        signals.add("file_download")
    if any(shape.endswith((".exe", ".dll", ".bin", ".elf", ".sh", ".ps1")) for shape in uri_shapes):
        signals.add("executable_resource")
    if session.get("tls_frame_count", 0):
        signals.add("encrypted_application")
    if int(session.get("request_count") or 0) and int(session.get("response_count") or 0):
        signals.add("request_response_exchange")
    if int(session.get("initiator_packets") or 0) and int(session.get("responder_packets") or 0):
        signals.add("bidirectional_exchange")
    if (
        int(session.get("tcp_synack") or 0)
        or (
            int(session.get("initiator_payload_bytes") or 0)
            and int(session.get("responder_payload_bytes") or 0)
        )
        or (int(session.get("request_count") or 0) and int(session.get("response_count") or 0))
    ):
        signals.add("established_exchange")
    if int(session.get("packet_count") or 0) <= 12 and int(session.get("byte_count") or 0) <= 4096:
        signals.add("small_flow")
    if int(session.get("initiator_payload_bytes") or 0) >= 65536:
        signals.add("large_client_body")
    if int(session.get("initiator_payload_bytes") or 0) >= 4 * max(
        1, int(session.get("responder_payload_bytes") or 0)
    ):
        signals.add("client_payload_asymmetry")
    if int(session.get("tcp_syn") or 0) and not int(session.get("tcp_synack") or 0):
        signals.add("incomplete_handshake")
    if int(session.get("tcp_rst") or 0):
        signals.add("reset_observed")
    return frozenset(signals)


def _past_direct_anchor(
    past: Sequence[Mapping[str, Any]],
    *,
    required: set[str],
) -> bool:
    return any(required <= set(item.get("mechanism_signals") or ()) for item in past)


def classify_session_signal(
    fine_label: str,
    session: Mapping[str, Any],
    *,
    past_10s_same_relation: Sequence[Mapping[str, Any]] = (),
    past_60s_same_relation: Sequence[Mapping[str, Any]] = (),
    past_history_same_relation: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Map label-free observations to a backend-only fine-label assessment.

    The class is consulted only after signals are extracted.  Capture name,
    filename, run identity, future sessions, and majority capture label are not
    accepted as inputs.  Every contextual rule is strict past-only.
    """

    if fine_label not in TARGET_CLASSES:
        raise ValueError(f"unsupported capture-wide target class: {fine_label}")
    signals = set(session.get("mechanism_signals") or session_mechanism_signals(session))
    past10 = list(past_10s_same_relation)
    past60 = list(past_60s_same_relation)
    past_history = list(past_history_same_relation)
    direct = False
    contextual10 = False
    contextual60 = False
    contextually_attack_informative = False
    reasons: list[str] = []

    if fine_label == "Password":
        direct = bool({"authentication_attempt", "authentication_failure"} & signals)
        auth_anchor = {"authentication_attempt"}
        current_auth_context = bool(
            {"http_activity", "application_success_response", "authentication_failure"}
            & signals
        )
        contextual10 = current_auth_context and _past_direct_anchor(past10, required=auth_anchor)
        contextual60 = current_auth_context and _past_direct_anchor(past60, required=auth_anchor)
        contextually_attack_informative = contextual60
        if direct:
            reasons.append("session_contains_authentication_attempt_or_failure")
        elif contextual60:
            reasons.append("same_relation_http_session_follows_observed_authentication_attempt")

    elif fine_label == "Uploading":
        explicit_transfer = "file_transfer_metadata" in signals and bool(
            {"write_method", "ftp_upload"} & signals
        )
        directional_transfer = {
            "write_method",
            "large_client_body",
            "client_payload_asymmetry",
        } <= signals
        direct = explicit_transfer or directional_transfer
        transfer_anchor = {"file_transfer_metadata", "write_method"}
        current_transfer_context = bool(
            {
                "http_activity",
                "script_content",
                "file_download",
                "application_success_response",
            }
            & signals
        )
        contextual10 = current_transfer_context and _past_direct_anchor(
            past10, required=transfer_anchor
        )
        contextual60 = current_transfer_context and _past_direct_anchor(
            past60, required=transfer_anchor
        )
        contextually_attack_informative = contextual60
        if direct:
            reasons.append("session_contains_explicit_or_directionally_strong_upload_semantics")
        elif contextual60:
            reasons.append("same_relation_follow_up_to_observed_upload")

    elif fine_label == "Backdoor":
        direct = "command_structure" in signals and "established_exchange" in signals
        current_time = float(session.get("timestamp_start") or 0.0)

        def established_small_times(values: Sequence[Mapping[str, Any]]) -> list[float]:
            return [
                float(item["timestamp_start"])
                for item in values
                if {"established_exchange", "small_flow"}
                <= set(item.get("mechanism_signals") or ())
            ]

        def periodic(values: Sequence[float]) -> bool:
            recurrence = interval_profile([*values, current_time])
            interval_cv = recurrence["interval_cv"]
            return bool(
                int(recurrence["interval_count"] or 0) >= 3
                and float(interval_cv if interval_cv is not None else math.inf) <= 0.35
            )

        prior_history = established_small_times(past_history)
        prior60 = established_small_times(past60)
        prior10 = established_small_times(past10)
        target_is_established_small = {"established_exchange", "small_flow"} <= signals
        contextually_attack_informative = bool(
            target_is_established_small and len(prior_history) >= 3 and periodic(prior_history)
        )
        contextual60 = bool(
            target_is_established_small and len(prior60) >= 3 and periodic(prior60)
        )
        contextual10 = bool(
            target_is_established_small and len(prior10) >= 3 and periodic(prior10)
        )
        if direct:
            reasons.append("bidirectional_session_contains_command_structure")
        elif contextually_attack_informative:
            reasons.append("strict_past_periodic_small_established_relation")

    else:  # Ransomware
        # Generic command, file-transfer, TLS, or suspicious traffic does not
        # distinguish ransomware from other malware.  A direct fine-label
        # signal therefore requires explicit network-observed key/encryption
        # workflow semantics, not capture membership.
        direct = "ransomware_specific_network_semantics" in signals
        contextual10 = False
        contextual60 = False
        contextually_attack_informative = False
        if direct:
            reasons.append("network_observed_ransomware_specific_workflow")

    if direct:
        category = "DIRECTLY_ATTACK_INFORMATIVE"
    elif contextually_attack_informative:
        category = "CONTEXTUALLY_ATTACK_INFORMATIVE"
    else:
        category = "GENERIC_OR_BACKGROUND"
    if category not in SESSION_CATEGORIES:  # pragma: no cover - internal invariant
        raise AssertionError(category)
    return {
        "category": category,
        "directly_attack_informative": direct,
        "past_10s_recoverable": bool(not direct and contextual10),
        "past_60s_recoverable": bool(not direct and contextual60),
        "reasons": reasons,
    }


def propagation_risk(generic_rate: float) -> str:
    if not 0.0 <= generic_rate <= 1.0:
        raise ValueError("generic rate must be within zero and one")
    if generic_rate >= 0.50:
        return "HIGH"
    if generic_rate >= 0.20:
        return "MEDIUM"
    return "LOW"
