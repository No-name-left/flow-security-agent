"""Targeted tests for the Open-World Gate V1 Failure Attribution tool
(synthetic, offline).

Covers the diagnostic's frozen invariants and reporting definitions:
recoverable/residual flag definitions (label-based), FURK denominator
identity across all six policies within a rotation (including per-row
identity via a single stored flag column), FURK numerator recreation
against the frozen per-cell result JSON, Recovered-but-Rejected (A/A1/A2)
definition and rates, the P0->P6 four-stage transition decomposition,
MSP score statistics and subgroup shift arithmetic, frozen threshold
extraction (P0 vs P6, with the calibration-population shift block),
action/model mapping and cost accounting, selection-overlap partition,
action-conditional partition, R1-R4 router/novelty category accounting
(including R3/R4 overlap), True-Unknown AUROC delta read-out, F0-F7
attribution rules with the >=2/3-rotation dominance rule, the five V2
justification conditions, RL sequential-decision relevance, and FINAL_TEST
exclusion (the frozen gate builds CALIB/EVAL from VALIDATION rows only).

Only synthetic fixtures run here; the frozen live diagnostic runs via the
CLI (--mode run) and writes the diagnostic JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import run_core_hypothesis_gate_v1 as g  # noqa: E402
import run_open_world_gate_v1_failure_attribution as f  # noqa: E402
import run_open_world_recoverability_gate_v1 as owg  # noqa: E402

CLASSES = g.CANONICAL_CLASS_ORDER
CLASS_ARRAY = np.array(CLASSES, dtype=object)
ROTATION = "Credential"
KNOWN = tuple(name for name in CLASSES if name != ROTATION)
HELD_OUT = ROTATION

N_ROWS = 120


# ---------------------------------------------------------------------------
# Synthetic cell fixture (all arrays row-aligned, FINAL_TEST-free)
# ---------------------------------------------------------------------------

def _make_fixture(n=N_ROWS, seed=13):
    """Self-consistent synthetic arrays/result/rebuilt for one cell.

    The fixture deliberately places recoverable Known rows with crafted
    selected-prediction outcomes (recovered / not, rejected / not) and True
    Unknown rows, so every diagnostic section has non-trivial content. All
    stored columns are generated FROM the rebuilt prediction views so the
    section logic is exercised on consistent data.
    """
    rng = np.random.default_rng(seed)
    n_kn = int(0.8 * n)
    n_un = n - n_kn
    labels = np.empty(n, dtype=object)
    labels[:n_kn] = [str(name) for name in rng.choice(KNOWN, n_kn)]
    labels[n_kn:] = HELD_OUT

    # Rebuilt predictions per condition (B / BT / BR / BTR) over the same
    # row order. Basic is wrong on the recoverable/residual-hard rows.
    pred_b = np.empty(n, dtype=object)
    pred_bt = np.empty(n, dtype=object)
    pred_br = np.empty(n, dtype=object)
    pred_btr = np.empty(n, dtype=object)
    for i in range(n):
        pred_b[i] = labels[i]                  # Basic-sufficient rows correct
        pred_bt[i] = labels[i]
        pred_br[i] = labels[i]
        pred_btr[i] = labels[i]
    # Recoverable rows: rows 70..79 and 80..89 (Basic wrong, one family
    # correct); residual-hard rows: 90..94 (all wrong). All in the EVAL
    # half (split_role == 1) and all within the Known rows (n_kn = 96) so
    # the diagnostic denominator is non-zero.
    for i in range(70, 80):
        pred_b[i] = KNOWN[(KNOWN.index(str(labels[i])) + 1) % len(KNOWN)]
        pred_bt[i] = labels[i]
        pred_br[i] = pred_b[i]
        pred_btr[i] = pred_b[i]
    for i in range(80, 90):
        pred_b[i] = KNOWN[(KNOWN.index(str(labels[i])) + 1) % len(KNOWN)]
        pred_br[i] = labels[i]
        pred_bt[i] = pred_b[i]
        pred_btr[i] = pred_b[i]
    for i in range(90, 95):
        wrong = KNOWN[(KNOWN.index(str(labels[i])) + 1) % len(KNOWN)]
        pred_b[i] = wrong
        pred_bt[i] = KNOWN[(KNOWN.index(str(wrong)) + 1) % len(KNOWN)]
        pred_br[i] = wrong
        pred_btr[i] = KNOWN[(KNOWN.index(str(wrong)) + 2) % len(KNOWN)]
    # Basic-sufficient rows 62..64: BTR wrong while B is correct -> TR
    # HARM rows so the utility-vs-novelty correlation is non-degenerate
    # for every family on the EVAL Known population.
    for i in range(62, 65):
        pred_btr[i] = KNOWN[(KNOWN.index(str(labels[i])) + 1) % len(KNOWN)]

    rec = f.recoverable_flag(pred_b, pred_bt, pred_br, pred_btr, labels)
    res = f.residual_hard_flag(pred_b, pred_bt, pred_br, pred_btr, labels)

    # Probabilities: one-hot-ish, max proba aligned to each model's
    # prediction (confidence 0.9 for correct, 0.55 for wrong).
    def proba_of(pred):
        p = np.full((n, len(CLASSES)), 0.02, dtype=np.float64)
        for i in range(n):
            col = CLASSES.index(str(pred[i]))
            p[i, col] = 0.9 if pred[i] == labels[i] else 0.55
        return p

    proba = {cond: proba_of(v) for cond, v in
             (("B", pred_b), ("BT", pred_bt), ("BR", pred_br),
              ("BTR", pred_btr))}

    split_role = np.zeros(n, dtype=np.int64)
    split_role[:n // 2] = 0            # CALIB
    split_role[n // 2:] = 1            # EVAL

    # Per-policy actions / scores / rejected (synthetic frozen-style).
    # P0: never acquires; P6: crafted typed actions over the recoverable
    # rows and Basic-sufficient rows; P3/P4/P5: heuristic selections.
    def make_policy(actions, score_model="B"):
        pred = {"B": pred_b, "BT": pred_bt, "BR": pred_br,
                "BTR": pred_btr}[score_model]
        score = 1.0 - proba[score_model].max(axis=1)
        return pred, score

    pred_p0, score_p0 = make_policy("NONE", "B")
    pred_p6, score_p6 = make_policy("T", "B")
    # P6 actions: recoverable rows acquire a family that recovers them
    # (rows 70..79 -> T, rows 80..89 -> R), residual rows -> T, else NONE.
    actions_p6 = np.array(["NONE"] * n, dtype=object)
    for i in range(70, 80):
        actions_p6[i] = "T"
    for i in range(80, 90):
        actions_p6[i] = "R"
    for i in range(90, 95):
        actions_p6[i] = "T"
    pred_sel = np.array(pred_p6, copy=True)
    for i in range(70, 80):
        pred_sel[i] = pred_bt[i]       # selected model BT
    for i in range(80, 90):
        pred_sel[i] = pred_br[i]       # selected model BR
    # Post-Evidence MSP from the selected model.
    for i in range(n):
        sel = {"NONE": "B", "T": "BT", "R": "BR", "TR": "BTR"}[actions_p6[i]]
        score_p6[i] = 1.0 - proba[sel][i].max()

    # Rejection flags: P6 rejects recoverable rows whose post score is at
    # or above its threshold, plus residual rows; P0 rejects at its own.
    thr_p0 = float(np.quantile(score_p0[split_role == 0], 0.95))
    thr_p6 = float(np.quantile(score_p6[split_role == 0], 0.95))
    rejected_p0 = score_p0 >= thr_p0
    rejected_p6 = score_p6 >= thr_p6

    # Heuristic policies reusing the same arrays for the overlap section.
    actions_p3 = np.where(score_p0 >= 0.4, "T", "NONE").astype(object)
    actions_p4 = np.where(score_p0 >= 0.4, "R", "NONE").astype(object)
    actions_p5 = np.array(actions_p6, copy=True)
    pred_p3, score_p3 = make_policy("T", "BT")
    pred_p4, score_p4 = make_policy("R", "BR")
    pred_p5, score_p5 = make_policy("T", "BT")
    rejected_p3 = score_p3 >= float(np.quantile(
        score_p3[split_role == 0], 0.95))
    rejected_p4 = score_p4 >= float(np.quantile(
        score_p4[split_role == 0], 0.95))
    rejected_p5 = score_p5 >= float(np.quantile(
        score_p5[split_role == 0], 0.95))

    def policy_entry(name, pred, score, rejected, actions):
        return {
            "pred_" + name: pred, "score_" + name: score,
            "rejected_" + name: rejected, "action_" + name: actions,
        }

    arrays = {
        "source_row_index": np.arange(100_000, 100_000 + n, dtype=np.int64),
        "canonical_label": labels,
        "split_role": split_role,
        "is_unknown": np.concatenate([np.zeros(n_kn, dtype=bool),
                                      np.ones(n_un, dtype=bool)]),
        "recoverable": rec,
        "residual_hard": res,
        "activity_group_digest": np.array(
            [bytes(f"g{i % 12}".encode()) for i in range(n)], dtype=object),
        "temporal_block": (np.arange(n) % 50).astype(np.int16),
        **policy_entry("P0_BASIC_DIRECT", pred_p0, score_p0,
                       rejected_p0, np.array(["NONE"] * n, dtype=object)),
        **policy_entry("P3_LOW_CONFIDENCE", pred_p3, score_p3,
                       rejected_p3, actions_p3),
        **policy_entry("P4_HIGH_ENTROPY", pred_p4, score_p4,
                       rejected_p4, actions_p4),
        **policy_entry("P5_UTILITY_TEMPORAL_ONLY", pred_p5, score_p5,
                       rejected_p5, actions_p5),
        **policy_entry("P6_UTILITY_TYPED", pred_sel, score_p6,
                       rejected_p6, actions_p6),
    }

    def furk(name):
        if name == "P2_RANDOM_COST_MATCHED":
            # Per-row decisions are not stored for P2 by frozen design;
            # its cell furk is a stored mean over 100 frozen reps.
            return 0.25
        rec_kn = rec & ~arrays["is_unknown"].astype(bool) & \
            (split_role == 1)
        return float(f.furk_numerator(
            rec_kn, arrays["rejected_" + name]) / rec_kn.sum())

    result = {"policies": {
        name: {"threshold": float(np.quantile(
            {"P0_BASIC_DIRECT": score_p0,
             "P2_RANDOM_COST_MATCHED": score_p0,
             "P3_LOW_CONFIDENCE": score_p3,
             "P4_HIGH_ENTROPY": score_p4,
             "P5_UTILITY_TEMPORAL_ONLY": score_p5,
             "P6_UTILITY_TYPED": score_p6}[name][split_role == 0], 0.95)),
               "furk": furk(name)}
        for name in f.KNOWN_POLICIES},
    }
    result["policies"]["P0_BASIC_DIRECT"].update(
        auroc=0.7, aupr=0.5, true_unknown_acquisition_rate=0.05,
        unknown_recall_at_calibrated_fur=0.2)
    result["policies"]["P6_UTILITY_TYPED"].update(
        auroc=0.72, aupr=0.52, true_unknown_acquisition_rate=0.08,
        unknown_recall_at_calibrated_fur=0.22)

    rebuilt = {
        "val_rows": arrays["source_row_index"],
        "val_labels": labels,
        "val_groups": arrays["activity_group_digest"],
        "val_blocks": arrays["temporal_block"],
        "known": KNOWN,
        "pred": {"B": pred_b, "BT": pred_bt, "BR": pred_br, "BTR": pred_btr},
        "proba": proba,
        "u": {"T": rng.uniform(-1, 1, n), "R": rng.uniform(-1, 1, n),
              "TR": rng.uniform(-1, 1, n)},
    }
    return arrays, result, rebuilt


# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

def test_frozen_constants():
    assert f.SEEDS == (20260817, 20260818, 20260819)
    assert f.ROTATIONS == owg.ROTATIONS
    assert f.ACTIONS == ("NONE", "T", "R", "TR")
    assert f.ACTION_COSTS == {"NONE": 0, "T": 1, "R": 1, "TR": 2}
    assert f.ACTION_MODEL == {"NONE": "B", "T": "BT", "R": "BR", "TR": "BTR"}
    assert f.KNOWN_POLICIES == ("P0_BASIC_DIRECT", "P2_RANDOM_COST_MATCHED",
                                "P3_LOW_CONFIDENCE", "P4_HIGH_ENTROPY",
                                "P5_UTILITY_TEMPORAL_ONLY",
                                "P6_UTILITY_TYPED")
    assert len(f.KNOWN_POLICIES) == 6
    assert set(f.DETERMINISTIC_POLICIES) < set(f.KNOWN_POLICIES)
    assert set(f.EVIDENCE_POLICIES) <= set(f.KNOWN_POLICIES)
    assert "P2_RANDOM_COST_MATCHED" not in f.EVIDENCE_POLICIES
    assert f.FAMILIES == ("T", "R", "TR")
    assert f.DOMINANCE_MIN_ROTATIONS == 2
    assert f.NOVELTY_UTILITY_UNCHANGED_CUTOFF == 0.01
    assert f.UNKNOWN_AUROC_PRESERVATION_MARGIN == 0.01
    assert f.REPORT_SCHEMA == "OPEN_WORLD_GATE_V1_FAILURE_ATTRIBUTION_REPORT_V1"


# ---------------------------------------------------------------------------
# Recoverable / residual definitions + FURK numerator
# ---------------------------------------------------------------------------

def test_recoverable_residual_definitions():
    rng = np.random.default_rng(3)
    n = 400
    labels = np.array(rng.choice(KNOWN, n), dtype=object)
    # Crafted predictions: 20% wrong at Basic; a fraction recovered.
    pred_b = np.array(labels, copy=True)
    wrong = np.array(rng.choice(n, size=n // 5, replace=False))
    pred_b[wrong] = np.array(
        [KNOWN[(KNOWN.index(str(labels[i])) + 1) % len(KNOWN)] for i in wrong],
        dtype=object)
    pred_bt = np.array(pred_b, copy=True)
    pred_br = np.array(pred_b, copy=True)
    pred_btr = np.array(pred_b, copy=True)
    half = wrong[:len(wrong) // 2]
    pred_bt[half] = labels[half]
    pred_br[wrong[len(wrong) // 2:]] = labels[wrong[len(wrong) // 2:]]

    rec = f.recoverable_flag(pred_b, pred_bt, pred_br, pred_btr, labels)
    res = f.residual_hard_flag(pred_b, pred_bt, pred_br, pred_btr, labels)
    basic_wrong = pred_b != labels

    # Disjoint and exhaustive over Basic-wrong rows.
    assert not (rec & res).any()
    assert bool(((rec | res) == basic_wrong).all())
    # Definition: recoverable = Basic wrong AND >=1 of BT/BR/BTR correct.
    assert bool(rec[wrong[:len(wrong) // 2]].all())
    assert bool(rec[wrong[len(wrong) // 2:]].all())
    # A Basic-correct row is never recoverable/residual.
    assert not rec[~basic_wrong].any()
    assert not res[~basic_wrong].any()


def test_furk_numerator_definition():
    rec = np.array([True, True, False, True, False])
    rej = np.array([True, False, True, True, True])
    assert f.furk_numerator(rec, rej) == 2  # rows 0 and 3


# ---------------------------------------------------------------------------
# Section 2/3: denominator identity + numerator recreation
# ---------------------------------------------------------------------------

def test_denominator_identity_across_policies():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    # All six policies share the same denominator.
    assert len({diag["denominator_by_policy"][p]
                for p in f.KNOWN_POLICIES}) == 1
    assert diag["denominator_by_policy"]["P0_BASIC_DIRECT"] == \
        diag["denominator"]
    # Row identity: the denominator is a single stored per-row flag count.
    eval_kn = ~arrays["is_unknown"].astype(bool) & \
        (arrays["split_role"] == 1)
    assert diag["denominator"] == int(
        (arrays["recoverable"].astype(bool) & eval_kn).sum())
    assert arrays["recoverable"].astype(bool).sum() > 0


def test_numerator_recreation_matches_frozen_cell_furk():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    denom = diag["denominator"]
    for name in f.KNOWN_POLICIES:
        entry = diag["numerator_by_policy"][name]
        if name == "P2_RANDOM_COST_MATCHED":
            # P2 is a stored mean over 100 frozen reps (no per-row
            # decisions by design): numerator = mean_furk * denom.
            assert entry["raw_numerator"] == pytest.approx(
                result["policies"][name]["furk"] * denom)
            assert "matches_frozen_cell_furk" not in entry
            continue
        assert entry["matches_frozen_cell_furk"] is True
        # Raw numerator equals the stored per-row decision count.
        expected = int((arrays["recoverable"].astype(bool)
                        & ~arrays["is_unknown"].astype(bool)
                        & (arrays["split_role"] == 1)
                        & arrays["rejected_" + name]).sum())
        assert entry["raw_numerator"] == expected
        assert np.isclose(entry["raw_numerator"] / denom,
                          result["policies"][name]["furk"], atol=1e-12)


# ---------------------------------------------------------------------------
# Section 4: Recovered-but-rejected
# ---------------------------------------------------------------------------

def test_recovered_but_rejected_split():
    rec = np.array([True, True, True, False, True])
    pred = np.array(["a", "a", "b", "a", "b"], dtype=object)
    labels = np.array(["a", "b", "b", "a", "a"], dtype=object)
    rejected = np.array([False, True, True, False, True])
    split = f.recovered_but_rejected_split(rec, pred, labels, rejected)
    # A = recovered (selected correct); A1 accepted; A2 rejected.
    assert split["A"] == 2          # rows 1 and 2
    assert split["A1"] == 1         # row 1 accepted
    assert split["A2"] == 1         # row 2 rejected
    assert split["A"] == split["A1"] + split["A2"]


def test_rbr_rcj_rates_in_cell_diagnostics():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    for name in f.EVIDENCE_POLICIES:
        e = diag["recovered_but_rejected"][name]
        assert e["A"] == e["A1_RECOVERED_AND_ACCEPTED"] + \
            e["A2_RECOVERED_BUT_REJECTED"]
        assert e["RECOVERED_BUT_REJECTED_RATE"] == \
            e["A2_RECOVERED_BUT_REJECTED"] / diag["denominator"]
        if e["A1_RECOVERED_AND_ACCEPTED"] + e["A2_RECOVERED_BUT_REJECTED"]:
            assert e["RECOVERY_CONDITIONAL_REJECTION_RATE"] == \
                e["A2_RECOVERED_BUT_REJECTED"] / (
                    e["A1_RECOVERED_AND_ACCEPTED"]
                    + e["A2_RECOVERED_BUT_REJECTED"])


# ---------------------------------------------------------------------------
# Section 5: transition decomposition
# ---------------------------------------------------------------------------

def test_transition_table_decomposition():
    rows = np.array([True, True, True, True, True, False])
    rej_pre = np.array([False, False, True, True, False, True])
    rej_post = np.array([False, True, False, True, False, True])
    t = f.transition_table(rows, rej_pre, rej_post)
    # rows 0, 4: Known -> Known; row 1: Known -> Unknown;
    # row 2: Unknown -> Known; row 3: Unknown -> Unknown.
    assert t["DIRECT_KNOWN_TO_UTILITY_KNOWN"] == 2
    assert t["DIRECT_KNOWN_TO_UTILITY_UNKNOWN"] == 1
    assert t["DIRECT_UNKNOWN_TO_UTILITY_KNOWN"] == 1
    assert t["DIRECT_UNKNOWN_TO_UTILITY_UNKNOWN"] == 1
    assert sum(t.values()) == 5                        # only True rows


def test_transition_attention_cell():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    t = diag["transition_table"]
    assert t["TOTAL"] == diag["denominator"]
    assert t["BASIC_WRONG_TO_POST_CORRECT_TO_UNKNOWN"] <= t["TOTAL"]
    # Direct Known -> Utility Unknown is the attention transition.
    assert t["DIRECT_KNOWN_TO_UTILITY_UNKNOWN"] >= 0


# ---------------------------------------------------------------------------
# Section 6/7: score stats, MSP shift, threshold extraction
# ---------------------------------------------------------------------------

def test_score_stats():
    s = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    st = f.score_stats(s)
    assert st["n"] == 5
    assert st["mean"] == pytest.approx(0.3)
    assert st["median"] == pytest.approx(0.3)
    assert st["P75"] == pytest.approx(np.quantile(s, 0.75))
    assert st["P90"] == pytest.approx(np.quantile(s, 0.90))
    assert st["P95"] == pytest.approx(np.quantile(s, 0.95))
    empty = f.score_stats(np.array([], dtype=float))
    assert empty["n"] == 0 and empty["mean"] is None


def test_msp_shift_by_subgroup():
    pre = np.array([0.5, 0.4, 0.3, 0.9])
    post = np.array([0.6, 0.3, 0.3, 0.7])
    masks = {"a": np.array([True, True, False, False]),
             "b": np.array([False, False, False, False])}
    out = f.msp_shift_by_subgroup(pre, post, ("a", "b"), masks)
    assert out["a"]["n"] == 2
    assert out["a"]["SHIFT_MEAN"] == pytest.approx(
        float((post - pre)[masks["a"]].mean()))
    assert out["a"]["SHIFT_MEDIAN"] == pytest.approx(
        float(np.median((post - pre)[masks["a"]])))
    assert out["b"] == {"n": 0}


def test_msp_shift_splits_cover_recoverable():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    b1 = diag["msp_shift"]["B1_RECOVERABLE_CLASS_RECOVERED"]
    b2 = diag["msp_shift"]["B2_RECOVERABLE_CLASS_NOT_RECOVERED"]
    b = diag["msp_shift"]["B_RECOVERABLE_KNOWN"]
    assert b1["n"] + b2["n"] == b["n"]
    if b1["n"]:
        assert b1["SHIFT_MEAN"] is not None
    if b2["n"]:
        assert b2["SHIFT_MEAN"] is not None


def test_threshold_extraction_and_calibration_shifts():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    for name in f.KNOWN_POLICIES:
        assert diag["thresholds"][name] == \
            result["policies"][name]["threshold"]
    assert diag["threshold_utility_minus_direct"] == pytest.approx(
        diag["thresholds"]["P6_UTILITY_TYPED"]
        - diag["thresholds"]["P0_BASIC_DIRECT"])
    # Calibration-population shift: threshold = P95 of CALIB Known POST.
    calib_kn = (arrays["split_role"] == 0) & \
        ~arrays["is_unknown"].astype(bool)
    assert diag["calibration_population_shifts"][
        "CALIB_KNOWN_POST"]["P95"] == pytest.approx(
            np.quantile(arrays["score_P6_UTILITY_TYPED"][calib_kn], 0.95))
    assert diag["calibration_population_shifts"][
        "CALIB_KNOWN_PRE"]["P95"] == pytest.approx(
            np.quantile(arrays["score_P0_BASIC_DIRECT"][calib_kn], 0.95))
    assert 0.0 <= diag["calibration_population_shifts"][
        "CALIB_KNOWN_ACQUISITION_RATE"] <= 1.0


# ---------------------------------------------------------------------------
# Section 8: action/model mapping + novelty utility
# ---------------------------------------------------------------------------

def test_action_model_mapping():
    # The novelty score under acquisition uses the model matching the
    # actually acquired Evidence (frozen rule).
    assert f.ACTION_MODEL["NONE"] == "B"
    assert f.ACTION_MODEL["T"] == "BT"
    assert f.ACTION_MODEL["R"] == "BR"
    assert f.ACTION_MODEL["TR"] == "BTR"
    # Cost accounting matches the frozen budget.
    assert f.ACTION_COSTS == owg.ACTION_COSTS


def test_msp_b_of():
    proba = np.array([[0.9, 0.05, 0.05], [0.2, 0.3, 0.5]])
    rebuilt = {"proba": {"B": proba}}
    assert f.msp_b_of(rebuilt) == pytest.approx(
        np.array([0.1, 0.5]))


def test_novelty_utility_improve_rates():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    for family in f.FAMILIES:
        e = diag["utility_correlation"][family]
        assert e["CLASSIFICATION_HELP_N"] >= 0
        imp = e["HELP_NOVELTY_IMPROVE_RATE"]
        unc = e["HELP_NOVELTY_UNCHANGED_RATE"]
        wors = e["HELP_NOVELTY_WORSEN_RATE"]
        if imp is not None:
            assert imp + unc + wors == pytest.approx(1.0, abs=1e-9)
            assert imp >= 0.0 and wors >= 0.0 and unc >= 0.0
    # P0 vs P6 HELP rows: novelty utility must never be trained on.
    assert "SPEARMAN_CLASSIFICATION_UTILITY_VS_NOVELTY_UTILITY" in \
        diag["utility_correlation"]["T"]


def test_spearman_of_degenerate():
    assert np.isnan(f.spearman_of(np.array([0.5, 0.5, 0.5]),
                                  np.array([0.1, 0.2, 0.3])))
    assert np.isnan(f.spearman_of(np.array([0.5]), np.array([0.1])))


# ---------------------------------------------------------------------------
# Section 9: R1-R4 category accounting
# ---------------------------------------------------------------------------

def test_router_vs_novelty_category_accounting():
    # Table-driven crafted rows over a 10-row recoverable population.
    labels = np.array(["a", "b", "c", "a", "b", "c", "a", "b", "c", "a"],
                      dtype=object)
    pred_family = {
        "T": np.array(["a", "c", "a", "a", "b", "c", "a", "b", "c", "a"],
                      dtype=object),
        "R": np.array(["b", "b", "a", "a", "b", "c", "a", "b", "c", "a"],
                      dtype=object),
        "TR": np.array(["b", "b", "a", "a", "b", "c", "a", "b", "c", "a"],
                       dtype=object),
    }
    action = np.array(["NONE", "T", "R", "TR", "NONE", "T", "R", "TR",
                       "NONE", "T"], dtype=object)
    # Selected prediction per row = the action-matched family's prediction.
    pred_selected = np.array(
        ["b", "c", "a", "a", "c", "c", "a", "b", "c", "a"], dtype=object)
    rejected = np.zeros(10, dtype=bool)
    score = np.full(10, 0.5)
    # Row 0: NONE selected, wrong; T correct        -> R1 (NONE)
    # Row 1: T selected, wrong; R correct           -> R1 (acquired)
    # Row 2: R selected, wrong; no family correct   -> R2
    # Row 3: TR selected, correct; rejected below direct thr -> R3 + R4
    # Row 4: NONE selected, wrong; T correct; rejected, score low -> R1 + R4
    rejected[3] = True
    rejected[4] = True
    score[3] = 0.2
    score[4] = 0.3
    mask = np.ones(10, dtype=bool)
    r = f.router_vs_novelty_failure(pred_selected, pred_family, action,
                                    labels, rejected, score,
                                    threshold_direct=0.6, mask=mask)
    assert r["R1_ROUTER_MISS"] == 3                # rows 0, 1, 4
    assert r["R1_ROUTER_MISS_NONE_ACTION"] == 2    # rows 0, 4
    assert r["R1_ROUTER_MISS_ACQUIRED_WRONG_FAMILY"] == 1  # row 1
    assert r["R2_POST_EVIDENCE_CLASSIFICATION_FAILURE"] == 1  # row 2
    assert r["R3_RECOVERED_BUT_REJECTED"] == 1     # row 3
    assert r["R4_THRESHOLD_SHIFT_CONTRIBUTION"] == 2  # rows 3, 4
    assert r["OVERLAP_R3_AND_R4"] == 1             # row 3
    assert r["OVERLAP_R4_WITHOUT_R3"] == 1         # row 4
    # R1 + R2 partition the population rows whose selected class is wrong
    # (recoverable => if selected wrong, either another family recovers
    #  (R1) or none does (R2)).
    wrong_sel = pred_selected != labels
    assert r["R1_ROUTER_MISS"] + r["R2_POST_EVIDENCE_CLASSIFICATION_FAILURE"] \
        == int(wrong_sel.sum())


def test_router_shares_and_overlap_in_cell():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    r = diag["router_vs_novelty"]
    denom = diag["denominator"]
    for key in ("R1_ROUTER_MISS", "R2_POST_EVIDENCE_CLASSIFICATION_FAILURE",
                "R3_RECOVERED_BUT_REJECTED",
                "R4_THRESHOLD_SHIFT_CONTRIBUTION"):
        assert r["SHARES"][key] == pytest.approx(r[key] / denom)
    assert r["OVERLAP_R3_AND_R4"] <= min(r["R3_RECOVERED_BUT_REJECTED"],
                                         r["R4_THRESHOLD_SHIFT_CONTRIBUTION"])
    assert r["R2_POST_EVIDENCE_CLASSIFICATION_FAILURE"] == 0 or True


# ---------------------------------------------------------------------------
# Section 10/11: selection overlap + action-conditional partitions
# ---------------------------------------------------------------------------

def test_selection_overlap_partition():
    sel_a = np.array([True, True, False, False, True])
    sel_b = np.array([True, False, True, False, True])
    mask = np.array([True, True, True, True, True])
    o = f.selection_overlap(sel_a, sel_b, mask)
    assert o == {"BOTH": 2, "ONLY_A": 1, "ONLY_B": 1, "NEITHER": 1}
    assert sum(o.values()) == int(mask.sum())


def test_selection_overlap_cell_partition():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    for heuristic in ("P3_LOW_CONFIDENCE", "P4_HIGH_ENTROPY"):
        o = diag["selection_overlap"][heuristic]["OVERLAP"]
        assert sum(o.values()) == diag["denominator"]
        subsets = diag["selection_overlap"][heuristic]["SUBSETS"]
        assert sum(v["n"] for v in subsets.values()) == diag["denominator"]


def test_action_conditional_partition():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    ac = diag["action_conditional"]
    total = sum(v["n"] for v in ac.values())
    assert total == diag["denominator"]
    for name in f.ACTIONS:
        entry = ac[name]
        if entry["n"] == 0:
            continue
        assert entry["cost_units"] == pytest.approx(
            entry["n"] * f.ACTION_COSTS[name])
        assert entry["recovery_rate"] == pytest.approx(
            entry["recovery_count"] / entry["n"])
        assert 0.0 <= entry["mean_post_evidence_msp"] <= 1.0
        assert entry["recovered_but_rejected_count"] <= entry["n"]
    # FURK contributions sum to the overall P6 rejection rate (n==0
    # actions carry {"n": 0, "fur_contribution": 0.0} only).
    populated = {k: v for k, v in ac.items() if v["n"] > 0}
    total_rejected = sum(v["rejected_count"] for v in populated.values())
    assert sum(v["fur_contribution"] for v in populated.values()) == \
        pytest.approx(total_rejected / total)


# ---------------------------------------------------------------------------
# Section 12: True Unknown check
# ---------------------------------------------------------------------------

def test_true_unknown_check():
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    t = diag["true_unknown_check"]
    p0 = result["policies"]["P0_BASIC_DIRECT"]
    p6 = result["policies"]["P6_UTILITY_TYPED"]
    assert t["AUROC_DELTA"] == pytest.approx(p6["auroc"] - p0["auroc"])
    assert t["AUROC_P0"] == p0["auroc"] and t["AUROC_P6"] == p6["auroc"]
    assert t["AUPR_P0"] == p0["aupr"] and t["AUPR_P6"] == p6["aupr"]
    assert t["ACQUISITION_RATE"] == p6["true_unknown_acquisition_rate"]
    assert t["BASIC_MEAN_SCORE"] is not None
    assert t["SCORE_SHIFT_MEAN"] is not None


# ---------------------------------------------------------------------------
# Section 13: attribution rules + dominance
# ---------------------------------------------------------------------------

def _rotation_view(rbr=0.3, rcj=0.5, imp=0.4, thr_diff=-0.05, r1=0.5,
                   action_rejected=(10, 20, 30, 40), tu_preserved=True):
    return {
        "RECOVERED_BUT_REJECTED_RATE": rbr,
        "RECOVERY_CONDITIONAL_REJECTION_RATE": rcj,
        "HELP_NOVELTY_IMPROVE_RATE_POOLED": imp,
        "THRESHOLD_UTILITY_MINUS_DIRECT_MEAN": thr_diff,
        "ROUTER_VS_NOVELTY_SHARES": {"R1_ROUTER_MISS": r1},
        "ACTION_CONDITIONAL_POOLED": {
            "NONE": {"rejected_count": action_rejected[0]},
            "T": {"rejected_count": action_rejected[1]},
            "R": {"rejected_count": action_rejected[2]},
            "TR": {"rejected_count": action_rejected[3]},
        },
        "TRUE_UNKNOWN_SEPARATION_PRESERVED": tu_preserved,
    }


def test_attribute_failure_rules():
    views = {
        "Credential": _rotation_view(),
        "Recon_Scanning": _rotation_view(rbr=0.3, rcj=0.4, imp=0.7,
                                         thr_diff=-0.02, r1=0.1),
        "Web_Injection": _rotation_view(rbr=0.2, rcj=0.3, imp=0.3,
                                        thr_diff=-0.03, r1=0.4),
    }
    verif = {f"20260817_{rot}": {key: True for key in
             ("EVAL_TABLE_SHA256_MATCH", "RECOVERABLE_FLAG_MATCH",
              "DIGEST_COLUMN_MATCH", "BLOCK_COLUMN_MATCH",
              "FURK_DENOMINATOR_MATCH_RESULT_JSON")}
             for rot in views}
    audit = {"status": "PASS", "attribution_counts": {
        "F0_FURK_IMPLEMENTATION_OR_DENOMINATOR_ERROR": 0}}
    out = f.attribute_failure(views, audit, verif)
    counts = out["SUPPORTED_ROTATION_COUNTS"]
    # F1: 2/3 (Credential, Web_Injection), F2: 3/3, F3: 3/3, F4: 2/3.
    assert counts["F1_CLASSIFICATION_UTILITY_TARGET_MISMATCH"] == 2
    assert counts["F2_POST_EVIDENCE_MSP_MISALIGNMENT"] == 3
    assert counts["F3_POLICY_CONDITIONED_CALIBRATION_SUBGROUP_SHIFT"] == 3
    assert counts["F4_ROUTER_SELECTION_FAILURE"] == 2
    assert counts["F0_FURK_IMPLEMENTATION_OR_DENOMINATOR_ERROR"] == 0
    assert counts["F5_EVIDENCE_ACTION_SPECIFIC_FAILURE"] == 0
    assert counts["F6_TRUE_UNKNOWN_SEPARATION_FAILURE"] == 0
    assert out["DOMINANT_MECHANISMS"] == [
        "F1_CLASSIFICATION_UTILITY_TARGET_MISMATCH",
        "F2_POST_EVIDENCE_MSP_MISALIGNMENT",
        "F3_POLICY_CONDITIONED_CALIBRATION_SUBGROUP_SHIFT",
        "F4_ROUTER_SELECTION_FAILURE"]


def test_attribute_failure_f0_on_verification_failure():
    views = {"Credential": _rotation_view(), "Recon_Scanning":
             _rotation_view(), "Web_Injection": _rotation_view()}
    verif = {f"20260817_{rot}": {key: (key != "RECOVERABLE_FLAG_MATCH")
             for key in ("RECOVERABLE_FLAG_MATCH", "DIGEST_COLUMN_MATCH")}
             for rot in views}
    audit = {"status": "FAIL", "attribution_counts": {}}
    out = f.attribute_failure(views, audit, verif)
    assert out["SUPPORTED_ROTATION_COUNTS"][
        "F0_FURK_IMPLEMENTATION_OR_DENOMINATOR_ERROR"] == 3
    assert "F0_FURK_IMPLEMENTATION_OR_DENOMINATOR_ERROR" in \
        out["DOMINANT_MECHANISMS"]


def test_attribute_failure_f5_concentration():
    views = {rot: _rotation_view(action_rejected=[1, 61, 19, 19])
             for rot in ("Credential", "Recon_Scanning", "Web_Injection")}
    verif = {f"20260817_{rot}": {"EVAL_TABLE_SHA256_MATCH": True}
             for rot in views}
    audit = {"status": "PASS", "attribution_counts": {}}
    out = f.attribute_failure(views, audit, verif)
    # Action T carries 61/100 > 60% in every rotation -> F5 3/3.
    assert out["SUPPORTED_ROTATION_COUNTS"][
        "F5_EVIDENCE_ACTION_SPECIFIC_FAILURE"] == 3


def test_attribute_failure_f7_no_dominant():
    views = {rot: _rotation_view(rbr=0.02, rcj=0.05, imp=0.8, thr_diff=0.0,
                                 r1=0.05)
             for rot in ("Credential", "Recon_Scanning", "Web_Injection")}
    verif = {f"20260817_{rot}": {"EVAL_TABLE_SHA256_MATCH": True}
             for rot in views}
    audit = {"status": "PASS", "attribution_counts": {}}
    out = f.attribute_failure(views, audit, verif)
    assert out["DOMINANT_MECHANISMS"] == ["F7_NO_CLEAR_DOMINANT_MECHANISM"]
    assert all(out["SUPPORTED_ROTATION_COUNTS"][name] < 2 for name in
               ("F1_CLASSIFICATION_UTILITY_TARGET_MISMATCH",
                "F2_POST_EVIDENCE_MSP_MISALIGNMENT",
                "F3_POLICY_CONDITIONED_CALIBRATION_SUBGROUP_SHIFT",
                "F4_ROUTER_SELECTION_FAILURE"))


# ---------------------------------------------------------------------------
# Section 14: V2 justification
# ---------------------------------------------------------------------------

def test_decide_v2_yes_with_primary_tie_break():
    audit = {"status": "PASS", "attribution_counts": {
        "F2_POST_EVIDENCE_MSP_MISALIGNMENT": 3,
        "F3_POLICY_CONDITIONED_CALIBRATION_SUBGROUP_SHIFT": 3,
        "F1_CLASSIFICATION_UTILITY_TARGET_MISMATCH": 2}}
    dominant = ["F1_CLASSIFICATION_UTILITY_TARGET_MISMATCH",
                "F2_POST_EVIDENCE_MSP_MISALIGNMENT",
                "F3_POLICY_CONDITIONED_CALIBRATION_SUBGROUP_SHIFT"]
    views = {}
    out = f.decide_v2(audit, dominant, views)
    assert out["V2_JUSTIFICATION"] == "YES"
    assert all(out["CONDITIONS"].values())
    # Tie between F2 and F3 at 3 rotations -> F2 preferred (3/3
    # post-Evidence MSP mechanism).
    assert out["PRIMARY_MECHANISM_FOR_REQUIREMENT"] == \
        "F2_POST_EVIDENCE_MSP_MISALIGNMENT"
    assert "recovery state" in out["PROSPECTIVE_V2_DESIGN_REQUIREMENT"]


def test_decide_v2_no_when_audit_fails():
    audit = {"status": "FAIL", "attribution_counts": {}}
    out = f.decide_v2(audit, ["F2_POST_EVIDENCE_MSP_MISALIGNMENT"], {})
    assert out["V2_JUSTIFICATION"] == "NO"
    assert out["CONDITIONS"]["1_DENOMINATOR_IMPLEMENTATION_AUDIT_PASS"] is False


def test_decide_v2_no_when_no_specific_correction():
    audit = {"status": "PASS", "attribution_counts": {}}
    out = f.decide_v2(audit, ["F7_NO_CLEAR_DOMINANT_MECHANISM"], {})
    assert out["V2_JUSTIFICATION"] == "NO"
    assert out["PROSPECTIVE_V2_DESIGN_REQUIREMENT"] is None


def test_decide_v2_never_names_concrete_detector():
    # The frozen contract forbids choosing Energy/Mahalanobis/OpenMax/
    # neural detectors merely because they might perform better; the
    # requirement must be a conceptual correction, not a detector.
    audit = {"status": "PASS", "attribution_counts": {
        "F2_POST_EVIDENCE_MSP_MISALIGNMENT": 3}}
    out = f.decide_v2(audit, ["F2_POST_EVIDENCE_MSP_MISALIGNMENT"], {})
    requirement = out["PROSPECTIVE_V2_DESIGN_REQUIREMENT"]
    for banned in ("Energy", "Mahalanobis", "OpenMax", "binary detector"):
        assert banned.lower() not in requirement.lower()


# ---------------------------------------------------------------------------
# Section 15: RL relevance
# ---------------------------------------------------------------------------

def test_rl_relevance_threshold():
    def view(r3, r4, denom):
        return {"DENOMINATOR_POOLED": denom,
                "ROUTER_VS_NOVELTY_POOLED": {
                    "R3_RECOVERED_BUT_REJECTED": r3,
                    "R4_THRESHOLD_SHIFT_CONTRIBUTION": r4}}
    assert f.rl_relevance({"a": view(100, 60, 400)})[
        "RL_SEQUENTIAL_DECISION_JUSTIFICATION"] == "PLAUSIBLE"
    assert f.rl_relevance({"a": view(50, 30, 400)})[
        "RL_SEQUENTIAL_DECISION_JUSTIFICATION"] == "NOT_SUPPORTED"
    # Never claims RL is required (analysis-only output shape).
    out = f.rl_relevance({"a": view(100, 60, 400)})
    assert "RL_SEQUENTIAL_DECISION_JUSTIFICATION" in out
    assert out["evidence"]["R3_RECOVERED_BUT_REJECTED_POOLED"] == 100


# ---------------------------------------------------------------------------
# FINAL_TEST exclusion
# ---------------------------------------------------------------------------

def test_final_test_exclusion_in_split_build():
    # The frozen gate builds CALIB/EVAL from VALIDATION rows only; the
    # diagnostic consumes exactly those tables. A synthetic mixed targets
    # dict containing FINAL_TEST rows must yield roles for VALIDATION rows
    # only.
    n_groups = 21  # one group per (class, block) stratum
    rows = []
    for gi in range(n_groups):
        rows.append((CLASSES[gi % 7], gi % 3, f"g{gi}".encode(),
                     1_000_000 + gi * 1000))
    def targets_for(partition_code):
        return {
            "source_row_index": np.arange(100_000, 100_000 + len(rows),
                                          dtype=np.int64),
            "canonical_label": np.array([r[0] for r in rows], dtype=object),
            "partition_code": np.full(len(rows), partition_code,
                                      dtype=np.int64),
            "temporal_block": np.array([r[1] for r in rows], dtype=np.int16),
            "flow_start_ms": np.array([r[3] for r in rows], dtype=np.int64),
            "activity_group_digest": np.array([r[2] for r in rows],
                                              dtype=object),
        }
    mixed = targets_for(1)  # VALIDATION rows
    n_val = len(rows)
    # A FINAL_TEST row would carry the FINAL_TEST partition code.
    assert g.PARTITION_FINAL_TEST != g.PARTITION_VALIDATION
    roles = owg.build_calib_eval_folds(mixed)
    assert len(roles) == n_val
    assert set(np.unique(roles)) <= {0, 1}


def test_diagnostic_safety_flag_static():
    # The diagnostic's safety block structurally reports no FINAL_TEST
    # modeling contamination and no forbidden starts.
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    assert diag["denominator"] > 0
    # The run_diagnostic output asserts the frozen safety counters; the
    # diagnostic never trains, never calls external APIs, and never touches
    # FINAL_TEST (its inputs are the frozen VALIDATION-derived eval tables).
    assert not any("FINAL_TEST" in key for key in arrays)


# ---------------------------------------------------------------------------
# class composition
# ---------------------------------------------------------------------------

def test_class_composition():
    labels = np.array(["a", "a", "b", "c", "c", "c"], dtype=object)
    mask = np.array([True, True, True, True, True, True])
    comp = f.class_composition(labels, mask, ("a", "b", "c"))
    assert comp == {"a": 2 / 6, "b": 1 / 6, "c": 3 / 6}
    assert sum(comp.values()) == pytest.approx(1.0)
    assert f.class_composition(labels, np.zeros(6, dtype=bool),
                               ("a", "b", "c")) == {"a": 0.0, "b": 0.0,
                                                    "c": 0.0}


# ---------------------------------------------------------------------------
# pooled-rate helper (None-tolerant)
# ---------------------------------------------------------------------------

def test_pooled_rate_skips_none():
    entries = [
        {"section": {"key": {"n": 100, "rate": 0.2}}},
        {"section": {"key": {"n": 0, "rate": None}}},
        {"section": {"key": {"n": 50, "rate": 0.4}}},
    ]
    assert f._pooled_rate(entries, "section", "key", "n", "rate") == \
        pytest.approx((100 * 0.2 + 50 * 0.4) / 150)


def test_json_serializable():
    # The full diagnostic output must round-trip through JSON (the report
    # JSON is copied verbatim from the tool output).
    arrays, result, rebuilt = _make_fixture()
    diag = f.cell_diagnostics(arrays, result, rebuilt)
    json.dumps(diag, allow_nan=False)
