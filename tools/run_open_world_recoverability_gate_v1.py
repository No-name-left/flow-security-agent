#!/usr/bin/env python3
"""OPEN WORLD RECOVERABILITY GATE V1 — kill gate (low-cost, RF-only).

Question: does selective runtime Evidence acquisition reduce avoidable
false-Unknown decisions on Evidence-recoverable Known observations WITHOUT
materially degrading True Unknown recognition?

Frozen protocol (pre-registered before any result of this gate; no rescue,
no tuning after results exist):

- Data: frozen Gate 1 per-seed target views (TRAIN 175,000 / VALIDATION
  56,000 per seed; seeds 20260817/18/19). FINAL_TEST never enters any array.
- Derived split: per seed, VALIDATION -> VAL_CALIB / VAL_GATE_EVAL 50/50,
  atomic at private activity_group_digest, stratified by (class,
  temporal_block), groups processed chronologically (minimum flow_start_ms)
  and placed into the bin with the smaller cumulative row count (ties ->
  CALIB); per-stratum imbalance bounded by the largest group's size. An
  initial freeze using the Gate-1B OOF searchsorted chunking produced a
  systematic 22/78 imbalance under this data's group-size skew and was
  corrected BEFORE any gate result (see build_calib_eval_folds note); every
  protected property (atomicity, stratification, chronological order,
  determinism) is preserved. Frozen before any gate result; manifest +
  sha256 recorded.
- Rotations: three whole-class held-out rotations — Credential,
  Recon_Scanning, Web_Injection. Held-out class = TRUE_UNKNOWN for that
  rotation; excluded from known-classifier training, utility OOF
  construction, utility-selector training, novelty-threshold calibration,
  and policy tuning. Labels used ONLY for final offline evaluation.
- Known models: RandomForestClassifier(n_estimators=80, max_depth=20,
  min_samples_leaf=2, class_weight="balanced_subsample", random_state=seed)
  — the frozen Gate-1-compatible config — trained per rotation on the six
  Known classes, conditions B / BT / BR / BTR (same feature transforms as
  Gate 1: safe_basic 47 fields; T = 16 temporal history fields, R = 18
  relation history fields, log1p(clip)); no estimator change, no tuning.
- Utility selectors: per rotation, TRAIN-only 3-fold group-atomic OOF
  signed utility labels (HELP=+1 / HARM=-1 / 0, frozen definitions) over
  the six Known classes; one RandomForestRegressor family
  (n_estimators=200, max_depth=12, min_samples_leaf=20, max_features="sqrt",
  n_jobs=-1, random_state=seed) per family U_T / U_R / U_TR; input =
  pre-acquisition Basic runtime state only (47 basic + 6-class one-hot +
  proba_B + max/margin/entropy + availability mask); leakage audit on
  feature names. No held-out Unknown sample enters utility training.
- Actions: NONE / T / R / TR; unit costs COST(NONE)=0, COST(T)=1,
  COST(R)=1, COST(TR)=2. PRIMARY_TOTAL_COST_BUDGET = 0.15 * N_targets
  (single-family-equivalent units), applied to the population the policy
  operates on (calibration set and evaluation set separately).
- Typed policy (P6, deterministic, pre-registered): eligible targets have
  max(u_T,u_R,u_TR) > 0; sort by max utility descending (tie: ascending
  target order); ideal family = argmax with tie-break priority T, R, TR;
  if remaining budget >= cost(ideal) select with the ideal family, else
  fall back to the cheapest affordable family with positive predicted
  utility in priority order T then R, else keep NONE; stop when budget is
  exhausted.
- Policies: P0 BASIC_DIRECT, P1 ALWAYS_FULL (TR for all, uncapped),
  P2 RANDOM_COST_MATCHED (>=100 deterministic repetitions, per-rep
  calibration and metrics, T acquired at cost 1), P3 LOW_CONFIDENCE
  COST_MATCHED (top-K by max proba_B ascending, T at cost 1),
  P4 HIGH_ENTROPY COST_MATCHED (top-K by proba_B entropy descending, T at
  cost 1), P5 UTILITY_TEMPORAL_ONLY COST_MATCHED (top-K by u_T, only
  u_T > 0), P6 UTILITY_TYPED COST_MATCHED (greedy typed rule above),
  P7 ORACLE_TYPED_ANALYSIS_ONLY (realized-outcome selection; analysis only,
  NEVER deployable).
- Novelty score: UNKNOWN_SCORE_MSP = 1 - max known-class probability, from
  the model matching the actually acquired Evidence (NONE->B, T->BT,
  R->BR, TR->BTR). Primary score fixed before results (no selection after
  seeing results). Secondary non-gating scores: entropy, margin.
- Policy-conditioned calibration (mandatory): for EVERY policy
  independently, VAL_CALIB Known rows -> execute the complete frozen
  acquisition policy -> post-acquisition probabilities -> post-acquisition
  novelty scores -> threshold at KNOWN_FALSE_UNKNOWN_RATE = 5% (95th
  percentile of Known post-acquisition scores). Held-out Unknown labels
  never choose a threshold. The BASIC_DIRECT threshold is never reused for
  other policies. VAL_GATE_EVAL then traverses the same frozen policy and
  applies that policy's own calibrated threshold.
- Metrics: FURK (recoverable-Known rejected / recoverable-Known), residual
  Known false-Unknown rate, total Known rejection rate, Known Macro-F1,
  Known Balanced Accuracy, Evidence Recovery Rate, recoverable-Known
  recovery count, residual Known rejection, acquisition rate, Evidence
  cost, Unknown AUROC/AUPR/Recall@5%KnownFUR, TRUE_UNKNOWN_ACQUISITION_RATE,
  TRUE_UNKNOWN_MEAN_COST, TRUE_UNKNOWN_POST_ACQUISITION_SCORE_SHIFT.
- Recoverable Known (definition frozen, NOT novelty-outcome-based): Basic
  prediction wrong AND at least one legal Evidence state among BT/BR/BTR
  predicts correctly; family-specific recoverability also recorded.
  Residual-hard Known: Basic wrong AND BT wrong AND BR wrong AND BTR wrong.
- Gate criteria OW1-OW7 over 3 rotations (per-rotation value = mean over
  seeds), OW7 pooled paired group/temporal-block bootstrap (>=1000
  replicates, group-atomic, paired across policies by construction).
- Decision: PASS (7/7), YELLOW (>=5/7 with OW1+OW3+OW4 and no severe
  failure), FAIL otherwise. Severe: mean Unknown AUROC loss > 0.05, mean
  Unknown Recall@5%KnownFUR loss > 0.08, or FURK_UTILITY > FURK_DIRECT in
  >= 2 rotations. YELLOW/FAIL => STOP, no Phase C.
- Secondary non-gating: GCLC-style pseudo-unknown calibration analysis
  (inner Known-class holdout on VAL_CALIB; threshold transferred from
  pseudo-unknown score distribution; never replaces the primary
  fixed-Known-FPR policy-conditioned calibration); utility-vs-difficulty
  comparison (P6 vs P3 vs P4); Evidence specialization audit
  (true-known-class x family HELP/HARM/UNIQUE_HELP/NET_UTILITY; statistics
  never become runtime routing rules).

No FINAL_TEST row-level data. No DeepSeek, no Qwen, no GPU training, no RL,
no continual training. Results are NOT committed.

Modes: split | run | bootstrap | decide | purification
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_core_hypothesis_gate_v1 import (  # noqa: E402
    CANONICAL_CLASS_ORDER,
    CONDITIONS,
    N_TEMPORAL_BLOCKS,
    PARTITION_TRAIN,
    PARTITION_VALIDATION,
    build_feature_matrices,
    fit_estimator,
    safe_basic,
)
from run_core_hypothesis_gate_v1b import (  # noqa: E402
    DERIVED_BASIC_FEATURES,
    FORBIDDEN_SELECTOR_MARKERS,
    SELECTOR_CONFIG,
    align_proba_to_class_order,
    entropy_of,
    load_basic_features,
    basic_matrix_for,
    load_history_features,
    load_targets,
    utility_labels,
)

FORMAL_SEEDS = (20260817, 20260818, 20260819)
SMOKE_SEED = 777001
ROTATIONS = ("Credential", "Recon_Scanning", "Web_Injection")

DEFAULT_OWG_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/open_world_recoverability_gate_v1"
)
DEFAULT_GATE1_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1"
)

CALIB_RATIO = 0.5
CALIB_EVAL_FOLDS = 2
CALIB_KNOWN_FALSE_UNKNOWN_RATE = 0.05

ACTIONS = ("NONE", "T", "R", "TR")
ACTION_COSTS = {"NONE": 0, "T": 1, "R": 1, "TR": 2}
ACTION_MODEL = {"NONE": "B", "T": "BT", "R": "BR", "TR": "BTR"}
PRIMARY_COST_BUDGET_FRACTION = 0.15
FAMILY_PRIORITY = ("T", "R", "TR")
FALLBACK_PRIORITY = ("T", "R")

RANDOM_REPS = 100
RANDOM_RNG_OFFSET = 131000
BOOTSTRAP_REPS = 1000
BOOTSTRAP_RNG_OFFSET = 161000
PROBA_EPS = 1e-12

# Gate criteria (frozen)
OW1_FURK_MEAN_MAX = -0.03
OW1_ROTATION_IMPROVE = 0.02
OW1_ROTATION_WORST = 0.02
OW2_FURK_MEAN_MAX = -0.02
OW3_AUROC_MARGIN = 0.01
OW3_ROTATION_WORST = 0.03
OW4_RECALL_MARGIN = 0.03
OW4_ROTATION_WORST = 0.05
OW5_MACRO_MIN_GAIN = 0.003
OW6_RECOVERY_MEAN_MIN = 0.25
OW6_RECOVERY_ROTATION_MIN = 0.20
SEVERE_AUROC_LOSS = 0.05
SEVERE_RECALL_LOSS = 0.08
SEVERE_FURK_WORSE_ROTATIONS = 2

# Phase C purification criteria (frozen)
PU1_PURITY_GAIN_MIN = 0.03
PU2_RK_CONTAMINATION_REL_REDUCTION = 0.30
PU3_RETENTION_LOSS_MAX = 0.03
PU3_RETENTION_ROTATION_LOSS_MAX = 0.05
PU4_KNOWN_CONTAMINATION_REL_REDUCTION = 0.15


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def known_classes_for(rotation: str) -> tuple[str, ...]:
    return tuple(name for name in CANONICAL_CLASS_ORDER if name != rotation)


def rotation_one_hot(predicted: np.ndarray, known_classes: tuple[str, ...],
                     ) -> np.ndarray:
    codes = np.array([known_classes.index(name) for name in predicted], dtype=np.int64)
    out = np.zeros((len(predicted), len(known_classes)), dtype=np.float64)
    out[np.arange(len(predicted)), codes] = 1.0
    return out


def align_rotation_proba(proba: np.ndarray, classes: np.ndarray,
                         known_classes: tuple[str, ...]) -> np.ndarray:
    classes = list(classes)
    if classes == list(known_classes):
        return proba
    if sorted(classes) != sorted(known_classes):
        raise SystemExit(f"OPEN_WORLD_GATE_STATUS=UNEXPECTED_MODEL_CLASSES "
                         f"classes={classes} known={known_classes}")
    order = [classes.index(name) for name in known_classes]
    return proba[:, order]


def rotation_selector_features(
    basic: np.ndarray,
    pred_b: np.ndarray,
    proba_b: np.ndarray,
    availability: np.ndarray,
    known_classes: tuple[str, ...],
) -> tuple[np.ndarray, list[str]]:
    """Pre-acquisition Basic runtime state only (6-class rotation variant of
    the frozen Gate 1B selector input)."""
    basic_t = safe_basic(basic)
    columns = [basic_t, rotation_one_hot(pred_b, known_classes), proba_b]
    max_prob = proba_b.max(axis=1)
    sorted_proba = np.sort(proba_b, axis=1)
    margin = sorted_proba[:, -1] - sorted_proba[:, -2]
    ent = entropy_of(proba_b)
    columns.extend([max_prob[:, None], margin[:, None], ent[:, None]])
    columns.append(availability.astype(np.float64)[:, None])
    matrix = np.column_stack(columns)
    names = (list(range_basic_names())
             + [f"pred_class_onehot_{name}" for name in known_classes]
             + [f"proba_B_{name}" for name in known_classes]
             + list(DERIVED_BASIC_FEATURES))
    if len(names) != matrix.shape[1]:
        raise SystemExit("OPEN_WORLD_GATE_STATUS=SELECTOR_FEATURE_NAME_MISMATCH")
    return matrix, names


def range_basic_names() -> list[str]:
    # 47 MODEL_VISIBLE_FIELDS names are re-imported below via MODEL_VISIBLE_FIELDS
    from run_core_hypothesis_gate_v1 import MODEL_VISIBLE_FIELDS  # noqa: PLC0415
    return list(MODEL_VISIBLE_FIELDS)


def selector_leakage_audit(names: list[str]) -> str:
    lower = " ".join(names).lower()
    violations = [marker for marker in FORBIDDEN_SELECTOR_MARKERS if marker in lower]
    if violations:
        return f"FAIL:{','.join(violations)}"
    return "PASS"


# ---------------------------------------------------------------------------
# CALIB / EVAL split (frozen before results)
# ---------------------------------------------------------------------------

def build_calib_eval_folds(targets: dict[str, np.ndarray]) -> np.ndarray:
    """Per-seed VALIDATION split into CALIB / EVAL (50/50), atomic at the
    private activity-group level, stratified by (class, temporal_block):
    within each stratum groups are processed chronologically (minimum
    flow_start_ms) and each group is placed in the bin with the smaller
    cumulative row count (ties -> CALIB/role 0). Per-stratum imbalance is
    bounded by the largest group's size, so the overall ratio stays near
    50/50 even under the strongly skewed private-group sizes of this dataset.
    Deterministic (no RNG).

    NOTE (recorded in the frozen manifest): the initial freeze used the
    Gate-1B OOF searchsorted chunking (chronological largest-remainder with
    boundary-crossing groups in the later bin), which produced a systematic
    22/78 CALIB/EVAL imbalance under this data's group-size skew. Before any
    gate result existed, the split rule was corrected to the balanced rule
    above (pre-registration is unaffected: the corrected split is still
    frozen before any result). Every protected property — group atomicity,
    (class, temporal_block) stratification, chronological ordering within
    each bin, determinism — is preserved by both rules."""
    val_mask = targets["partition_code"] == PARTITION_VALIDATION
    rows_all = np.flatnonzero(val_mask)
    groups = targets["activity_group_digest"][rows_all]
    unique_groups, inverse = np.unique(groups, return_inverse=True)
    starts = targets["flow_start_ms"][rows_all]
    labels = targets["canonical_label"][rows_all]
    blocks = targets["temporal_block"][rows_all]

    order = np.lexsort((rows_all, starts))
    _, first_idx = np.unique(groups[order], return_index=True)
    primary_positions = order[first_idx]
    gid_index = {bytes(value): index for index, value in enumerate(unique_groups)}
    primary_gidx = np.array(
        [gid_index[bytes(value)] for value in groups[primary_positions]],
        dtype=np.int64)
    reorder = np.argsort(primary_gidx, kind="stable")
    primary_class = labels[primary_positions][reorder]
    primary_block = blocks[primary_positions][reorder]
    primary_start = starts[primary_positions][reorder]
    group_counts = np.bincount(inverse)

    group_role = np.full(len(unique_groups), -1, dtype=np.int8)
    for class_name in CANONICAL_CLASS_ORDER:
        for block in range(N_TEMPORAL_BLOCKS):
            gids = np.flatnonzero((primary_class == class_name)
                                  & (primary_block == block))
            if not len(gids):
                continue
            pstarts = primary_start[gids]
            counts = group_counts[gids]
            order_g = np.argsort(pstarts, kind="stable")
            cumulative = np.zeros(CALIB_EVAL_FOLDS, dtype=np.int64)
            for group in order_g:
                bin_id = int(np.argmin(cumulative))  # ties -> lowest index
                group_role[gids[group]] = bin_id
                cumulative[bin_id] += int(counts[group])
    if (group_role < 0).any():
        raise SystemExit("OPEN_WORLD_GATE_STATUS=CALIB_EVAL_ASSIGNMENT_INCOMPLETE")
    return group_role[inverse]


def run_split(args) -> int:
    artifact_root = Path(args.artifact_root)
    gate1_root = Path(args.gate1_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema_version": "OPEN_WORLD_GATE_CALIB_EVAL_SPLIT_MANIFEST_V1",
        "date": "2026-08-17",
        "source": "frozen Gate 1 per-seed VALIDATION target views (56,000/seed)",
        "rule": ("atomic at activity_group_digest; stratified by "
                 "(canonical class, temporal_block); groups chronological "
                 "within stratum, placed into the smaller cumulative bin "
                 "(ties -> CALIB); target ratio 50/50; initial Gate-1B-style "
                 "searchsorted freeze corrected pre-results (22/78 -> ~50/50)"),
        "ratio": CALIB_RATIO,
        "seeds": {},
    }
    for seed in (SMOKE_SEED, ) + FORMAL_SEEDS:
        started = time.monotonic()
        targets = load_targets(gate1_root, seed)
        val_mask = targets["partition_code"] == PARTITION_VALIDATION
        # build_calib_eval_folds already returns one role per VALIDATION row
        # (in ascending source-row order, matching boolean-masked slices)
        roles = build_calib_eval_folds(targets)
        counts = {name: int((roles == code).sum())
                  for name, code in (("CALIB", 0), ("EVAL", 1))}
        groups = targets["activity_group_digest"][val_mask]
        unique_groups = np.unique(groups)
        table = pa.table({
            "source_row_index": pa.array(
                targets["source_row_index"][val_mask], pa.int64()),
            "canonical_label": pa.array(
                targets["canonical_label"][val_mask], pa.string()),
            "partition_code": pa.array(
                targets["partition_code"][val_mask].astype(np.int64), pa.int8()),
            "temporal_block": pa.array(
                targets["temporal_block"][val_mask].astype(np.int64), pa.int16()),
            "flow_start_ms": pa.array(
                targets["flow_start_ms"][val_mask], pa.int64()),
            "activity_group_digest": pa.array(
                [bytes(v) for v in groups], pa.binary(16)),
            "split_role": pa.array(roles.astype(np.int64), pa.int8()),
        })
        out = artifact_root / f"owg_v1_seed_{seed}_split.parquet"
        pq.write_table(table, out, compression="zstd")
        digest = sha256_file(out)
        manifest["seeds"][str(seed)] = {
            "split_parquet": out.name,
            "sha256": digest,
            "n_calib": counts["CALIB"],
            "n_eval": counts["EVAL"],
            "n_groups": int(len(unique_groups)),
            "seconds": round(time.monotonic() - started, 1),
        }
        print(f"[split seed {seed}] CALIB={counts['CALIB']:,} "
              f"EVAL={counts['EVAL']:,} groups={len(unique_groups):,} "
              f"sha256={digest[:16]}…")
    manifest_path = artifact_root / "owg_v1_split_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[split] OPEN_WORLD_GATE_SPLIT_STATUS=FROZEN "
          f"manifest={manifest_path}")
    return 0


def verify_split(args, seed: int) -> dict[str, Any]:
    """Verify the frozen split exists and its hash matches the manifest
    BEFORE any gate computation for that seed."""
    artifact_root = Path(args.artifact_root)
    manifest = json.loads(
        (artifact_root / "owg_v1_split_manifest.json").read_text(encoding="utf-8"))
    info = manifest["seeds"][str(seed)]
    path = artifact_root / info["split_parquet"]
    if not path.exists():
        raise SystemExit(f"OPEN_WORLD_GATE_STATUS=SPLIT_MISSING seed={seed} "
                         f"run mode=split first")
    if sha256_file(path) != info["sha256"]:
        raise SystemExit(f"OPEN_WORLD_GATE_STATUS=SPLIT_HASH_MISMATCH seed={seed}")
    return info


# ---------------------------------------------------------------------------
# OOF folds over TRAIN Known rows (group-atomic, per rotation)
# ---------------------------------------------------------------------------

def build_rotation_oof_folds(targets: dict[str, np.ndarray],
                             train_known: np.ndarray) -> np.ndarray:
    """3-fold assignment over TRAIN rows whose label is a Known class for
    this rotation (`train_known` is a boolean mask over TRAIN rows only).
    Group-atomic at the private activity-group level, primary (class,
    temporal_block) stratum of the group's earliest row, chronological
    largest-remainder chunking (identical semantics to the frozen Gate 1B
    OOF folds). Returns fold ids aligned to the TRAIN-row order of the
    feature matrices; rows outside the OOF set carry -1."""
    train_rows_all = np.flatnonzero(targets["partition_code"] == PARTITION_TRAIN)
    known_positions = np.flatnonzero(train_known)
    rows_all = train_rows_all[known_positions]
    groups = targets["activity_group_digest"][rows_all]
    unique_groups, inverse = np.unique(groups, return_inverse=True)
    starts = targets["flow_start_ms"][rows_all]
    labels = targets["canonical_label"][rows_all]
    blocks = targets["temporal_block"][rows_all]

    order = np.lexsort((rows_all, starts))
    _, first_idx = np.unique(groups[order], return_index=True)
    primary_positions = order[first_idx]
    gid_index = {bytes(value): index for index, value in enumerate(unique_groups)}
    primary_gidx = np.array(
        [gid_index[bytes(value)] for value in groups[primary_positions]],
        dtype=np.int64)
    reorder = np.argsort(primary_gidx, kind="stable")
    primary_class = labels[primary_positions][reorder]
    primary_block = blocks[primary_positions][reorder]
    primary_start = starts[primary_positions][reorder]
    group_counts = np.bincount(inverse)

    group_fold = np.full(len(unique_groups), -1, dtype=np.int8)
    for class_name in known_classes_for_any():  # only classes present matter
        for block in range(N_TEMPORAL_BLOCKS):
            gids = np.flatnonzero((primary_class == class_name)
                                  & (primary_block == block))
            if not len(gids):
                continue
            pstarts = primary_start[gids]
            counts = group_counts[gids]
            order_g = np.argsort(pstarts, kind="stable")
            total = int(counts.sum())
            boundaries = np.floor(total * np.arange(1, 3) / 3).astype(np.int64)
            cum = np.cumsum(counts[order_g])
            group_fold[gids[order_g]] = np.searchsorted(
                boundaries, cum, side="left").astype(np.int8)
    if (group_fold < 0).any():
        raise SystemExit("OPEN_WORLD_GATE_STATUS=OOF_FOLD_ASSIGNMENT_INCOMPLETE")
    fold = np.full(len(train_rows_all), -1, dtype=np.int8)
    fold[known_positions] = group_fold[inverse]
    return fold


def known_classes_for_any() -> tuple[str, ...]:
    return CANONICAL_CLASS_ORDER


# ---------------------------------------------------------------------------
# Policies (deterministic, pre-registered)
# ---------------------------------------------------------------------------

def select_topk(scores: np.ndarray, k: int, order: np.ndarray) -> np.ndarray:
    """Deterministic top-k: score descending, tie-break ascending row order."""
    ranked = np.lexsort((order, -scores))
    selected = np.zeros(len(scores), dtype=bool)
    selected[ranked[:k]] = True
    return selected


def typed_policy_actions(u_t: np.ndarray, u_r: np.ndarray, u_tr: np.ndarray,
                         budget_units: int, order: np.ndarray) -> np.ndarray:
    """Greedy cost-aware typed policy (frozen rule): eligible = max utility
    > 0; sort by max utility descending (tie: ascending order); ideal family
    = argmax with tie-break priority T, R, TR; if remaining budget covers the
    ideal family cost acquire it, else fall back to the cheapest affordable
    family with positive predicted utility (priority T then R), else NONE;
    stop when the budget is exhausted. Returns actions (NONE/T/R/TR)."""
    n = len(u_t)
    max_u = np.maximum(np.maximum(u_t, u_r), u_tr)
    eligible = max_u > 0
    candidates = np.flatnonzero(eligible)
    if not len(candidates):
        return np.full(n, "NONE", dtype=object)
    ranked = np.lexsort((order[candidates], -max_u[candidates]))
    actions = np.full(n, "NONE", dtype=object)
    remaining = int(budget_units)
    for position in candidates[ranked]:
        if remaining <= 0:
            break
        family = None
        for name in FAMILY_PRIORITY:
            if (name == "T" and u_t[position] == max_u[position]) \
                    or (name == "R" and u_r[position] == max_u[position]) \
                    or (name == "TR" and u_tr[position] == max_u[position]):
                family = name
                break
        if family is None:
            continue
        cost = ACTION_COSTS[family]
        if cost <= remaining:
            actions[position] = family
            remaining -= cost
            continue
        # budget fallback: cheapest affordable family with positive utility
        for name in FALLBACK_PRIORITY:
            value = {"T": u_t, "R": u_r}[name][position]
            if ACTION_COSTS[name] <= remaining and value > 0:
                actions[position] = name
                remaining -= ACTION_COSTS[name]
                break
    return actions


def random_selection(n: int, k: int, rng_seed: int) -> np.ndarray:
    rng = np.random.default_rng(rng_seed)
    selected = np.zeros(n, dtype=bool)
    selected[rng.choice(n, size=k, replace=False)] = True
    return selected


def calibrate_threshold(scores_known: np.ndarray,
                        fur: float = CALIB_KNOWN_FALSE_UNKNOWN_RATE) -> float:
    """Policy-conditioned operating threshold: the `fur` quantile of Known
    post-acquisition novelty scores (Known-only; Unknown labels never enter).
    If no Known rows are available (not expected), returns +inf (reject
    nothing)."""
    if not len(scores_known):
        return float("inf")
    return float(np.quantile(scores_known, 1.0 - fur))


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def macro_f1_of(labels: np.ndarray, predicted: np.ndarray) -> float:
    return float(f1_score(labels, predicted, average="macro"))


def unknown_metrics(unknown_score: np.ndarray, known_score: np.ndarray,
                    threshold: float) -> dict[str, float]:
    """AUROC / AUPR over pooled Known+Unknown novelty scores, and Unknown
    recall at the calibrated threshold."""
    y = np.r_[np.zeros(len(known_score)), np.ones(len(unknown_score))]
    scores = np.r_[known_score, unknown_score]
    return {
        "auroc": float(roc_auc_score(y, scores)),
        "aupr": float(average_precision_score(y, scores)),
        "unknown_recall_at_calibrated_fur": float(
            (unknown_score >= threshold).mean()),
    }


# ---------------------------------------------------------------------------
# Per-seed run
# ---------------------------------------------------------------------------

def run_seed(args, seed: int, is_smoke: bool = False) -> int:
    artifact_root = Path(args.artifact_root)
    gate1_root = Path(args.gate1_root)
    (artifact_root / "models").mkdir(parents=True, exist_ok=True)
    verify_split(args, seed)
    started = time.monotonic()
    targets = load_targets(gate1_root, seed)
    train_mask = targets["partition_code"] == PARTITION_TRAIN
    val_mask = targets["partition_code"] == PARTITION_VALIDATION
    train_rows = targets["source_row_index"][train_mask]
    val_rows = targets["source_row_index"][val_mask]
    train_labels = targets["canonical_label"][train_mask]
    val_labels = targets["canonical_label"][val_mask]

    basic_rows, basic_arrays = load_basic_features(gate1_root)
    basic_positions = {int(value): index for index, value in enumerate(basic_rows)}
    basic_train = basic_matrix_for(train_rows, basic_arrays, basic_positions)
    basic_val = basic_matrix_for(val_rows, basic_arrays, basic_positions)
    history_train, history_names = load_history_features(gate1_root, seed, train_rows)
    history_val, _ = load_history_features(gate1_root, seed, val_rows)
    matrices_train = build_feature_matrices(basic_train, history_train, history_names)
    matrices_val = build_feature_matrices(basic_val, history_val, history_names)
    val_groups = np.array([bytes(v) for v in targets["activity_group_digest"][val_mask]],
                          dtype=object)
    val_blocks = targets["temporal_block"][val_mask]
    split_table = pq.read_table(artifact_root / f"owg_v1_seed_{seed}_split.parquet")
    split_order = split_table["source_row_index"].to_numpy(zero_copy_only=False)
    split_positions = {int(value): index for index, value in enumerate(split_order)}
    val_split = np.array(
        [int(split_table["split_role"][split_positions[int(row)]].as_py())
         for row in val_rows], dtype=np.int8)

    all_results: dict[str, Any] = {"seed": seed, "smoke": bool(is_smoke),
                                   "rotations": {}}
    for rotation in ROTATIONS:
        rot_started = time.monotonic()
        known = known_classes_for(rotation)
        train_known = train_labels != rotation  # mask over TRAIN rows only
        val_known_flag = val_labels != rotation
        val_unknown_flag = ~val_known_flag

        # 1) Known models B/BT/BR/BTR (6 classes, frozen estimator config)
        models: dict[str, Any] = {}
        for condition in CONDITIONS:
            model = fit_estimator(seed)
            model.fit(matrices_train[condition][train_known],
                      train_labels[train_known])
            models[condition] = model
            print(f"[seed {seed} rot {rotation}] {condition} fitted "
                  f"(known train n={int(train_known.sum()):,})", flush=True)

        # 2) OOF utility labels over TRAIN Known rows (3-fold group-atomic)
        fold = build_rotation_oof_folds(targets, train_known)
        oof_rows = np.flatnonzero(fold >= 0)
        oof_pred: dict[str, np.ndarray] = {}
        oof_proba_b = np.zeros((len(oof_rows), len(known)), dtype=np.float64)
        for condition in CONDITIONS:
            pred = np.empty(len(oof_rows), dtype=object)
            proba = np.zeros((len(oof_rows), len(known)), dtype=np.float64)
            for fold_id in range(3):
                held = fold[oof_rows] == fold_id
                train_here = ~held
                model = fit_estimator(seed)
                model.fit(matrices_train[condition][oof_rows[train_here]],
                          train_labels[oof_rows[train_here]])
                pred[held] = model.predict(
                    matrices_train[condition][oof_rows[held]])
                proba[held] = align_rotation_proba(
                    model.predict_proba(matrices_train[condition][oof_rows[held]]),
                    model.classes_, known)
            oof_pred[condition] = pred
            if condition == "B":
                oof_proba_b = proba
            print(f"[seed {seed} rot {rotation}] {condition} OOF complete "
                  f"n={len(oof_rows):,}", flush=True)
        oof_labels = train_labels[oof_rows]
        availability = np.ones(len(oof_rows))
        features_oof, names_oof = rotation_selector_features(
            basic_train[oof_rows], oof_pred["B"], oof_proba_b, availability, known)
        audit = selector_leakage_audit(names_oof)
        if audit != "PASS":
            raise SystemExit(f"OPEN_WORLD_GATE_STATUS=SELECTOR_LEAKAGE_AUDIT_FAIL "
                             f"rotation={rotation} audit={audit}")
        selectors: dict[str, Any] = {}
        for family in ("T", "R", "TR"):
            condition = {"T": "BT", "R": "BR", "TR": "BTR"}[family]
            _, _, signed = utility_labels(oof_pred["B"], oof_pred[condition],
                                          oof_labels)
            config = dict(SELECTOR_CONFIG)
            config["random_state"] = seed
            model = RandomForestRegressor(**config)
            model.fit(features_oof, signed)
            selectors[family] = model
            print(f"[seed {seed} rot {rotation}] Selector_{family} fitted "
                  f"(help={int((signed == 1).sum()):,} "
                  f"harm={int((signed == -1).sum()):,})", flush=True)

        # 3) Validation scoring: proba + predictions from every model
        val_proba: dict[str, np.ndarray] = {}
        val_pred: dict[str, np.ndarray] = {}
        for condition in CONDITIONS:
            proba = align_rotation_proba(
                models[condition].predict_proba(matrices_val[condition]),
                models[condition].classes_, known)
            val_proba[condition] = proba
            val_pred[condition] = models[condition].predict(matrices_val[condition])
        unknown_score_direct = 1.0 - val_proba["B"].max(axis=1)

        # 4) Selector features + utility predictions on VALIDATION
        pred_b_val = val_pred["B"]
        availability_val = np.ones(len(val_rows))
        features_val, names_val = rotation_selector_features(
            basic_val, pred_b_val, val_proba["B"], availability_val, known)
        audit_val = selector_leakage_audit(names_val)
        if audit_val != "PASS":
            raise SystemExit(f"OPEN_WORLD_GATE_STATUS=SELECTOR_LEAKAGE_AUDIT_FAIL_VAL "
                             f"rotation={rotation} audit={audit_val}")
        u_t = selectors["T"].predict(features_val)
        u_r = selectors["R"].predict(features_val)
        u_tr = selectors["TR"].predict(features_val)

        # 5) Recoverability (frozen definition, model-based, novelty-independent)
        basic_wrong = val_pred["B"] != val_labels
        bt_correct = val_pred["BT"] == val_labels
        br_correct = val_pred["BR"] == val_labels
        btr_correct = val_pred["BTR"] == val_labels
        recoverable = basic_wrong & (bt_correct | br_correct | btr_correct)
        residual_hard = basic_wrong & (~bt_correct) & (~br_correct) & (~btr_correct)
        rec_by_family = {
            "T": basic_wrong & bt_correct,
            "R": basic_wrong & br_correct,
            "TR": basic_wrong & btr_correct,
        }

        # 6) Policies (population-relative, pre-registered): the frozen rule
        # runs separately on VAL_CALIB (budget 0.15*N_calib) and VAL_GATE_EVAL
        # (budget 0.15*N_eval); calibration and evaluation traverse the SAME
        # rule. Threshold: policy-conditioned, Known-only calibration rows.
        n_eval = int(val_split.sum())
        n_calib = len(val_rows) - n_eval
        budget_eval = int(np.floor(PRIMARY_COST_BUDGET_FRACTION * n_eval))
        budget_calib = int(np.floor(PRIMARY_COST_BUDGET_FRACTION * n_calib))
        eval_mask = val_split == 1
        calib_mask = val_split == 0
        calib_known = calib_mask & val_known_flag

        def policy_scores(actions: np.ndarray) -> np.ndarray:
            out = np.empty(len(val_rows), dtype=np.float64)
            for action in ACTIONS:
                mask = (actions == action).astype(bool)
                if action == "NONE":
                    out[mask] = unknown_score_direct[mask]
                else:
                    out[mask] = 1.0 - val_proba[ACTION_MODEL[action]][mask].max(axis=1)
            return out

        def policy_preds(actions: np.ndarray) -> np.ndarray:
            out = np.empty(len(val_rows), dtype=object)
            for action in ACTIONS:
                mask = (actions == action).astype(bool)
                if action == "NONE":
                    out[mask] = val_pred["B"][mask]
                else:
                    out[mask] = val_pred[ACTION_MODEL[action]][mask]
            return out

        def policy_actions(pop_mask: np.ndarray, budget_units: int, rule
                           ) -> np.ndarray:
            """Apply `rule` to the population subset with its own budget;
            returns full-array actions (NONE outside the subset)."""
            idx = np.flatnonzero(pop_mask)
            actions = np.full(len(val_rows), "NONE", dtype=object)
            actions[idx] = rule(idx, budget_units)
            return actions

        def eval_policy(rule) -> tuple[dict[str, Any], np.ndarray]:
            actions = np.where(calib_mask,
                               policy_actions(calib_mask, budget_calib, rule),
                               policy_actions(eval_mask, budget_eval, rule))
            scores = policy_scores(actions)
            preds = policy_preds(actions)
            threshold = calibrate_threshold(scores[calib_known])
            rejected = scores >= threshold
            kn = val_known_flag & eval_mask
            un = val_unknown_flag & eval_mask
            rec_kn = recoverable & kn
            res_kn = residual_hard & kn
            costs = np.array([ACTION_COSTS[a] for a in actions], dtype=np.float64)
            out: dict[str, Any] = {
                "threshold": threshold,
                "known_n": int(kn.sum()),
                "unknown_n": int(un.sum()),
                "furk": float(rejected[rec_kn].mean()) if rec_kn.sum() else 0.0,
                "residual_known_false_unknown_rate": float(
                    rejected[res_kn].mean()) if res_kn.sum() else 0.0,
                "total_known_rejection_rate": float(rejected[kn].mean()),
                "known_macro_f1": macro_f1_of(val_labels[kn], preds[kn]),
                "known_balanced_accuracy": float(
                    balanced_accuracy_score(val_labels[kn], preds[kn])),
                "evidence_recovery_rate": float(
                    (preds[rec_kn] == val_labels[rec_kn]).mean()) if rec_kn.sum() else 0.0,
                "recoverable_known_recovery_count": int(
                    (preds[rec_kn] == val_labels[rec_kn]).sum()),
                "residual_known_rejected_count": int(rejected[res_kn].sum()),
                "acquisition_rate": float((actions != "NONE")[eval_mask].mean()),
                "evidence_cost_total_units": float(costs[eval_mask].sum()),
                "evidence_mean_cost": float(costs[eval_mask].mean()),
            }
            out.update(unknown_metrics(scores[un], scores[kn], threshold))
            out["true_unknown_acquisition_rate"] = float(
                (actions[un] != "NONE").mean()) if un.sum() else 0.0
            out["true_unknown_mean_cost"] = float(costs[un].mean()) if un.sum() else 0.0
            out["true_unknown_post_acquisition_score_shift"] = float(
                (scores[un] - unknown_score_direct[un]).mean()) if un.sum() else 0.0
            return out, actions

        def rule_p0(idx, budget_units):
            return np.full(len(idx), "NONE", dtype=object)

        def rule_p1(idx, budget_units):
            return np.full(len(idx), "TR", dtype=object)

        def rule_p3(idx, budget_units):
            scores = -val_proba["B"][idx].max(axis=1)
            sel = select_topk(scores, min(budget_units, len(idx)), idx)
            return np.where(sel, "T", "NONE").astype(object)

        def rule_p4(idx, budget_units):
            scores = entropy_of(val_proba["B"][idx])
            sel = select_topk(scores, min(budget_units, len(idx)), idx)
            return np.where(sel, "T", "NONE").astype(object)

        def rule_p5(idx, budget_units):
            u = u_t[idx]
            scores = np.where(u > 0, u, -np.inf)
            sel = select_topk(scores, min(budget_units, len(idx)), idx)
            return np.where(sel, "T", "NONE").astype(object)

        def rule_p6(idx, budget_units):
            return typed_policy_actions(u_t[idx], u_r[idx], u_tr[idx],
                                        budget_units, idx)

        def rule_p7(idx, budget_units):
            sub_pred = {c: val_pred[c][idx] for c in CONDITIONS}
            return oracle_actions(val_labels[idx], sub_pred,
                                  val_unknown_flag[idx], budget_units, idx)

        policies: dict[str, Any] = {}
        policy_actions_store: dict[str, np.ndarray] = {}
        for name, rule in (("P0_BASIC_DIRECT", rule_p0),
                           ("P1_ALWAYS_FULL", rule_p1),
                           ("P3_LOW_CONFIDENCE", rule_p3),
                           ("P4_HIGH_ENTROPY", rule_p4),
                           ("P5_UTILITY_TEMPORAL_ONLY", rule_p5),
                           ("P6_UTILITY_TYPED", rule_p6),
                           ("P7_ORACLE_TYPED", rule_p7)):
            metrics, actions = eval_policy(rule)
            policies[name] = metrics
            policy_actions_store[name] = actions

        # P2 RANDOM_COST_MATCHED (>=100 deterministic reps; T at cost 1;
        # per-rep population-relative selection AND per-rep calibration)
        random_metrics: dict[str, list[float]] = {}
        for rep in range(RANDOM_REPS):
            rng_seed = RANDOM_RNG_OFFSET + seed * 1000 + rep

            def random_rule(idx, budget_units):
                k = min(budget_units, len(idx))
                sel = random_selection(len(idx), k, rng_seed)
                return np.where(sel, "T", "NONE").astype(object)

            m, _ = eval_policy(random_rule)
            for key, value in m.items():
                random_metrics.setdefault(key, []).append(float(value))
        policies["P2_RANDOM_COST_MATCHED"] = {
            key: float(np.mean(values)) for key, values in random_metrics.items()
        }
        policies["P2_RANDOM_COST_MATCHED"]["reps"] = RANDOM_REPS

        # Specialization audit (non-gating, EVAL Known rows, P6 actions)
        specialization = specialization_audit(
            val_labels, val_known_flag, eval_mask, recoverable, rec_by_family,
            policy_actions_store["P6_UTILITY_TYPED"], val_pred)
        # GCLC-style pseudo-unknown secondary (non-gating)
        pseudo = gclc_pseudo_unknown_secondary(
            matrices_train, matrices_val, train_labels, train_known,
            val_rows, val_labels, val_known_flag, val_split, known, seed,
            policy_actions_store["P6_UTILITY_TYPED"], policies)

        result = {
            "rotation": rotation,
            "known_classes": list(known),
            "train_known_n": int(train_known.sum()),
            "val_n": int(len(val_rows)),
            "n_eval": n_eval,
            "n_calib": n_calib,
            "budget_eval_units": budget_eval,
            "budget_calib_units": budget_calib,
            "n_recoverable_known": int(recoverable[val_known_flag & eval_mask].sum()),
            "n_residual_hard_known": int(residual_hard[val_known_flag & eval_mask].sum()),
            "recoverable_by_family": {
                f: int((rec_by_family[f] & val_known_flag & eval_mask).sum())
                for f in ("T", "R", "TR")
            },
            "policies": policies,
            "specialization_audit": specialization,
            "gclc_pseudo_unknown_secondary": pseudo,
            "seconds": round(time.monotonic() - rot_started, 1),
        }
        # persist per-cell evaluation table for Phase C (frozen outputs)
        records = {
            "source_row_index": pa.array(val_rows, pa.int64()),
            "canonical_label": pa.array(val_labels, pa.string()),
            "split_role": pa.array(val_split.astype(np.int64), pa.int8()),
            "is_unknown": pa.array(val_unknown_flag.astype(np.int64), pa.int8()),
            "recoverable": pa.array(recoverable.astype(np.int64), pa.int8()),
            "residual_hard": pa.array(residual_hard.astype(np.int64), pa.int8()),
            "activity_group_digest": pa.array(val_groups, pa.binary(16)),
            "temporal_block": pa.array(val_blocks.astype(np.int64), pa.int16()),
        }
        for name in ("P0_BASIC_DIRECT", "P1_ALWAYS_FULL", "P3_LOW_CONFIDENCE",
                     "P4_HIGH_ENTROPY", "P5_UTILITY_TEMPORAL_ONLY",
                     "P6_UTILITY_TYPED", "P7_ORACLE_TYPED"):
            actions = policy_actions_store[name]
            scores = policy_scores(actions)
            preds = policy_preds(actions)
            threshold = policies[name]["threshold"]
            records[f"action_{name}"] = pa.array(actions, pa.string())
            records[f"score_{name}"] = pa.array(scores, pa.float64())
            records[f"pred_{name}"] = pa.array(preds, pa.string())
            records[f"rejected_{name}"] = pa.array(
                (scores >= threshold).astype(np.int64), pa.int8())
        eval_table_path = artifact_root / (
            f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet")
        pq.write_table(pa.table(records), eval_table_path, compression="zstd")
        result["eval_table_sha256"] = sha256_file(eval_table_path)
        (artifact_root / f"owg_v1_seed_{seed}_rotation_{rotation}_result.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        with open(artifact_root / "models"
                  / f"owg_v1_seed_{seed}_rotation_{rotation}_models.pkl", "wb") as handle:
            pickle.dump({"models": models, "selectors": selectors}, handle, protocol=5)
        print(f"[seed {seed} rot {rotation}] done in "
              f"{result['seconds']}s: FURK "
              f"P0={policies['P0_BASIC_DIRECT']['furk']:.4f} "
              f"P6={policies['P6_UTILITY_TYPED']['furk']:.4f} "
              f"P2={policies['P2_RANDOM_COST_MATCHED']['furk']:.4f} | AUROC "
              f"P0={policies['P0_BASIC_DIRECT']['auroc']:.4f} "
              f"P6={policies['P6_UTILITY_TYPED']['auroc']:.4f}", flush=True)
        all_results["rotations"][rotation] = result

    (artifact_root / f"owg_v1_seed_{seed}_run_summary.json").write_text(
        json.dumps({"schema_version": "OPEN_WORLD_GATE_RUN_SUMMARY_V1",
                    "seed": seed, "seconds": round(time.monotonic() - started, 1)},
                   indent=2), encoding="utf-8")
    print(f"[seed {seed}] OPEN_WORLD_GATE_SEED_COMPLETE "
          f"in {time.monotonic() - started:.0f}s")
    return 0


def oracle_actions(labels: np.ndarray, pred: dict[str, np.ndarray],
                   unknown_flag: np.ndarray, budget_units: int,
                   order: np.ndarray) -> np.ndarray:
    """Analysis-only oracle: for Known rows choose the family with the best
    realized outcome (HELP = B wrong and B+E correct; rank TR > T > R on
    ties) subject to cost <= remaining budget; NONE otherwise. Uses realized
    future outcomes — NEVER deployable, never part of the gate decision."""
    n = len(labels)
    actions = np.full(n, "NONE", dtype=object)
    known = ~unknown_flag
    help_t = (pred["B"] != labels) & (pred["BT"] == labels)
    help_r = (pred["B"] != labels) & (pred["BR"] == labels)
    help_tr = (pred["B"] != labels) & (pred["BTR"] == labels)
    score = np.full(n, -np.inf)
    score[help_tr & known] = 3.0
    score[help_t & known & ~help_tr] = 2.0
    score[help_r & known & ~help_tr & ~help_t] = 1.0
    ranked = np.lexsort((order, -score))
    remaining = int(budget_units)
    for position in ranked:
        if remaining <= 0:
            break
        if not known[position]:
            continue
        family = None
        for name in FAMILY_PRIORITY:
            value = {"T": help_t, "R": help_r, "TR": help_tr}[name][position]
            if value and ACTION_COSTS[name] <= remaining:
                family = name
                break
        if family is None:
            continue
        actions[position] = family
        remaining -= ACTION_COSTS[family]
    return actions


def specialization_audit(labels, known_flag, eval_mask, recoverable,
                         rec_by_family, actions, pred) -> dict[str, Any]:
    """Non-gating: per true-Known class x family HELP/HARM/UNIQUE_HELP/NET
    utility + P6 acquisition behavior. Statistics never become runtime
    routing rules."""
    out: dict[str, Any] = {}
    kn = known_flag & eval_mask
    for class_name in CANONICAL_CLASS_ORDER:
        cls = kn & (labels == class_name)
        if not cls.sum():
            continue
        cell: dict[str, Any] = {"n": int(cls.sum())}
        for family, condition in (("T", "BT"), ("R", "BR"), ("TR", "BTR")):
            help_f, harm_f, _ = utility_labels(pred["B"], pred[condition], labels)
            unique = rec_by_family[family] & ~(
                {"T": rec_by_family["R"] | rec_by_family["TR"],
                 "R": rec_by_family["T"] | rec_by_family["TR"],
                 "TR": rec_by_family["T"] | rec_by_family["R"]}[family])
            cell[family] = {
                "help_rate": float(help_f[cls].mean()),
                "harm_rate": float(harm_f[cls].mean()),
                "unique_help_rate": float(unique[cls].mean()),
                "net_utility_rate": float((help_f[cls].mean() - harm_f[cls].mean())),
            }
        acquired = cls & (actions == "T") | cls & (actions == "R") | cls & (actions == "TR")
        cell["acquisition_rate"] = float(acquired.mean())
        cell["help_capture"] = float(acquired.sum() / max(1, int(
            ((pred["B"] != labels) & (cls)).sum())))
        out[class_name] = cell
    return out


def gclc_pseudo_unknown_secondary(
    matrices_train: dict[str, np.ndarray], matrices_val: dict[str, np.ndarray],
    train_labels: np.ndarray, train_known: np.ndarray,
    val_rows: np.ndarray, val_labels: np.ndarray, val_known_flag: np.ndarray,
    val_split: np.ndarray, known_classes: tuple[str, ...], seed: int,
    actions_p6: np.ndarray, policies: dict[str, Any],
) -> dict[str, Any]:
    """SECONDARY non-gating analysis (GCLC-inspired): inner Known-class
    holdout on VAL_CALIB -> pseudo-unknown scores -> percentile transfer.
    Uses only Known calibration rows; never the real held-out Unknown.
    The transferred threshold is reported as a reference and NEVER replaces
    the primary fixed-Known-FPR policy-conditioned calibration."""
    calib_known = (val_split == 0) & val_known_flag
    inner_holdout = known_classes[0]  # deterministic
    calib_rest = calib_known & (val_labels != inner_holdout)
    if calib_rest.sum() < 100 or calib_known.sum() < 200:
        return {"status": "SKIPPED_INSUFFICIENT_ROWS"}
    model = fit_estimator(seed)
    model.fit(matrices_train["B"][train_known & (train_labels != inner_holdout)],
              train_labels[train_known & (train_labels != inner_holdout)])
    model_classes = tuple(name for name in known_classes if name != inner_holdout)
    pseudo_proba = align_rotation_proba(
        model.predict_proba(matrices_val["B"][calib_known]),
        model.classes_, model_classes)
    pseudo_scores = 1.0 - pseudo_proba.max(axis=1)
    held_proba = align_rotation_proba(
        model.predict_proba(matrices_val["B"][calib_rest]),
        model.classes_, model_classes)
    held_known_scores = 1.0 - held_proba.max(axis=1)
    threshold_pseudo = calibrate_threshold(pseudo_scores)
    return {
        "status": "COMPLETE",
        "inner_holdout_class": inner_holdout,
        "pseudo_unknown_n": int(calib_known.sum()),
        "inner_known_n": int(calib_rest.sum()),
        "pseudo_unknown_threshold": threshold_pseudo,
        "inner_known_fur_at_pseudo_threshold": float(
            (held_known_scores >= threshold_pseudo).mean()),
        "primary_threshold_P6": policies["P6_UTILITY_TYPED"]["threshold"],
        "secondary_only": True,
        "never_replaces_primary_calibration": True,
    }


# ---------------------------------------------------------------------------
# Aggregation and decision
# ---------------------------------------------------------------------------

def per_rotation_mean(results_by_seed: dict[int, dict[str, Any]],
                      rotation: str, metric_path: list[str],
                      ) -> float:
    values = []
    for seed_result in results_by_seed.values():
        node = seed_result["rotations"][rotation]
        for key in metric_path:
            node = node[key]
        values.append(float(node))
    return float(np.mean(values))


def run_decide(args) -> int:
    artifact_root = Path(args.artifact_root)
    results_by_seed: dict[int, dict[str, Any]] = {}
    for seed in FORMAL_SEEDS:
        summary = json.loads(
            (artifact_root / f"owg_v1_seed_{seed}_run_summary.json").read_text())
        results_by_seed[seed] = {"rotations": {}}
        for rotation in ROTATIONS:
            results_by_seed[seed]["rotations"][rotation] = json.loads(
                (artifact_root
                 / f"owg_v1_seed_{seed}_rotation_{rotation}_result.json").read_text())

    def rot_metric(rotation: str, policy: str, metric: str) -> float:
        return per_rotation_mean(results_by_seed, rotation,
                                 ["policies", policy, metric])

    furk = {rotation: {p: rot_metric(rotation, p, "furk")
                       for p in ("P0_BASIC_DIRECT", "P2_RANDOM_COST_MATCHED",
                                 "P3_LOW_CONFIDENCE", "P4_HIGH_ENTROPY",
                                 "P5_UTILITY_TEMPORAL_ONLY",
                                 "P6_UTILITY_TYPED")}
            for rotation in ROTATIONS}
    auroc = {rotation: {p: rot_metric(rotation, p, "auroc")
                        for p in ("P0_BASIC_DIRECT", "P6_UTILITY_TYPED")}
             for rotation in ROTATIONS}
    recall = {rotation: {p: rot_metric(rotation, p, "unknown_recall_at_calibrated_fur")
                         for p in ("P0_BASIC_DIRECT", "P6_UTILITY_TYPED")}
              for rotation in ROTATIONS}
    macro = {rotation: {p: rot_metric(rotation, p, "known_macro_f1")
                        for p in ("P0_BASIC_DIRECT", "P3_LOW_CONFIDENCE",
                                  "P4_HIGH_ENTROPY", "P6_UTILITY_TYPED")}
             for rotation in ROTATIONS}
    recovery = {rotation: rot_metric(rotation, "P6_UTILITY_TYPED",
                                     "evidence_recovery_rate")
                for rotation in ROTATIONS}

    def mean_of(dct: dict[str, float]) -> float:
        return float(np.mean(list(dct.values())))

    d_furk_direct = {r: furk[r]["P6_UTILITY_TYPED"] - furk[r]["P0_BASIC_DIRECT"]
                     for r in ROTATIONS}
    d_furk_random = {r: furk[r]["P6_UTILITY_TYPED"] - furk[r]["P2_RANDOM_COST_MATCHED"]
                     for r in ROTATIONS}
    d_auroc = {r: auroc[r]["P6_UTILITY_TYPED"] - auroc[r]["P0_BASIC_DIRECT"]
               for r in ROTATIONS}
    d_recall = {r: recall[r]["P6_UTILITY_TYPED"] - recall[r]["P0_BASIC_DIRECT"]
                for r in ROTATIONS}
    d_macro = {r: macro[r]["P6_UTILITY_TYPED"] - macro[r]["P0_BASIC_DIRECT"]
               for r in ROTATIONS}

    ow1 = (mean_of(d_furk_direct) <= OW1_FURK_MEAN_MAX
           and sum(1 for r in ROTATIONS if d_furk_direct[r] <= -OW1_ROTATION_IMPROVE) >= 2
           and all(d_furk_direct[r] <= OW1_ROTATION_WORST for r in ROTATIONS))
    ow2 = (mean_of(d_furk_random) <= OW2_FURK_MEAN_MAX
           and sum(1 for r in ROTATIONS if d_furk_random[r] < 0) >= 2)
    ow3 = (mean_of(d_auroc) >= -OW3_AUROC_MARGIN
           and all(d_auroc[r] >= -OW3_ROTATION_WORST for r in ROTATIONS))
    ow4 = (mean_of(d_recall) >= -OW4_RECALL_MARGIN
           and all(d_recall[r] >= -OW4_ROTATION_WORST for r in ROTATIONS))
    ow5 = (mean_of(d_macro) >= OW5_MACRO_MIN_GAIN
           and sum(1 for r in ROTATIONS if d_macro[r] > 0) >= 2)
    ow6 = (mean_of(recovery) >= OW6_RECOVERY_MEAN_MIN
           and sum(1 for r in ROTATIONS if recovery[r] >= OW6_RECOVERY_ROTATION_MIN) >= 2)

    bootstrap = json.loads((artifact_root / "owg_v1_bootstrap.json").read_text())
    ow7_ci = bootstrap["furk_diff_utility_minus_direct"]["ci95"]
    ow7 = ow7_ci[1] < 0.0

    pass_count = sum([ow1, ow2, ow3, ow4, ow5, ow6, ow7])
    mean_auroc_loss = -mean_of(d_auroc)
    mean_recall_loss = -mean_of(d_recall)
    severe = (mean_auroc_loss > SEVERE_AUROC_LOSS
              or mean_recall_loss > SEVERE_RECALL_LOSS
              or sum(1 for r in ROTATIONS if d_furk_direct[r] > 0)
              >= SEVERE_FURK_WORSE_ROTATIONS)
    if pass_count == 7 and not severe:
        decision = "PASS"
    elif pass_count >= 5 and ow1 and ow3 and ow4 and not severe:
        decision = "YELLOW"
    else:
        decision = "FAIL"

    report = {
        "schema_version": "OPEN_WORLD_RECOVERABILITY_GATE_V1_REPORT_V1",
        "date": "2026-08-17",
        "branch": args.branch,
        "head": args.head,
        "master_split_modified": False,
        "final_test_modeling_contamination": False,
        "rotations": list(ROTATIONS),
        "seeds": list(FORMAL_SEEDS),
        "calib_known_false_unknown_rate": CALIB_KNOWN_FALSE_UNKNOWN_RATE,
        "cost_budget_fraction": PRIMARY_COST_BUDGET_FRACTION,
        "per_rotation": {},
        "criteria": {
            "OW1_furk_vs_direct": {"pass": ow1, "mean_diff": mean_of(d_furk_direct),
                                   "by_rotation": d_furk_direct,
                                   "rule": "mean<=-0.03, >=2/3 improve >=0.02, none worse >0.02"},
            "OW2_furk_vs_random": {"pass": ow2, "mean_diff": mean_of(d_furk_random),
                                   "by_rotation": d_furk_random,
                                   "rule": "mean<=-0.02, >=2/3 improve"},
            "OW3_unknown_auroc": {"pass": ow3, "mean_diff": mean_of(d_auroc),
                                  "by_rotation": d_auroc,
                                  "rule": "mean>=-0.01, none worse >0.03"},
            "OW4_unknown_recall": {"pass": ow4, "mean_diff": mean_of(d_recall),
                                   "by_rotation": d_recall,
                                   "rule": "mean>=-0.03, none worse >0.05"},
            "OW5_known_macro_f1": {"pass": ow5, "mean_diff": mean_of(d_macro),
                                   "by_rotation": d_macro,
                                   "rule": "mean>=+0.003, utility>direct in >=2/3"},
            "OW6_evidence_recovery": {"pass": ow6, "by_rotation": recovery,
                                      "rule": "mean>=0.25, >=0.20 in >=2/3"},
            "OW7_paired_bootstrap": {"pass": ow7, "ci95": ow7_ci,
                                     "reps": BOOTSTRAP_REPS,
                                     "rule": "FURK(utility-direct) CI upper < 0"},
            "pass_count": pass_count,
            "severe_failure": severe,
        },
        "decision": decision,
        "safety": {
            "FINAL_TEST_MODELING_CONTAMINATION": False,
            "UTILITY_SELECTOR_UNKNOWN_TRAINING_LEAKAGE": False,
            "CALIB_EVAL_LEAKAGE": False,
            "POLICY_CONDITIONED_CALIBRATION": True,
        },
    }
    for rotation in ROTATIONS:
        report["per_rotation"][rotation] = {
            "FURK": furk[rotation],
            "UNKNOWN_AUROC": auroc[rotation],
            "UNKNOWN_RECALL_AT_5PCT_KNOWN_FUR": recall[rotation],
            "KNOWN_MACRO_F1": macro[rotation],
            "EVIDENCE_RECOVERY_RATE": recovery[rotation],
            "TRUE_UNKNOWN_ACQUISITION_RATE": {
                p: rot_metric(rotation, p, "true_unknown_acquisition_rate")
                for p in ("P0_BASIC_DIRECT", "P6_UTILITY_TYPED")},
            "TRUE_UNKNOWN_POST_ACQUISITION_SCORE_SHIFT": {
                p: rot_metric(rotation, p, "true_unknown_post_acquisition_score_shift")
                for p in ("P0_BASIC_DIRECT", "P6_UTILITY_TYPED")},
            "UTILITY_VS_LOW_CONFIDENCE_FURK":
                furk[rotation]["P6_UTILITY_TYPED"] - furk[rotation]["P3_LOW_CONFIDENCE"],
            "UTILITY_VS_HIGH_ENTROPY_FURK":
                furk[rotation]["P6_UTILITY_TYPED"] - furk[rotation]["P4_HIGH_ENTROPY"],
            "KNOWN_BALANCED_ACCURACY": {
                p: rot_metric(rotation, p, "known_balanced_accuracy")
                for p in ("P0_BASIC_DIRECT", "P6_UTILITY_TYPED")},
        }
    (artifact_root / "owg_v1_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"[decide] OW1={ow1} OW2={ow2} OW3={ow3} OW4={ow4} OW5={ow5} "
          f"OW6={ow6} OW7={ow7} pass_count={pass_count} severe={severe}")
    print(f"[decide] OPEN_WORLD_RECOVERABILITY_GATE={decision}")
    return 0


# ---------------------------------------------------------------------------
# Bootstrap (OW7)
# ---------------------------------------------------------------------------

def run_bootstrap(args) -> int:
    artifact_root = Path(args.artifact_root)
    group_rec: list[np.ndarray] = []
    group_rej_u: list[np.ndarray] = []
    group_rej_d: list[np.ndarray] = []
    group_unknown: list[np.ndarray] = []
    group_known: list[np.ndarray] = []
    group_cand_u: list[np.ndarray] = []
    group_cand_d: list[np.ndarray] = []
    group_cand_unk_u: list[np.ndarray] = []
    group_cand_unk_d: list[np.ndarray] = []
    group_cand_rk_u: list[np.ndarray] = []
    group_cand_rk_d: list[np.ndarray] = []
    for seed in FORMAL_SEEDS:
        for rotation in ROTATIONS:
            table = pq.read_table(artifact_root
                                  / f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet")
            groups = np.array([bytes(v) for v in table["activity_group_digest"].to_pylist()],
                              dtype=object)
            unique_groups = np.unique(groups)
            _, inverse = np.unique(groups, return_inverse=True)
            recoverable = table["recoverable"].to_numpy().astype(bool)
            is_unknown = table["is_unknown"].to_numpy().astype(bool)
            rejected_u = table["rejected_P6_UTILITY_TYPED"].to_numpy().astype(bool)
            rejected_d = table["rejected_P0_BASIC_DIRECT"].to_numpy().astype(bool)
            n_groups = len(unique_groups)
            group_rec.append(np.bincount(inverse, weights=recoverable.astype(np.float64),
                                         minlength=n_groups))
            group_rej_u.append(np.bincount(
                inverse, weights=(recoverable & rejected_u).astype(np.float64),
                minlength=n_groups))
            group_rej_d.append(np.bincount(
                inverse, weights=(recoverable & rejected_d).astype(np.float64),
                minlength=n_groups))
            group_unknown.append(np.bincount(inverse, weights=is_unknown.astype(np.float64),
                                             minlength=n_groups))
            group_known.append(np.bincount(
                inverse, weights=(~is_unknown).astype(np.float64), minlength=n_groups))
            group_cand_u.append(np.bincount(inverse, weights=rejected_u.astype(np.float64),
                                            minlength=n_groups))
            group_cand_d.append(np.bincount(inverse, weights=rejected_d.astype(np.float64),
                                            minlength=n_groups))
            group_cand_unk_u.append(np.bincount(
                inverse, weights=(rejected_u & is_unknown).astype(np.float64),
                minlength=n_groups))
            group_cand_unk_d.append(np.bincount(
                inverse, weights=(rejected_d & is_unknown).astype(np.float64),
                minlength=n_groups))
            group_cand_rk_u.append(np.bincount(
                inverse, weights=(rejected_u & recoverable).astype(np.float64),
                minlength=n_groups))
            group_cand_rk_d.append(np.bincount(
                inverse, weights=(rejected_d & recoverable).astype(np.float64),
                minlength=n_groups))

    rec = np.concatenate(group_rec)
    rej_u = np.concatenate(group_rej_u)
    rej_d = np.concatenate(group_rej_d)
    unk = np.concatenate(group_unknown)
    known = np.concatenate(group_known)
    cand_u = np.concatenate(group_cand_u)
    cand_d = np.concatenate(group_cand_d)
    cand_unk_u = np.concatenate(group_cand_unk_u)
    cand_unk_d = np.concatenate(group_cand_unk_d)
    cand_rk_u = np.concatenate(group_cand_rk_u)
    cand_rk_d = np.concatenate(group_cand_rk_d)
    n_groups_total = len(rec)

    rng = np.random.default_rng(BOOTSTRAP_RNG_OFFSET)
    furk_diff = np.empty(BOOTSTRAP_REPS, dtype=np.float64)
    purity_gain = np.empty(BOOTSTRAP_REPS, dtype=np.float64)
    rk_contam_diff = np.empty(BOOTSTRAP_REPS, dtype=np.float64)
    for rep in range(BOOTSTRAP_REPS):
        # per-replicate resampling (bounded memory): draw n group ids with
        # replacement, then aggregate; policies are paired by construction
        # because every per-group count vector is fixed before resampling.
        draws = rng.integers(0, n_groups_total, size=n_groups_total)
        w = np.bincount(draws, minlength=n_groups_total).astype(np.float64)
        denom_rec = float(w @ rec)
        furk_u = float(w @ rej_u) / denom_rec if denom_rec > 0 else 0.0
        furk_d = float(w @ rej_d) / denom_rec if denom_rec > 0 else 0.0
        furk_diff[rep] = furk_u - furk_d
        denom_u = float(w @ cand_u)
        denom_d = float(w @ cand_d)
        purity_u = float(w @ cand_unk_u) / denom_u if denom_u > 0 else 0.0
        purity_d = float(w @ cand_unk_d) / denom_d if denom_d > 0 else 0.0
        purity_gain[rep] = purity_u - purity_d
        rk_u = float(w @ cand_rk_u) / denom_u if denom_u > 0 else 0.0
        rk_d = float(w @ cand_rk_d) / denom_d if denom_d > 0 else 0.0
        rk_contam_diff[rep] = rk_u - rk_d

    def ci95(values: np.ndarray) -> list[float]:
        return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]

    out = {
        "schema_version": "OPEN_WORLD_GATE_BOOTSTRAP_V1",
        "reps": BOOTSTRAP_REPS,
        "unit": "private activity group, pooled over 3 rotations x 3 seeds",
        "paired": True,
        "furk_diff_utility_minus_direct": {
            "mean": float(furk_diff.mean()), "ci95": ci95(furk_diff)},
        "buffer_purity_gain_utility_minus_direct": {
            "mean": float(purity_gain.mean()), "ci95": ci95(purity_gain)},
        "rk_contamination_diff_utility_minus_direct": {
            "mean": float(rk_contam_diff.mean()), "ci95": ci95(rk_contam_diff)},
        "observed": {
            "furk_utility": float(rej_u.sum() / max(rec.sum(), 1e-12)),
            "furk_direct": float(rej_d.sum() / max(rec.sum(), 1e-12)),
            "buffer_purity_utility": float(cand_unk_u.sum() / max(cand_u.sum(), 1e-12)),
            "buffer_purity_direct": float(cand_unk_d.sum() / max(cand_d.sum(), 1e-12)),
            "rk_contamination_utility": float(cand_rk_u.sum() / max(cand_u.sum(), 1e-12)),
            "rk_contamination_direct": float(cand_rk_d.sum() / max(cand_d.sum(), 1e-12)),
        },
    }
    (artifact_root / "owg_v1_bootstrap.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    print(f"[bootstrap] FURK diff (utility-direct) mean={furk_diff.mean():+.6f} "
          f"CI95={ci95(furk_diff)}")
    print(f"[bootstrap] buffer purity gain mean={purity_gain.mean():+.6f} "
          f"CI95={ci95(purity_gain)}")
    print(f"[bootstrap] RK contamination diff mean={rk_contam_diff.mean():+.6f} "
          f"CI95={ci95(rk_contam_diff)}")
    return 0


# ---------------------------------------------------------------------------
# Phase C — Unknown-Candidate Purification Gate (frozen Phase-B outputs only)
# ---------------------------------------------------------------------------

def run_purification(args) -> int:
    artifact_root = Path(args.artifact_root)
    per_cell: dict[str, Any] = {}
    for seed in FORMAL_SEEDS:
        for rotation in ROTATIONS:
            table = pq.read_table(artifact_root
                                  / f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet")
            eval_mask = table["split_role"].to_numpy() == 1
            is_unknown = table["is_unknown"].to_numpy().astype(bool)[eval_mask]
            recoverable = table["recoverable"].to_numpy().astype(bool)[eval_mask]
            rejected_u = table["rejected_P6_UTILITY_TYPED"].to_numpy().astype(bool)[eval_mask]
            rejected_d = table["rejected_P0_BASIC_DIRECT"].to_numpy().astype(bool)[eval_mask]
            n = int(eval_mask.sum())

            def buffer_stats(rejected: np.ndarray) -> dict[str, float]:
                cand = int(rejected.sum())
                unknown_cand = int((rejected & is_unknown).sum())
                rk_cand = int((rejected & recoverable).sum())
                other_known = cand - unknown_cand - rk_cand
                return {
                    "candidate_count": cand,
                    "candidate_rate": cand / n,
                    "BUFFER_PURITY": unknown_cand / cand if cand else 0.0,
                    "RECOVERABLE_KNOWN_CONTAMINATION": rk_cand / cand if cand else 0.0,
                    "OTHER_KNOWN_CONTAMINATION": other_known / cand if cand else 0.0,
                    "TOTAL_KNOWN_CONTAMINATION": (rk_cand + other_known) / cand if cand else 0.0,
                    "TRUE_UNKNOWN_RETENTION": unknown_cand / max(int(is_unknown.sum()), 1),
                    "LABEL_WASTE_PROXY": (rk_cand + other_known) / cand if cand else 0.0,
                }

            per_cell[f"{rotation}|{seed}"] = {
                "rotation": rotation, "seed": seed,
                "DIRECT_BUFFER": buffer_stats(rejected_d),
                "EVIDENCE_GATED_BUFFER": buffer_stats(rejected_u),
            }

    def rot_mean(rotation: str, buffer: str, metric: str) -> float:
        return float(np.mean([
            per_cell[f"{rotation}|{seed}"][buffer][metric] for seed in FORMAL_SEEDS]))

    def rel_reduction(a: float, b: float) -> float:
        return (a - b) / a if a > 0 else 0.0

    purity_gain = {r: rot_mean(r, "EVIDENCE_GATED_BUFFER", "BUFFER_PURITY")
                   - rot_mean(r, "DIRECT_BUFFER", "BUFFER_PURITY") for r in ROTATIONS}
    rk_contam = {r: rot_mean(r, "EVIDENCE_GATED_BUFFER", "RECOVERABLE_KNOWN_CONTAMINATION")
                 - rot_mean(r, "DIRECT_BUFFER", "RECOVERABLE_KNOWN_CONTAMINATION")
                 for r in ROTATIONS}
    rk_rel = {r: rel_reduction(rot_mean(r, "DIRECT_BUFFER", "RECOVERABLE_KNOWN_CONTAMINATION"),
                               rot_mean(r, "EVIDENCE_GATED_BUFFER",
                                        "RECOVERABLE_KNOWN_CONTAMINATION"))
              for r in ROTATIONS}
    retention = {r: rot_mean(r, "EVIDENCE_GATED_BUFFER", "TRUE_UNKNOWN_RETENTION")
                 - rot_mean(r, "DIRECT_BUFFER", "TRUE_UNKNOWN_RETENTION")
                 for r in ROTATIONS}
    known_contam = {r: rot_mean(r, "EVIDENCE_GATED_BUFFER", "TOTAL_KNOWN_CONTAMINATION")
                    - rot_mean(r, "DIRECT_BUFFER", "TOTAL_KNOWN_CONTAMINATION")
                    for r in ROTATIONS}
    known_rel = {r: rel_reduction(rot_mean(r, "DIRECT_BUFFER", "TOTAL_KNOWN_CONTAMINATION"),
                                  rot_mean(r, "EVIDENCE_GATED_BUFFER",
                                           "TOTAL_KNOWN_CONTAMINATION"))
                 for r in ROTATIONS}

    def mean_of(dct: dict[str, float]) -> float:
        return float(np.mean(list(dct.values())))

    pu1 = (mean_of(purity_gain) >= PU1_PURITY_GAIN_MIN
           and sum(1 for r in ROTATIONS if purity_gain[r] > 0) >= 2)
    pu2 = (mean_of(rk_rel) >= PU2_RK_CONTAMINATION_REL_REDUCTION
           and all(rk_rel[r] > 0 for r in ROTATIONS))
    pu3 = (mean_of(retention) >= -PU3_RETENTION_LOSS_MAX
           and all(retention[r] >= -PU3_RETENTION_ROTATION_LOSS_MAX for r in ROTATIONS))
    pu4 = mean_of(known_rel) >= PU4_KNOWN_CONTAMINATION_REL_REDUCTION

    bootstrap = json.loads((artifact_root / "owg_v1_bootstrap.json").read_text())
    purity_ci = bootstrap["buffer_purity_gain_utility_minus_direct"]["ci95"]
    rk_ci = bootstrap["rk_contamination_diff_utility_minus_direct"]["ci95"]
    pu5 = (purity_ci[0] > 0.0) or (rk_ci[1] < 0.0)

    pass_count = sum([pu1, pu2, pu3, pu4, pu5])
    if pass_count == 5:
        decision = "PASS"
    elif pass_count >= 4 and pu2 and pu3:
        decision = "YELLOW"
    else:
        decision = "FAIL"
    foundation = {"PASS": "SUPPORTED",
                  "YELLOW": "PROMISING_NOT_ESTABLISHED",
                  "FAIL": "NOT_SUPPORTED"}[decision]

    report = {
        "schema_version": "UNKNOWN_CANDIDATE_PURIFICATION_GATE_V1_REPORT_V1",
        "date": "2026-08-17",
        "branch": args.branch,
        "head": args.head,
        "inputs": "frozen Phase-B evaluation outputs (no new thresholds or policies tuned)",
        "no_continual_model_training": True,
        "per_rotation": {
            r: {
                "DIRECT_BUFFER": {m: rot_mean(r, "DIRECT_BUFFER", m)
                                  for m in ("BUFFER_PURITY",
                                            "RECOVERABLE_KNOWN_CONTAMINATION",
                                            "TOTAL_KNOWN_CONTAMINATION",
                                            "TRUE_UNKNOWN_RETENTION")},
                "EVIDENCE_GATED_BUFFER": {m: rot_mean(r, "EVIDENCE_GATED_BUFFER", m)
                                          for m in ("BUFFER_PURITY",
                                                    "RECOVERABLE_KNOWN_CONTAMINATION",
                                                    "TOTAL_KNOWN_CONTAMINATION",
                                                    "TRUE_UNKNOWN_RETENTION")},
                "purity_gain": purity_gain[r],
                "rk_contamination_rel_reduction": rk_rel[r],
                "known_contamination_rel_reduction": known_rel[r],
                "retention_change": retention[r],
            } for r in ROTATIONS
        },
        "criteria": {
            "PU1_buffer_purity_gain": {"pass": pu1, "mean": mean_of(purity_gain),
                                       "by_rotation": purity_gain,
                                       "rule": "mean>=+0.03, positive >=2/3"},
            "PU2_rk_contamination_rel_reduction": {"pass": pu2, "mean": mean_of(rk_rel),
                                                   "by_rotation": rk_rel,
                                                   "rule": "mean>=30%, reduced 3/3"},
            "PU3_true_unknown_retention": {"pass": pu3, "mean": mean_of(retention),
                                           "by_rotation": retention,
                                           "rule": "mean loss<=0.03, none >0.05"},
            "PU4_known_contamination_rel_reduction": {"pass": pu4,
                                                      "mean": mean_of(known_rel),
                                                      "rule": "mean>=15%"},
            "PU5_paired_bootstrap": {"pass": pu5,
                                     "purity_ci95": purity_ci,
                                     "rk_ci95": rk_ci,
                                     "reps": BOOTSTRAP_REPS,
                                     "rule": "purity gain CI lower>0 OR rk diff CI upper<0"},
            "pass_count": pass_count,
        },
        "decision": decision,
        "SELF_EVOLUTION_PURIFICATION_FOUNDATION": foundation,
    }
    (artifact_root / "owg_v1_purification_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"[purification] PU1={pu1} PU2={pu2} PU3={pu3} PU4={pu4} PU5={pu5} "
          f"pass_count={pass_count}")
    print(f"[purification] UNKNOWN_CANDIDATE_PURIFICATION_GATE={decision} "
          f"SELF_EVOLUTION_PURIFICATION_FOUNDATION={foundation}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True,
                        choices=["split", "run", "bootstrap", "decide",
                                 "purification"])
    parser.add_argument("--artifact-root", default=DEFAULT_OWG_ROOT)
    parser.add_argument("--gate1-root", default=DEFAULT_GATE1_ROOT)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--head", default="")
    args = parser.parse_args()

    if args.mode == "split":
        return run_split(args)
    if args.mode == "run":
        seeds = (args.seed,) if args.seed else (
            (SMOKE_SEED,) if args.smoke else FORMAL_SEEDS)
        for seed in seeds:
            run_seed(args, seed, is_smoke=seed == SMOKE_SEED)
        return 0
    if args.mode == "bootstrap":
        return run_bootstrap(args)
    if args.mode == "decide":
        return run_decide(args)
    return run_purification(args)


if __name__ == "__main__":
    raise SystemExit(main())
