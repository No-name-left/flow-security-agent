from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

from flowsec.production.label_provenance import assign_session_label
from flowsec.production.schema import (
    CANONICAL_SCHEMA_VERSION,
    INITIAL_VIEW_VERSION,
    MODEL_FEATURE_WHITELIST,
    PROHIBITED_FIELDS_VERSION,
    PROHIBITED_MODEL_FIELDS,
    canonical_json,
    initial_model_view,
    model_view_violations,
)
from flowsec.production.storage import ParquetShardWriter, ProductionCatalog


def canonical_schema_manifest() -> dict[str, Any]:
    return {
        "name": "CanonicalSessionRecord",
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "sample_id_algorithm": {
            "id": "flowsec_sample_id_v1",
            "inputs": [
                "dataset_version",
                "source_content_sha256",
                "sha256(canonical bidirectional session identity)",
                "integer session start microseconds",
                "deterministic source ordinal",
            ],
            "path_independent": True,
            "raw_identity_exposed": False,
        },
        "logical_layers": {
            "backend_audit_record": [
                "sample_id", "dataset", "source_hash", "scenario_or_capture_id",
                "original_tuple", "raw_ip", "raw_port", "absolute_timestamp",
                "packet_provenance", "original_label", "split", "exclusion_reason",
                "anomaly_ids",
            ],
            "model_safe_initial_view": {
                "packet_limit": 8,
                "packet_fields": [
                    "direction", "packet_length", "relative_iat", "l3_protocol",
                    "l4_protocol", "tcp_flags",
                ],
                "summary_fields": [
                    "duration", "initiator_packets", "responder_packets",
                    "initiator_bytes", "responder_bytes", "packet_length_stats",
                    "iat_stats", "handshake_state",
                ],
                "other_fields": ["label_schema_id", "capabilities", "missing_fields"],
                "service_category_in_primary": False,
            },
            "expandable_evidence_store": [
                "packets_9_16", "past_only_temporal_index", "relation_index",
                "application_evidence", "sanitized_payload_if_whitelisted", "rag_retrieval_key",
            ],
        },
        "physical_format": {
            "type": "partitioned parquet",
            "compression": "zstd",
            "jsonl_scope": "small human-review fixtures only",
        },
    }


def label_schema_edge(config: dict[str, Any]) -> dict[str, Any]:
    mapping = dict(config["coarse_mapping"])
    labels = sorted(mapping)
    return {
        "id": config["label_schema_id"],
        "dataset": config["dataset_name"],
        "version": "edge_native_full_v1",
        "sample_unit": "bidirectional inactivity-bounded session",
        "benign_label": config["benign_label"],
        "fine_labels": labels,
        "coarse_labels": sorted(set(mapping.values())),
        "parent_of": mapping,
        "label_descriptions": {
            label: f"Edge-IIoTset native fine label {label}; parent={mapping[label]}"
            for label in labels
        },
        "scenario_or_capture_group": "backend_only",
        "missing_fields": ["application_evidence unless explicitly parsed", "sanitized_payload"],
        "prohibited_model_fields_version": PROHIBITED_FIELDS_VERSION,
    }


def label_schema_iot(config: dict[str, Any], observed_fine: Iterable[str]) -> dict[str, Any]:
    labels = sorted(set(observed_fine))
    return {
        "id": config["label_schema_id"],
        "dataset": config["dataset_name"],
        "version": "iot23_native_behavior_full_v1",
        "sample_unit": "reliably PCAP-matched official Zeek connection record",
        "task_label_level": config["task_label_level"],
        "benign_label": config["benign_label"],
        "fine_labels": labels,
        "coarse_labels": sorted(
            set(config["known_coarse_labels"])
            | set(config["u_dev_coarse_labels"])
            | set(config["u_final_coarse_labels"])
            | {"Availability", "FileTransfer", "MaliciousOther"}
        ),
        "parent_of": "deterministic native detailed-label substring rules in production config",
        "label_descriptions": {
            label: f"IoT-23 native detailed-label {label}" for label in labels
        },
        "scenario_family_is_backend_only": True,
        "det_label_compatibility": ["detailed-label", "det_label"],
        "prohibited_model_fields_version": PROHIBITED_FIELDS_VERSION,
    }


def _partition_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def write_logical_assets(
    *,
    catalog: ProductionCatalog,
    output_root: Path,
    processing: dict[str, Any],
    label_schema_ids: dict[str, str],
    edge_label_provenance: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    asset_names = [
        "backend_records",
        "canonical_sessions",
        "initial_model_views",
        "expandable_packet_store",
        "temporal_index",
        "relation_index",
        "sample_id_index",
    ]
    metadata: dict[str, Any] = {name: {"partitions": {}} for name in asset_names}
    counts: Counter[str] = Counter()
    compression = str(processing["parquet_compression"])
    max_rows = int(processing["parquet_shard_rows"])
    context_seconds = float(processing["context_window_seconds"])
    edge_label_provenance = edge_label_provenance or {}
    label_metadata_cache: dict[tuple[str, str, str], dict[str, Any]] = {}

    def label_metadata(dataset: str, capture: str, fine: str) -> dict[str, Any]:
        cache_key = (dataset, capture, fine)
        if cache_key in label_metadata_cache:
            return label_metadata_cache[cache_key]
        provenance = edge_label_provenance.get(capture)
        if provenance is None:
            metadata = {
                "capture_provenance_status": "NOT_APPLICABLE",
                "direct_evidence_count": 0,
                "direct_label_set_json": "[]",
                "label_assignment_method": "SOURCE_ADAPTER_NATIVE",
            }
        else:
            decision = assign_session_label(
                expected_label=fine,
                capture_provenance=provenance,
                direct_labels=(),
                session_capture_id=capture,
            )
            if decision["quarantined"]:
                raise ValueError(
                    f"cannot write unverified Edge session {dataset}/{capture}: "
                    f"{decision['reason']}"
                )
            metadata = {
                "capture_provenance_status": str(provenance["status"]),
                "direct_evidence_count": int(decision["direct_evidence_count"]),
                "direct_label_set_json": canonical_json(decision["direct_label_set"]),
                "label_assignment_method": str(decision["label_assignment_method"]),
            }
        label_metadata_cache[cache_key] = metadata
        return metadata

    def writer(asset: str, dataset: str, split: str) -> ParquetShardWriter:
        key = f"{dataset}|{split}"
        existing = metadata[asset]["partitions"].get(key)
        if existing is not None:
            return existing["_writer"]
        path = (
            output_root
            / asset
            / f"dataset={_partition_name(dataset)}"
            / f"split={_partition_name(split)}"
        )
        value = ParquetShardWriter(path, compression, max_rows)
        metadata[asset]["partitions"][key] = {"_writer": value}
        return value

    # Backend rows include excluded/quarantined records and are never a model input.
    backend_cursor = catalog.connection.execute(
        """
        SELECT sample_id,dataset,dataset_version,capture_id,source_hash,source_file,
               timestamp_start,timestamp_end,raw_initiator_ip,raw_responder_ip,
               raw_initiator_port,raw_responder_port,l3_protocol,l4_protocol,
               first_frame,last_frame,fine_label,coarse_label,base_split,
               anomaly_ids_json,original_label,retained,exclusion_reason,
               source_identity_hash,destination_identity_hash,communication_pair_hash
        FROM records
        ORDER BY dataset,capture_id,base_split,timestamp_start,sample_id
        """
    )
    for row in backend_cursor:
        (
            sample_id, dataset, dataset_version, capture_id, source_hash, source_file,
            start, end, src_ip, dst_ip, sport, dport, l3, l4, first_frame, last_frame,
            fine, coarse, split, anomalies, original, retained, exclusion,
            src_hash, dst_hash, pair_hash,
        ) = row
        writer("backend_records", dataset, split).write(
            {
                "schema_version": CANONICAL_SCHEMA_VERSION,
                "sample_id": sample_id,
                "dataset": dataset,
                "dataset_version": dataset_version,
                "scenario_or_capture_id": capture_id,
                "source_sha256": source_hash,
                "source_file": source_file,
                "timestamp_start": float(start),
                "timestamp_end": float(end),
                "raw_initiator_ip": src_ip,
                "raw_responder_ip": dst_ip,
                "raw_initiator_port": int(sport),
                "raw_responder_port": int(dport),
                "l3_protocol": l3,
                "l4_protocol": l4,
                "first_frame_or_record": int(first_frame),
                "last_frame_or_record": int(last_frame),
                "fine_label": fine,
                "coarse_label": coarse,
                "split": split,
                "original_label": original,
                "source_identity_hash": src_hash,
                "destination_identity_hash": dst_hash,
                "communication_pair_hash": pair_hash,
                "anomaly_ids_json": anomalies,
                "retained": bool(retained),
                "exclusion_reason": exclusion,
                **label_metadata(dataset, capture_id, fine),
            }
        )
        counts["backend_records"] += 1

    # Context state is reset for every capture/scenario + split. Same timestamps are
    # evaluated together and appended only after all views at t are computed.
    current_scope: tuple[str, str, str] | None = None
    recent: deque[dict[str, Any]] = deque()
    destination_counts: Counter[str] = Counter()
    destination_service_counts: Counter[tuple[str, str]] = Counter()
    destination_source_counts: Counter[tuple[str, str]] = Counter()
    destination_distinct_sources: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    prior_packets = prior_bytes = incomplete = 0
    last_source_time: dict[str, float] = {}
    last_pair_sample: dict[str, str] = {}
    pending_timestamp: float | None = None
    pending: list[dict[str, Any]] = []
    violations = Counter()

    def reset_state() -> None:
        nonlocal recent, destination_counts, destination_service_counts
        nonlocal destination_source_counts, destination_distinct_sources
        nonlocal pair_counts, prior_packets, prior_bytes, incomplete
        nonlocal last_source_time, last_pair_sample, pending, pending_timestamp
        recent = deque()
        destination_counts = Counter()
        destination_service_counts = Counter()
        destination_source_counts = Counter()
        destination_distinct_sources = Counter()
        pair_counts = Counter()
        prior_packets = prior_bytes = incomplete = 0
        last_source_time = {}
        last_pair_sample = {}
        pending = []
        pending_timestamp = None

    def evict(now: float) -> None:
        nonlocal prior_packets, prior_bytes, incomplete
        while recent and now - recent[0]["timestamp"] > context_seconds:
            old = recent.popleft()
            destination_counts[old["dst"]] -= 1
            if destination_counts[old["dst"]] <= 0:
                del destination_counts[old["dst"]]
            ds = (old["dst"], old["service"])
            destination_service_counts[ds] -= 1
            if destination_service_counts[ds] <= 0:
                del destination_service_counts[ds]
            dsrc = (old["dst"], old["src"])
            destination_source_counts[dsrc] -= 1
            if destination_source_counts[dsrc] <= 0:
                del destination_source_counts[dsrc]
                destination_distinct_sources[old["dst"]] -= 1
                if destination_distinct_sources[old["dst"]] <= 0:
                    del destination_distinct_sources[old["dst"]]
            pair_counts[old["pair"]] -= 1
            if pair_counts[old["pair"]] <= 0:
                del pair_counts[old["pair"]]
            prior_packets -= old["packets"]
            prior_bytes -= old["bytes"]
            incomplete -= old["incomplete"]

    def add_pending() -> None:
        nonlocal prior_packets, prior_bytes, incomplete
        for item in pending:
            recent.append(item)
            destination_counts[item["dst"]] += 1
            ds = (item["dst"], item["service"])
            destination_service_counts[ds] += 1
            dsrc = (item["dst"], item["src"])
            if destination_source_counts[dsrc] == 0:
                destination_distinct_sources[item["dst"]] += 1
            destination_source_counts[dsrc] += 1
            pair_counts[item["pair"]] += 1
            prior_packets += item["packets"]
            prior_bytes += item["bytes"]
            incomplete += item["incomplete"]
            last_source_time[item["src"]] = item["timestamp"]
            last_pair_sample[item["pair"]] = item["sample_id"]
        pending.clear()

    retained_cursor = catalog.connection.execute(
        """
        SELECT sample_id,dataset,capture_id,source_hash,timestamp_start,timestamp_end,
               fine_label,coarse_label,base_split,packet_sequence_json,session_summary_json,
               capabilities_json,missing_fields_json,anomaly_ids_json,
               source_identity_hash,destination_identity_hash,communication_pair_hash,
               evidence_signature,exact_signature,reverse_signature,near_signature,
               raw_initiator_ip,raw_responder_ip
        FROM records
        WHERE retained=1 AND base_split!='quarantine'
        ORDER BY dataset,capture_id,base_split,timestamp_start,sample_id
        """
    )
    for row in retained_cursor:
        (
            sample_id, dataset, capture, source_hash, start, end, fine, coarse, split,
            packet_json, summary_json, capabilities_json, missing_json, anomalies_json,
            src_hash, dst_hash, pair_hash, evidence_sig, exact_sig, reverse_sig, near_sig,
            raw_src_ip, raw_dst_ip,
        ) = row
        scope = (dataset, split, capture)
        if scope != current_scope:
            if pending:
                add_pending()
            reset_state()
            current_scope = scope
        start = float(start)
        if pending_timestamp is not None and start != pending_timestamp:
            add_pending()
        pending_timestamp = start
        evict(start)
        packets = json.loads(packet_json)
        summary = json.loads(summary_json)
        capabilities = json.loads(capabilities_json)
        missing = json.loads(missing_json)
        initial = initial_model_view(
            label_schema_id=label_schema_ids[dataset],
            packets=packets,
            summary=summary,
            capabilities=capabilities,
            missing_fields=missing,
            include_service=False,
        )
        found = model_view_violations(initial, (raw_src_ip, raw_dst_ip))
        if found:
            violations.update(found)
        canonical_row = {
            "schema_version": CANONICAL_SCHEMA_VERSION,
            "sample_id": sample_id,
            "label_schema_id": label_schema_ids[dataset],
            "split": split,
            "fine_label": fine,
            "coarse_label": coarse,
            "packet_sequence_1_8_json": canonical_json(packets[:8]),
            "session_summary_json": summary_json,
            "capabilities_json": capabilities_json,
            "missing_fields_json": missing_json,
            "expandable_packet_ref": sample_id if len(packets) > 8 else "",
            "temporal_index_ref": sample_id,
            "application_evidence_ref": "",
            **label_metadata(dataset, capture, fine),
        }
        writer("canonical_sessions", dataset, split).write(canonical_row)
        writer("initial_model_views", dataset, split).write(
            {
                "schema_version": CANONICAL_SCHEMA_VERSION,
                "view_version": INITIAL_VIEW_VERSION,
                "sample_id": sample_id,
                "split": split,
                "view_json": canonical_json(initial),
            }
        )
        if len(packets) > 8:
            writer("expandable_packet_store", dataset, split).write(
                {
                    "schema_version": CANONICAL_SCHEMA_VERSION,
                    "sample_id": sample_id,
                    "split": split,
                    "packets_9_16_json": canonical_json(packets[8:16]),
                    "rag_retrieval_key": hashlib.sha256(
                        f"rag|{sample_id}".encode("utf-8")
                    ).hexdigest(),
                }
            )
        service = str(summary.get("service_category", "UNKNOWN"))
        packet_count = int(summary["initiator_packets"]) + int(summary["responder_packets"])
        byte_count = int(summary["initiator_bytes"]) + int(summary["responder_bytes"])
        is_incomplete = int(summary["handshake_state"] == "INCOMPLETE_HANDSHAKE")
        # ``recent`` is appended in nondecreasing timestamp order and evicted
        # only from the left. Reading the rightmost timestamp is equivalent to
        # max(recent) but avoids an O(window-size) scan for every DDoS session.
        latest = recent[-1]["timestamp"] if recent else None
        if latest is not None and latest >= start:
            violations["future_context"] += 1
        context = {
            "window_seconds": context_seconds,
            "prior_session_count": len(recent),
            "unique_destination_count": len(destination_counts),
            "unique_destination_service_category_count": len(destination_service_counts),
            "same_destination_distinct_source_count": destination_distinct_sources.get(dst_hash, 0),
            "repeated_pair_count": pair_counts.get(pair_hash, 0),
            "incomplete_handshake_ratio": incomplete / len(recent) if recent else 0.0,
            "inter_session_gap": (
                start - last_source_time[src_hash] if src_hash in last_source_time else None
            ),
            "prior_packets": prior_packets,
            "prior_bytes": prior_bytes,
        }
        writer("temporal_index", dataset, split).write(
            {
                "schema_version": CANONICAL_SCHEMA_VERSION,
                "sample_id": sample_id,
                "split": split,
                "timestamp": start,
                "context_latest_timestamp": latest,
                "source_identity_hash": src_hash,
                "destination_identity_hash": dst_hash,
                "communication_pair_hash": pair_hash,
                "context_stats_json": canonical_json(context),
            }
        )
        writer("relation_index", dataset, split).write(
            {
                "schema_version": CANONICAL_SCHEMA_VERSION,
                "sample_id": sample_id,
                "split": split,
                "source_identity_hash": src_hash,
                "destination_identity_hash": dst_hash,
                "communication_pair_hash": pair_hash,
                "previous_pair_sample_ref": last_pair_sample.get(pair_hash, ""),
                "model_node_roles": "CURRENT_SOURCE,TARGET_CLUSTER",
            }
        )
        writer("sample_id_index", dataset, split).write(
            {
                "schema_version": CANONICAL_SCHEMA_VERSION,
                "sample_id": sample_id,
                "dataset": dataset,
                "split": split,
                "fine_label": fine,
                "coarse_label": coarse,
                "capture_ref_hash": hashlib.sha256(capture.encode("utf-8")).hexdigest(),
                "source_sha256": source_hash,
                "evidence_signature": evidence_sig,
                "exact_signature": exact_sig,
                "reverse_signature": reverse_sig,
                "near_signature": near_sig,
            }
        )
        pending.append(
            {
                "sample_id": sample_id,
                "timestamp": start,
                "src": src_hash,
                "dst": dst_hash,
                "pair": pair_hash,
                "service": service,
                "packets": packet_count,
                "bytes": byte_count,
                "incomplete": is_incomplete,
            }
        )
        counts["canonical_sessions"] += 1
        counts["initial_model_views"] += 1
        counts["expandable_packet_store"] += int(len(packets) > 8)
        counts["temporal_index"] += 1
        counts["relation_index"] += 1
        counts["sample_id_index"] += 1
    if pending:
        add_pending()

    # Application evidence is intentionally empty until a reliable protocol parser
    # and explicit sanitizer whitelist exist.
    empty_application = ParquetShardWriter(
        output_root / "application_evidence", compression, max_rows
    )
    metadata["application_evidence"] = empty_application.close()
    for asset in asset_names:
        for key, partition in list(metadata[asset]["partitions"].items()):
            value = partition.pop("_writer").close()
            partition.update(value)
        metadata[asset]["rows"] = sum(
            item["rows"] for item in metadata[asset]["partitions"].values()
        )
        metadata[asset]["bytes"] = sum(
            item["bytes"] for item in metadata[asset]["partitions"].values()
        )
        digest = hashlib.sha256()
        for key in sorted(metadata[asset]["partitions"]):
            digest.update(key.encode("utf-8"))
            digest.update(metadata[asset]["partitions"][key]["logical_sha256"].encode("ascii"))
        metadata[asset]["logical_sha256"] = digest.hexdigest()
    metadata["_projection_violations"] = dict(violations)
    return metadata, dict(counts)


def _deterministic_candidates(
    catalog: ProductionCatalog,
    *,
    dataset: str,
    label_column: str,
    label: str,
    split: str,
    seed: int,
    capacity: int,
) -> list[tuple[str, str, str, str]]:
    if label_column not in {"fine_label", "coarse_label"}:
        raise ValueError(label_column)
    if capacity <= 0:
        return []
    # Select one deterministic representative from every exact model-evidence
    # group before applying the capacity bound. Capping raw sessions first can
    # let a high-frequency repeated view crowd out otherwise valid evidence
    # groups and manufacture a false few-shot shortage.
    best_by_exact: dict[str, tuple[int, str, str, str]] = {}
    cursor = catalog.connection.execute(
        f"""
        SELECT sample_id,evidence_signature,reverse_signature,near_signature
        FROM records
        WHERE dataset=? AND {label_column}=? AND base_split=? AND retained=1
        """,
        (dataset, label, split),
    )
    for sample_id, exact_sig, reverse_sig, near_sig in cursor:
        rank = int(hashlib.sha256(f"{seed}|{sample_id}".encode("utf-8")).hexdigest(), 16)
        candidate = (rank, str(sample_id), str(reverse_sig), str(near_sig))
        exact_sig = str(exact_sig)
        previous = best_by_exact.get(exact_sig)
        if previous is None or candidate < previous:
            best_by_exact[exact_sig] = candidate
    ordered = sorted(
        (rank, sample_id, exact_sig, reverse_sig, near_sig)
        for exact_sig, (rank, sample_id, reverse_sig, near_sig) in best_by_exact.items()
    )[:capacity]
    return [
        (sample_id, exact_sig, reverse_sig, near_sig)
        for _, sample_id, exact_sig, reverse_sig, near_sig in ordered
    ]


def build_support_entry(
    catalog: ProductionCatalog,
    *,
    dataset: str,
    label_column: str,
    label: str,
    split: str,
    seed: int,
    shots: list[int],
    query_cap: int,
) -> dict[str, Any]:
    candidates = _deterministic_candidates(
        catalog,
        dataset=dataset,
        label_column=label_column,
        label=label,
        split=split,
        seed=seed,
        capacity=query_cap + max(shots) * 20 + 2000,
    )
    support: list[tuple[str, str, str, str]] = []
    used_exact: set[str] = set()
    used_reverse: set[str] = set()
    used_near: set[str] = set()
    for item in candidates:
        sample_id, exact_sig, reverse_sig, near_sig = item
        if exact_sig in used_exact or reverse_sig in used_reverse or near_sig in used_near:
            continue
        support.append(item)
        used_exact.add(exact_sig)
        used_reverse.add(reverse_sig)
        used_near.add(near_sig)
        if len(support) >= max(shots):
            break
    # Near-duplicate diversity is a preference, not permission to duplicate a
    # sample or its exact/reverse evidence. Fill any remaining shot capacity
    # only after exhausting near-distinct candidates and report the relaxation.
    if len(support) < max(shots):
        support_ids = {item[0] for item in support}
        for item in candidates:
            sample_id, exact_sig, reverse_sig, near_sig = item
            if (
                sample_id in support_ids
                or exact_sig in used_exact
                or reverse_sig in used_reverse
            ):
                continue
            support.append(item)
            support_ids.add(sample_id)
            used_exact.add(exact_sig)
            used_reverse.add(reverse_sig)
            used_near.add(near_sig)
            if len(support) >= max(shots):
                break
    support_ids = {item[0] for item in support}
    support_exact = {item[1] for item in support}
    support_reverse = {item[2] for item in support}
    support_near = {item[3] for item in support}
    query: list[str] = []
    query_exact: set[str] = set()
    query_reverse: set[str] = set()
    query_near: set[str] = set()
    for sample_id, exact_sig, reverse_sig, near_sig in candidates:
        if sample_id in support_ids or exact_sig in support_exact or reverse_sig in support_reverse:
            continue
        if exact_sig in query_exact or reverse_sig in query_reverse:
            continue
        if near_sig in support_near or near_sig in query_near:
            continue
        query.append(sample_id)
        query_exact.add(exact_sig)
        query_reverse.add(reverse_sig)
        query_near.add(near_sig)
        if len(query) >= query_cap:
            break
    # As above, fill after the near-diverse pass while preserving the hard
    # sample/exact/reverse disjointness contracts.
    if len(query) < query_cap:
        query_ids = set(query)
        for sample_id, exact_sig, reverse_sig, near_sig in candidates:
            if sample_id in support_ids or sample_id in query_ids:
                continue
            if exact_sig in support_exact or reverse_sig in support_reverse:
                continue
            if exact_sig in query_exact or reverse_sig in query_reverse:
                continue
            query.append(sample_id)
            query_ids.add(sample_id)
            query_exact.add(exact_sig)
            query_reverse.add(reverse_sig)
            query_near.add(near_sig)
            if len(query) >= query_cap:
                break
    query_ids = set(query)
    support_near_values = [item[3] for item in support]
    query_near_values = [item[3] for item in candidates if item[0] in query_ids]
    result: dict[str, Any] = {
        "label": label,
        "shots_requested": list(shots),
        "query_cap_requested": int(query_cap),
        "available_unique_candidates": len(candidates),
        "query_sample_ids": query,
        "query_count": len(query),
        "support_query_overlap": 0,
        "support_query_exact_duplicate": 0,
        "support_query_reverse_duplicate": 0,
        "support_near_duplicate_count": len(support_near_values)
        - len(set(support_near_values)),
        "query_near_duplicate_count": len(query_near_values)
        - len(set(query_near_values)),
        "support_query_near_duplicate": sum(
            near in support_near for near in query_near_values
        ),
        "near_duplicate_policy": (
            "maximize diversity first; permit reported near collisions only after "
            "exhausting candidates, while sample/exact/reverse disjointness remains hard"
        ),
    }
    for shot in shots:
        ids = [item[0] for item in support[:shot]]
        result[f"{shot}_shot"] = {
            "status": "READY" if len(ids) == shot else "INSUFFICIENT_SUPPORT",
            "support_sample_ids": ids,
            "support_count": len(ids),
        }
    return result


def ku_counts(
    catalog: ProductionCatalog,
    *,
    dataset: str,
    label_column: str,
    labels: Iterable[str],
) -> dict[str, int]:
    if label_column not in {"fine_label", "coarse_label"}:
        raise ValueError(label_column)
    result: dict[str, int] = {}
    for label in labels:
        result[label] = int(
            catalog.scalar(
                f"SELECT COUNT(*) FROM records WHERE dataset=? AND {label_column}=? AND retained=1",
                (dataset, label),
            )
            or 0
        )
    return result
