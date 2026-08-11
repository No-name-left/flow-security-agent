from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from flowsec.production.storage import ParquetShardWriter, ProductionCatalog


SPLIT_POLICY_ID = "CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2"
SFT_POLICY_ID = "CLASS_BALANCED_DIVERSITY_AWARE_SFT_SELECTION_V1"
PAPER_READINESS_POLICY_ID = "PAPER_EVALUATION_READINESS_V1"
LOW_RESOURCE_STRESS_STATUS = "PLANNED_OPTIONAL_NOT_RUN"

PAPER_SUPPORT_THRESHOLDS = {
    "ZERO": (0, 0),
    "CRITICAL_LOW": (1, 29),
    "LOW": (30, 99),
    "ADEQUATE": (100, math.inf),
}

SFT_PLANS: dict[str, dict[str, int]] = {
    "PLAN_A": {"class_budget": 512, "max_per_exact_group": 4},
    "PLAN_B": {"class_budget": 2048, "max_per_exact_group": 16},
    "PLAN_C": {"class_budget": 8192, "max_per_exact_group": 64},
}

PHASE_A_POLICY_ORDER = (
    "CURRENT_WALL_CLOCK_SPAN_CHRONOLOGICAL",
    "NAIVE_SESSION_START_QUANTILE",
    "PER_CAPTURE_SESSION_CROSSING_ONLY",
    "PER_CAPTURE_LOCAL_EMBARGO_5S",
    SPLIT_POLICY_ID,
)

_FORMAL_SPLITS = ("train", "validation", "test")
_SPLIT_BITS = {"train": 1, "validation": 2, "test": 4}


@dataclass(frozen=True, slots=True)
class Boundary:
    capture_id: str
    fine_label: str
    first_timestamp: float
    second_timestamp: float
    first_anchor_fraction: float
    second_anchor_fraction: float
    local_embargo_seconds: float
    source_session_count: int
    search_applied: bool


def paper_support_status(count: int) -> str:
    if count == 0:
        return "ZERO"
    if count < 30:
        return "CRITICAL_LOW"
    if count < 100:
        return "LOW"
    return "ADEQUATE"


def assign_constrained_split(
    *,
    timestamp_start: float,
    timestamp_end: float,
    first_boundary: float,
    second_boundary: float,
    local_embargo_seconds: float,
) -> tuple[str, str]:
    """Assign one complete session to one chronological split.

    A session that touches a boundary-local embargo or crosses a boundary is
    quarantined. No session is shortened, divided, or moved between captures.
    """

    half_gap = float(local_embargo_seconds) / 2.0
    if timestamp_end <= first_boundary - half_gap:
        return "train", ""
    if (
        timestamp_start >= first_boundary + half_gap
        and timestamp_end <= second_boundary - half_gap
    ):
        return "validation", ""
    if timestamp_start >= second_boundary + half_gap:
        return "test", ""
    return "quarantine", "split_boundary_or_gap"


def _tier(count: int) -> int:
    return 3 if count >= 100 else 2 if count >= 30 else 1 if count else 0


def _candidate_anchor_grid() -> Iterator[tuple[float, float]]:
    for first_percent in range(50, 81):
        second_minimum = max(first_percent + 8, 75)
        for second_percent in range(second_minimum, 96):
            yield first_percent / 100.0, second_percent / 100.0


def _split_counts(
    rows: list[tuple[float, float, str, str]],
    *,
    first: float,
    second: float,
    embargo: float,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for start, end, _, _ in rows:
        split, _ = assign_constrained_split(
            timestamp_start=start,
            timestamp_end=end,
            first_boundary=first,
            second_boundary=second,
            local_embargo_seconds=embargo,
        )
        counts[split] += 1
    return counts


def choose_constrained_boundary(
    *,
    capture_id: str,
    fine_label: str,
    rows: list[tuple[float, float, str, str]],
    local_embargo_seconds: float = 5.0,
) -> Boundary:
    """Search a small capture using the pre-model lexicographic objective."""

    if not rows:
        raise ValueError(f"capture has no sessions: {capture_id}")
    ordered = sorted(rows, key=lambda row: (row[0], row[1], row[2], row[3]))
    starts = [row[0] for row in ordered]
    exact_total = len({row[2] for row in ordered})
    near_total = len({row[3] for row in ordered})
    ranked: list[tuple[tuple[Any, ...], float, float, float, float]] = []
    for first_fraction, second_fraction in _candidate_anchor_grid():
        first = starts[min(len(starts) - 1, int(len(starts) * first_fraction))]
        second = starts[min(len(starts) - 1, int(len(starts) * second_fraction))]
        counts = _split_counts(
            ordered,
            first=first,
            second=second,
            embargo=local_embargo_seconds,
        )
        ratio_deviation = (
            abs(counts["train"] / len(ordered) - 0.70)
            + abs(counts["validation"] / len(ordered) - 0.15)
            + abs(counts["test"] / len(ordered) - 0.15)
        )
        # Identity safety is invariant for every candidate. The remaining
        # tuple follows the preregistered priority: evaluation support, legal
        # train support, then ratios and quarantine.
        score = (
            min(_tier(counts["validation"]), _tier(counts["test"])),
            _tier(counts["validation"]) + _tier(counts["test"]),
            int(counts["train"] >= 100),
            -ratio_deviation,
            -counts["quarantine"],
        )
        ranked.append((score, first, second, first_fraction, second_fraction))
    ranked.sort(reverse=True)

    best: tuple[tuple[Any, ...], float, float, float, float] | None = None
    for raw_score, first, second, first_fraction, second_fraction in ranked[:80]:
        train_exact: set[str] = set()
        train_near: set[str] = set()
        for start, end, exact, near in ordered:
            split, _ = assign_constrained_split(
                timestamp_start=start,
                timestamp_end=end,
                first_boundary=first,
                second_boundary=second,
                local_embargo_seconds=local_embargo_seconds,
            )
            if split == "train":
                train_exact.add(exact)
                train_near.add(near)
        structural_exact = exact_total < 30
        structural_near = near_total < 30
        score = (
            raw_score[:3],
            int(len(train_exact) >= 30 or structural_exact)
            + int(len(train_near) >= 30 or structural_near),
            min(len(train_exact), 30) + min(len(train_near), 30),
            raw_score[3],
            raw_score[4],
        )
        candidate = (score, first, second, first_fraction, second_fraction)
        if best is None or candidate[0] > best[0]:
            best = candidate
    assert best is not None
    return Boundary(
        capture_id=capture_id,
        fine_label=fine_label,
        first_timestamp=best[1],
        second_timestamp=best[2],
        first_anchor_fraction=best[3],
        second_anchor_fraction=best[4],
        local_embargo_seconds=local_embargo_seconds,
        source_session_count=len(ordered),
        search_applied=True,
    )


def _rank_anchors(
    catalog: ProductionCatalog,
    *,
    dataset: str,
    capture_id: str,
    session_count: int,
) -> tuple[float, float]:
    targets = {
        min(session_count - 1, int(session_count * 0.70)): 0,
        min(session_count - 1, int(session_count * 0.85)): 1,
    }
    values: list[float | None] = [None, None]
    cursor = catalog.connection.execute(
        """
        SELECT timestamp_start
        FROM main.records
        WHERE dataset=? AND capture_id=?
        ORDER BY timestamp_start,sample_id
        """,
        (dataset, capture_id),
    )
    for index, (timestamp,) in enumerate(cursor):
        target = targets.get(index)
        if target is not None:
            values[target] = float(timestamp)
        if values[1] is not None:
            break
    if values[0] is None or values[1] is None:
        raise ValueError(f"could not determine rank anchors: {capture_id}")
    return values[0], values[1]


def build_revision_boundaries(
    catalog: ProductionCatalog,
    *,
    dataset: str,
    local_embargo_seconds: float = 5.0,
    search_max_sessions: int = 20_000,
) -> dict[str, Boundary]:
    boundaries: dict[str, Boundary] = {}
    captures = catalog.connection.execute(
        """
        SELECT capture_id,fine_label,COUNT(*)
        FROM main.records
        WHERE dataset=?
        GROUP BY capture_id,fine_label
        ORDER BY capture_id
        """,
        (dataset,),
    )
    for capture_id, fine_label, count_value in captures:
        count = int(count_value)
        if count <= search_max_sessions:
            rows = [
                (float(start), float(end), str(exact), str(near))
                for start, end, exact, near in catalog.connection.execute(
                    """
                    SELECT timestamp_start,timestamp_end,evidence_signature,near_signature
                    FROM main.records
                    WHERE dataset=? AND capture_id=?
                    ORDER BY timestamp_start,sample_id
                    """,
                    (dataset, capture_id),
                )
            ]
            boundary = choose_constrained_boundary(
                capture_id=str(capture_id),
                fine_label=str(fine_label),
                rows=rows,
                local_embargo_seconds=local_embargo_seconds,
            )
        else:
            first, second = _rank_anchors(
                catalog,
                dataset=dataset,
                capture_id=str(capture_id),
                session_count=count,
            )
            boundary = Boundary(
                capture_id=str(capture_id),
                fine_label=str(fine_label),
                first_timestamp=first,
                second_timestamp=second,
                first_anchor_fraction=0.70,
                second_anchor_fraction=0.85,
                local_embargo_seconds=local_embargo_seconds,
                source_session_count=count,
                search_applied=False,
            )
        boundaries[boundary.capture_id] = boundary
    return boundaries


def build_rank_quantile_boundaries(
    catalog: ProductionCatalog,
    *,
    dataset: str,
    local_embargo_seconds: float,
) -> dict[str, Boundary]:
    """Build fixed per-capture 70/15/15 rank boundaries for Phase A audits."""

    boundaries: dict[str, Boundary] = {}
    captures = catalog.connection.execute(
        """
        SELECT capture_id,fine_label,COUNT(*)
        FROM main.records
        WHERE dataset=?
        GROUP BY capture_id,fine_label
        ORDER BY capture_id
        """,
        (dataset,),
    )
    for capture_id, fine_label, count_value in captures:
        count = int(count_value)
        first, second = _rank_anchors(
            catalog,
            dataset=dataset,
            capture_id=str(capture_id),
            session_count=count,
        )
        boundary = Boundary(
            capture_id=str(capture_id),
            fine_label=str(fine_label),
            first_timestamp=first,
            second_timestamp=second,
            first_anchor_fraction=0.70,
            second_anchor_fraction=0.85,
            local_embargo_seconds=float(local_embargo_seconds),
            source_session_count=count,
            search_applied=False,
        )
        boundaries[boundary.capture_id] = boundary
    return boundaries


def _naive_quantile_split(timestamp_start: float, boundary: Boundary) -> str:
    if timestamp_start < boundary.first_timestamp:
        return "train"
    if timestamp_start < boundary.second_timestamp:
        return "validation"
    return "test"


def _mask_has_multiple_splits(mask: int) -> bool:
    return bool(mask and mask & (mask - 1))


def audit_phase_a_split_candidates(
    *,
    catalog: ProductionCatalog,
    dataset: str,
    selected_boundaries: dict[str, Boundary],
    local_embargo_seconds: float = 5.0,
) -> dict[str, Any]:
    """Compare split policies in one read-only streaming pass over the catalog.

    The source table is never mutated. Model-view collision counts remain an
    audit/sensitivity statistic and are not treated as backend identity.
    """

    fixed_boundaries = build_rank_quantile_boundaries(
        catalog,
        dataset=dataset,
        local_embargo_seconds=local_embargo_seconds,
    )
    if set(fixed_boundaries) != set(selected_boundaries):
        raise ValueError("selected boundary capture set does not match source catalog")

    policies = list(PHASE_A_POLICY_ORDER)
    policy_count = len(policies)
    counts: dict[str, dict[str, Counter[str]]] = {
        policy: defaultdict(Counter) for policy in policies
    }
    exact_masks: dict[str, list[int]] = {}
    near_masks: dict[str, list[int]] = {}
    class_exact_masks: dict[tuple[str, str], list[int]] = {}
    class_near_masks: dict[tuple[str, str], list[int]] = {}
    source_rows = 0

    def record_mask(
        mapping: dict[Any, list[int]], key: Any, policy_index: int, split: str
    ) -> None:
        bit = _SPLIT_BITS.get(split)
        if bit is None:
            return
        masks = mapping.get(key)
        if masks is None:
            masks = [0] * policy_count
            mapping[key] = masks
        masks[policy_index] |= bit

    cursor = catalog.connection.execute(
        """
        SELECT capture_id,fine_label,timestamp_start,timestamp_end,
               base_split,retained,evidence_signature,near_signature
        FROM main.records
        WHERE dataset=?
        ORDER BY record_id
        """,
        (dataset,),
    )
    for capture_id, fine_label, start, end, current_split, retained, exact, near in cursor:
        source_rows += 1
        capture = str(capture_id)
        label = str(fine_label)
        timestamp_start = float(start)
        timestamp_end = float(end)
        fixed = fixed_boundaries[capture]
        selected = selected_boundaries[capture]
        crossing_split, _ = assign_constrained_split(
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            first_boundary=fixed.first_timestamp,
            second_boundary=fixed.second_timestamp,
            local_embargo_seconds=0.0,
        )
        fixed_gap_split, _ = assign_constrained_split(
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            first_boundary=fixed.first_timestamp,
            second_boundary=fixed.second_timestamp,
            local_embargo_seconds=local_embargo_seconds,
        )
        selected_split, _ = assign_constrained_split(
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            first_boundary=selected.first_timestamp,
            second_boundary=selected.second_timestamp,
            local_embargo_seconds=selected.local_embargo_seconds,
        )
        assignments = (
            str(current_split)
            if bool(retained) and str(current_split) in _FORMAL_SPLITS
            else "quarantine",
            _naive_quantile_split(timestamp_start, fixed),
            crossing_split,
            fixed_gap_split,
            selected_split,
        )
        exact_value = str(exact)
        near_value = str(near)
        for policy_index, (policy, split) in enumerate(zip(policies, assignments)):
            counts[policy][label][split] += 1
            record_mask(exact_masks, exact_value, policy_index, split)
            record_mask(near_masks, near_value, policy_index, split)
            record_mask(class_exact_masks, (label, exact_value), policy_index, split)
            record_mask(class_near_masks, (label, near_value), policy_index, split)

    diversity: dict[str, dict[str, dict[str, Counter[str]]]] = {
        policy: {
            label: {split: Counter() for split in _FORMAL_SPLITS}
            for label in sorted(counts[policy])
        }
        for policy in policies
    }
    for kind, mapping in (
        ("exact_groups", class_exact_masks),
        ("near_groups", class_near_masks),
    ):
        for (label, _), masks in mapping.items():
            for policy_index, mask in enumerate(masks):
                for split, bit in _SPLIT_BITS.items():
                    if mask & bit:
                        diversity[policies[policy_index]][label][split][kind] += 1

    candidates: dict[str, Any] = {}
    for policy_index, policy in enumerate(policies):
        rows: list[dict[str, Any]] = []
        aggregate = Counter()
        zero = 0
        critical = 0
        for label in sorted(counts[policy]):
            split_values: dict[str, Any] = {}
            for split in _FORMAL_SPLITS:
                split_count = int(counts[policy][label][split])
                aggregate[split] += split_count
                split_values[split] = {
                    "count": split_count,
                    "exact_groups": int(
                        diversity[policy][label][split]["exact_groups"]
                    ),
                    "near_groups": int(
                        diversity[policy][label][split]["near_groups"]
                    ),
                }
                if split != "train":
                    split_values[split]["paper_status"] = paper_support_status(
                        split_count
                    )
            evaluation_statuses = {
                split_values[split]["paper_status"]
                for split in ("validation", "test")
            }
            if "ZERO" in evaluation_statuses:
                zero += 1
            elif "CRITICAL_LOW" in evaluation_statuses:
                critical += 1
            rows.append({"class": label, "splits": split_values})
        aggregate["quarantine"] = sum(
            int(item["quarantine"]) for item in counts[policy].values()
        )
        formal_total = sum(aggregate[split] for split in _FORMAL_SPLITS)
        candidates[policy] = {
            "counts": dict(aggregate),
            "formal_ratios": {
                split: aggregate[split] / formal_total if formal_total else 0.0
                for split in _FORMAL_SPLITS
            },
            "zero_class_count": zero,
            "critical_low_class_count": critical,
            "identity_cross_split_leakage": 0,
            "exact_model_view_cross_split_collision_groups": sum(
                _mask_has_multiple_splits(masks[policy_index])
                for masks in exact_masks.values()
            ),
            "near_signature_cross_split_collision_groups": sum(
                _mask_has_multiple_splits(masks[policy_index])
                for masks in near_masks.values()
            ),
            "classes": rows,
        }

    return {
        "audit_mode": "READ_ONLY_SINGLE_PASS_NO_ASSET_REBUILD",
        "dataset": dataset,
        "source_rows": source_rows,
        "candidate_order": policies,
        "candidate_definitions": {
            "CURRENT_WALL_CLOCK_SPAN_CHRONOLOGICAL": (
                "existing Production base_split/retained assignment"
            ),
            "NAIVE_SESSION_START_QUANTILE": (
                "per-capture 70/15/15 session-start rank; no crossing protection"
            ),
            "PER_CAPTURE_SESSION_CROSSING_ONLY": (
                "per-capture 70/15/15 rank boundaries; complete crossing sessions quarantined"
            ),
            "PER_CAPTURE_LOCAL_EMBARGO_5S": (
                "fixed per-capture 70/15/15 rank boundaries; crossing plus 5-second embargo"
            ),
            SPLIT_POLICY_ID: (
                "small-capture deterministic readiness search; large-capture 70/15/15 rank; "
                "crossing plus 5-second embargo"
            ),
        },
        "candidates": candidates,
        "selection": {
            "policy": SPLIT_POLICY_ID,
            "lexicographic_priority": [
                "identity leakage equals zero",
                "eliminate ZERO and CRITICAL_LOW evaluation support where possible",
                "retain legal train evidence diversity",
                "approach 70/15/15",
                "minimize quarantine",
                "report exact/near collision without identity conflation",
            ],
        },
    }


def _shadow_records_view(catalog: ProductionCatalog, dataset: str) -> None:
    catalog.connection.execute("DROP VIEW IF EXISTS temp.records")
    columns = [
        str(row[1])
        for row in catalog.connection.execute("PRAGMA main.table_info(records)")
    ]
    projected: list[str] = []
    for column in columns:
        if column == "base_split":
            projected.append("COALESCE(revision.base_split,source.base_split) AS base_split")
        elif column == "retained":
            projected.append("COALESCE(revision.retained,source.retained) AS retained")
        elif column == "exclusion_reason":
            projected.append(
                "COALESCE(revision.exclusion_reason,source.exclusion_reason) AS exclusion_reason"
            )
        else:
            projected.append(f"source.{column} AS {column}")
    catalog.connection.execute(
        f"""
        CREATE TEMP VIEW records AS
        SELECT {','.join(projected)}
        FROM main.records AS source
        LEFT JOIN edge_split_revision AS revision
          ON revision.record_id=source.record_id
         AND source.dataset={json.dumps(dataset)}
        """
    )


def install_revision_overlay(
    catalog: ProductionCatalog,
    *,
    dataset: str,
    boundaries: dict[str, Boundary],
    assignment_root: Path | None,
    compression: str = "zstd",
    max_rows: int = 100_000,
) -> dict[str, Any]:
    """Install a temporary split overlay and optionally persist assignments."""

    catalog.connection.execute("DROP VIEW IF EXISTS temp.records")
    catalog.connection.execute("DROP TABLE IF EXISTS temp.edge_split_revision")
    catalog.connection.execute(
        """
        CREATE TEMP TABLE edge_split_revision (
            record_id INTEGER PRIMARY KEY,
            sample_id TEXT NOT NULL UNIQUE,
            base_split TEXT NOT NULL,
            retained INTEGER NOT NULL,
            exclusion_reason TEXT NOT NULL
        )
        """
    )
    writer = (
        ParquetShardWriter(assignment_root, compression, max_rows)
        if assignment_root is not None
        else None
    )
    counts: Counter[str] = Counter()
    by_capture: dict[str, Counter[str]] = defaultdict(Counter)
    batch: list[tuple[int, str, str, int, str]] = []
    cursor = catalog.connection.execute(
        """
        SELECT record_id,sample_id,capture_id,timestamp_start,timestamp_end
        FROM main.records
        WHERE dataset=?
        ORDER BY record_id
        """,
        (dataset,),
    )
    for record_id, sample_id, capture_id, start, end in cursor:
        boundary = boundaries[str(capture_id)]
        split, reason = assign_constrained_split(
            timestamp_start=float(start),
            timestamp_end=float(end),
            first_boundary=boundary.first_timestamp,
            second_boundary=boundary.second_timestamp,
            local_embargo_seconds=boundary.local_embargo_seconds,
        )
        retained = int(split != "quarantine")
        row = (int(record_id), str(sample_id), split, retained, reason)
        batch.append(row)
        if len(batch) >= 10_000:
            catalog.connection.executemany(
                "INSERT INTO edge_split_revision VALUES (?,?,?,?,?)", batch
            )
            batch.clear()
        counts[split] += 1
        by_capture[str(capture_id)][split] += 1
        if writer is not None:
            writer.write(
                {
                    "sample_id": str(sample_id),
                    "dataset": dataset,
                    "capture_id": str(capture_id),
                    "split": split,
                    "retained": bool(retained),
                    "exclusion_reason": reason,
                    "split_policy": SPLIT_POLICY_ID,
                }
            )
    if batch:
        catalog.connection.executemany(
            "INSERT INTO edge_split_revision VALUES (?,?,?,?,?)", batch
        )
    _shadow_records_view(catalog, dataset)
    metadata = writer.close() if writer is not None else None
    return {
        "policy": SPLIT_POLICY_ID,
        "counts": dict(counts),
        "captures": {
            capture_id: {
                "boundary": asdict(boundaries[capture_id]),
                "split_counts": dict(split_counts),
            }
            for capture_id, split_counts in sorted(by_capture.items())
        },
        "assignment_asset": metadata,
    }


def build_paper_readiness(
    *,
    catalog: ProductionCatalog,
    dataset: str,
    edge_presets: dict[str, Any],
) -> dict[str, Any]:
    rows = catalog.query(
        """
        SELECT fine_label,coarse_label,base_split,COUNT(*),
               COUNT(DISTINCT evidence_signature),COUNT(DISTINCT near_signature)
        FROM records
        WHERE dataset=? AND retained=1
          AND base_split IN ('train','validation','test')
        GROUP BY fine_label,coarse_label,base_split
        ORDER BY fine_label,base_split
        """,
        (dataset,),
    )
    matrix: dict[str, dict[str, Any]] = {}
    for label, coarse, split, count, exact, near in rows:
        item = matrix.setdefault(
            str(label),
            {
                "class": str(label),
                "coarse_parent": str(coarse),
                "splits": {
                    key: {"count": 0, "exact_groups": 0, "near_groups": 0}
                    for key in ("train", "validation", "test")
                },
            },
        )
        item["splits"][str(split)] = {
            "count": int(count),
            "exact_groups": int(exact),
            "near_groups": int(near),
        }
    for item in matrix.values():
        for split in ("validation", "test"):
            item["splits"][split]["paper_status"] = paper_support_status(
                int(item["splits"][split]["count"])
            )
        train = item["splits"]["train"]
        train["reference_exact_ready"] = int(train["exact_groups"]) >= 30
        train["reference_near_ready"] = int(train["near_groups"]) >= 30
        item["training_diversity_status"] = (
            "ADEQUATE"
            if train["reference_exact_ready"] and train["reference_near_ready"]
            else "TRAIN_INSUFFICIENT"
        )

    preset_results: dict[str, Any] = {}
    for preset_name, preset in sorted(edge_presets.items()):
        known = list(preset["K_known"])
        statuses = Counter()
        insufficient: list[str] = []
        for label in known:
            item = matrix[label]
            worst = min(
                (item["splits"][split]["paper_status"] for split in ("validation", "test")),
                key=lambda value: ("ZERO", "CRITICAL_LOW", "LOW", "ADEQUATE").index(value),
            )
            statuses[worst] += 1
            if item["training_diversity_status"] != "ADEQUATE":
                insufficient.append(label)
        preset_results[preset_name] = {
            "K_known_count": len(known),
            "imbalance_counts": {
                key: statuses[key]
                for key in ("ZERO", "CRITICAL_LOW", "LOW", "ADEQUATE")
            },
            "training_insufficient": sorted(insufficient),
        }
    zero = sum(
        any(item["splits"][split]["paper_status"] == "ZERO" for split in ("validation", "test"))
        for item in matrix.values()
    )
    critical = sum(
        not any(item["splits"][split]["paper_status"] == "ZERO" for split in ("validation", "test"))
        and any(item["splits"][split]["paper_status"] == "CRITICAL_LOW" for split in ("validation", "test"))
        for item in matrix.values()
    )
    return {
        "policy": PAPER_READINESS_POLICY_ID,
        "thresholds": {
            "ZERO": "0",
            "CRITICAL_LOW": "1-29",
            "LOW": "30-99",
            "ADEQUATE": ">=100",
            "train_exact_reference": 30,
            "train_near_reference": 30,
        },
        "PAPER_EVALUATION_READINESS_GATE": (
            "PASS_WITH_LIMITATIONS" if zero == 0 and critical == 0 else "FAIL"
        ),
        "zero_class_count": zero,
        "critical_low_class_count": critical,
        "classes": [matrix[label] for label in sorted(matrix)],
        "presets": preset_results,
    }


def _stable_rank(sample_id: str, seed: int) -> bytes:
    return hashlib.sha256(f"{seed}|{sample_id}".encode("utf-8")).digest()


def _training_candidate_index(
    catalog: ProductionCatalog,
    *,
    dataset: str,
    seed: int,
    maximum_per_exact: int,
) -> tuple[
    Counter[str],
    dict[str, dict[str, list[tuple[int, str, str]]]],
    dict[str, dict[str, tuple[bytes, str, str]]],
]:
    raw: Counter[str] = Counter()
    exact_heaps: dict[str, dict[str, list[tuple[int, str, str]]]] = defaultdict(dict)
    near_best: dict[str, dict[str, tuple[bytes, str, str]]] = defaultdict(dict)
    cursor = catalog.connection.execute(
        """
        SELECT fine_label,sample_id,evidence_signature,near_signature
        FROM records
        WHERE dataset=? AND retained=1 AND base_split='train'
        """,
        (dataset,),
    )
    for fine_label, sample_id, exact, near in cursor:
        label = str(fine_label)
        sample = str(sample_id)
        exact_value = str(exact)
        near_value = str(near)
        raw[label] += 1
        rank = _stable_rank(sample, seed)
        previous = near_best[label].get(near_value)
        if previous is None or rank < previous[0]:
            near_best[label][near_value] = (rank, sample, exact_value)
        heap = exact_heaps[label].setdefault(exact_value, [])
        integer_rank = int.from_bytes(rank, "big")
        candidate = (-integer_rank, sample, near_value)
        if len(heap) < maximum_per_exact:
            heapq.heappush(heap, candidate)
        elif integer_rank < -heap[0][0]:
            heapq.heapreplace(heap, candidate)
    return raw, exact_heaps, near_best


def _select_class_candidates(
    *,
    exact_heaps: dict[str, list[tuple[int, str, str]]],
    near_best: dict[str, tuple[bytes, str, str]],
    budget: int,
    maximum_per_exact: int,
) -> dict[str, tuple[str, str, str]]:
    exact_items = {
        exact: sorted((sample, near) for _, sample, near in heap)[
            :maximum_per_exact
        ]
        for exact, heap in exact_heaps.items()
    }
    selected: dict[str, tuple[str, str, str]] = {}
    for near, (_, sample, exact) in sorted(near_best.items()):
        selected.setdefault(sample, (exact, near, "NEAR_GROUP_FIRST"))
        if len(selected) >= budget:
            return selected
    for exact, items in sorted(exact_items.items()):
        for sample, near in items:
            if sample not in selected:
                selected[sample] = (exact, near, "EXACT_GROUP_SECOND")
                break
        if len(selected) >= budget:
            return selected
    for depth in range(1, maximum_per_exact):
        for exact, items in sorted(exact_items.items()):
            if depth >= len(items):
                continue
            sample, near = items[depth]
            selected.setdefault(sample, (exact, near, "BOUNDED_MULTIPLICITY"))
            if len(selected) >= budget:
                return selected
    return selected


def build_sft_candidate_manifests(
    *,
    catalog: ProductionCatalog,
    dataset: str,
    edge_presets: dict[str, Any],
    output_root: Path | None,
    seed: int = 20260811,
    selected_plan: str = "PLAN_B",
    compression: str = "zstd",
    max_rows: int = 100_000,
) -> dict[str, Any]:
    if selected_plan not in SFT_PLANS:
        raise ValueError(selected_plan)
    maximum = max(value["max_per_exact_group"] for value in SFT_PLANS.values())
    raw, exact_heaps, near_best = _training_candidate_index(
        catalog,
        dataset=dataset,
        seed=seed,
        maximum_per_exact=maximum,
    )
    selected_by_plan: dict[str, dict[str, dict[str, tuple[str, str, str]]]] = {}
    for plan_name, plan in SFT_PLANS.items():
        selected_by_plan[plan_name] = {
            label: _select_class_candidates(
                exact_heaps=exact_heaps[label],
                near_best=near_best[label],
                budget=plan["class_budget"],
                maximum_per_exact=plan["max_per_exact_group"],
            )
            for label in sorted(raw)
        }

    writers: dict[str, ParquetShardWriter] = {}
    if output_root is not None:
        for preset_name in edge_presets:
            writers[preset_name] = ParquetShardWriter(
                output_root / f"preset={preset_name}", compression, max_rows
            )
    plans: dict[str, Any] = {}
    for preset_name, preset in sorted(edge_presets.items()):
        known = sorted(preset["K_known"])
        plans[preset_name] = {}
        for plan_name, plan in SFT_PLANS.items():
            class_rows: list[dict[str, Any]] = []
            unique_ids: set[str] = set()
            for label in known:
                chosen = selected_by_plan[plan_name][label]
                exact_selected = {item[0] for item in chosen.values()}
                near_selected = {item[1] for item in chosen.values()}
                overlap = unique_ids & set(chosen)
                if overlap:
                    raise ValueError(f"duplicate SFT sample IDs: {preset_name}/{label}")
                unique_ids.update(chosen)
                class_rows.append(
                    {
                        "class": label,
                        "raw_train_sessions": raw[label],
                        "selected_sessions": len(chosen),
                        "selection_fraction": len(chosen) / raw[label] if raw[label] else 0.0,
                        "exact_groups": len(exact_selected),
                        "exact_groups_available": len(exact_heaps[label]),
                        "exact_coverage": (
                            len(exact_selected) / len(exact_heaps[label])
                            if exact_heaps[label]
                            else 0.0
                        ),
                        "near_groups": len(near_selected),
                        "near_groups_available": len(near_best[label]),
                        "near_coverage": (
                            len(near_selected) / len(near_best[label])
                            if near_best[label]
                            else 0.0
                        ),
                        "compression_ratio": raw[label] / len(chosen) if chosen else None,
                    }
                )
                if output_root is not None and plan_name == selected_plan:
                    for sample_id, (exact, near, stage) in sorted(chosen.items()):
                        writers[preset_name].write(
                            {
                                "sample_id": sample_id,
                                "dataset": dataset,
                                "preset": preset_name,
                                "fine_label": label,
                                "physical_split": "train",
                                "ku_role": "K_known",
                                "policy": SFT_POLICY_ID,
                                "plan": selected_plan,
                                "selection_stage": stage,
                                "evidence_signature": exact,
                                "near_signature": near,
                            }
                        )
            total = sum(item["selected_sessions"] for item in class_rows)
            for item in class_rows:
                item["class_share"] = item["selected_sessions"] / total if total else 0.0
            nonzero = [item["selected_sessions"] for item in class_rows if item["selected_sessions"]]
            raw_total = sum(raw[label] for label in known)
            plans[preset_name][plan_name] = {
                "parameters": dict(plan),
                "classes": class_rows,
                "total_sessions": total,
                "evidence_card_count": total,
                "unique_sample_ids": len(unique_ids),
                "duplicate_sample_ids": total - len(unique_ids),
                "estimated_tokens_at_768_per_card": total * 768,
                "estimated_tokens_range_512_1024": [total * 512, total * 1024],
                "relative_compute_vs_raw_train": total / raw_total if raw_total else 0.0,
                "largest_smallest_class_ratio": max(nonzero) / min(nonzero),
            }
    assets = {
        name: writer.close() for name, writer in sorted(writers.items())
    }
    return {
        "policy": SFT_POLICY_ID,
        "selection_order": [
            "cover distinct near groups",
            "cover distinct exact evidence groups",
            "bounded deterministic multiplicity within exact groups",
            "stop at class-level plan budget",
        ],
        "eligibility": "K_known intersection physical train only",
        "forbidden": ["validation", "test", "U_dev", "U_final"],
        "seed": seed,
        "selected_plan": selected_plan,
        "token_estimate_status": "ESTIMATE_ONLY_RENDERER_AND_TOKENIZER_NOT_FROZEN",
        "plans": plans,
        "selected_candidate_assets": assets,
    }


def build_low_resource_analysis(
    *,
    paper_readiness: dict[str, Any],
    coarse_mapping: dict[str, str],
    total_counts: dict[str, int],
) -> dict[str, Any]:
    low_known: set[str] = set()
    structural: set[str] = set()
    candidate_pool: list[dict[str, Any]] = []
    all_labels = set(coarse_mapping)
    for item in paper_readiness["classes"]:
        label = str(item["class"])
        train = item["splits"]["train"]
        eval_low = any(
            item["splits"][split]["paper_status"] in {"ZERO", "CRITICAL_LOW", "LOW"}
            for split in ("validation", "test")
        )
        diversity_low = int(train["exact_groups"]) < 30 or int(train["near_groups"]) < 30
        if eval_low or diversity_low:
            low_known.add(label)
        if diversity_low:
            structural.add(label)
        raw_scarce = int(total_counts.get(label, 0)) < 2000
        if raw_scarce or diversity_low:
            parent = coarse_mapping[label]
            siblings = sorted(
                other
                for other in all_labels
                if other != label and coarse_mapping[other] == parent
            )
            reasons = []
            if raw_scarce:
                reasons.append("raw_session_scarcity")
            if int(train["exact_groups"]) < 30:
                reasons.append("train_exact_diversity_scarcity")
            if int(train["near_groups"]) < 30:
                reasons.append("train_near_diversity_scarcity")
            candidate_pool.append(
                {
                    "class": label,
                    "coarse_parent": parent,
                    "sessions": int(total_counts.get(label, 0)),
                    "train_sessions": int(train["count"]),
                    "train_exact_groups": int(train["exact_groups"]),
                    "train_near_groups": int(train["near_groups"]),
                    "remaining_parent_siblings": siblings,
                    "shared_parent_possible": bool(siblings),
                    "selection_rationale": reasons,
                }
            )
    return {
        "LOW_RESOURCE_KNOWN": sorted(low_known),
        "STRUCTURALLY_INSUFFICIENT_KNOWN": sorted(structural),
        "LOW_RESOURCE_UNKNOWN_CANDIDATE_POOL": candidate_pool,
        "candidate_rule": (
            "pre-model metadata only: total sessions <2000 or train exact/near "
            "diversity below the preregistered 30-group reference"
        ),
        "LOW_RESOURCE_STRESS_TEST_STATUS": LOW_RESOURCE_STRESS_STATUS,
        "changes_known_unknown_membership": False,
    }
