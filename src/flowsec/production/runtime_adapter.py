from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pydantic import Field, model_validator

from flowsec.production.schema import (
    CANONICAL_SCHEMA_VERSION,
    INITIAL_VIEW_VERSION,
    canonical_json,
)
from flowsec.runtime.contracts import (
    AgentAction,
    CallMetrics,
    Capability,
    CapabilityStatus,
    EvidenceItem,
    EvidenceTrust,
    FrozenRuntimeModel,
    GapDomain,
    GapType,
    RuntimeInput,
    RuntimePhase,
    ToolRequest,
    ToolResult,
    ToolStatus,
    validate_model_visible_value,
)


ADAPTER_VERSION = "production_runtime_adapter_v1"
EVIDENCE_SCHEMA_VERSION = "production_runtime_evidence_v1"
PAPER_SPLIT_VERSION = "CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2"
PRODUCTION_ASSET_VERSION = "edge_split_revision_v2"
_SAMPLE_ID = re.compile(r"^fs1_[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")

_DATASETS = frozenset({"Edge-IIoTset", "IoT-23"})
_INITIAL_SOURCE_KEYS = frozenset(
    {"label_schema_id", "packet_sequence", "session_summary", "capabilities", "missing_fields"}
)
_PACKET_KEYS = frozenset(
    {"direction", "packet_length", "relative_iat", "l3_protocol", "l4_protocol", "tcp_flags"}
)
_SUMMARY_KEYS = frozenset(
    {
        "duration",
        "initiator_packets",
        "responder_packets",
        "initiator_bytes",
        "responder_bytes",
        "packet_length_stats",
        "iat_stats",
        "handshake_state",
    }
)
_STATS_KEYS = frozenset({"min", "max", "mean", "std"})
_SOURCE_CAPABILITIES = frozenset(
    {
        "packet_expand_9_16",
        "temporal_context",
        "relation_context",
        "service_diagnostic",
        "application_evidence",
    }
)
_SOURCE_MISSING_FIELDS = frozenset({"application_evidence", "sanitized_payload"})
_TEMPORAL_STATS_KEYS = frozenset(
    {
        "window_seconds",
        "prior_session_count",
        "unique_destination_count",
        "unique_destination_service_category_count",
        "same_destination_distinct_source_count",
        "repeated_pair_count",
        "incomplete_handshake_ratio",
        "inter_session_gap",
        "prior_packets",
        "prior_bytes",
    }
)

_ASSET_SCHEMAS: dict[str, frozenset[str]] = {
    "sample_id_index": frozenset(
        {
            "schema_version",
            "sample_id",
            "dataset",
            "split",
            "fine_label",
            "coarse_label",
            "capture_ref_hash",
            "source_sha256",
            "evidence_signature",
            "exact_signature",
            "reverse_signature",
            "near_signature",
        }
    ),
    "initial_model_views": frozenset(
        {"schema_version", "view_version", "sample_id", "split", "view_json"}
    ),
    "expandable_packet_store": frozenset(
        {"schema_version", "sample_id", "split", "packets_9_16_json", "rag_retrieval_key"}
    ),
    "temporal_index": frozenset(
        {
            "schema_version",
            "sample_id",
            "split",
            "timestamp",
            "context_latest_timestamp",
            "source_identity_hash",
            "destination_identity_hash",
            "communication_pair_hash",
            "context_stats_json",
        }
    ),
    "relation_index": frozenset(
        {
            "schema_version",
            "sample_id",
            "split",
            "source_identity_hash",
            "destination_identity_hash",
            "communication_pair_hash",
            "previous_pair_sample_ref",
            "model_node_roles",
        }
    ),
}

_EXPECTED_KU_ROLE = {
    RuntimePhase.TRAIN: "K_known",
    RuntimePhase.VALIDATION: "K_known",
    RuntimePhase.TEST: "K_known",
    RuntimePhase.U_DEV: "U_dev",
    RuntimePhase.U_FINAL: "U_final",
}
_ROLE_BY_PHASE = {
    RuntimePhase.TRAIN: frozenset({"sft_train"}),
    RuntimePhase.VALIDATION: frozenset({"sft_validation"}),
    RuntimePhase.TEST: frozenset({"closed_test", "scenario_held_closed_test"}),
    RuntimePhase.U_DEV: frozenset({"unknown_development"}),
    RuntimePhase.U_FINAL: frozenset({"final_unknown"}),
}


class ProductionRuntimeAdapterError(ValueError):
    """Raised when a Production asset cannot be safely projected into Runtime."""


class ProductionRuntimeAccessError(PermissionError):
    """Raised when the requested sample is not allowed in the requested Runtime phase."""


class ProductionSampleRequest(FrozenRuntimeModel):
    """Backend-only request from an evaluation harness to the safe adapter."""

    sample_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    split: str = Field(min_length=1)
    phase: RuntimePhase
    preset: str | None = None
    final_evaluation_authorized: bool = False

    @model_validator(mode="after")
    def validate_access_shape(self) -> "ProductionSampleRequest":
        if not _SAMPLE_ID.fullmatch(self.sample_id):
            raise ValueError("sample_id is not a frozen Production identity")
        if self.dataset not in _DATASETS:
            raise ValueError("unsupported Production dataset")
        if any(token in self.split for token in ("/", "\\", "..")):
            raise ValueError("invalid Production split")
        if self.dataset == "Edge-IIoTset" and not self.preset:
            raise ValueError("Edge requests require a frozen K/U preset")
        if self.dataset == "IoT-23" and self.preset is not None:
            raise ValueError("IoT-23 does not use an Edge K/U preset")
        if self.phase is RuntimePhase.U_FINAL and not self.final_evaluation_authorized:
            raise ProductionRuntimeAccessError(
                "U_final requires explicit formal-final-evaluation authorization"
            )
        if self.phase is not RuntimePhase.U_FINAL and self.final_evaluation_authorized:
            raise ProductionRuntimeAccessError(
                "final-evaluation authorization is valid only for U_final"
            )
        return self


@dataclass(frozen=True, slots=True, repr=False)
class BackendProvenance:
    """Backend-only trace reference; never render or pass this object to an LLM."""

    sample_id: str
    dataset: str
    split: str
    preset: str | None
    manifest_role: str
    ku_role: str
    capture_ref_hash: str
    source_sha256: str
    adapter_version: str
    production_version: str
    production_config_hash: str
    paper_split_version: str
    evidence_schema_version: str

    def __repr__(self) -> str:
        return "BackendProvenance(<backend-only redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ProductionRuntimeSample:
    """Strict separation between model-safe Runtime input and backend provenance."""

    runtime_input: RuntimeInput
    backend_provenance: BackendProvenance
    tools: tuple["ProductionEvidenceTool", ...]

    def __repr__(self) -> str:
        return "ProductionRuntimeSample(runtime_input=<typed>, backend_provenance=<redacted>)"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionRuntimeAdapterError(f"invalid required manifest: {path.name}") from exc
    if not isinstance(value, dict):
        raise ProductionRuntimeAdapterError(f"manifest must be an object: {path.name}")
    return value


def _strict_keys(value: dict[str, Any], allowed: frozenset[str], *, location: str) -> None:
    keys = frozenset(str(key) for key in value)
    if keys != allowed:
        unexpected = sorted(keys - allowed)
        missing = sorted(allowed - keys)
        raise ProductionRuntimeAdapterError(
            f"{location} schema mismatch; unexpected={unexpected}; missing={missing}"
        )


def _finite_number(value: Any, *, location: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProductionRuntimeAdapterError(f"{location} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ProductionRuntimeAdapterError(f"{location} must be finite")
    if minimum is not None and number < minimum:
        raise ProductionRuntimeAdapterError(f"{location} is below its minimum")
    return number


def _nonnegative_int(value: Any, *, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProductionRuntimeAdapterError(f"{location} must be a nonnegative integer")
    return value


def _parse_object(raw: Any, *, location: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise ProductionRuntimeAdapterError(f"{location} must be canonical JSON text")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProductionRuntimeAdapterError(f"{location} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ProductionRuntimeAdapterError(f"{location} must decode to an object")
    return value


def _parse_array(raw: Any, *, location: str) -> list[Any]:
    if not isinstance(raw, str):
        raise ProductionRuntimeAdapterError(f"{location} must be canonical JSON text")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProductionRuntimeAdapterError(f"{location} is invalid JSON") from exc
    if not isinstance(value, list):
        raise ProductionRuntimeAdapterError(f"{location} must decode to an array")
    return value


def _safe_text(value: Any, *, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProductionRuntimeAdapterError(f"{location} must be nonempty text")
    validate_model_visible_value(value, location=location)
    return value


def _safe_packet(value: Any, *, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProductionRuntimeAdapterError(f"{location} must be an object")
    _strict_keys(value, _PACKET_KEYS, location=location)
    direction = _safe_text(value["direction"], location=f"{location}.direction")
    if direction not in {"initiator_to_responder", "responder_to_initiator"}:
        raise ProductionRuntimeAdapterError(f"{location}.direction is invalid")
    tcp_flags = value["tcp_flags"]
    if tcp_flags is not None:
        tcp_flags = _nonnegative_int(tcp_flags, location=f"{location}.tcp_flags")
        if tcp_flags > 255:
            raise ProductionRuntimeAdapterError(f"{location}.tcp_flags is out of range")
    return {
        "direction": direction,
        "packet_length": _nonnegative_int(
            value["packet_length"], location=f"{location}.packet_length"
        ),
        "relative_iat": _finite_number(
            value["relative_iat"], location=f"{location}.relative_iat", minimum=0.0
        ),
        "l3_protocol": _safe_text(value["l3_protocol"], location=f"{location}.l3_protocol"),
        "l4_protocol": _safe_text(value["l4_protocol"], location=f"{location}.l4_protocol"),
        "tcp_flags": tcp_flags,
    }


def _safe_stats(value: Any, *, location: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ProductionRuntimeAdapterError(f"{location} must be an object")
    _strict_keys(value, _STATS_KEYS, location=location)
    return {
        key: _finite_number(value[key], location=f"{location}.{key}", minimum=0.0)
        for key in sorted(_STATS_KEYS)
    }


def _safe_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProductionRuntimeAdapterError("session_summary must be an object")
    _strict_keys(value, _SUMMARY_KEYS, location="session_summary")
    return {
        "duration": _finite_number(
            value["duration"], location="session_summary.duration", minimum=0.0
        ),
        "initiator_packets": _nonnegative_int(
            value["initiator_packets"], location="session_summary.initiator_packets"
        ),
        "responder_packets": _nonnegative_int(
            value["responder_packets"], location="session_summary.responder_packets"
        ),
        "initiator_bytes": _nonnegative_int(
            value["initiator_bytes"], location="session_summary.initiator_bytes"
        ),
        "responder_bytes": _nonnegative_int(
            value["responder_bytes"], location="session_summary.responder_bytes"
        ),
        "packet_length_stats": _safe_stats(
            value["packet_length_stats"], location="session_summary.packet_length_stats"
        ),
        "iat_stats": _safe_stats(value["iat_stats"], location="session_summary.iat_stats"),
        "handshake_state": _safe_text(
            value["handshake_state"], location="session_summary.handshake_state"
        ),
    }


def _opaque_evidence_id(sample_id: str, evidence_kind: str, request_signature: str = "") -> str:
    material = "|".join(
        (
            ADAPTER_VERSION,
            PRODUCTION_ASSET_VERSION,
            EVIDENCE_SCHEMA_VERSION,
            sample_id,
            evidence_kind,
            request_signature,
        )
    )
    return "ev_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


class ProductionParquetEvidenceStore:
    """Read-only, strict-schema access to the materialized Production evidence assets."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.manifest_root = self.root / "manifests"
        if not self.root.is_dir():
            raise ProductionRuntimeAdapterError("Production asset root is unavailable")
        self.canonical_manifest = _load_json(self.manifest_root / "canonical_schema_v1.json")
        self.completion_manifest = _load_json(
            self.manifest_root / "split_revision_completion.json"
        )
        self.split_manifest = _load_json(self.manifest_root / "edge_split_manifest.json")
        self.source_manifest = _load_json(self.manifest_root / "source_checksum_manifest.json")
        self.statistics_manifest = _load_json(self.manifest_root / "production_statistics.json")
        self.leakage_manifest = _load_json(self.manifest_root / "leakage_audit.json")
        self.training_manifests = {
            "Edge-IIoTset": _load_json(
                self.manifest_root / "training_asset_manifest_edge.json"
            ),
            "IoT-23": _load_json(
                self.manifest_root / "training_asset_manifest_iot23.json"
            ),
        }
        self.label_schema_ids = {
            "Edge-IIoTset": str(
                _load_json(self.manifest_root / "edge_label_schema.json")["id"]
            ),
            "IoT-23": str(_load_json(self.manifest_root / "iot23_label_schema.json")["id"]),
        }
        self._cache: dict[tuple[str, str, str, str], dict[str, Any] | None] = {}
        self._validate_manifests()

    @property
    def production_config_hash(self) -> str:
        return str(self.source_manifest["config_hash"])

    @property
    def production_version(self) -> str:
        return (
            f"{CANONICAL_SCHEMA_VERSION}/{PRODUCTION_ASSET_VERSION}/"
            f"{self.production_config_hash}"
        )

    def _validate_manifests(self) -> None:
        if self.canonical_manifest.get("schema_version") != CANONICAL_SCHEMA_VERSION:
            raise ProductionRuntimeAdapterError("unexpected CanonicalSessionRecord version")
        if self.split_manifest.get("policy") != PAPER_SPLIT_VERSION:
            raise ProductionRuntimeAdapterError("unexpected paper split version")
        required_gates = {
            "SPLIT_REVISION_STATUS": "PASS_WITH_LIMITATIONS",
            "U_FINAL_ISOLATION": "PASS",
            "LABEL_PROVENANCE_FINAL_GATE": "PASS",
        }
        for key, expected in required_gates.items():
            if self.completion_manifest.get(key) != expected:
                raise ProductionRuntimeAdapterError(f"required Production gate failed: {key}")
        app = self.statistics_manifest.get("asset_metadata", {}).get("application_evidence", {})
        if app.get("rows") != 0:
            raise ProductionRuntimeAdapterError(
                "application evidence exists without a frozen sanitizer contract"
            )
        if not (self.root / "application_evidence" / "_EMPTY.json").is_file():
            raise ProductionRuntimeAdapterError("application evidence empty marker is missing")
        leakage_items = {
            str(item.get("name")): item
            for item in self.leakage_manifest.get("items", [])
            if isinstance(item, dict)
        }
        if self.leakage_manifest.get("LEAKAGE_AUDIT_OK") is not True:
            raise ProductionRuntimeAdapterError("Production leakage Gate is not ready")
        for name in (
            "future context",
            "cross-split temporal context",
            "U_final development leakage",
        ):
            if leakage_items.get(name, {}).get("status") != "PASS":
                raise ProductionRuntimeAdapterError(f"required leakage check failed: {name}")

    @staticmethod
    def _pyarrow_dataset() -> Any:
        try:
            import pyarrow.dataset as ds
        except ImportError as exc:  # pragma: no cover - exercised in minimal installs
            raise ProductionRuntimeAdapterError(
                "Production Runtime adapter requires the optional data dependencies"
            ) from exc
        return ds

    def _partition(self, asset: str, dataset: str, split: str) -> Path:
        if asset not in _ASSET_SCHEMAS:
            raise ProductionRuntimeAdapterError("unsupported Production evidence asset")
        if dataset not in _DATASETS or any(token in split for token in ("/", "\\", "..")):
            raise ProductionRuntimeAdapterError("unsafe Production partition reference")
        return self.root / asset / f"dataset={dataset}" / f"split={split}"

    def _dataset(self, asset: str, dataset: str, split: str) -> Any | None:
        path = self._partition(asset, dataset, split)
        if not path.is_dir() or not any(path.glob("*.parquet")):
            return None
        ds = self._pyarrow_dataset()
        parquet = ds.dataset(path, format="parquet")
        columns = frozenset(parquet.schema.names)
        expected = _ASSET_SCHEMAS[asset]
        if columns != expected:
            raise ProductionRuntimeAdapterError(
                f"{asset} Parquet schema mismatch; unexpected={sorted(columns - expected)}; "
                f"missing={sorted(expected - columns)}"
            )
        return parquet

    def prefetch(
        self,
        *,
        dataset: str,
        split: str,
        sample_ids: Iterable[str],
        assets: Iterable[str] = tuple(_ASSET_SCHEMAS),
    ) -> None:
        ids = tuple(sorted(set(sample_ids)))
        if not ids:
            return
        if any(not _SAMPLE_ID.fullmatch(item) for item in ids):
            raise ProductionRuntimeAdapterError("invalid Production sample identity")
        ds = self._pyarrow_dataset()
        for asset in assets:
            parquet = self._dataset(asset, dataset, split)
            found: dict[str, dict[str, Any]] = {}
            if parquet is not None:
                table = parquet.to_table(filter=ds.field("sample_id").isin(ids))
                for row in table.to_pylist():
                    sample_id = str(row["sample_id"])
                    if sample_id in found:
                        raise ProductionRuntimeAdapterError(
                            f"duplicate {asset} row for one Production identity"
                        )
                    found[sample_id] = row
            for sample_id in ids:
                self._cache[(asset, dataset, split, sample_id)] = found.get(sample_id)

    def row(
        self,
        asset: str,
        *,
        dataset: str,
        split: str,
        sample_id: str,
        required: bool = False,
    ) -> dict[str, Any] | None:
        key = (asset, dataset, split, sample_id)
        if key not in self._cache:
            self.prefetch(
                dataset=dataset,
                split=split,
                sample_ids=(sample_id,),
                assets=(asset,),
            )
        row = self._cache[key]
        if row is None:
            if required:
                raise ProductionRuntimeAdapterError(f"required {asset} row is unavailable")
            return None
        if str(row.get("sample_id")) != sample_id or str(row.get("split")) != split:
            raise ProductionRuntimeAdapterError(f"{asset} identity/split mismatch")
        if row.get("schema_version") != CANONICAL_SCHEMA_VERSION:
            raise ProductionRuntimeAdapterError(f"{asset} schema version mismatch")
        return dict(row)


class ProductionSafeAdapter:
    """Allow-list-only Production → Runtime boundary with no label inference."""

    def __init__(self, store: ProductionParquetEvidenceStore):
        self.store = store

    def prefetch(self, requests: Iterable[ProductionSampleRequest]) -> None:
        grouped: dict[tuple[str, str], list[str]] = {}
        for item in requests:
            request = ProductionSampleRequest.model_validate(item.model_dump(mode="python"))
            grouped.setdefault((request.dataset, request.split), []).append(request.sample_id)
        for (dataset, split), sample_ids in grouped.items():
            self.store.prefetch(dataset=dataset, split=split, sample_ids=sample_ids)

    def adapt(self, request: ProductionSampleRequest) -> ProductionRuntimeSample:
        if not isinstance(request, ProductionSampleRequest):
            raise TypeError("ProductionSafeAdapter accepts only ProductionSampleRequest")
        request = ProductionSampleRequest.model_validate(request.model_dump(mode="python"))
        index = self.store.row(
            "sample_id_index",
            dataset=request.dataset,
            split=request.split,
            sample_id=request.sample_id,
            required=True,
        )
        assert index is not None
        authorization = self._authorize(index, request)
        initial_row = self.store.row(
            "initial_model_views",
            dataset=request.dataset,
            split=request.split,
            sample_id=request.sample_id,
            required=True,
        )
        assert initial_row is not None
        initial_view = self._validate_initial_view(initial_row, request)

        packet_row = self.store.row(
            "expandable_packet_store",
            dataset=request.dataset,
            split=request.split,
            sample_id=request.sample_id,
        )
        temporal_row = self.store.row(
            "temporal_index",
            dataset=request.dataset,
            split=request.split,
            sample_id=request.sample_id,
        )
        relation_row = self.store.row(
            "relation_index",
            dataset=request.dataset,
            split=request.split,
            sample_id=request.sample_id,
        )

        source_capabilities = frozenset(initial_view.pop("_source_capabilities"))
        if packet_row is not None:
            self._validate_packet_row(packet_row)
        if temporal_row is not None:
            self._safe_temporal_content(temporal_row)
        if relation_row is not None:
            self._safe_relation_content(relation_row)

        packet_available = packet_row is not None and "packet_expand_9_16" in source_capabilities
        temporal_available = temporal_row is not None and "temporal_context" in source_capabilities
        graph_available = relation_row is not None and "relation_context" in source_capabilities
        if (packet_row is None) != ("packet_expand_9_16" not in source_capabilities):
            raise ProductionRuntimeAdapterError(
                "packet expansion capability and materialized store disagree"
            )
        if "application_evidence" in source_capabilities:
            raise ProductionRuntimeAdapterError(
                "source declares application evidence but the frozen store is empty"
            )

        capabilities = (
            CapabilityStatus(
                capability=Capability.PACKET_EXPANSION,
                available=packet_available,
                reason=(
                    None
                    if packet_available
                    else "packets 9-16 are not materialized for this session"
                ),
            ),
            CapabilityStatus(
                capability=Capability.TEMPORAL_CONTEXT,
                available=temporal_available,
                reason=None if temporal_available else "past-only temporal evidence is unavailable",
            ),
            CapabilityStatus(
                capability=Capability.GRAPH_CONTEXT,
                available=graph_available,
                reason=None if graph_available else "local relation evidence is unavailable",
            ),
            CapabilityStatus(
                capability=Capability.APPLICATION_EVIDENCE,
                available=False,
                reason="materialized application evidence store is empty",
            ),
            CapabilityStatus(
                capability=Capability.KNOWLEDGE_RETRIEVAL,
                available=False,
                reason="no production Knowledge RAG tool is integrated",
            ),
        )
        content = canonical_json(
            {
                "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                "evidence_type": "initial_session_evidence",
                "packet_sequence": initial_view["packet_sequence"],
                "session_summary": initial_view["session_summary"],
                "missing_fields": initial_view["missing_fields"],
            }
        )
        evidence = EvidenceItem(
            evidence_id=_opaque_evidence_id(request.sample_id, "initial"),
            gap_type=GapType.OTHER,
            domain=GapDomain.OBSERVATIONAL,
            content=content,
            provenance="production_safe_adapter:initial_evidence",
            trust=EvidenceTrust.TRUSTED,
            model_safe=True,
            metadata={
                "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                "packet_start": 1,
                "packet_end": len(initial_view["packet_sequence"]),
                "whole_session_summary": True,
            },
        )
        runtime_input = RuntimeInput(
            sample_id=request.sample_id,
            initial_evidence=(evidence,),
            capabilities=capabilities,
            phase=request.phase,
            verified_feedback=None,
            memory_query="",
        )
        provenance = BackendProvenance(
            sample_id=request.sample_id,
            dataset=request.dataset,
            split=request.split,
            preset=request.preset,
            manifest_role=authorization["role"],
            ku_role=authorization["ku_role"],
            capture_ref_hash=str(index["capture_ref_hash"]),
            source_sha256=str(index["source_sha256"]),
            adapter_version=ADAPTER_VERSION,
            production_version=self.store.production_version,
            production_config_hash=self.store.production_config_hash,
            paper_split_version=PAPER_SPLIT_VERSION,
            evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
        )
        tools: tuple[ProductionEvidenceTool, ...] = (
            ProductionPacketExpansionTool(self, request),
            ProductionTemporalContextTool(self, request),
            ProductionGraphContextTool(self, request),
            ProductionApplicationEvidenceTool(self, request),
        )
        return ProductionRuntimeSample(
            runtime_input=runtime_input,
            backend_provenance=provenance,
            tools=tools,
        )

    def _authorize(
        self, index: dict[str, Any], request: ProductionSampleRequest
    ) -> dict[str, str]:
        if index["dataset"] != request.dataset or index["split"] != request.split:
            raise ProductionRuntimeAccessError("sample index does not match requested partition")
        manifest = self.store.training_manifests[request.dataset]
        expected_role = _EXPECTED_KU_ROLE[request.phase]
        allowed_roles = _ROLE_BY_PHASE[request.phase]
        for asset in manifest.get("assets", []):
            if not isinstance(asset, dict):
                continue
            if asset.get("role") not in allowed_roles or asset.get("ku_role") != expected_role:
                continue
            if asset.get("split") != request.split:
                continue
            if request.dataset == "Edge-IIoTset" and asset.get("preset") != request.preset:
                continue
            filters = asset.get("sample_ids", {}).get("filter", {})
            if filters.get("split") != request.split:
                continue
            fine_allowed = filters.get("fine_label_in")
            coarse_allowed = filters.get("coarse_label_in")
            if fine_allowed is not None and index["fine_label"] not in fine_allowed:
                continue
            if coarse_allowed is not None and index["coarse_label"] not in coarse_allowed:
                continue
            if fine_allowed is None and coarse_allowed is None:
                continue
            return {"role": str(asset["role"]), "ku_role": str(asset["ku_role"])}
        raise ProductionRuntimeAccessError(
            "sample is not authorized by the frozen training/evaluation manifest"
        )

    def _validate_initial_view(
        self, row: dict[str, Any], request: ProductionSampleRequest
    ) -> dict[str, Any]:
        if row["view_version"] != INITIAL_VIEW_VERSION:
            raise ProductionRuntimeAdapterError("initial model view version mismatch")
        view = _parse_object(row["view_json"], location="initial_model_view.view_json")
        _strict_keys(view, _INITIAL_SOURCE_KEYS, location="initial_model_view")
        if view["label_schema_id"] != self.store.label_schema_ids[request.dataset]:
            raise ProductionRuntimeAdapterError("label schema identity mismatch")
        packets_raw = view["packet_sequence"]
        if not isinstance(packets_raw, list) or not 1 <= len(packets_raw) <= 8:
            raise ProductionRuntimeAdapterError("initial packet sequence must contain 1-8 packets")
        packets = [
            _safe_packet(item, location=f"initial_packet[{index}]")
            for index, item in enumerate(packets_raw, start=1)
        ]
        capabilities = view["capabilities"]
        missing = view["missing_fields"]
        if (
            not isinstance(capabilities, list)
            or any(not isinstance(item, str) for item in capabilities)
            or len(capabilities) != len(set(capabilities))
            or not set(capabilities).issubset(_SOURCE_CAPABILITIES)
        ):
            raise ProductionRuntimeAdapterError("source capability declaration is invalid")
        if (
            not isinstance(missing, list)
            or any(not isinstance(item, str) for item in missing)
            or len(missing) != len(set(missing))
            or not set(missing).issubset(_SOURCE_MISSING_FIELDS)
        ):
            raise ProductionRuntimeAdapterError("source missing-fields declaration is invalid")
        return {
            "packet_sequence": packets,
            "session_summary": _safe_summary(view["session_summary"]),
            "missing_fields": sorted(missing),
            "_source_capabilities": sorted(capabilities),
        }

    def _validate_packet_row(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        packets = _parse_array(row["packets_9_16_json"], location="packets_9_16_json")
        if not 1 <= len(packets) <= 8:
            raise ProductionRuntimeAdapterError("expandable packet store must contain packets 9-16")
        key = row["rag_retrieval_key"]
        if not isinstance(key, str) or not _HEX_64.fullmatch(key):
            raise ProductionRuntimeAdapterError("backend RAG reference is invalid")
        return [
            _safe_packet(item, location=f"expanded_packet[{index}]")
            for index, item in enumerate(packets, start=9)
        ]

    def _safe_temporal_content(self, row: dict[str, Any]) -> dict[str, Any]:
        current = _finite_number(row["timestamp"], location="temporal.timestamp")
        latest_raw = row["context_latest_timestamp"]
        if latest_raw is not None:
            latest = _finite_number(latest_raw, location="temporal.context_latest_timestamp")
            if latest >= current:
                raise ProductionRuntimeAdapterError("temporal context is not strictly past-only")
        for field in (
            "source_identity_hash",
            "destination_identity_hash",
            "communication_pair_hash",
        ):
            if not isinstance(row[field], str) or not _HEX_64.fullmatch(row[field]):
                raise ProductionRuntimeAdapterError("invalid backend relation identity")
        stats = _parse_object(row["context_stats_json"], location="temporal.context_stats_json")
        _strict_keys(stats, _TEMPORAL_STATS_KEYS, location="temporal.context_stats")
        output: dict[str, Any] = {
            "window_seconds": _finite_number(
                stats["window_seconds"], location="temporal.window_seconds", minimum=0.0
            ),
            "prior_session_count": _nonnegative_int(
                stats["prior_session_count"], location="temporal.prior_session_count"
            ),
            "unique_destination_count": _nonnegative_int(
                stats["unique_destination_count"], location="temporal.unique_destination_count"
            ),
            "unique_destination_service_category_count": _nonnegative_int(
                stats["unique_destination_service_category_count"],
                location="temporal.unique_destination_service_category_count",
            ),
            "same_destination_distinct_source_count": _nonnegative_int(
                stats["same_destination_distinct_source_count"],
                location="temporal.same_destination_distinct_source_count",
            ),
            "repeated_pair_count": _nonnegative_int(
                stats["repeated_pair_count"], location="temporal.repeated_pair_count"
            ),
            "prior_packets": _nonnegative_int(
                stats["prior_packets"], location="temporal.prior_packets"
            ),
            "prior_bytes": _nonnegative_int(stats["prior_bytes"], location="temporal.prior_bytes"),
        }
        ratio = _finite_number(
            stats["incomplete_handshake_ratio"],
            location="temporal.incomplete_handshake_ratio",
            minimum=0.0,
        )
        if ratio > 1.0:
            raise ProductionRuntimeAdapterError("temporal incomplete-handshake ratio is invalid")
        output["incomplete_handshake_ratio"] = ratio
        gap = stats["inter_session_gap"]
        output["inter_session_gap"] = (
            None
            if gap is None
            else _finite_number(gap, location="temporal.inter_session_gap", minimum=0.0)
        )
        return output

    def _safe_relation_content(self, row: dict[str, Any]) -> dict[str, Any]:
        for field in (
            "source_identity_hash",
            "destination_identity_hash",
            "communication_pair_hash",
        ):
            if not isinstance(row[field], str) or not _HEX_64.fullmatch(row[field]):
                raise ProductionRuntimeAdapterError("invalid backend graph identity")
        previous = row["previous_pair_sample_ref"]
        if previous and (not isinstance(previous, str) or not _SAMPLE_ID.fullmatch(previous)):
            raise ProductionRuntimeAdapterError("invalid prior relation reference")
        roles = row["model_node_roles"]
        if roles != "CURRENT_SOURCE,TARGET_CLUSTER":
            raise ProductionRuntimeAdapterError("unexpected relation role projection")
        return {
            "node_roles": ["current_source", "target_cluster"],
            "repeated_relation": bool(previous),
        }


class ProductionEvidenceTool:
    action: AgentAction
    capability: Capability

    def __init__(self, adapter: ProductionSafeAdapter, sample: ProductionSampleRequest):
        self.adapter = adapter
        self.sample = sample

    def estimate(self, request: ToolRequest) -> CallMetrics:
        return CallMetrics()

    @staticmethod
    def _repeated(request: ToolRequest, current: tuple[EvidenceItem, ...]) -> bool:
        return any(
            item.metadata.get("request_signature") == request.signature for item in current
        )

    @staticmethod
    def _failure(request: ToolRequest, error: str) -> ToolResult:
        return ToolResult(
            status=ToolStatus.FAILURE,
            request_signature=request.signature,
            error=error,
        )


class ProductionPacketExpansionTool(ProductionEvidenceTool):
    action = AgentAction.EXPAND_PACKETS
    capability = Capability.PACKET_EXPANSION

    def execute(
        self, request: ToolRequest, current_evidence: tuple[EvidenceItem, ...]
    ) -> ToolResult:
        if request.action is not self.action:
            return self._failure(request, "action mismatch")
        if self._repeated(request, current_evidence):
            return self._failure(request, "repeated request signature")
        if set(request.parameters) != {"start_packet", "end_packet"}:
            return self._failure(request, "invalid packet range")
        start = request.parameters["start_packet"]
        end = request.parameters["end_packet"]
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or not 9 <= start <= end <= 16
        ):
            return self._failure(request, "packet range must be within 9-16")
        row = self.adapter.store.row(
            "expandable_packet_store",
            dataset=self.sample.dataset,
            split=self.sample.split,
            sample_id=self.sample.sample_id,
        )
        if row is None:
            return ToolResult(
                status=ToolStatus.UNAVAILABLE,
                request_signature=request.signature,
                error="packets 9-16 are unavailable",
            )
        try:
            packets = self.adapter._validate_packet_row(row)
        except ProductionRuntimeAdapterError:
            return self._failure(request, "packet evidence validation failed")
        available_end = 8 + len(packets)
        if start > available_end:
            return ToolResult(
                status=ToolStatus.UNAVAILABLE,
                request_signature=request.signature,
                error="requested packet range is not materialized",
            )
        actual_end = min(end, available_end)
        selected = packets[start - 9 : actual_end - 8]
        indexed = [
            {"packet_index": index, **packet}
            for index, packet in enumerate(selected, start=start)
        ]
        evidence = EvidenceItem(
            evidence_id=_opaque_evidence_id(
                self.sample.sample_id, "packet_expansion", request.signature
            ),
            gap_type=GapType.PACKET,
            domain=GapDomain.OBSERVATIONAL,
            content=canonical_json(
                {
                    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                    "evidence_type": "packet_expansion",
                    "packet_sequence": indexed,
                }
            ),
            provenance="production_safe_adapter:packet_expansion",
            metadata={
                "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                "packet_start": start,
                "packet_end": actual_end,
                "request_signature": request.signature,
            },
        )
        return ToolResult(
            status=ToolStatus.SUCCESS,
            request_signature=request.signature,
            evidence=(evidence,),
        )


class ProductionTemporalContextTool(ProductionEvidenceTool):
    action = AgentAction.EXPAND_TEMPORAL_CONTEXT
    capability = Capability.TEMPORAL_CONTEXT

    def execute(
        self, request: ToolRequest, current_evidence: tuple[EvidenceItem, ...]
    ) -> ToolResult:
        if request.action is not self.action:
            return self._failure(request, "action mismatch")
        if self._repeated(request, current_evidence):
            return self._failure(request, "repeated request signature")
        if set(request.parameters) != {"past_only", "window_seconds"}:
            return self._failure(request, "invalid temporal request")
        if request.parameters["past_only"] is not True:
            return self._failure(request, "temporal context must be past-only")
        row = self.adapter.store.row(
            "temporal_index",
            dataset=self.sample.dataset,
            split=self.sample.split,
            sample_id=self.sample.sample_id,
        )
        if row is None:
            return ToolResult(
                status=ToolStatus.UNAVAILABLE,
                request_signature=request.signature,
                error="past-only temporal context is unavailable",
            )
        try:
            content = self.adapter._safe_temporal_content(row)
            requested_window = _finite_number(
                request.parameters["window_seconds"], location="request.window_seconds"
            )
        except ProductionRuntimeAdapterError:
            return self._failure(request, "temporal evidence validation failed")
        if requested_window != content["window_seconds"]:
            return self._failure(request, "requested temporal window is not materialized")
        evidence = EvidenceItem(
            evidence_id=_opaque_evidence_id(
                self.sample.sample_id, "temporal_context", request.signature
            ),
            gap_type=GapType.TEMPORAL,
            domain=GapDomain.OBSERVATIONAL,
            content=canonical_json(
                {
                    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                    "evidence_type": "past_only_temporal_context",
                    "past_only": True,
                    "context_stats": content,
                }
            ),
            provenance="production_safe_adapter:past_only_temporal_context",
            metadata={
                "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                "past_only": True,
                "window_seconds": requested_window,
                "request_signature": request.signature,
            },
        )
        return ToolResult(
            status=ToolStatus.SUCCESS,
            request_signature=request.signature,
            evidence=(evidence,),
        )


class ProductionGraphContextTool(ProductionEvidenceTool):
    action = AgentAction.EXPAND_GRAPH_CONTEXT
    capability = Capability.GRAPH_CONTEXT

    def execute(
        self, request: ToolRequest, current_evidence: tuple[EvidenceItem, ...]
    ) -> ToolResult:
        if request.action is not self.action:
            return self._failure(request, "action mismatch")
        if self._repeated(request, current_evidence):
            return self._failure(request, "repeated request signature")
        if request.parameters != {"scope": "local"}:
            return self._failure(request, "only the materialized local relation scope is allowed")
        row = self.adapter.store.row(
            "relation_index",
            dataset=self.sample.dataset,
            split=self.sample.split,
            sample_id=self.sample.sample_id,
        )
        if row is None:
            return ToolResult(
                status=ToolStatus.UNAVAILABLE,
                request_signature=request.signature,
                error="local relation context is unavailable",
            )
        try:
            content = self.adapter._safe_relation_content(row)
        except ProductionRuntimeAdapterError:
            return self._failure(request, "relation evidence validation failed")
        evidence = EvidenceItem(
            evidence_id=_opaque_evidence_id(
                self.sample.sample_id, "graph_context", request.signature
            ),
            gap_type=GapType.GRAPH,
            domain=GapDomain.OBSERVATIONAL,
            content=canonical_json(
                {
                    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                    "evidence_type": "local_relation_context",
                    **content,
                }
            ),
            provenance="production_safe_adapter:local_relation_context",
            metadata={
                "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                "scope": "local",
                "request_signature": request.signature,
            },
        )
        return ToolResult(
            status=ToolStatus.SUCCESS,
            request_signature=request.signature,
            evidence=(evidence,),
        )


class ProductionApplicationEvidenceTool(ProductionEvidenceTool):
    action = AgentAction.REQUEST_APPLICATION_EVIDENCE
    capability = Capability.APPLICATION_EVIDENCE

    def execute(
        self, request: ToolRequest, current_evidence: tuple[EvidenceItem, ...]
    ) -> ToolResult:
        if request.action is not self.action:
            return self._failure(request, "action mismatch")
        if self._repeated(request, current_evidence):
            return self._failure(request, "repeated request signature")
        return ToolResult(
            status=ToolStatus.UNAVAILABLE,
            request_signature=request.signature,
            error="CAPABILITY_UNAVAILABLE",
        )
