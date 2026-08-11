from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from .contracts import (
    APPLICATION_EVIDENCE_VERSION,
    SANITIZED_PAYLOAD_VERSION,
    canonical_json,
    content_digest,
)
from .evidence import (
    TSHARK_FIELDS_V1,
    ApplicationEvidenceV1,
    SanitizedPayloadV1,
    application_observation_from_frame,
    audit_shortcut_tokens,
    decode_hex_payload,
    sanitize_payload_text,
)


MATERIALIZER_VERSION = "near_application_payload_materializer_v5"
TSHARK_PROFILE_VERSION = "EDGE_TSHARK_APPLICATION_PAYLOAD_FIELDS_V1"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class SessionLocator:
    sample_id: str
    fine_label: str
    coarse_label: str
    capture_id: str
    pcap_path: Path
    pcap_sha256: str
    first_frame: int
    last_frame: int
    l4_protocol: str
    initiator_ip: str
    responder_ip: str
    initiator_port: int
    responder_port: int

    @property
    def flow_key(self) -> tuple[str, tuple[str, int], tuple[str, int]]:
        endpoints = sorted(
            (
                (self.initiator_ip, self.initiator_port),
                (self.responder_ip, self.responder_port),
            )
        )
        return (self.l4_protocol.upper(), endpoints[0], endpoints[1])


@dataclass(slots=True)
class SessionAccumulator:
    application: dict[str, dict[str, Any]]
    raw_payload: list[str]
    sanitized_payload: list[str]
    matched_frames: int = 0

    @classmethod
    def empty(cls) -> "SessionAccumulator":
        return cls(application={}, raw_payload=[], sanitized_payload=[])


def _require_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.dataset as ds
    except ImportError as exc:  # pragma: no cover - optional data environment
        raise RuntimeError("materialization requires the optional PyArrow data stack") from exc
    return pa, ds


def load_near_candidate_locators(production_root: Path) -> list[SessionLocator]:
    pa, ds = _require_pyarrow()
    import pyarrow.parquet as pq

    production_root = Path(production_root)
    candidate_path = production_root / "sft_candidates/preset=Near/part-00000.parquet"
    candidate_rows = pq.read_table(candidate_path).to_pylist()
    candidate_ids = [str(row["sample_id"]) for row in candidate_rows]
    if len(candidate_ids) != 16979 or len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Near PLAN_B candidate identity/count mismatch")
    for row in candidate_rows:
        if (
            row.get("physical_split") != "train"
            or row.get("ku_role") != "K_known"
            or row.get("preset") != "Near"
            or row.get("plan") != "PLAN_B"
        ):
            raise ValueError("Near candidate escaped frozen PLAN_B K_known TRAIN scope")

    backend = ds.dataset(
        production_root / "backend_records/dataset=Edge-IIoTset/split=train",
        format="parquet",
    )
    table = backend.to_table(
        columns=[
            "sample_id",
            "scenario_or_capture_id",
            "fine_label",
            "coarse_label",
            "first_frame_or_record",
            "last_frame_or_record",
            "l4_protocol",
            "raw_initiator_ip",
            "raw_responder_ip",
            "raw_initiator_port",
            "raw_responder_port",
        ],
        filter=ds.field("sample_id").isin(candidate_ids),
    )
    rows = {str(row["sample_id"]): row for row in table.to_pylist()}
    if len(rows) != len(candidate_ids):
        raise ValueError("Near candidates do not map one-to-one to backend records")

    provenance = json.loads(
        (production_root / "manifests/edge_label_provenance_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    source_map = {
        str(item["capture_id"]): (
            Path(item["source_mapping"]["pcap"]),
            str(item["pcap_sha256"]),
        )
        for item in provenance["captures"]
        if item.get("status") == "PASS"
    }
    locators: list[SessionLocator] = []
    for sample_id in candidate_ids:
        row = rows[sample_id]
        capture_id = str(row["scenario_or_capture_id"])
        if capture_id not in source_map:
            raise ValueError(f"capture provenance is unavailable: {capture_id}")
        pcap_path, pcap_sha = source_map[capture_id]
        if not pcap_path.is_file():
            raise FileNotFoundError(pcap_path)
        locators.append(
            SessionLocator(
                sample_id=sample_id,
                fine_label=str(row["fine_label"]),
                coarse_label=str(row["coarse_label"]),
                capture_id=capture_id,
                pcap_path=pcap_path,
                pcap_sha256=pcap_sha,
                first_frame=int(row["first_frame_or_record"]),
                last_frame=int(row["last_frame_or_record"]),
                l4_protocol=str(row["l4_protocol"]),
                initiator_ip=str(row["raw_initiator_ip"]),
                responder_ip=str(row["raw_responder_ip"]),
                initiator_port=int(row["raw_initiator_port"]),
                responder_port=int(row["raw_responder_port"]),
            )
        )
    return locators


def _frame_flow_key(frame: dict[str, str]) -> tuple[str, tuple[str, int], tuple[str, int]] | None:
    source_ip = frame.get("ip.src") or frame.get("ipv6.src")
    destination_ip = frame.get("ip.dst") or frame.get("ipv6.dst")
    if not source_ip or not destination_ip:
        return None
    if frame.get("tcp.srcport") and frame.get("tcp.dstport"):
        protocol = "TCP"
        source_port, destination_port = int(frame["tcp.srcport"]), int(frame["tcp.dstport"])
    elif frame.get("udp.srcport") and frame.get("udp.dstport"):
        protocol = "UDP"
        source_port, destination_port = int(frame["udp.srcport"]), int(frame["udp.dstport"])
    else:
        protocols = frame.get("frame.protocols", "").casefold()
        protocol = "ICMP" if "icmp" in protocols else "OTHER"
        source_port = destination_port = 0
    endpoints = sorted(((source_ip, source_port), (destination_ip, destination_port)))
    return (protocol, endpoints[0], endpoints[1])


class CaptureSessionMatcher:
    def __init__(self, locators: Iterable[SessionLocator]):
        grouped: dict[
            tuple[str, tuple[str, int], tuple[str, int]], list[SessionLocator]
        ] = defaultdict(list)
        for locator in locators:
            grouped[locator.flow_key].append(locator)
        self._groups = {
            key: sorted(items, key=lambda item: (item.first_frame, item.last_frame, item.sample_id))
            for key, items in grouped.items()
        }
        self._starts = {
            key: [item.first_frame for item in items] for key, items in self._groups.items()
        }

    def match(self, frame_number: int, frame: dict[str, str]) -> SessionLocator | None:
        key = _frame_flow_key(frame)
        if key is None or key not in self._groups:
            return None
        items = self._groups[key]
        index = bisect_right(self._starts[key], frame_number) - 1
        if index >= 0 and frame_number <= items[index].last_frame:
            return items[index]
        return None


def _tshark_command(pcap: Path, *, packet_limit: int | None = None) -> list[str]:
    command = [
        "tshark",
        "-n",
        "-r",
        str(pcap),
    ]
    if packet_limit is not None:
        if packet_limit < 1:
            raise ValueError("TShark packet limit must be positive")
        command.extend(("-c", str(packet_limit)))
    command.extend(
        [
        "-T",
        "fields",
        "-E",
        "separator=/t",
        "-E",
        "quote=d",
        "-E",
        "occurrence=f",
        ]
    )
    for field in TSHARK_FIELDS_V1:
        command.extend(("-e", field))
    return command


def iter_tshark_frames(
    pcap: Path,
    *,
    stderr_path: Path,
    packet_limit: int | None = None,
) -> Iterator[dict[str, str]]:
    csv.field_size_limit(8 * 1024 * 1024)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stderr_path.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            _tshark_command(pcap, packet_limit=packet_limit),
            stdout=subprocess.PIPE,
            stderr=stderr_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        reader = csv.reader(process.stdout, delimiter="\t", quotechar='"')
        for row in reader:
            if len(row) < len(TSHARK_FIELDS_V1):
                row.extend([""] * (len(TSHARK_FIELDS_V1) - len(row)))
            if len(row) != len(TSHARK_FIELDS_V1):
                continue
            yield dict(zip(TSHARK_FIELDS_V1, row, strict=True))
        return_code = process.wait()
    if return_code:
        raise RuntimeError(f"TShark failed for {pcap.name}; see {stderr_path}")


def _atomic_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(pa.Table.from_pylist(rows), temporary, compression="zstd")
    os.replace(temporary, path)


def _capture_checkpoint_valid(path: Path, *, locator_digest: str, pcap_sha256: str) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    metadata_matches = (
        value.get("status") == "PASS"
        and value.get("locator_digest") == locator_digest
        and value.get("pcap_sha256") == pcap_sha256
        and value.get("materializer_version") == MATERIALIZER_VERSION
    )
    if not metadata_matches:
        return False
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return False
    for artifact in artifacts.values():
        if not isinstance(artifact, dict):
            return False
        artifact_path = Path(str(artifact.get("path", "")))
        if not artifact_path.is_file() or sha256_file(artifact_path) != artifact.get("sha256"):
            return False
    return True


def tshark_version() -> str:
    result = subprocess.run(
        ["tshark", "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.splitlines()[0].strip()


def materialize_capture(
    locators: list[SessionLocator],
    *,
    output_root: Path,
    force: bool = False,
) -> dict[str, Any]:
    if not locators:
        raise ValueError("capture materialization requires legal session locators")
    capture_id = locators[0].capture_id
    if any(item.capture_id != capture_id for item in locators):
        raise ValueError("one materialization call may process only one capture")
    pcap = locators[0].pcap_path
    pcap_sha = locators[0].pcap_sha256
    if sha256_file(pcap) != pcap_sha:
        raise ValueError(f"PCAP identity mismatch: {capture_id}")
    locator_digest = content_digest(
        [
            [item.sample_id, item.first_frame, item.last_frame, item.flow_key]
            for item in sorted(locators, key=lambda value: value.sample_id)
        ]
    )
    safe_capture = re_sub_nonword(capture_id)
    checkpoint_path = output_root / "checkpoints" / f"{safe_capture}.json"
    if not force and _capture_checkpoint_valid(
        checkpoint_path, locator_digest=locator_digest, pcap_sha256=pcap_sha
    ):
        return json.loads(checkpoint_path.read_text(encoding="utf-8"))

    accumulators = {item.sample_id: SessionAccumulator.empty() for item in locators}
    matcher = CaptureSessionMatcher(locators)
    tshark_frames = 0
    matched_frames = 0
    packet_limit = max(item.last_frame for item in locators)
    for frame in iter_tshark_frames(
        pcap,
        stderr_path=output_root / "logs" / f"{safe_capture}.tshark.stderr.log",
        packet_limit=packet_limit,
    ):
        tshark_frames += 1
        try:
            frame_number = int(frame["frame.number"])
        except (KeyError, ValueError):
            continue
        locator = matcher.match(frame_number, frame)
        if locator is None:
            continue
        matched_frames += 1
        accumulator = accumulators[locator.sample_id]
        accumulator.matched_frames += 1
        observation = application_observation_from_frame(frame)
        if observation is not None and len(accumulator.application) < 24:
            accumulator.application.setdefault(canonical_json(observation), observation)
        if len(accumulator.raw_payload) < 3:
            raw_fragment = None
            for field in ("tcp.payload", "udp.payload", "data.data"):
                raw_fragment = decode_hex_payload(frame.get(field, ""))
                if raw_fragment:
                    break
            if raw_fragment:
                sanitized = sanitize_payload_text(raw_fragment, max_chars=768)
                if sanitized and sanitized not in accumulator.sanitized_payload:
                    accumulator.raw_payload.append(raw_fragment[:2048])
                    accumulator.sanitized_payload.append(sanitized)

    application_rows: list[dict[str, Any]] = []
    raw_payload_rows: list[dict[str, Any]] = []
    payload_rows: list[dict[str, Any]] = []
    for locator in sorted(locators, key=lambda item: item.sample_id):
        accumulator = accumulators[locator.sample_id]
        observations = tuple(accumulator.application.values())
        protocols = sorted({str(item.get("kind", "unknown")) for item in observations})
        if observations:
            value = ApplicationEvidenceV1(
                protocol="+".join(protocols),
                observations=observations,
                frame_count=accumulator.matched_frames,
                truncated=len(accumulator.application) >= 24,
            )
            application_rows.append(
                {
                    "schema_version": APPLICATION_EVIDENCE_VERSION,
                    "sample_id": locator.sample_id,
                    "split": "train",
                    "fine_label": locator.fine_label,
                    "application_json": canonical_json(value.model_dump(mode="json")),
                }
            )
        if accumulator.sanitized_payload:
            value = SanitizedPayloadV1(
                protocol=locator.l4_protocol.upper(),
                fragments=tuple(accumulator.sanitized_payload),
                raw_fragment_count=len(accumulator.raw_payload),
                max_fragment_chars=768,
                truncated=any(len(item) > 768 for item in accumulator.raw_payload),
            )
            raw_payload_rows.append(
                {
                    "schema_version": "RAW_BACKEND_PAYLOAD_AUDIT_V1",
                    "sample_id": locator.sample_id,
                    "split": "train",
                    "fine_label": locator.fine_label,
                    "raw_fragments_json": canonical_json(accumulator.raw_payload),
                }
            )
            payload_rows.append(
                {
                    "schema_version": SANITIZED_PAYLOAD_VERSION,
                    "sample_id": locator.sample_id,
                    "split": "train",
                    "fine_label": locator.fine_label,
                    "payload_json": canonical_json(value.model_dump(mode="json")),
                }
            )

    paths = {
        "application": output_root / "application" / "captures" / f"{safe_capture}.parquet",
        "raw_payload": output_root
        / "sanitized_payload"
        / "backend_raw_audit"
        / f"{safe_capture}.parquet",
        "payload": output_root
        / "sanitized_payload"
        / "captures"
        / f"{safe_capture}.parquet",
    }
    _atomic_parquet(paths["application"], application_rows or _empty_application_rows())
    _atomic_parquet(paths["raw_payload"], raw_payload_rows or _empty_raw_payload_rows())
    _atomic_parquet(paths["payload"], payload_rows or _empty_payload_rows())
    checkpoint = {
        "status": "PASS",
        "materializer_version": MATERIALIZER_VERSION,
        "tshark_profile": TSHARK_PROFILE_VERSION,
        "tshark_version": tshark_version(),
        "tshark_options": ["-n", "-T fields", "-E separator=/t", "-E quote=d", "-E occurrence=f"],
        "tshark_packet_limit": packet_limit,
        "tshark_fields": list(TSHARK_FIELDS_V1),
        "capture_id": capture_id,
        "pcap_path": str(pcap),
        "pcap_sha256": pcap_sha,
        "locator_digest": locator_digest,
        "candidate_sessions": len(locators),
        "tshark_frames": tshark_frames,
        "matched_frames": matched_frames,
        "application_sessions": len(application_rows),
        "payload_sessions": len(payload_rows),
        "artifacts": {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in paths.items()},
    }
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = checkpoint_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, checkpoint_path)
    return checkpoint


def re_sub_nonword(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _empty_application_rows() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": APPLICATION_EVIDENCE_VERSION,
            "sample_id": "",
            "split": "train",
            "fine_label": "",
            "application_json": "",
        }
    ]


def _empty_raw_payload_rows() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": "RAW_BACKEND_PAYLOAD_AUDIT_V1",
            "sample_id": "",
            "split": "train",
            "fine_label": "",
            "raw_fragments_json": "[]",
        }
    ]


def _empty_payload_rows() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": SANITIZED_PAYLOAD_VERSION,
            "sample_id": "",
            "split": "train",
            "fine_label": "",
            "payload_json": "",
        }
    ]


def materialize_application_payload(
    production_root: Path,
    output_root: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    locators = load_near_candidate_locators(production_root)
    by_capture: dict[str, list[SessionLocator]] = defaultdict(list)
    for locator in locators:
        by_capture[locator.capture_id].append(locator)
    checkpoints = [
        materialize_capture(items, output_root=output_root, force=force)
        for _capture, items in sorted(by_capture.items())
    ]
    return audit_materialized_sidecars(
        output_root,
        candidate_locators=locators,
        checkpoints=checkpoints,
    )


def resanitize_materialized_payload(
    production_root: Path,
    output_root: Path,
    *,
    accepted_source_versions: tuple[str, ...] = ("near_application_payload_materializer_v4",),
) -> dict[str, Any]:
    """Rebuild only model-visible payload from verified backend raw sidecars."""

    import pyarrow.parquet as pq

    locators = load_near_candidate_locators(production_root)
    by_capture: dict[str, list[SessionLocator]] = defaultdict(list)
    for locator in locators:
        by_capture[locator.capture_id].append(locator)
    checkpoints: list[dict[str, Any]] = []
    for capture_id, capture_locators in sorted(by_capture.items()):
        safe_capture = re_sub_nonword(capture_id)
        checkpoint_path = output_root / "checkpoints" / f"{safe_capture}.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("materializer_version") not in accepted_source_versions:
            raise ValueError(f"raw sidecar source version is not accepted: {capture_id}")
        for artifact in checkpoint["artifacts"].values():
            path = Path(artifact["path"])
            if sha256_file(path) != artifact["sha256"]:
                raise ValueError(f"sidecar hash mismatch before resanitization: {capture_id}")
        raw_path = Path(checkpoint["artifacts"]["raw_payload"]["path"])
        payload_path = Path(checkpoint["artifacts"]["payload"]["path"])
        raw_rows = [row for row in pq.read_table(raw_path).to_pylist() if row.get("sample_id")]
        prior_payload = {
            str(row["sample_id"]): json.loads(str(row["payload_json"]))
            for row in pq.read_table(payload_path).to_pylist()
            if row.get("sample_id")
        }
        payload_rows: list[dict[str, Any]] = []
        for raw_row in raw_rows:
            sample_id = str(raw_row["sample_id"])
            previous = prior_payload.get(sample_id)
            if previous is None:
                raise ValueError(f"raw payload has no prior protocol lineage: {sample_id}")
            raw_fragments = json.loads(str(raw_row["raw_fragments_json"]))
            sanitized: list[str] = []
            for raw_fragment in raw_fragments:
                value = sanitize_payload_text(str(raw_fragment), max_chars=768)
                if value and value not in sanitized:
                    sanitized.append(value)
            if not sanitized:
                continue
            value = SanitizedPayloadV1(
                protocol=str(previous["protocol"]),
                fragments=tuple(sanitized[:3]),
                raw_fragment_count=len(raw_fragments),
                max_fragment_chars=768,
                truncated=any(len(str(item)) > 768 for item in raw_fragments),
            )
            payload_rows.append(
                {
                    "schema_version": SANITIZED_PAYLOAD_VERSION,
                    "sample_id": sample_id,
                    "split": "train",
                    "fine_label": str(raw_row["fine_label"]),
                    "payload_json": canonical_json(value.model_dump(mode="json")),
                }
            )
        _atomic_parquet(payload_path, payload_rows or _empty_payload_rows())
        checkpoint["resanitize_source_materializer_version"] = checkpoint["materializer_version"]
        checkpoint["materializer_version"] = MATERIALIZER_VERSION
        checkpoint["resanitized_from_verified_raw_sidecar"] = True
        checkpoint["payload_sessions"] = len(payload_rows)
        checkpoint["artifacts"]["payload"]["sha256"] = sha256_file(payload_path)
        temporary = checkpoint_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, checkpoint_path)
        checkpoints.append(checkpoint)
    return audit_materialized_sidecars(
        output_root,
        candidate_locators=locators,
        checkpoints=checkpoints,
    )


def _read_nonempty_parquet_rows(paths: Iterable[Path]) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    output: list[dict[str, Any]] = []
    for path in sorted(paths):
        for row in pq.read_table(path).to_pylist():
            if row.get("sample_id"):
                output.append(row)
    return output


def audit_materialized_sidecars(
    output_root: Path,
    *,
    candidate_locators: list[SessionLocator],
    checkpoints: list[dict[str, Any]],
) -> dict[str, Any]:
    application_rows = _read_nonempty_parquet_rows(
        (output_root / "application/captures").glob("*.parquet")
    )
    payload_rows = _read_nonempty_parquet_rows(
        (output_root / "sanitized_payload/captures").glob("*.parquet")
    )
    raw_rows = _read_nonempty_parquet_rows(
        (output_root / "sanitized_payload/backend_raw_audit").glob("*.parquet")
    )
    candidate_ids = {item.sample_id for item in candidate_locators}
    for name, rows in (("application", application_rows), ("payload", payload_rows), ("raw", raw_rows)):
        ids = [str(row["sample_id"]) for row in rows]
        if len(ids) != len(set(ids)) or not set(ids).issubset(candidate_ids):
            raise ValueError(f"{name} sidecar identity/scope violation")
        if any(row.get("split") != "train" for row in rows):
            raise ValueError(f"{name} sidecar escaped TRAIN")

    payload_by_id = {str(row["sample_id"]): row for row in payload_rows}
    shortcut_input: list[tuple[str, tuple[str, ...]]] = []
    for row in payload_rows:
        value = json.loads(str(row["payload_json"]))
        shortcut_input.append((str(row["fine_label"]), tuple(value["fragments"])))
    shortcut_findings = audit_shortcut_tokens(shortcut_input)
    explicit_blockers = [
        item
        for item in shortcut_findings
        if item.token in {"sqlmap", "nikto", "hydra", "dvwa", "metasploit", "nmap"}
    ]
    risk = "HIGH" if explicit_blockers else ("MEDIUM" if len(shortcut_findings) > 20 else "LOW")

    raw_by_id = {str(row["sample_id"]): row for row in raw_rows}
    semantic_patterns = {
        "sql": ("select", "union", " or ", " and ", "--"),
        "http": ("http/", "get ", "post ", "content-type"),
        "script": ("<script", "javascript:", "onerror="),
        "command": ("/bin/", "cmd=", "<command_param>=", "powershell", "wget ", "curl "),
    }
    preservation: dict[str, dict[str, int]] = {
        name: {"raw": 0, "sanitized": 0} for name in semantic_patterns
    }
    for sample_id, raw_row in raw_by_id.items():
        if sample_id not in payload_by_id:
            continue
        raw_text = "\n".join(json.loads(str(raw_row["raw_fragments_json"]))).casefold()
        safe_text = "\n".join(json.loads(str(payload_by_id[sample_id]["payload_json"]))["fragments"]).casefold()
        for name, patterns in semantic_patterns.items():
            if any(pattern in raw_text for pattern in patterns):
                preservation[name]["raw"] += 1
                if any(pattern in safe_text for pattern in patterns):
                    preservation[name]["sanitized"] += 1

    class_total = Counter(item.fine_label for item in candidate_locators)
    app_by_class = Counter(str(row["fine_label"]) for row in application_rows)
    payload_by_class = Counter(str(row["fine_label"]) for row in payload_rows)
    protocol_counts: Counter[str] = Counter()
    for row in application_rows:
        protocol_counts.update(str(json.loads(str(row["application_json"]))["protocol"]).split("+"))
    manifest = {
        "status": "PASS" if risk != "HIGH" else "FAIL",
        "version": MATERIALIZER_VERSION,
        "application_version": APPLICATION_EVIDENCE_VERSION,
        "payload_version": SANITIZED_PAYLOAD_VERSION,
        "candidate_scope": "Near PLAN_B K_known TRAIN only",
        "candidate_sessions": len(candidate_locators),
        "capture_count": len(checkpoints),
        "application_sessions": len(application_rows),
        "payload_sessions": len(payload_rows),
        "application_coverage": len(application_rows) / len(candidate_locators),
        "payload_coverage": len(payload_rows) / len(candidate_locators),
        "class_coverage": {
            label: {
                "candidate": count,
                "application": app_by_class[label],
                "payload": payload_by_class[label],
            }
            for label, count in sorted(class_total.items())
        },
        "application_protocol_counts": dict(sorted(protocol_counts.items())),
        "payload_shortcut_risk": risk,
        "shortcut_findings": [asdict(item) for item in shortcut_findings[:100]],
        "semantic_preservation": preservation,
        "redaction_rules": [
            "raw IP/IPv6",
            "host/origin/referer",
            "cookie/authorization",
            "UUID/long tokens",
            "absolute time",
            "fixed lab path",
            "automation tool marker",
            "device/session/user identifiers",
        ],
        "checkpoints": checkpoints,
        "artifact_digest": content_digest(
            [
                checkpoint["artifacts"]
                for checkpoint in sorted(checkpoints, key=lambda item: item["capture_id"])
            ]
        ),
        "u_final_count": 0,
    }
    manifest_path = output_root / "manifests/application_payload_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, manifest_path)
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    return manifest
