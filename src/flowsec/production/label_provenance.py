from __future__ import annotations

import csv
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from flowsec.production.core import combine_hashes, sha256_file
from flowsec.production.storage import ProductionCatalog


PROVENANCE_POLICY_VERSION = "edge_label_provenance_v1"
DIRECT_EVIDENCE_POLICY = "DIRECT_EVIDENCE_UNANIMOUS_ONLY"
CAPTURE_FALLBACK_METHOD = "VERIFIED_CAPTURE_FALLBACK"
CAPTURE_FAILURE = "PROVENANCE_CAPTURE_LABEL_FAIL"
CONFLICT_METHOD = "LABEL_CONFLICT_QUARANTINE"
UNMATCHED_METHOD = "UNMATCHED_PROVENANCE_QUARANTINE"

_ABSOLUTE_FRAME_TIME = re.compile(
    r"^\s*\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\s*$"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_attack_label(value: str) -> str:
    stripped = value.strip().strip('"').strip("'")
    try:
        numeric = float(stripped)
    except ValueError:
        return stripped
    return str(int(numeric)) if numeric.is_integer() else stripped


def _normalized_attack_type(value: str) -> str:
    return value.strip().strip('"').strip("'")


def scan_companion_labels(path: Path) -> dict[str, Any]:
    """Stream the two official label columns without parsing large payload fields."""

    with path.open("rb") as handle:
        header_line = handle.readline()
        header = next(
            csv.reader([header_line.decode("utf-8-sig", errors="replace").rstrip("\r\n")])
        )
        attack_label_present = "Attack_label" in header
        attack_type_present = "Attack_type" in header
        label_counts: Counter[tuple[str, str]] = Counter()
        malformed_rows = 0
        rows = 0
        first_frame_time = ""
        for raw in handle:
            if not raw.strip():
                continue
            rows += 1
            parts = raw.rstrip(b"\r\n").rsplit(b",", 2)
            if len(parts) != 3:
                malformed_rows += 1
                continue
            prefix, raw_label, raw_type = parts
            label = _normalized_attack_label(raw_label.decode("utf-8", errors="replace"))
            attack_type = _normalized_attack_type(
                raw_type.decode("utf-8", errors="replace")
            )
            if not label or not attack_type:
                malformed_rows += 1
                continue
            label_counts[(label, attack_type)] += 1
            if not first_frame_time:
                first_frame_time = prefix.split(b",", 1)[0].decode(
                    "utf-8", errors="replace"
                ).strip()
    valid_rows = sum(label_counts.values())
    dominant = max(label_counts.values(), default=0)
    return {
        "header_columns": header,
        "attack_label_present": attack_label_present,
        "attack_type_present": attack_type_present,
        "rows": rows,
        "valid_label_rows": valid_rows,
        "malformed_label_rows": malformed_rows,
        "observed_label_counts": {
            f"{label}|{attack_type}": count
            for (label, attack_type), count in sorted(label_counts.items())
        },
        "observed_labels": [
            {"Attack_label": label, "Attack_type": attack_type}
            for label, attack_type in sorted(label_counts)
        ],
        "label_purity": dominant / valid_rows if valid_rows else 0.0,
        "first_frame_time": first_frame_time,
        "has_stable_direct_join_key": bool(
            "frame.number" in header
            or "frame.time_epoch" in header
            or _ABSOLUTE_FRAME_TIME.match(first_frame_time)
        ),
    }


def pcap_packet_count(path: Path, capinfos_bin: str = "capinfos") -> int | None:
    try:
        completed = subprocess.run(
            [capinfos_bin, "-M", "-c", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    for line in completed.stdout.splitlines():
        if line.startswith("Number of packets:"):
            try:
                return int(line.split(":", 1)[1].strip().replace(",", ""))
            except ValueError:
                return None
    return None


def validate_edge_capture_provenance(
    *,
    capture_id: str,
    pcap_path: Path,
    companion_csv_path: Path,
    expected_label: str,
    pcap_sha256: str | None = None,
    companion_csv_sha256: str | None = None,
    expected_pcap_sha256: str | None = None,
    expected_companion_csv_sha256: str | None = None,
    official_archive_verified: bool = True,
    packet_count: int | None = None,
) -> dict[str, Any]:
    if not pcap_path.is_file() or not companion_csv_path.is_file():
        missing = [
            str(path)
            for path in (pcap_path, companion_csv_path)
            if not path.is_file()
        ]
        return {
            "capture_id": capture_id,
            "status": CAPTURE_FAILURE,
            "failure_reasons": [f"missing_source:{item}" for item in missing],
            "expected_label": expected_label,
        }

    observed_pcap_sha = pcap_sha256 or sha256_file(pcap_path)
    observed_csv_sha = companion_csv_sha256 or sha256_file(companion_csv_path)
    labels = scan_companion_labels(companion_csv_path)
    expected_pair = ("0", "Normal") if expected_label == "Normal" else ("1", expected_label)
    observed_pairs = {
        (item["Attack_label"], item["Attack_type"])
        for item in labels["observed_labels"]
    }
    failures: list[str] = []
    if not official_archive_verified:
        failures.append("official_archive_identity_unverified")
    if expected_pcap_sha256 and observed_pcap_sha != expected_pcap_sha256:
        failures.append("pcap_sha256_mismatch")
    if expected_companion_csv_sha256 and observed_csv_sha != expected_companion_csv_sha256:
        failures.append("companion_csv_sha256_mismatch")
    if not labels["attack_label_present"]:
        failures.append("Attack_label_missing")
    if not labels["attack_type_present"]:
        failures.append("Attack_type_missing")
    if labels["malformed_label_rows"]:
        failures.append("malformed_label_rows")
    if len(observed_pairs) != 1:
        failures.append("companion_csv_not_single_label")
    if observed_pairs != {expected_pair}:
        failures.append("expected_capture_label_mismatch")
    if labels["label_purity"] != 1.0:
        failures.append("companion_csv_label_purity_not_100_percent")

    packets = packet_count if packet_count is not None else pcap_packet_count(pcap_path)
    csv_rows = int(labels["rows"])
    direct_key = bool(labels["has_stable_direct_join_key"])
    return {
        "policy_version": PROVENANCE_POLICY_VERSION,
        "capture_id": capture_id,
        "status": "PASS" if not failures else CAPTURE_FAILURE,
        "failure_reasons": failures,
        "source_mapping": {
            "pcap": str(pcap_path),
            "companion_csv": str(companion_csv_path),
            "expected_capture_label": expected_label,
        },
        "pcap_sha256": observed_pcap_sha,
        "companion_csv_sha256": observed_csv_sha,
        "expected_pcap_sha256": expected_pcap_sha256 or observed_pcap_sha,
        "expected_companion_csv_sha256": (
            expected_companion_csv_sha256 or observed_csv_sha
        ),
        "pcap_identity_verified": bool(
            official_archive_verified
            and (not expected_pcap_sha256 or observed_pcap_sha == expected_pcap_sha256)
        ),
        "companion_csv_identity_verified": bool(
            official_archive_verified
            and (
                not expected_companion_csv_sha256
                or observed_csv_sha == expected_companion_csv_sha256
            )
        ),
        "combined_source_sha256": combine_hashes([observed_pcap_sha, observed_csv_sha]),
        "expected_label": expected_label,
        "expected_official_label": {
            "Attack_label": expected_pair[0],
            "Attack_type": expected_pair[1],
        },
        "csv_observed_labels": labels["observed_labels"],
        "csv_observed_label_counts": labels["observed_label_counts"],
        "csv_label_purity": labels["label_purity"],
        "csv_rows": csv_rows,
        "pcap_packets": packets,
        "packet_row_count_ratio": (
            csv_rows / packets if packets not in {None, 0} else None
        ),
        "direct_match_capability": {
            "status": "AVAILABLE" if direct_key else "UNAVAILABLE",
            "reason": (
                "stable frame number/absolute timestamp exists"
                if direct_key
                else "official CSV has no stable frame number or absolute frame.time_epoch"
            ),
            "formal_packet_frame_direct_match_coverage": None,
        },
        "session_scope": "one source capture only",
        "session_crosses_capture": False,
    }


def assign_session_label(
    *,
    expected_label: str,
    capture_provenance: dict[str, Any] | None,
    direct_labels: Iterable[str] = (),
    session_capture_id: str,
    provenance_capture_id: str | None = None,
) -> dict[str, Any]:
    labels = [str(item) for item in direct_labels]
    label_set = sorted(set(labels))
    result = {
        "assigned_label": None,
        "direct_evidence_count": len(labels),
        "direct_label_set": label_set,
        "label_assignment_method": UNMATCHED_METHOD,
        "quarantined": True,
        "reason": "capture_provenance_not_verified",
    }
    if not capture_provenance or capture_provenance.get("status") != "PASS":
        return result
    provenance_id = provenance_capture_id or str(capture_provenance.get("capture_id", ""))
    if not provenance_id or session_capture_id != provenance_id:
        result["reason"] = "session_capture_mismatch"
        return result
    if len(label_set) > 1:
        result["label_assignment_method"] = CONFLICT_METHOD
        result["reason"] = "multiple_official_labels_in_session"
        return result
    if len(label_set) == 1:
        if label_set[0] != expected_label:
            result["label_assignment_method"] = CONFLICT_METHOD
            result["reason"] = "direct_label_disagrees_with_verified_capture_label"
            return result
        result.update(
            assigned_label=label_set[0],
            label_assignment_method=DIRECT_EVIDENCE_POLICY,
            quarantined=False,
            reason="all_direct_official_evidence_is_unanimous",
        )
        return result

    fallback_requirements = (
        capture_provenance.get("pcap_identity_verified") is True,
        capture_provenance.get("companion_csv_identity_verified") is True,
        capture_provenance.get("csv_label_purity") == 1.0,
        capture_provenance.get("expected_label") == expected_label,
        capture_provenance.get("session_crosses_capture") is False,
    )
    if all(fallback_requirements):
        result.update(
            assigned_label=expected_label,
            label_assignment_method=CAPTURE_FALLBACK_METHOD,
            quarantined=False,
            reason="all_verified_capture_fallback_requirements_pass",
        )
    else:
        result["reason"] = "verified_capture_fallback_requirements_failed"
    return result


def preflight_edge_captures(
    *,
    edge_config: dict[str, Any],
    edge_root: Path,
    official_archive_verified: bool,
    expected_hashes: dict[str, dict[str, str]] | None = None,
    capinfos_bin: str = "capinfos",
) -> dict[str, Any]:
    captures: list[dict[str, Any]] = []
    expected_hashes = expected_hashes or {}
    for spec in edge_config["captures"]:
        capture_id = str(spec["id"])
        baseline = expected_hashes.get(capture_id, {})
        pcap_path = edge_root / spec["pcap"]
        csv_path = edge_root / spec["csv"]
        capture = validate_edge_capture_provenance(
            capture_id=capture_id,
            pcap_path=pcap_path,
            companion_csv_path=csv_path,
            expected_label=str(spec["fine_label"]),
            pcap_sha256=spec.get("_pcap_sha256"),
            companion_csv_sha256=spec.get("_csv_sha256"),
            expected_pcap_sha256=baseline.get("pcap_sha256"),
            expected_companion_csv_sha256=baseline.get("companion_csv_sha256"),
            official_archive_verified=official_archive_verified,
            packet_count=pcap_packet_count(pcap_path, capinfos_bin),
        )
        spec["_label_provenance"] = capture
        captures.append(capture)
    passed = sum(item["status"] == "PASS" for item in captures)
    return {
        "generated_at": _now(),
        "policy_version": PROVENANCE_POLICY_VERSION,
        "session_label_policy": DIRECT_EVIDENCE_POLICY,
        "capture_fallback_policy": CAPTURE_FALLBACK_METHOD,
        "CAPTURE_PROVENANCE_GATE": "PASS" if passed == len(captures) else "BLOCKED",
        "capture_count": len(captures),
        "passed_capture_count": passed,
        "failed_capture_count": len(captures) - passed,
        "captures": captures,
    }


def provenance_by_capture(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["capture_id"]): item for item in manifest.get("captures", [])}


def summarize_catalog_session_provenance(
    *,
    catalog: ProductionCatalog,
    dataset: str,
    preflight_manifest: dict[str, Any],
) -> dict[str, Any]:
    by_capture = provenance_by_capture(preflight_manifest)
    captures: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    catalog_groups: dict[str, dict[str, int]] = {}
    for capture_id, source_hash, count in catalog.query(
        """
        SELECT capture_id,source_hash,COUNT(*)
        FROM records
        WHERE dataset=?
        GROUP BY capture_id,source_hash
        """,
        (dataset,),
    ):
        catalog_groups.setdefault(str(capture_id), {})[str(source_hash)] = int(count)
    for capture_id, provenance in sorted(by_capture.items()):
        capture_groups = catalog_groups.get(capture_id, {})
        sessions = sum(capture_groups.values())
        source_hashes = set(capture_groups)
        source_matches = not source_hashes or source_hashes == {
            provenance.get("combined_source_sha256")
        }
        verified = provenance.get("status") == "PASS" and source_matches
        fallback = sessions if verified else 0
        unmatched = 0 if verified else sessions
        method_distribution = {
            DIRECT_EVIDENCE_POLICY: 0,
            CAPTURE_FALLBACK_METHOD: fallback,
            CONFLICT_METHOD: 0,
            UNMATCHED_METHOD: unmatched,
        }
        entry = {
            **provenance,
            "catalog_source_hashes": sorted(source_hashes),
            "catalog_source_identity_matches": source_matches,
            "session_count": sessions,
            "session_direct_evidence_count": 0,
            "unanimous_session_count": 0,
            "conflict_session_count": 0,
            "verified_capture_fallback_count": fallback,
            "unmatched_quarantine_count": unmatched,
            "assignment_method_distribution": method_distribution,
        }
        captures.append(entry)
        totals["sessions"] += sessions
        totals["direct_evidence_sessions"] += 0
        totals["unanimous_sessions"] += 0
        totals["conflict_sessions"] += 0
        totals["verified_capture_fallback_sessions"] += fallback
        totals["unmatched_quarantine_sessions"] += unmatched
    total_direct = totals["direct_evidence_sessions"]
    totals_dict = dict(totals)
    totals_dict["unanimous_rate_among_direct_evidence"] = (
        totals["unanimous_sessions"] / total_direct if total_direct else None
    )
    return {
        **{key: value for key, value in preflight_manifest.items() if key != "captures"},
        "captures": captures,
        "totals": totals_dict,
        "limitations": [
            "Official companion CSVs do not provide a uniformly stable frame number or absolute epoch key; sessions without reliable direct evidence use only verified pure-capture fallback.",
            "A separately preserved exact-relative-time audit provides direct evidence for selected captures but is not silently promoted to every production session.",
        ],
    }


def checkpoint_reuse_audit(
    *,
    output_root: Path,
    catalog: ProductionCatalog,
    dataset: str,
    config_hash: str,
    mode: str,
    preflight_manifest: dict[str, Any],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for capture_id, provenance in sorted(provenance_by_capture(preflight_manifest).items()):
        safe = "".join(
            ch if ch.isalnum() or ch in {"_", "-"} else "_"
            for ch in f"{dataset}_{capture_id}"
        )
        path = output_root / "_state" / "checkpoints" / f"{safe}.json"
        if not path.is_file():
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        rows = catalog.capture_count(dataset, capture_id)
        expected_rows = int(value.get("result", {}).get("records", -1))
        checks = {
            "completed": value.get("status") == "COMPLETED",
            "config_hash_matches": value.get("config_hash") == config_hash,
            "mode_matches": value.get("mode") == mode,
            "source_fingerprint_matches": value.get("source_fingerprint")
            == provenance.get("combined_source_sha256"),
            "catalog_row_count_matches": rows == expected_rows,
            "capture_provenance_passes": provenance.get("status") == "PASS",
        }
        entries.append(
            {
                "capture_id": capture_id,
                "checkpoint": str(path),
                "catalog_rows": rows,
                "expected_rows": expected_rows,
                "checks": checks,
                "reusable": all(checks.values()),
            }
        )
    database_integrity = str(catalog.scalar("PRAGMA integrity_check"))
    reusable = (
        bool(entries)
        and all(item["reusable"] for item in entries)
        and database_integrity == "ok"
    )
    return {
        "CHECKPOINT_REUSABLE": reusable,
        "database_integrity": database_integrity,
        "completed_checkpoint_count": len(entries),
        "completed_checkpoints": entries,
        "requires_tshark_for_completed_captures": not reusable,
        "reason": (
            "catalog retains capture/source identity and frame spans; verified pure-capture fallback can be projected without packet re-extraction"
            if reusable
            else "one or more completed checkpoint identity/count/provenance checks failed"
        ),
    }
