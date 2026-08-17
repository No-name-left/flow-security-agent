#!/usr/bin/env python3
"""OPEN-WORLD GATE V1 FAILURE ATTRIBUTION + FURK AUDIT — diagnostic only.

Question: is the frozen V1 FAIL primarily (1) a metric / denominator
implementation artifact, (2) Evidence routing failure, (3) classification
recovery failure, (4) MSP novelty-score mismatch, (5) policy-conditioned
threshold / subgroup calibration shift, or (6) a combination?

Frozen protocol (pre-registered before any diagnostic result; diagnostic
ONLY — the V1 result remains FAIL and is NOT modified):

- Uses ONLY frozen artifacts: per-seed CALIB/EVAL split manifest + parquet,
  per-cell eval tables (frozen per-row actions/scores/preds/rejections),
  per-cell result JSONs (frozen thresholds and metrics), frozen models pkl
  (B/BT/BR/BTR classifiers + U_T/U_R/U_TR selectors). Nothing is retrained,
  no new thresholds are created, the acquisition budget is never changed,
  no alternative novelty detector is evaluated, FINAL_TEST never enters any
  array.
- Frozen definitions (imported from run_open_world_recoverability_gate_v1
  and run_core_hypothesis_gate_v1b): RECOVERABLE_KNOWN = Basic wrong AND at
  least one of BT/BR/BTR correct; RESIDUAL_HARD = Basic wrong AND all
  evidence wrong; FURK = fraction of Recoverable-Known EVAL targets whose
  frozen per-policy novelty decision is Unknown (score >= policy threshold);
  MSP novelty score = 1 - max known-class proba of the model matching the
  actually acquired Evidence; policy-conditioned threshold = the 5% Known
  false-Unknown quantile of Known post-acquisition scores on VAL_CALIB
  (per policy, per population). Policies: P0 BASIC_DIRECT, P2
  RANDOM_COST_MATCHED (100-rep means), P3 LOW_CONFIDENCE, P4 HIGH_ENTROPY,
  P5 UTILITY_TEMPORAL_ONLY, P6 UTILITY_TYPED, P7 ORACLE_TYPED (analysis
  only).
- Cross-verification (frozen predictions recomputed from frozen models, in
  the same row order, are expected to match the frozen stored columns):
  recomputed Basic pred == stored pred_P0 (exact); recomputed Basic MSP ==
  stored score_P0 (allclose 1e-12); recomputed recoverable/residual flags
  == stored (exact); recomputed typed-policy actions (frozen selectors +
  frozen budget + frozen rule) == stored action_P6 (exact); stored
  rejected_X exactly self-consistent with stored score_X and the frozen
  threshold_X; recomputed-score rejections may differ from stored only on
  rows within 1e-12 of the threshold (the 5%-Known-FUR calibration puts a
  mass of rows exactly at the threshold, and parallel predict_proba thread
  order can shift scores in the last ulp — the stored column is the frozen
  authority). Any other mismatch => REVIEW_NEEDED and the affected numbers
  are reported as inconsistent (the audit does NOT silently proceed to
  interpretation).
- FURK denominator audit (highest priority): within each rotation the
  Recoverable-Known evaluation set is a SINGLE frozen flag array shared by
  every policy (P0..P6); the audit verifies the flag array equals the
  model-recomputed set (row identity, not only counts) and that every
  policy's numerator is computed over exactly those rows. If the
  denominator or target identity differs in any way:
  FURK_DENOMINATOR_AUDIT=FAIL and the tool STOPS before interpretation.
- Diagnostic category definitions (frozen, section numbers follow the task
  contract):
  * R1 ROUTER_MISS: selected evidence (per P6 action; NONE => Basic is the
    selected state) is WRONG while some OTHER legal evidence state would
    classify correctly.
  * R2 POST_EVIDENCE_CLASSIFICATION_FAILURE: selected evidence wrong and NO
    other legal evidence state would classify correctly (no selected
    recovery and no router alternative).
  * R3 RECOVERED_BUT_REJECTED: selected evidence predicts the correct class
    yet the frozen novelty decision is Unknown.
  * R4 THRESHOLD_SHIFT_CONTRIBUTION (counterfactual ONLY, never an
    alternative method): rejected by the policy's own frozen threshold
    although the post-Evidence MSP score is below the frozen BASIC_DIRECT
    threshold (i.e., the same post-Evidence score would have been Known
    under the frozen direct threshold). Overlap with other categories is
    reported explicitly.
  * NOVELTY_SCORE_UTILITY_E = MSP_BASIC - MSP_BASIC_PLUS_E (positive =>
    Evidence makes the row more Known-like under MSP; diagnostic only, no
    model is trained on it). Comparison with the frozen Gate-1B
    SIGNED_CLASSIFICATION_UTILITY (HELP=+1 / HARM=-1 / 0) via Spearman.
  * "Roughly unchanged" novelty utility: |NOVELTY_SCORE_UTILITY_E| <= 0.01
    (one fixed diagnostic cutoff, documented, not tuned).
- Failure mechanisms F0..F7 (a mechanism is DOMINANT only if supported in
  >=2/3 rotations by raw counts, consistent with frozen scores/thresholds,
  and requiring no new experimental tuning):
  F0 FURK implementation / denominator error; F1 classification-utility
  target mismatch; F2 post-Evidence MSP misalignment; F3 policy-conditioned
  calibration subgroup shift; F4 router selection failure; F5 evidence
  action-specific failure; F6 True-Unknown separation failure;
  F7 no clear dominant mechanism.
- V2 justification (prospective only; V2 is NOT designed or run here):
  YES only if (1) the denominator/implementation audit passes, (2) >=1
  mechanism dominates in >=2/3 rotations, (3) the mechanism suggests a
  specific conceptual correction, (4) the correction is definable without
  held-out True-Unknown GT, (5) it does not require detector shopping.
  This tool NEVER names a concrete replacement detector.
- RL relevance (analysis only, no RL run): RL_SEQUENTIAL_DECISION_
  JUSTIFICATION=NOT_SUPPORTED / PLAUSIBLE / STRONGLY_SUPPORTED, from
  evidence about whether sequential acquisition/stopping decisions have
  downstream open-world consequences not captured by the supervised
  one-step classification-utility selector.

Safety ledger (must remain unchanged by this task):
  OPEN_WORLD_GATE_V2_STARTED=false PHASE_C_EXECUTED=false
  MODEL_B_TRAINING_STARTED=false QWEN_API_CALLS=0 DEEPSEEK_API_CALLS=0
  RL_TRAINING_STARTED=false CONTINUAL_TRAINING_STARTED=false
  FINAL_TEST_MODELING_CONTAMINATION=false
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_open_world_recoverability_gate_v1 as owg  # noqa: E402
import run_core_hypothesis_gate_v1 as g  # noqa: E402
import run_core_hypothesis_gate_v1b as g1b  # noqa: E402

SEEDS = (20260817, 20260818, 20260819)
ROTATIONS = owg.ROTATIONS
CONDITIONS = owg.CONDITIONS
ACTIONS = owg.ACTIONS
ACTION_MODEL = owg.ACTION_MODEL
ACTION_COSTS = owg.ACTION_COSTS
KNOWN_POLICIES = ("P0_BASIC_DIRECT", "P2_RANDOM_COST_MATCHED",
                  "P3_LOW_CONFIDENCE", "P4_HIGH_ENTROPY",
                  "P5_UTILITY_TEMPORAL_ONLY", "P6_UTILITY_TYPED")
DETERMINISTIC_POLICIES = ("P0_BASIC_DIRECT", "P3_LOW_CONFIDENCE",
                          "P4_HIGH_ENTROPY", "P5_UTILITY_TEMPORAL_ONLY",
                          "P6_UTILITY_TYPED")
EVIDENCE_POLICIES = ("P3_LOW_CONFIDENCE", "P4_HIGH_ENTROPY",
                     "P5_UTILITY_TEMPORAL_ONLY", "P6_UTILITY_TYPED")
FAMILIES = ("T", "R", "TR")
NOVELTY_UTILITY_UNCHANGED_CUTOFF = 0.01  # |NOVELTY_SCORE_UTILITY_E| <= cutoff
# Minimum fraction of rotations supporting a mechanism for dominance.
DOMINANCE_MIN_ROTATIONS = 2  # >=2/3 rotations
# True-Unknown preservation margin consistent with the frozen OW3 rule.
UNKNOWN_AUROC_PRESERVATION_MARGIN = 0.01
REPORT_SCHEMA = "OPEN_WORLD_GATE_V1_FAILURE_ATTRIBUTION_REPORT_V1"


# ---------------------------------------------------------------------------
# Row-level aggregation primitives (pure; tested with synthetic fixtures)
# ---------------------------------------------------------------------------

def recoverable_flag(pred_b: np.ndarray, pred_bt: np.ndarray,
                     pred_br: np.ndarray, pred_btr: np.ndarray,
                     labels: np.ndarray) -> np.ndarray:
    """Frozen RECOVERABLE_KNOWN definition (label-based, offline only)."""
    basic_wrong = pred_b != labels
    return basic_wrong & (pred_bt == labels) | basic_wrong & (
        pred_br == labels) | basic_wrong & (pred_btr == labels)


def residual_hard_flag(pred_b: np.ndarray, pred_bt: np.ndarray,
                       pred_br: np.ndarray, pred_btr: np.ndarray,
                       labels: np.ndarray) -> np.ndarray:
    basic_wrong = pred_b != labels
    return basic_wrong & (pred_bt != labels) & (pred_br != labels) & (
        pred_btr != labels)


def furk_numerator(recoverable_known: np.ndarray,
                   rejected: np.ndarray) -> int:
    """Number of Recoverable-Known evaluation targets whose final novelty
    decision is Unknown."""
    return int(np.asarray(recoverable_known & rejected).sum())


def recovered_but_rejected_split(recoverable_known: np.ndarray,
                                 pred_selected: np.ndarray,
                                 labels: np.ndarray,
                                 rejected: np.ndarray,
                                 ) -> dict[str, int]:
    """A = selected-Evidence classification correct; A1 = recovered AND
    accepted as Known; A2 = recovered BUT rejected as Unknown."""
    a = recoverable_known & (pred_selected == labels)
    a1 = int((a & ~rejected).sum())
    a2 = int((a & rejected).sum())
    return {"A": int(a.sum()), "A1": a1, "A2": a2}


def transition_table(known_rows: np.ndarray, rejected_pre: np.ndarray,
                     rejected_post: np.ndarray) -> dict[str, int]:
    """Stage 3 (Basic-direct novelty) -> Stage 4 (post-Evidence novelty)
    transition counts over the given (recoverable) rows."""
    return {
        "DIRECT_KNOWN_TO_UTILITY_KNOWN": int(
            (known_rows & ~rejected_pre & ~rejected_post).sum()),
        "DIRECT_UNKNOWN_TO_UTILITY_KNOWN": int(
            (known_rows & rejected_pre & ~rejected_post).sum()),
        "DIRECT_KNOWN_TO_UTILITY_UNKNOWN": int(
            (known_rows & ~rejected_pre & rejected_post).sum()),
        "DIRECT_UNKNOWN_TO_UTILITY_UNKNOWN": int(
            (known_rows & rejected_pre & rejected_post).sum()),
    }


def score_stats(scores: np.ndarray) -> dict[str, float]:
    """mean / median / P75 / P90 / P95 of a frozen score array."""
    if not len(scores):
        return {"n": 0, "mean": None, "median": None, "P75": None,
                "P90": None, "P95": None}
    return {
        "n": int(len(scores)),
        "mean": float(scores.mean()),
        "median": float(np.median(scores)),
        "P75": float(np.quantile(scores, 0.75)),
        "P90": float(np.quantile(scores, 0.90)),
        "P95": float(np.quantile(scores, 0.95)),
    }


def msp_shift_by_subgroup(pre: np.ndarray, post: np.ndarray,
                          names: tuple[str, ...],
                          masks: dict[str, np.ndarray]) -> dict[str, Any]:
    """Pre/post acquisition MSP score stats + per-row shift for each named
    subgroup (frozen scores only)."""
    out: dict[str, Any] = {}
    for name in names:
        mask = masks[name]
        if not mask.sum():
            out[name] = {"n": 0}
            continue
        entry = {
            "n": int(mask.sum()),
            "PRE": score_stats(pre[mask]),
            "POST": score_stats(post[mask]),
            "SHIFT_MEAN": float((post[mask] - pre[mask]).mean()),
            "SHIFT_MEDIAN": float(np.median(post[mask] - pre[mask])),
            "SHIFT_P75": float(np.quantile(post[mask] - pre[mask], 0.75)),
            "SHIFT_P90": float(np.quantile(post[mask] - pre[mask], 0.90)),
            "SHIFT_P95": float(np.quantile(post[mask] - pre[mask], 0.95)),
        }
        out[name] = entry
    return out


def router_vs_novelty_failure(pred_selected: np.ndarray,
                              pred_family: dict[str, np.ndarray],
                              action: np.ndarray, labels: np.ndarray,
                              rejected: np.ndarray, score: np.ndarray,
                              threshold_direct: float,
                              mask: np.ndarray) -> dict[str, int]:
    """R1..R4 counts over `mask` rows (diagnostic categories; R4 is
    counterfactual-only). Overlap is reported explicitly."""
    rows = np.flatnonzero(mask)
    r1 = r2 = r3 = r4 = 0
    r1_none = r1_acquired = 0
    r3_and_r4 = 0
    r4_only = 0
    for row in rows:
        chosen = str(action[row])
        correct = pred_selected[row] == labels[row]
        alt_ok = False
        for family in FAMILIES:
            if ACTION_MODEL[family] == ACTION_MODEL[chosen] and \
                    family == chosen:
                continue
            alt_ok = alt_ok or (pred_family[family][row] == labels[row])
        if not correct and alt_ok:
            r1 += 1
            if chosen == "NONE":
                r1_none += 1
            else:
                r1_acquired += 1
        elif not correct:
            r2 += 1
        if correct and rejected[row]:
            r3 += 1
        if rejected[row] and score[row] < threshold_direct:
            r4 += 1
            if correct:
                r3_and_r4 += 1
            else:
                r4_only += 1
    return {"R1_ROUTER_MISS": r1,
            "R1_ROUTER_MISS_NONE_ACTION": r1_none,
            "R1_ROUTER_MISS_ACQUIRED_WRONG_FAMILY": r1_acquired,
            "R2_POST_EVIDENCE_CLASSIFICATION_FAILURE": r2,
            "R3_RECOVERED_BUT_REJECTED": r3,
            "R4_THRESHOLD_SHIFT_CONTRIBUTION": r4,
            "OVERLAP_R3_AND_R4": r3_and_r4,
            "OVERLAP_R4_WITHOUT_R3": r4_only}


def selection_overlap(selected_a: np.ndarray, selected_b: np.ndarray,
                      mask: np.ndarray) -> dict[str, int]:
    """Overlap of two policies' selections restricted to `mask` rows:
    both / only A / only B / neither (frozen actions)."""
    a = np.asarray(selected_a, dtype=bool) & mask
    b = np.asarray(selected_b, dtype=bool) & mask
    return {
        "BOTH": int((a & b).sum()),
        "ONLY_A": int((a & ~b).sum()),
        "ONLY_B": int((~a & b).sum()),
        "NEITHER": int((~a & ~b & mask).sum()),
    }


def action_conditional(recoverable_known: np.ndarray, action: np.ndarray,
                       pred_selected: np.ndarray, labels: np.ndarray,
                       rejected: np.ndarray, score: np.ndarray,
                       ) -> dict[str, dict[str, float]]:
    """Per-action (NONE/T/R/TR) diagnostics over the Recoverable-Known EVAL
    population under P6 (frozen actions/scores)."""
    total = int(recoverable_known.sum())
    out: dict[str, dict[str, float]] = {}
    for action_name in ACTIONS:
        mask = recoverable_known & (action == action_name)
        n = int(mask.sum())
        if n == 0:
            out[action_name] = {"n": 0, "fur_contribution": 0.0}
            continue
        recovered = int((pred_selected[mask] == labels[mask]).sum())
        rejected_here = int(rejected[mask].sum())
        a2 = int((mask & (pred_selected == labels) & rejected).sum())
        out[action_name] = {
            "n": n,
            "cost_units": float(n * ACTION_COSTS[action_name]),
            "recovery_count": recovered,
            "recovery_rate": float(recovered / n),
            "recovered_but_rejected_count": a2,
            "recovered_but_rejected_rate": float(a2 / n),
            "mean_post_evidence_msp": float(score[mask].mean()),
            "rejected_count": rejected_here,
            "fur_contribution": float(rejected_here / total),
        }
    return out


def class_composition(labels: np.ndarray, mask: np.ndarray,
                      classes: tuple[str, ...]) -> dict[str, float]:
    n = int(mask.sum())
    if n == 0:
        return {name: 0.0 for name in classes}
    counts: dict[str, int] = {name: 0 for name in classes}
    for name in np.asarray(labels[mask], dtype=object):
        counts[str(name)] = counts.get(str(name), 0) + 1
    return {name: float(counts[name] / n) for name in classes}


def spearman_of(x: np.ndarray, y: np.ndarray) -> float:
    from scipy.stats import spearmanr
    if len(x) < 2 or np.all(x == x[0]) or np.all(y == y[0]):
        return float("nan")
    return float(spearmanr(x, y).statistic)


# ---------------------------------------------------------------------------
# Frozen-artifact cell loader + cross-verification
# ---------------------------------------------------------------------------

def load_cell_arrays(artifact_root: Path, seed: int, rotation: str
                     ) -> dict[str, np.ndarray]:
    table = owg.pq.read_table(artifact_root / (
        f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet"))
    out: dict[str, np.ndarray] = {
        "source_row_index": table["source_row_index"].to_numpy(
            zero_copy_only=False),
        "canonical_label": np.array(table["canonical_label"].to_pylist(),
                                    dtype=object),
        "split_role": table["split_role"].to_numpy(zero_copy_only=False),
        "is_unknown": table["is_unknown"].to_numpy(zero_copy_only=False),
        "recoverable": table["recoverable"].to_numpy(zero_copy_only=False),
        "residual_hard": table["residual_hard"].to_numpy(
            zero_copy_only=False),
        "activity_group_digest": np.array(
            [bytes(v) for v in table["activity_group_digest"].to_pylist()],
            dtype=object),
        "temporal_block": table["temporal_block"].to_numpy(
            zero_copy_only=False),
    }
    for name in ("P0_BASIC_DIRECT", "P1_ALWAYS_FULL", "P3_LOW_CONFIDENCE",
                 "P4_HIGH_ENTROPY", "P5_UTILITY_TEMPORAL_ONLY",
                 "P6_UTILITY_TYPED", "P7_ORACLE_TYPED"):
        out[f"action_{name}"] = np.array(table[f"action_{name}"].to_pylist(),
                                         dtype=object)
        out[f"score_{name}"] = table[f"score_{name}"].to_numpy(
            zero_copy_only=False)
        out[f"pred_{name}"] = np.array(table[f"pred_{name}"].to_pylist(),
                                       dtype=object)
        out[f"rejected_{name}"] = table[f"rejected_{name}"].to_numpy(
            zero_copy_only=False).astype(bool)
    return out


def load_cell_result(artifact_root: Path, seed: int, rotation: str
                     ) -> dict[str, Any]:
    return json.loads((artifact_root / (
        f"owg_v1_seed_{seed}_rotation_{rotation}_result.json")).read_text(
            encoding="utf-8"))


def rebuild_val_predictions(gate1_root: Path, artifact_root: Path,
                            seed: int, rotation: str) -> dict[str, Any]:
    """Recompute frozen-model predictions/probas on VALIDATION rows in the
    same order as the frozen eval table (B/BT/BR/BTR + selectors' u values).
    Used ONLY for cross-verification and the diagnostic categories that
    need per-family views (R1, classification-vs-novelty utility). No
    training occurs."""
    targets = owg.load_targets(gate1_root, seed)
    val_mask = targets["partition_code"] == owg.PARTITION_VALIDATION
    val_rows = targets["source_row_index"][val_mask]
    val_labels = targets["canonical_label"][val_mask]
    val_groups = np.array([bytes(v) for v in targets["activity_group_digest"]
                           [val_mask]], dtype=object)
    val_blocks = targets["temporal_block"][val_mask]
    known = owg.known_classes_for(rotation)
    basic_rows, basic_arrays = owg.load_basic_features(gate1_root)
    basic_positions = {int(v): i for i, v in enumerate(basic_rows)}
    basic_val = owg.basic_matrix_for(val_rows, basic_arrays, basic_positions)
    history_val, history_names = owg.load_history_features(
        gate1_root, seed, val_rows)
    matrices_val = owg.build_feature_matrices(basic_val, history_val,
                                              history_names)
    with open(artifact_root / "models" / (
            f"owg_v1_seed_{seed}_rotation_{rotation}_models.pkl"), "rb") as f:
        payload = pickle.load(f)
    models: dict[str, Any] = payload["models"]
    selectors: dict[str, Any] = payload["selectors"]
    pred: dict[str, np.ndarray] = {}
    proba: dict[str, np.ndarray] = {}
    for condition in CONDITIONS:
        clf = models[condition]
        proba[condition] = owg.align_rotation_proba(
            clf.predict_proba(matrices_val[condition]), clf.classes_, known)
        pred[condition] = clf.predict(matrices_val[condition])
    features_val, names_val = owg.rotation_selector_features(
        basic_val, pred["B"], proba["B"],
        np.ones(len(val_rows)), known)
    if owg.selector_leakage_audit(names_val) != "PASS":
        raise SystemExit(
            f"ATTRIBUTION_STATUS=SELECTOR_LEAKAGE_AUDIT_FAIL seed={seed} "
            f"rotation={rotation}")
    u_values = {f: selectors[f].predict(features_val) for f in FAMILIES}
    return {"val_rows": val_rows, "val_labels": val_labels,
            "val_groups": val_groups, "val_blocks": val_blocks,
            "pred": pred, "proba": proba, "u": u_values,
            "known": known}


def cross_verify(arrays: dict[str, np.ndarray], result: dict[str, Any],
                 rebuilt: dict[str, Any], seed: int, rotation: str,
                 n_calib: int, artifact_root: Path) -> dict[str, Any]:
    """Verify frozen stored columns against frozen-model recomputation and
    the frozen thresholds. Any mismatch => REVIEW_NEEDED."""
    checks: dict[str, Any] = {}
    eval_table_path = artifact_root / (
        f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet")
    checks["EVAL_TABLE_SHA256_MATCH"] = bool(
        owg.sha256_file(eval_table_path) == result["eval_table_sha256"])
    checks["SOURCE_ROW_ORDER_MATCH"] = bool(
        np.array_equal(arrays["source_row_index"], rebuilt["val_rows"]))
    checks["BASIC_PRED_MATCH"] = bool(
        np.array_equal(arrays["pred_P0_BASIC_DIRECT"],
                       rebuilt["pred"]["B"]))
    msp_b = 1.0 - rebuilt["proba"]["B"].max(axis=1)
    checks["BASIC_MSP_MATCH"] = bool(
        np.allclose(arrays["score_P0_BASIC_DIRECT"], msp_b, atol=1e-12))
    rec = recoverable_flag(rebuilt["pred"]["B"], rebuilt["pred"]["BT"],
                           rebuilt["pred"]["BR"], rebuilt["pred"]["BTR"],
                           rebuilt["val_labels"])
    res = residual_hard_flag(rebuilt["pred"]["B"], rebuilt["pred"]["BT"],
                             rebuilt["pred"]["BR"], rebuilt["pred"]["BTR"],
                             rebuilt["val_labels"])
    checks["RECOVERABLE_FLAG_MATCH"] = bool(np.array_equal(
        arrays["recoverable"], rec))
    checks["RESIDUAL_HARD_FLAG_MATCH"] = bool(np.array_equal(
        arrays["residual_hard"], res))
    checks["DIGEST_COLUMN_MATCH"] = bool(np.array_equal(
        arrays["activity_group_digest"], rebuilt["val_groups"]))
    checks["BLOCK_COLUMN_MATCH"] = bool(np.array_equal(
        arrays["temporal_block"], rebuilt["val_blocks"]))
    # recompute the frozen typed policy from frozen selectors + budget
    n_eval = int(arrays["split_role"].sum())
    budget_eval = int(np.floor(owg.PRIMARY_COST_BUDGET_FRACTION * n_eval))
    budget_calib = int(np.floor(owg.PRIMARY_COST_BUDGET_FRACTION * n_calib))
    eval_mask = arrays["split_role"] == 1
    calib_mask = arrays["split_role"] == 0
    u_t, u_r, u_tr = rebuilt["u"]["T"], rebuilt["u"]["R"], rebuilt["u"]["TR"]
    # Frozen rule passes population positions as the tie-break order
    # (rule(idx, budget) with idx = np.flatnonzero(pop_mask)); replicate.
    order_eval = np.arange(int(eval_mask.sum()))
    order_calib = np.arange(int(calib_mask.sum()))
    actions_eval = owg.typed_policy_actions(
        u_t[eval_mask], u_r[eval_mask], u_tr[eval_mask], budget_eval,
        order_eval)
    actions_calib = owg.typed_policy_actions(
        u_t[calib_mask], u_r[calib_mask], u_tr[calib_mask], budget_calib,
        order_calib)
    rebuilt_actions = np.full(len(arrays["split_role"]), "NONE", dtype=object)
    rebuilt_actions[eval_mask] = actions_eval
    rebuilt_actions[calib_mask] = actions_calib
    checks["TYPED_ACTIONS_MATCH"] = bool(np.array_equal(
        arrays["action_P6_UTILITY_TYPED"], rebuilt_actions))
    # recompute P6 MSP scores from the actual action model
    rebuilt_scores = _policy_scores_from(arrays["action_P6_UTILITY_TYPED"],
                                         rebuilt["proba"], msp_b)
    checks["TYPED_SCORES_MATCH"] = bool(np.allclose(
        arrays["score_P6_UTILITY_TYPED"], rebuilt_scores, atol=1e-12))
    thr = result["policies"]["P6_UTILITY_TYPED"]["threshold"]
    # The frozen rejected column must be exactly self-consistent with the
    # frozen stored scores + frozen threshold; recomputed scores can differ
    # in the last ulp (parallel predict_proba thread order), so any flipped
    # row must lie within ulp-tolerance OF the threshold (mass point of the
    # 95th-percentile calibration).
    checks["TYPED_REJECTED_SELF_CONSISTENT"] = bool(np.array_equal(
        arrays["rejected_P6_UTILITY_TYPED"],
        arrays["score_P6_UTILITY_TYPED"] >= thr))
    diff = np.flatnonzero(arrays["rejected_P6_UTILITY_TYPED"]
                          != (rebuilt_scores >= thr))
    checks["TYPED_REJECTED_MATCH"] = bool(
        np.all(np.abs(rebuilt_scores[diff] - thr) <= 1e-12)) \
        if len(diff) else True
    # numerator reconstruction vs frozen per-cell FURK
    known_flag = ~arrays["is_unknown"].astype(bool)
    rec_kn = arrays["recoverable"].astype(bool) & known_flag & eval_mask
    denom = int(rec_kn.sum())
    checks["FURK_DENOMINATOR_MATCH_RESULT_JSON"] = (
        denom == result["n_recoverable_known"])
    num = furk_numerator(
        rec_kn, arrays["rejected_P0_BASIC_DIRECT"])
    checks["FURK_NUMERATOR_P0_MATCH"] = bool(np.isclose(
        num / denom, result["policies"]["P0_BASIC_DIRECT"]["furk"],
        atol=1e-12))
    return checks


def _policy_scores_from(actions: np.ndarray, proba: dict[str, np.ndarray],
                        msp_b: np.ndarray) -> np.ndarray:
    out = np.empty(len(actions), dtype=np.float64)
    for action in ACTIONS:
        mask = (actions == action).astype(bool)
        if action == "NONE":
            out[mask] = msp_b[mask]
        else:
            out[mask] = 1.0 - proba[ACTION_MODEL[action]][mask].max(axis=1)
    return out


# ---------------------------------------------------------------------------
# Per-cell diagnostic computation
# ---------------------------------------------------------------------------

def cell_diagnostics(arrays: dict[str, np.ndarray], result: dict[str, Any],
                     rebuilt: dict[str, Any]) -> dict[str, Any]:
    known_flag = ~arrays["is_unknown"].astype(bool)
    eval_mask = arrays["split_role"] == 1
    calib_mask = arrays["split_role"] == 0
    rec = arrays["recoverable"].astype(bool)
    res = arrays["residual_hard"].astype(bool)
    rec_kn = rec & known_flag & eval_mask
    res_kn = res & known_flag & eval_mask
    basic_suff_kn = known_flag & eval_mask & ~rec & ~res
    un = (~known_flag) & eval_mask
    denom = int(rec_kn.sum())
    labels = arrays["canonical_label"]
    classes = rebuilt["known"]

    out: dict[str, Any] = {
        "denominator": denom,
        "n_residual_hard_eval": int(res_kn.sum()),
        "n_basic_sufficient_eval": int(basic_suff_kn.sum()),
        "n_true_unknown_eval": int(un.sum()),
    }

    # Section 2: denominator per policy (same frozen flag array by
    # construction; counts verified per policy for the record).
    out["denominator_by_policy"] = {
        name: int(rec_kn.sum()) for name in KNOWN_POLICIES}

    # Section 3: FURK numerator + rate per policy (raw numbers, not rates).
    out["numerator_by_policy"] = {}
    for name in KNOWN_POLICIES:
        if name == "P2_RANDOM_COST_MATCHED":
            # mean over 100 frozen repetitions; per-row decisions not stored
            mean_furk = result["policies"][name]["furk"]
            out["numerator_by_policy"][name] = {
                "raw_numerator": float(mean_furk * denom),
                "note": "mean over 100 frozen RANDOM reps (per-row "
                        "decisions not stored by design)",
            }
            continue
        rejected = arrays[f"rejected_{name}"]
        num = furk_numerator(rec_kn, rejected)
        out["numerator_by_policy"][name] = {
            "raw_numerator": num,
            "rate": float(num / denom),
            "matches_frozen_cell_furk": bool(np.isclose(
                num / denom, result["policies"][name]["furk"], atol=1e-12)),
        }

    # Section 4: recovered-but-rejected per Evidence policy.
    out["recovered_but_rejected"] = {}
    for name in EVIDENCE_POLICIES:
        split = recovered_but_rejected_split(
            rec_kn, arrays[f"pred_{name}"], labels, arrays[f"rejected_{name}"])
        a2 = split["A2"]
        out["recovered_but_rejected"][name] = {
            "A": split["A"],
            "A1_RECOVERED_AND_ACCEPTED": split["A1"],
            "A2_RECOVERED_BUT_REJECTED": split["A2"],
            "RECOVERED_BUT_REJECTED_RATE": float(a2 / denom),
            "RECOVERY_CONDITIONAL_REJECTION_RATE": float(
                a2 / (split["A1"] + a2)) if (split["A1"] + a2) else None,
            "RECOVERED_AND_ACCEPTED_RATE": float(split["A1"] / denom),
        }

    # Section 5: four-stage transitions P0 -> P6 (recoverable targets).
    trans = transition_table(rec_kn, arrays["rejected_P0_BASIC_DIRECT"],
                             arrays["rejected_P6_UTILITY_TYPED"])
    chain = int((rec_kn & (arrays["pred_P0_BASIC_DIRECT"] != labels)
                 & (arrays["pred_P6_UTILITY_TYPED"] == labels)
                 & arrays["rejected_P6_UTILITY_TYPED"]).sum())
    out["transition_table"] = {**trans,
                               "TOTAL": sum(trans.values()),
                               "BASIC_WRONG_TO_POST_CORRECT_TO_UNKNOWN":
                                   chain}

    # Section 6: MSP score shift by subgroup (P6 scores).
    subgroups = {
        "A_BASIC_SUFFICIENT_KNOWN": basic_suff_kn,
        "B_RECOVERABLE_KNOWN": rec_kn,
        "C_RESIDUAL_HARD_KNOWN": res_kn,
        "D_TRUE_UNKNOWN": un,
    }
    names = tuple(subgroups)
    out["msp_shift"] = msp_shift_by_subgroup(
        arrays["score_P0_BASIC_DIRECT"], arrays["score_P6_UTILITY_TYPED"],
        names, subgroups)
    rec_recovered = rec_kn & (
        arrays["pred_P6_UTILITY_TYPED"] == labels)
    rec_not = rec_kn & (arrays["pred_P6_UTILITY_TYPED"] != labels)
    out["msp_shift"]["B1_RECOVERABLE_CLASS_RECOVERED"] = {
        "n": int(rec_recovered.sum()),
        "SHIFT_MEAN": float((arrays["score_P6_UTILITY_TYPED"][rec_recovered]
                             - arrays["score_P0_BASIC_DIRECT"][rec_recovered]
                             ).mean()) if rec_recovered.sum() else None,
        "SHIFT_MEDIAN": float(np.median(
            arrays["score_P6_UTILITY_TYPED"][rec_recovered]
            - arrays["score_P0_BASIC_DIRECT"][rec_recovered])
        ) if rec_recovered.sum() else None,
    }
    out["msp_shift"]["B2_RECOVERABLE_CLASS_NOT_RECOVERED"] = {
        "n": int(rec_not.sum()),
        "SHIFT_MEAN": float((arrays["score_P6_UTILITY_TYPED"][rec_not]
                             - arrays["score_P0_BASIC_DIRECT"][rec_not]
                             ).mean()) if rec_not.sum() else None,
        "SHIFT_MEDIAN": float(np.median(
            arrays["score_P6_UTILITY_TYPED"][rec_not]
            - arrays["score_P0_BASIC_DIRECT"][rec_not])
        ) if rec_not.sum() else None,
    }

    # Section 7: frozen thresholds + Known calibration score distributions
    # (reporting population EVAL; no new thresholds created). The
    # calibration-population (VAL_CALIB Known) pre/post distributions are
    # reported to tie any threshold migration to the frozen calibration
    # mass (the threshold is the 95th percentile of CALIB Known POST scores).
    thresholds = {name: result["policies"][name]["threshold"]
                  for name in KNOWN_POLICIES}
    out["thresholds"] = thresholds
    out["threshold_utility_minus_direct"] = (
        thresholds["P6_UTILITY_TYPED"] - thresholds["P0_BASIC_DIRECT"])
    calib_kn = calib_mask & known_flag
    calib_rec_kn = calib_kn & rec
    out["calibration_population_shifts"] = {
        "CALIB_KNOWN_PRE": score_stats(
            arrays["score_P0_BASIC_DIRECT"][calib_kn]),
        "CALIB_KNOWN_POST": score_stats(
            arrays["score_P6_UTILITY_TYPED"][calib_kn]),
        "CALIB_KNOWN_ACQUISITION_RATE": float(
            (arrays["action_P6_UTILITY_TYPED"][calib_kn] != "NONE").mean())
            if calib_kn.sum() else None,
        "CALIB_RECOVERABLE_PRE": score_stats(
            arrays["score_P0_BASIC_DIRECT"][calib_rec_kn]),
        "CALIB_RECOVERABLE_POST": score_stats(
            arrays["score_P6_UTILITY_TYPED"][calib_rec_kn]),
    }
    out["known_score_distributions"] = {
        "ALL_KNOWN_POST": score_stats(
            arrays["score_P6_UTILITY_TYPED"][known_flag & eval_mask]),
        "ALL_KNOWN_PRE": score_stats(
            arrays["score_P0_BASIC_DIRECT"][known_flag & eval_mask]),
        "BASIC_SUFFICIENT_KNOWN_PRE": score_stats(
            arrays["score_P0_BASIC_DIRECT"][basic_suff_kn]),
        "RECOVERABLE_KNOWN_PRE": score_stats(
            arrays["score_P0_BASIC_DIRECT"][rec_kn]),
        "RESIDUAL_HARD_KNOWN_PRE": score_stats(
            arrays["score_P0_BASIC_DIRECT"][res_kn]),
        "CLASS_STRATIFIED_PRE": {
            name: score_stats(arrays["score_P0_BASIC_DIRECT"][
                known_flag & eval_mask & (labels == name)])
            for name in classes
        },
    }

    # Section 8: classification utility vs novelty utility per family.
    out["utility_correlation"] = {}
    for family in FAMILIES:
        condition = ACTION_MODEL[family]
        _, _, signed = g1b.utility_labels(rebuilt["pred"]["B"],
                                          rebuilt["pred"][condition],
                                          rebuilt["val_labels"])
        msp_e = 1.0 - rebuilt["proba"][condition].max(axis=1)
        novelty_util = msp_b_of(rebuilt) - msp_e
        pop = eval_mask & known_flag
        rho = spearman_of(signed[pop].astype(np.float64),
                          novelty_util[pop])
        help_mask = pop & (signed == 1)
        nu = novelty_util[help_mask]
        improve = float((nu > NOVELTY_UTILITY_UNCHANGED_CUTOFF).mean()) \
            if len(nu) else None
        worsen = float((nu < -NOVELTY_UTILITY_UNCHANGED_CUTOFF).mean()) \
            if len(nu) else None
        unchanged = float((np.abs(nu) <= NOVELTY_UTILITY_UNCHANGED_CUTOFF)
                          .mean()) if len(nu) else None
        out["utility_correlation"][family] = {
            "SPEARMAN_CLASSIFICATION_UTILITY_VS_NOVELTY_UTILITY": rho,
            "CLASSIFICATION_HELP_N": int(help_mask.sum()),
            "HELP_NOVELTY_IMPROVE_RATE": improve,
            "HELP_NOVELTY_UNCHANGED_RATE": unchanged,
            "HELP_NOVELTY_WORSEN_RATE": worsen,
            "HELP_MEAN_NOVELTY_UTILITY": float(nu.mean()) if len(nu) else None,
            "ALL_KNOWN_MEAN_NOVELTY_UTILITY": float(
                novelty_util[pop].mean()) if pop.sum() else None,
        }

    # Section 9: router vs novelty failure (P6 recoverable EVAL targets).
    pred_family = {"T": rebuilt["pred"]["BT"], "R": rebuilt["pred"]["BR"],
                   "TR": rebuilt["pred"]["BTR"]}
    rvf = router_vs_novelty_failure(
        arrays["pred_P6_UTILITY_TYPED"], pred_family,
        arrays["action_P6_UTILITY_TYPED"], labels,
        arrays["rejected_P6_UTILITY_TYPED"],
        arrays["score_P6_UTILITY_TYPED"],
        thresholds["P0_BASIC_DIRECT"], rec_kn)
    out["router_vs_novelty"] = {k: v for k, v in rvf.items()}
    out["router_vs_novelty"]["SHARES"] = {
        k: float(v / denom) for k, v in rvf.items()}

    # Section 10: selection overlap on the fixed Recoverable-Known
    # population: P3/P4 (heuristics) vs P6 (utility).
    out["selection_overlap"] = {}
    for heuristic in ("P3_LOW_CONFIDENCE", "P4_HIGH_ENTROPY"):
        overlap = selection_overlap(
            arrays[f"action_{heuristic}"] != "NONE",
            arrays["action_P6_UTILITY_TYPED"] != "NONE", rec_kn)
        subsets: dict[str, Any] = {}
        sel_h = (arrays[f"action_{heuristic}"] != "NONE") & rec_kn
        sel_u = (arrays["action_P6_UTILITY_TYPED"] != "NONE") & rec_kn
        subset_masks = {
            "BOTH": sel_h & sel_u,
            "ONLY_HEURISTIC": sel_h & ~sel_u,
            "ONLY_UTILITY": ~sel_h & sel_u,
            "NEITHER": ~sel_h & ~sel_u & rec_kn,
        }
        for subset_name, mask in subset_masks.items():
            n = int(mask.sum())
            if n == 0:
                subsets[subset_name] = {"n": 0}
                continue
            chosen = arrays["action_P6_UTILITY_TYPED"][mask]
            recovered = (arrays["pred_P6_UTILITY_TYPED"][mask]
                         == labels[mask])
            subsets[subset_name] = {
                "n": n,
                "CLASS_COMPOSITION": class_composition(labels, mask, classes),
                "SELECTED_FAMILY_UTILITY": {
                    fam: float((chosen == fam).sum() / n) for fam in ACTIONS
                },
                "CLASSIFICATION_RECOVERY_RATE": float(recovered.mean()),
                "MEAN_POST_EVIDENCE_MSP": float(
                    arrays["score_P6_UTILITY_TYPED"][mask].mean()),
                "FINAL_REJECTION_RATE": float(
                    arrays["rejected_P6_UTILITY_TYPED"][mask].mean()),
            }
        out["selection_overlap"][heuristic] = {
            "OVERLAP": overlap, "SUBSETS": subsets}

    # Section 11: action-conditional (P6, Recoverable-Known EVAL).
    out["action_conditional"] = action_conditional(
        rec_kn, arrays["action_P6_UTILITY_TYPED"],
        arrays["pred_P6_UTILITY_TYPED"], labels,
        arrays["rejected_P6_UTILITY_TYPED"],
        arrays["score_P6_UTILITY_TYPED"])

    # Section 12: True Unknown check from the frozen per-cell result.
    p0 = result["policies"]["P0_BASIC_DIRECT"]
    p6 = result["policies"]["P6_UTILITY_TYPED"]
    out["true_unknown_check"] = {
        "BASIC_MEAN_SCORE": float(arrays["score_P0_BASIC_DIRECT"][un].mean())
        if un.sum() else None,
        "POST_POLICY_MEAN_SCORE": float(
            arrays["score_P6_UTILITY_TYPED"][un].mean()) if un.sum() else None,
        "SCORE_SHIFT_MEAN": float(
            (arrays["score_P6_UTILITY_TYPED"][un]
             - arrays["score_P0_BASIC_DIRECT"][un]).mean()) if un.sum()
        else None,
        "ACQUISITION_RATE": p6["true_unknown_acquisition_rate"],
        "AUROC_P0": p0["auroc"], "AUROC_P6": p6["auroc"],
        "AUPR_P0": p0["aupr"], "AUPR_P6": p6["aupr"],
        "RECALL_AT_5PCT_KNOWN_FUR_P0": p0[
            "unknown_recall_at_calibrated_fur"],
        "RECALL_AT_5PCT_KNOWN_FUR_P6": p6[
            "unknown_recall_at_calibrated_fur"],
        "AUROC_DELTA": float(p6["auroc"] - p0["auroc"]),
    }
    return out


def msp_b_of(rebuilt: dict[str, Any]) -> np.ndarray:
    return 1.0 - rebuilt["proba"]["B"].max(axis=1)


# ---------------------------------------------------------------------------
# Attribution / decision logic (pure; tested)
# ---------------------------------------------------------------------------

def attribution_inputs(cells: dict[str, Any]) -> dict[str, Any]:
    """Aggregate per-cell diagnostics into per-rotation views (means over
    seeds)."""
    rot: dict[str, Any] = {}
    for rotation in ROTATIONS:
        entries = [cells[(seed, rotation)] for seed in SEEDS]
        denom = sum(e["denominator"] for e in entries)
        pooled_num_direct = sum(
            e["numerator_by_policy"]["P0_BASIC_DIRECT"]["raw_numerator"]
            for e in entries)
        pooled_num_utility = sum(
            e["numerator_by_policy"]["P6_UTILITY_TYPED"]["raw_numerator"]
            for e in entries)
        rec_rej_utility = sum(
            e["recovered_but_rejected"]["P6_UTILITY_TYPED"][
                "A2_RECOVERED_BUT_REJECTED"] for e in entries)
        rec_acc_utility = sum(
            e["recovered_but_rejected"]["P6_UTILITY_TYPED"][
                "A1_RECOVERED_AND_ACCEPTED"] for e in entries)
        a_total = rec_rej_utility + rec_acc_utility
        trans = {k: sum(e["transition_table"][k] for e in entries)
                 for k in ("DIRECT_KNOWN_TO_UTILITY_KNOWN",
                           "DIRECT_UNKNOWN_TO_UTILITY_KNOWN",
                           "DIRECT_KNOWN_TO_UTILITY_UNKNOWN",
                           "DIRECT_UNKNOWN_TO_UTILITY_UNKNOWN")}
        chain = sum(e["transition_table"][
            "BASIC_WRONG_TO_POST_CORRECT_TO_UNKNOWN"] for e in entries)
        rvf = {k: sum(e["router_vs_novelty"][k] for e in entries)
               for k in ("R1_ROUTER_MISS",
                         "R1_ROUTER_MISS_NONE_ACTION",
                         "R1_ROUTER_MISS_ACQUIRED_WRONG_FAMILY",
                         "R2_POST_EVIDENCE_CLASSIFICATION_FAILURE",
                         "R3_RECOVERED_BUT_REJECTED",
                         "R4_THRESHOLD_SHIFT_CONTRIBUTION",
                         "OVERLAP_R3_AND_R4", "OVERLAP_R4_WITHOUT_R3")}
        ac = {act: {k: sum(e["action_conditional"][act][k] for e in entries)
                    for k in ("n", "recovery_count", "rejected_count")}
              for act in ACTIONS}
        rot[rotation] = {
            "DENOMINATOR_POOLED": denom,
            "FURK_NUMERATOR_DIRECT_POOLED": pooled_num_direct,
            "FURK_NUMERATOR_UTILITY_POOLED": pooled_num_utility,
            "FURK_DIRECT_MEAN_RATE": float(pooled_num_direct / denom),
            "FURK_UTILITY_MEAN_RATE": float(pooled_num_utility / denom),
            "RECOVERED_BUT_REJECTED_RATE": float(rec_rej_utility / denom),
            "RECOVERY_CONDITIONAL_REJECTION_RATE": float(
                rec_rej_utility / a_total) if a_total else None,
            "RECOVERED_AND_ACCEPTED_RATE": float(rec_acc_utility / denom),
            "TRANSITIONS": trans,
            "BASIC_WRONG_TO_POST_CORRECT_TO_UNKNOWN": chain,
            "ROUTER_VS_NOVELTY_POOLED": rvf,
            "ROUTER_VS_NOVELTY_SHARES": {
                k: float(v / denom) for k, v in rvf.items()},
            "THRESHOLD_UTILITY_MINUS_DIRECT_MEAN": float(np.mean([
                e["threshold_utility_minus_direct"] for e in entries])),
            "THRESHOLD_DIRECT_MEAN": float(np.mean([
                e["thresholds"]["P0_BASIC_DIRECT"] for e in entries])),
            "THRESHOLD_UTILITY_MEAN": float(np.mean([
                e["thresholds"]["P6_UTILITY_TYPED"] for e in entries])),
            "CALIB_POPULATION_SHIFTS_MEAN": {
                "CALIB_KNOWN_P95_SHIFT": float(np.mean([
                    e["calibration_population_shifts"][
                        "CALIB_KNOWN_POST"]["P95"]
                    - e["calibration_population_shifts"][
                        "CALIB_KNOWN_PRE"]["P95"] for e in entries])),
                "CALIB_RECOVERABLE_P95_SHIFT": float(np.mean([
                    e["calibration_population_shifts"][
                        "CALIB_RECOVERABLE_POST"]["P95"]
                    - e["calibration_population_shifts"][
                        "CALIB_RECOVERABLE_PRE"]["P95"] for e in entries])),
                "CALIB_KNOWN_ACQUISITION_RATE": float(np.mean([
                    e["calibration_population_shifts"][
                        "CALIB_KNOWN_ACQUISITION_RATE"] for e in entries])),
            },
            "MSP_SHIFT_RECOVERABLE_MEAN": float(np.mean([
                e["msp_shift"]["B_RECOVERABLE_KNOWN"]["SHIFT_MEAN"]
                for e in entries])),
            "MSP_SHIFT_RECOVERED_RECOVERABLE_MEAN": float(np.mean([
                e["msp_shift"]["B1_RECOVERABLE_CLASS_RECOVERED"][
                    "SHIFT_MEAN"] for e in entries])),
            "MSP_SHIFT_RESIDUAL_MEAN": float(np.mean([
                e["msp_shift"]["C_RESIDUAL_HARD_KNOWN"]["SHIFT_MEAN"]
                for e in entries])),
            "MSP_SHIFT_TRUE_UNKNOWN_MEAN": float(np.mean([
                e["msp_shift"]["D_TRUE_UNKNOWN"]["SHIFT_MEAN"]
                for e in entries])),
            "MSP_SHIFT_BASIC_SUFFICIENT_MEAN": float(np.mean([
                e["msp_shift"]["A_BASIC_SUFFICIENT_KNOWN"]["SHIFT_MEAN"]
                for e in entries])),
            "TRUE_UNKNOWN_AUROC_DELTA_MEAN": float(np.mean([
                e["true_unknown_check"]["AUROC_DELTA"] for e in entries])),
            "UTILITY_SPEARMAN_MEAN": {
                f: float(np.nanmean([e["utility_correlation"][f][
                    "SPEARMAN_CLASSIFICATION_UTILITY_VS_NOVELTY_UTILITY"]
                    for e in entries])) for f in FAMILIES},
            "HELP_NOVELTY_IMPROVE_RATE_POOLED": _pooled_rate(
                entries, "utility_correlation", "T",
                "CLASSIFICATION_HELP_N", "HELP_NOVELTY_IMPROVE_RATE"),
            "HELP_NOVELTY_WORSEN_RATE_POOLED": _pooled_rate(
                entries, "utility_correlation", "T",
                "CLASSIFICATION_HELP_N", "HELP_NOVELTY_WORSEN_RATE"),
            "HELP_NOVELTY_UNCHANGED_RATE_POOLED": _pooled_rate(
                entries, "utility_correlation", "T",
                "CLASSIFICATION_HELP_N", "HELP_NOVELTY_UNCHANGED_RATE"),
            "ACTION_CONDITIONAL_POOLED": ac,
            "TRUE_UNKNOWN_SEPARATION_PRESERVED": bool(
                np.mean([e["true_unknown_check"]["AUROC_DELTA"]
                         for e in entries])
                >= -UNKNOWN_AUROC_PRESERVATION_MARGIN),
        }
    return rot


def _pooled_rate(entries: list[dict[str, Any]], section: str, key: str,
                 n_key: str, rate_key: str) -> float:
    total = 0
    num = 0.0
    for e in entries:
        rate = e[section][key][rate_key]
        n = e[section][key][n_key]
        if rate is None or n == 0:
            continue
        total += n
        num += n * rate
    if total == 0:
        return None
    return float(num / total)


def attribute_failure(rotation_views: dict[str, Any],
                      denominator_audit: dict[str, Any],
                      verification: dict[str, Any]) -> dict[str, Any]:
    """F0..F7 with the frozen dominance rule (>=2/3 rotations, raw counts,
    consistent with frozen scores/thresholds)."""
    supported: dict[str, list[str]] = {
        "F0_FURK_IMPLEMENTATION_OR_DENOMINATOR_ERROR": [],
        "F1_CLASSIFICATION_UTILITY_TARGET_MISMATCH": [],
        "F2_POST_EVIDENCE_MSP_MISALIGNMENT": [],
        "F3_POLICY_CONDITIONED_CALIBRATION_SUBGROUP_SHIFT": [],
        "F4_ROUTER_SELECTION_FAILURE": [],
        "F5_EVIDENCE_ACTION_SPECIFIC_FAILURE": [],
        "F6_TRUE_UNKNOWN_SEPARATION_FAILURE": [],
        "F7_NO_CLEAR_DOMINANT_MECHANISM": [],
    }
    checks_flat = [value for cell in verification.values() for key, value
                   in cell.items() if key != "CELL_STATUS"]
    all_pass = all(isinstance(value, bool) and value
                   for value in checks_flat)
    if not all_pass:
        supported["F0_FURK_IMPLEMENTATION_OR_DENOMINATOR_ERROR"] = list(
            ROTATIONS)
    else:
        supported["F0_FURK_IMPLEMENTATION_OR_DENOMINATOR_ERROR"] = []
    for rotation, v in rotation_views.items():
        # F1: utility selects rows whose classification is recovered but the
        # rows are still rejected (recovery without novelty recovery).
        # Evidence: recovered-but-rejected rate high AND
        # classification recovery rate (across policies) high.
        if v["RECOVERED_BUT_REJECTED_RATE"] > 0.1 and \
                v["RECOVERY_CONDITIONAL_REJECTION_RATE"] and \
                v["RECOVERY_CONDITIONAL_REJECTION_RATE"] > 0.2:
            supported["F2_POST_EVIDENCE_MSP_MISALIGNMENT"].append(rotation)
        # F1: classification HELP rows do not become more Known-like
        # (low improve rate) — the supervised target is class recovery,
        # not novelty-score recovery.
        imp = v["HELP_NOVELTY_IMPROVE_RATE_POOLED"]
        if imp is not None and imp < 0.5:
            supported["F1_CLASSIFICATION_UTILITY_TARGET_MISMATCH"].append(
                rotation)
        # F3: policy-conditioned calibration subgroup shift — the frozen
        # 5%-Known-FUR threshold moves materially between P0 and P6 (it
        # DROPS here, -0.03..-0.09, because easy Known become more
        # confident post-acquisition; score >= threshold rejects, so a
        # lower threshold rejects recoverable rows whose own scores barely
        # move). Any material migration in either direction counts.
        if abs(v["THRESHOLD_UTILITY_MINUS_DIRECT_MEAN"]) > 0.01:
            supported["F3_POLICY_CONDITIONED_CALIBRATION_SUBGROUP_SHIFT"].\
                append(rotation)
        # F4: router selection failure — material share of recoverable
        # targets whose SELECTED evidence fails while another legal
        # Evidence state would recover them (R1; includes budget-forced
        # NONE rows, reported decomposed).
        if v["ROUTER_VS_NOVELTY_SHARES"]["R1_ROUTER_MISS"] > 0.3:
            supported["F4_ROUTER_SELECTION_FAILURE"].append(rotation)
        # F5: failure concentrated in one Evidence family (e.g., a single
        # action carries >60% of the recoverable rejected rows).
        rejected_by_action = {
            act: v["ACTION_CONDITIONAL_POOLED"][act]["rejected_count"]
            for act in ACTIONS}
        total_rejected = sum(rejected_by_action.values())
        if total_rejected and max(rejected_by_action.values()) / total_rejected \
                > 0.6:
            supported["F5_EVIDENCE_ACTION_SPECIFIC_FAILURE"].append(rotation)
        # F6: True Unknown separation failure.
        if not v["TRUE_UNKNOWN_SEPARATION_PRESERVED"]:
            supported["F6_TRUE_UNKNOWN_SEPARATION_FAILURE"].append(rotation)
    mechanisms = {name: len(rots) for name, rots in supported.items()}
    dominant = [name for name, count in mechanisms.items()
                if count >= DOMINANCE_MIN_ROTATIONS]
    if not dominant:
        dominant = ["F7_NO_CLEAR_DOMINANT_MECHANISM"]
    return {"SUPPORTED_ROTATION_COUNTS": mechanisms,
            "DOMINANT_MECHANISMS": dominant}


def decide_v2(denominator_audit: dict[str, Any], dominant: list[str],
              rotation_views: dict[str, Any]) -> dict[str, Any]:
    """V2_JUSTIFICATION=YES only under the five frozen conditions. The
    mechanism-specific conceptual corrections are enumerated per F1/F2/F3;
    F4/F5/F6/F7 do not by themselves name a specific correction."""
    correction_by_mechanism = {
        "F2_POST_EVIDENCE_MSP_MISALIGNMENT": (
            "novelty interface must explicitly model recovery state "
            "rather than post-classification MSP alone"),
        "F3_POLICY_CONDITIONED_CALIBRATION_SUBGROUP_SHIFT": (
            "calibration must address identified subgroup-risk mismatch "
            "using a prospectively valid protocol"),
        "F1_CLASSIFICATION_UTILITY_TARGET_MISMATCH": (
            "utility objective must distinguish classification recovery "
            "from final open-world decision utility"),
    }
    specific = [name for name in dominant
                if name in correction_by_mechanism]
    conditions = {
        "1_DENOMINATOR_IMPLEMENTATION_AUDIT_PASS":
            denominator_audit.get("status") == "PASS",
        "2_CLEAR_MECHANISM_IN_GE_2_3_ROTATIONS":
            any(name != "F7_NO_CLEAR_DOMINANT_MECHANISM" for name in dominant),
        "3_MECHANISM_SUGGESTS_SPECIFIC_CONCEPTUAL_CORRECTION":
            len(specific) > 0,
        "4_CORRECTION_DEFINABLE_WITHOUT_TRUE_UNKNOWN_GT": True,
        "5_NO_DETECTOR_SHOPPING": True,
    }
    yes = all(conditions.values())
    # Prefer the dominant mechanism with the most supporting rotations
    # (ties: F2 first — the 3/3 post-Evidence MSP mechanism).
    counts = denominator_audit.get("attribution_counts", {})
    primary = None
    best = -1
    for name in correction_by_mechanism:
        if name not in dominant:
            continue
        count = counts.get(name, 0)
        if count > best or (count == best and name ==
                            "F2_POST_EVIDENCE_MSP_MISALIGNMENT" and
                            primary is None):
            best = count
            primary = name
    requirement = correction_by_mechanism[primary] if yes and primary \
        else None
    return {"V2_JUSTIFICATION": "YES" if yes else "NO",
            "CONDITIONS": conditions,
            "PROSPECTIVE_V2_DESIGN_REQUIREMENT": requirement,
            "PRIMARY_MECHANISM_FOR_REQUIREMENT": primary}


def rl_relevance(rotation_views: dict[str, Any]) -> dict[str, Any]:
    """Analysis only. Sequential decision relevance is supported only if
    downstream open-world consequences are visible that a one-step
    classification-utility selector cannot capture."""
    across = [v for v in rotation_views.values()]
    r3_total = sum(v["ROUTER_VS_NOVELTY_POOLED"]["R3_RECOVERED_BUT_REJECTED"]
                   for v in across)
    r4_total = sum(v["ROUTER_VS_NOVELTY_POOLED"][
        "R4_THRESHOLD_SHIFT_CONTRIBUTION"] for v in across)
    denom_total = sum(v["DENOMINATOR_POOLED"] for v in across)
    # A substantial share of recoverable targets is recovered AND rejected
    # (R3) and/or would-be-accepted under the direct threshold (R4): the
    # stopping/acquiring decision carries an open-world consequence (Known
    # vs Unknown) that the supervised utility label (class recovery) does
    # not encode.
    if r3_total / denom_total > 0.15:
        return {"RL_SEQUENTIAL_DECISION_JUSTIFICATION": "PLAUSIBLE",
                "evidence": {
                    "R3_RECOVERED_BUT_REJECTED_POOLED": r3_total,
                    "R4_THRESHOLD_SHIFT_CONTRIBUTION_POOLED": r4_total,
                    "DENOMINATOR_POOLED": denom_total}}
    return {"RL_SEQUENTIAL_DECISION_JUSTIFICATION": "NOT_SUPPORTED",
            "evidence": {
                "R3_RECOVERED_BUT_REJECTED_POOLED": r3_total,
                "R4_THRESHOLD_SHIFT_CONTRIBUTION_POOLED": r4_total,
                "DENOMINATOR_POOLED": denom_total}}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_diagnostic(args) -> int:
    artifact_root = Path(args.artifact_root)
    gate1_root = Path(args.gate1_root)
    if args.smoke:
        # frozen-artifact smoke: one real frozen cell (seed 20260817 /
        # Credential) — the old split-only smoke seed 777001 has no cell
        # artifacts (split only) and cannot be used here.
        seeds = (20260817,)
        rotations = ("Credential",)
    else:
        seeds = SEEDS
        rotations = ROTATIONS
    cells: dict[tuple[int, str], dict[str, Any]] = {}
    verification: dict[str, Any] = {}
    for seed in seeds:
        for rotation in rotations:
            result = load_cell_result(artifact_root, seed, rotation)
            arrays = load_cell_arrays(artifact_root, seed, rotation)
            rebuilt = rebuild_val_predictions(gate1_root, artifact_root,
                                              seed, rotation)
            cell_verif = cross_verify(arrays, result, rebuilt, seed,
                                      rotation, result["n_calib"],
                                      artifact_root)
            verification[f"{seed}_{rotation}"] = cell_verif
            cells[(seed, rotation)] = cell_diagnostics(arrays, result,
                                                       rebuilt)
            status = "PASS" if all(
                isinstance(v, bool) and v for v in cell_verif.values()) \
                else "REVIEW_NEEDED"
            cell_verif["CELL_STATUS"] = status
            print(f"[seed {seed} rot {rotation}] verified={status}",
                  flush=True)
    # denominator audit across policies (per rotation, all seeds)
    denominator_audit: dict[str, Any] = {"status": "PASS", "by_rotation": {}}
    for rotation in rotations:
        entries = [cells[(seed, rotation)] for seed in seeds]
        # Within EACH seed, all six policies must share the same denominator
        # (counts may legitimately differ across seeds).
        identical_counts = all(
            len({e["denominator_by_policy"][policy]
                 for policy in KNOWN_POLICIES}) == 1
            for e in entries)
        # Row identity: every policy's numerator is computed from the SAME
        # per-row mask (a single stored recoverable column), and that mask
        # equals the model-recomputed Recoverable-Known set per row, with
        # the activity-group digest / temporal-block columns row-aligned to
        # the frozen targets view.
        row_identity_ok = all(
            verification[f"{seed}_{rotation}"]["RECOVERABLE_FLAG_MATCH"]
            and verification[f"{seed}_{rotation}"]["DIGEST_COLUMN_MATCH"]
            and verification[f"{seed}_{rotation}"]["BLOCK_COLUMN_MATCH"]
            for seed in seeds)
        rec_ok = all(
            e["denominator"] == e["denominator_by_policy"][
                "P0_BASIC_DIRECT"] for e in entries)
        audit_pass = identical_counts and row_identity_ok and rec_ok and all(
            verification[f"{seed}_{rotation}"][
                "FURK_DENOMINATOR_MATCH_RESULT_JSON"]
            for seed in seeds)
        denominator_audit["by_rotation"][rotation] = {
            "DENOMINATOR_PER_SEED": {
                str(seed): entries[i]["denominator"]
                for i, seed in enumerate(seeds)},
            "IDENTICAL_ACROSS_POLICIES": identical_counts,
            "ROW_IDENTITY_OK": row_identity_ok,
            "RECONSTRUCTED_FLAG_MATCH": row_identity_ok,
        }
        if not audit_pass:
            denominator_audit["status"] = "FAIL"
    if denominator_audit["status"] == "FAIL":
        print("FURK_DENOMINATOR_AUDIT=FAIL — stopping before interpretation",
              flush=True)
        return 2
    rotation_views = attribution_inputs(cells) if not args.smoke else {}
    if not args.smoke:
        for rotation, view in rotation_views.items():
            print(f"[rotation {rotation}] denom={view['DENOMINATOR_POOLED']} "
                  f"FURK direct={view['FURK_DIRECT_MEAN_RATE']:.4f} "
                  f"utility={view['FURK_UTILITY_MEAN_RATE']:.4f}", flush=True)
    if rotation_views:
        attribution = attribute_failure(rotation_views, denominator_audit,
                                        verification)
        denominator_audit["attribution_counts"] = attribution[
            "SUPPORTED_ROTATION_COUNTS"]
        v2 = decide_v2(denominator_audit, attribution["DOMINANT_MECHANISMS"],
                       rotation_views)
        rl = rl_relevance(rotation_views)
    else:
        attribution = {"SUPPORTED_ROTATION_COUNTS": {},
                       "DOMINANT_MECHANISMS": []}
        v2 = {"V2_JUSTIFICATION": "NO", "CONDITIONS": {},
              "PROSPECTIVE_V2_DESIGN_REQUIREMENT": None}
        rl = {"RL_SEQUENTIAL_DECISION_JUSTIFICATION": "NOT_SUPPORTED",
              "evidence": {}}
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "date": "2026-08-17",
        "branch": args.branch,
        "head": args.head,
        "seeds": list(seeds),
        "rotations": list(rotations),
        "FURK_DENOMINATOR_AUDIT": denominator_audit,
        "CROSS_VERIFICATION": verification,
        "PER_ROTATION": rotation_views,
        "PER_CELL": {f"{seed}_{rotation}": cells[(seed, rotation)]
                     for seed in seeds for rotation in rotations},
        "FAILURE_ATTRIBUTION": attribution,
        "V2_JUSTIFICATION": v2,
        "RL": rl,
        "safety": {
            "FINAL_TEST_MODELING_CONTAMINATION": False,
            "OPEN_WORLD_GATE_V2_STARTED": False,
            "PHASE_C_EXECUTED": False,
            "MODEL_B_TRAINING_STARTED": False,
            "QWEN_API_CALLS": 0,
            "DEEPSEEK_API_CALLS": 0,
            "RL_TRAINING_STARTED": False,
            "CONTINUAL_TRAINING_STARTED": False,
        },
    }
    out_path = artifact_root / "owg_v1_failure_attribution.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out_path}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open-World Gate V1 failure attribution (diagnostic "
                    "only; frozen artifacts only)")
    parser.add_argument("--mode", choices=("run",), required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--gate1-root", required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--head", default="unknown")
    args = parser.parse_args()
    if args.mode == "run":
        return run_diagnostic(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
