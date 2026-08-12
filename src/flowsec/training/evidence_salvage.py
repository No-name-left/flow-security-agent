from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


EVIDENCE_SALVAGE_AUDIT_VERSION = "CLASS_CONDITIONAL_EVIDENCE_SALVAGEABILITY_AUDIT_V1"
EVIDENCE_SALVAGE_SEED = 20260812

FAILURE_MODES = frozenset(
    {
        "NONE",
        "EVIDENCE_SELECTION_LOSS",
        "PAYLOAD_MATERIALIZATION_LOSS",
        "APPLICATION_EXTRACTION_LOSS",
        "TEMPORAL_FEATURE_GAP",
        "RELATION_FEATURE_GAP",
        "SESSIONIZATION_LOSS",
        "NETWORK_OBSERVABILITY_LIMITED",
        "AMBIGUOUS",
    }
)

SALVAGEABILITY_VALUES = frozenset(
    {
        "SALVAGEABLE_WITH_BASIC_V2",
        "SALVAGEABLE_WITH_RICHER_EVIDENCE",
        "NETWORK_OBSERVABILITY_LIMITED",
        "SESSIONIZATION_OR_GRANULARITY_RISK",
        "INCONCLUSIVE",
    }
)


def packet_bucket(packet_ordinal: int) -> str:
    """Return the frozen audit bucket for a one-based packet ordinal."""

    if packet_ordinal < 1:
        raise ValueError("packet ordinal must be one based")
    if packet_ordinal <= 8:
        return "first_8"
    if packet_ordinal <= 16:
        return "packet_9_16"
    return "after_16"


def payload_semantics(fragments: Iterable[str]) -> frozenset[str]:
    """Extract label-free semantic shapes from already-sanitized payload text.

    This is deliberately a small observational vocabulary. It never accepts a
    class name, capture name, tool marker, host identity, or ground-truth field.
    """

    text = "\n".join(str(item) for item in fragments).casefold()
    signals: set[str] = set()
    if "<sql_expr>" in text or "<database_error>" in text:
        signals.add("sql_expression")
    if "<credential_param>" in text or re.search(r"\bauth(?:entication|orization)?\b", text):
        signals.add("credential_structure")
    if any(token in text for token in ("multipart/form-data", "filename=", "<file_param>=")):
        signals.add("file_transfer_metadata")
    if "<command_param>=" in text:
        signals.add("command_structure")
    if "<path_traversal>" in text or "../" in text:
        signals.add("path_traversal")
    if "<script_expr>" in text or "<?php" in text:
        signals.add("script_content")
    if any(
        token in text
        for token in (
            "<!doctype",
            "<!entity",
            "/etc/passwd",
            "jndi:",
            "${jndi",
            "cgi-bin",
            "shellshock",
            "soapaction",
            "<amfx",
        )
    ):
        signals.add("exploit_structure")
    if re.search(r"(?:^|\n)(?:post|put)\s+", text):
        signals.add("upload_method")
    if re.search(r"(?:^|\n)(?:get|post|put|delete|head|options|patch)\s+", text):
        signals.add("http_request")
    if "content-type:" in text:
        signals.add("content_type")
    if re.search(r"\b(?:temperature|humidity|distance|moisture|sensor|water level)\b", text):
        signals.add("telemetry_semantics")
    if text.strip() and not signals:
        signals.add("generic_payload")
    return frozenset(signals)


def application_semantics(application: Mapping[str, Any] | None) -> frozenset[str]:
    if not application:
        return frozenset()
    observations = application.get("observations") or ()
    signals: set[str] = set()
    protocol = str(application.get("protocol", "")).casefold()
    if protocol:
        signals.add(f"protocol:{protocol}")
    for observation in observations:
        if not isinstance(observation, Mapping):
            continue
        kind = str(observation.get("kind", "")).casefold()
        method = str(observation.get("method", "")).upper()
        uri = str(observation.get("uri_shape", observation.get("uri", ""))).casefold()
        content_type = str(observation.get("content_type", "")).casefold()
        if kind == "http" or method:
            signals.add("http")
        if method in {"POST", "PUT"}:
            signals.add("upload_method")
        if method in {"OPTIONS", "TRACE", "CONNECT", "PROPFIND", "SEARCH", "DEBUG"}:
            signals.add("probe_method")
        if "multipart/form-data" in content_type:
            signals.add("file_transfer_metadata")
        if "<sql_expr>" in uri or "<database_error>" in uri:
            signals.add("sql_expression")
        if "<path_traversal>" in uri or "../" in uri:
            signals.add("path_traversal")
        if "<script_expr>" in uri:
            signals.add("script_content")
        if observation.get("status") in {401, 403}:
            signals.add("authentication_response")
        if observation.get("status") in {408, 429, 502, 503, 504}:
            signals.add("overload_response")
    return frozenset(signals)


def temporal_semantics(
    stats: Mapping[str, Any] | None,
    *,
    handshake_state: str,
) -> frozenset[str]:
    if not stats:
        return frozenset()
    prior = int(stats.get("prior_session_count") or 0)
    same_target_sources = int(stats.get("same_destination_distinct_source_count") or 0)
    incomplete = float(stats.get("incomplete_handshake_ratio") or 0.0)
    signals: set[str] = set()
    if prior >= 20:
        signals.add("session_burst")
    if prior >= 20 and same_target_sources / max(1, prior) >= 0.75:
        signals.add("target_concentration")
    if prior >= 20 and incomplete >= 0.75:
        signals.add("incomplete_handshake_burst")
    if prior >= 1000 and same_target_sources / max(1, prior) >= 0.75:
        signals.add("extreme_connection_rate_proxy")
    if int(stats.get("repeated_pair_count") or 0) > 0:
        signals.add("repeated_exact_relation")
    gap = stats.get("inter_session_gap")
    if gap is not None and float(gap) <= 1.0:
        signals.add("short_inter_session_gap")
    if handshake_state == "INCOMPLETE_HANDSHAKE":
        signals.add("target_incomplete_handshake")
    return frozenset(signals)


def relation_semantics(
    relation: Mapping[str, Any] | None,
    *,
    raw_arp_conflict: bool = False,
    raw_dns_conflict: bool = False,
) -> frozenset[str]:
    signals: set[str] = set()
    if relation and relation.get("previous_pair_sample_ref"):
        signals.add("repeated_exact_relation")
    if raw_arp_conflict:
        signals.add("arp_mapping_conflict")
    if raw_dns_conflict:
        signals.add("dns_mapping_conflict")
    return frozenset(signals)


def class_relevant_signal(
    fine_label: str,
    *,
    payload: Iterable[str] = (),
    application: Iterable[str] = (),
    temporal: Iterable[str] = (),
    relation: Iterable[str] = (),
    session: Iterable[str] = (),
) -> bool:
    """Conservative class-conditional mapping over label-free observations.

    The label is used only after the observational features have been extracted,
    to evaluate whether those features bear on that class. It is never used to
    synthesize or alter Evidence.
    """

    p, a, t, r, s = map(set, (payload, application, temporal, relation, session))
    if fine_label == "SQL_injection":
        return bool("sql_expression" in p or "sql_expression" in a)
    if fine_label == "Password":
        return bool(
            "credential_structure" in p
            or ({"http", "authentication_response"} <= a)
        )
    if fine_label == "Uploading":
        return bool(
            {"upload_method", "file_transfer_metadata", "script_content"} & (p | a)
            or ({"upload_method", "large_client_body"} <= (p | a | s))
        )
    if fine_label == "Vulnerability_scanner":
        return bool(
            {
                "path_traversal",
                "script_content",
                "probe_method",
                "command_structure",
                "exploit_structure",
            }
            & (p | a)
            or "probe_burst" in t
        )
    if fine_label == "DDoS_HTTP":
        return bool(
            "http_activity" in s
            and {"session_burst", "target_concentration"} <= t
        )
    if fine_label == "DDoS_TCP":
        return bool(
            "incomplete_handshake_burst" in t
            and "target_concentration" in t
            and (
                "extreme_connection_rate_proxy" in t
                or "high_syn_ratio" in s
            )
        )
    if fine_label == "Port_Scanning":
        return bool(
            "incomplete_handshake_burst" in t
            and ("port_diversity" in t or "probe_burst" in t)
        )
    if fine_label == "MITM":
        return bool({"arp_mapping_conflict", "dns_mapping_conflict"} & r)
    if fine_label == "Backdoor":
        return bool(
            "command_structure" in p
            or ({"periodic_service_pattern", "bidirectional_exchange"} <= (t | s))
        )
    if fine_label == "Ransomware":
        return bool(
            {"command_structure", "file_transfer_metadata", "script_content"} & p
            or "malware_network_exchange" in s
        )
    if fine_label == "Normal":
        return bool(
            "telemetry_semantics" in p
            or ({"mqtt_activity", "established_exchange"} <= s)
        )
    raise ValueError(f"unsupported Near class: {fine_label}")


def choose_failure_mode(
    *,
    current_support: bool,
    full_support: bool,
    raw_signal_present: bool,
    session_retains_signal: bool,
    payload_capability_available: bool,
    payload_visible_current: bool,
    application_available: bool,
    application_visible_current: bool,
    temporal_gap: bool,
    relation_gap: bool,
) -> str:
    if current_support:
        return "NONE"
    if raw_signal_present and not session_retains_signal:
        return "SESSIONIZATION_LOSS"
    if not raw_signal_present:
        return "NETWORK_OBSERVABILITY_LIMITED"
    if payload_capability_available and not payload_visible_current:
        return "EVIDENCE_SELECTION_LOSS"
    if application_available and not application_visible_current:
        return "EVIDENCE_SELECTION_LOSS"
    if temporal_gap:
        return "TEMPORAL_FEATURE_GAP"
    if relation_gap:
        return "RELATION_FEATURE_GAP"
    if full_support:
        return "AMBIGUOUS"
    return "AMBIGUOUS"


def validate_assessment(value: Mapping[str, Any]) -> None:
    failure_mode = str(value["failure_mode"])
    salvageability = str(value["salvageability"])
    if failure_mode not in FAILURE_MODES:
        raise ValueError(f"invalid failure mode: {failure_mode}")
    if salvageability not in SALVAGEABILITY_VALUES:
        raise ValueError(f"invalid salvageability: {salvageability}")
