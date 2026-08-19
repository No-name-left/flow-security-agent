"""Synthetic-only tests for the frozen Strong Hybrid OSR Evidence Gate V2.

Phase B constraint: NO real evaluation metrics. Everything here runs on
tiny synthetic fixtures. Covers:
  - preregistration manifest (tool constants == frozen preregistration JSON)
  - protocol sha256 consistency
  - hybrid metric helpers (accept-correct, FURK, AUROC/AUPR/recall)
  - policy state mapping for D0/D1/D2/D3
  - bootstrap CI consistency (paired FURK, specificity gap)
  - decision matrix logic
  - determinism settings recorded and applied
  - smoke mode end-to-end
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

torch = pytest.importorskip("torch")

import run_strong_hybrid_osr_evidence_gate_v2 as v2  # noqa: E402


def _load_preregistration() -> dict:
    return json.loads(
        (REPO / "reports" / "research_audit" /
         "strong_hybrid_osr_evidence_gate_v2_preregistration.json"
         ).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Preregistration consistency
# ---------------------------------------------------------------------------

def test_tool_constants_match_preregistration():
    reg = _load_preregistration()
    assert v2.H1_TOL == reg["adequacy"]["h1_tolerance"]
    assert v2.H2_POOLED_DELTA == reg["adequacy"]["h2_pooled_delta"]
    assert v2.H2_ROTATION_FLOOR == reg["adequacy"]["h2_rotation_floor"]
    assert v2.H3_POOLED_DELTA == reg["adequacy"]["h3_pooled_delta"]
    assert v2.H4_POOLED_MEAN_MIN == reg["adequacy"]["h4_pooled_mean_min"]
    assert v2.H4_CI_LOWER_MIN == reg["adequacy"]["h4_ci_lower_min"]
    assert v2.D1_POOLED_FURK_DELTA_MAX == \
        reg["deployable"]["d1_pooled_furk_delta_max"]
    assert v2.D1_ROTATION_WORST == reg["deployable"]["d1_rotation_worst"]
    assert v2.D3_AUROC_POOLED_LOSS_MAX == \
        reg["deployable"]["d3_auroc_pooled_loss_max"]
    assert v2.D4_RECALL_POOLED_LOSS_MAX == \
        reg["deployable"]["d4_recall_pooled_loss_max"]
    assert v2.D5_F1_POOLED_LOSS_MAX == \
        reg["deployable"]["d5_f1_pooled_loss_max"]
    assert v2.R1_POOLED_RATE_MIN == reg["recovery"]["r1_pooled_rate_min"]
    assert v2.R2_ROTATION_RATE_MIN == reg["recovery"]["r2_rotation_rate_min"]
    assert v2.ROUTER_HEADROOM_RECOVERY_RATE_MAX == \
        reg["decision"]["router_headroom_recovery_rate_max"]
    assert v2.CALIB_KNOWN_FALSE_UNKNOWN_RATE == 0.05
    assert list(v2.ROTATIONS) == ["Credential", "Recon_Scanning",
                                  "Web_Injection"]
    assert list(v2.FORMAL_SEEDS) == [20260817, 20260818, 20260819]


def test_protocol_sha256_matches_preregistration():
    reg = _load_preregistration()
    path = REPO / reg["protocol_path"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == reg["protocol_sha256"]
    assert reg["protocol_status"] == "FROZEN_BEFORE_EVALUATION"


def test_determinism_settings_recorded():
    settings = v2.set_determinism()
    assert settings["cudnn_deterministic"] is True
    assert settings["cudnn_benchmark"] is False
    assert settings["dataloader_workers"] == 0
    assert torch.backends.cudnn.deterministic is True
    assert torch.backends.cudnn.benchmark is False


# ---------------------------------------------------------------------------
# Hybrid helpers
# ---------------------------------------------------------------------------

def test_hybrid_bc_rows_on_synthetic_cell():
    from run_strong_neural_osr_evidence_gate_v1 import known_classes_for
    rng = np.random.default_rng(19)
    known = known_classes_for("Credential")
    n = 400
    cell = {
        "ev_labels": np.array([known[i % 6] for i in range(n)],
                              dtype=object),
        "ev_is_unknown": np.zeros(n, dtype=bool),
        "ev_recoverable": np.zeros(n, dtype=bool),
        "ev_groups": np.array([hashlib.sha256(f"g{i % 40}".encode()).digest()
                               for i in range(n)], dtype=object),
        "ev_split_role": np.ones(n, dtype=np.int64),
    }
    # One-hot class pattern in the first 6 feature columns so the fake RF
    # recovers the true class of each row from the matrix itself.
    onehot = np.zeros((n, 6))
    onehot[np.arange(n), np.arange(n) % 6] = 1.0

    def _feat(width):
        mat = rng.standard_normal((n, width))
        mat[:, :6] = onehot
        return mat
    cell["features_ev"] = {"B": _feat(47), "BT": _feat(63),
                           "BR": _feat(65), "BTR": _feat(81)}
    cell["ev_recoverable"][50:150] = True
    # Fake RF models: class read back from the one-hot columns -> always
    # correct on this fixture.
    class FakeModel:
        def predict(self, matrix):
            idx = np.argmax(matrix[:, :6], axis=1)
            return np.array([known[i] for i in idx], dtype=object)
    models = {s: FakeModel() for s in v2.EVIDENCE_STATES}
    # Scores: Basic high (rejected) for recoverable rows, legal states low.
    scores = {s: rng.random(n) for s in v2.EVIDENCE_STATES}
    for s in ("BT", "BR", "BTR"):
        scores[s][50:150] *= 0.1
    thresholds = {s: 0.5 for s in v2.EVIDENCE_STATES}
    bc, row_data = v2.hybrid_bc_rows(cell, models, scores, thresholds)
    assert bc["recovery"]["best_legal_accept_correct_rate"] > 0.9
    assert bc["recovery"]["basic_accept_correct_rate"] < 0.5
    assert row_data["rec_best"].sum() > 80


def test_metric_helpers():
    rng = np.random.default_rng(23)
    known = rng.random(1000) * 0.4
    unknown = 0.4 + rng.random(500) * 0.6
    assert v2.known_unknown_auroc(known, unknown) > 0.9
    assert v2.known_unknown_aupr(known, unknown) > 0.9
    recall = v2.recall_at_5fur(known, unknown)
    assert 0.0 <= recall <= 1.0
    rejected = np.array([True] * 60 + [False] * 140)
    recoverable = np.array([True] * 100 + [False] * 100)
    furk, numer, denom = v2.furk_of(rejected, recoverable)
    assert furk == pytest.approx(0.6) and denom == 100


def test_policy_state_mapping():
    rng = np.random.default_rng(29)
    cell = {
        "ev_labels": np.zeros(50, dtype=object),
        "ev_action_p6": np.array(["NONE", "T", "R", "TR"] * 12 +
                                 ["NONE", "T"], dtype=object),
        "seed": 20260817, "rotation": "Credential",
    }
    d0 = v2.policy_states(cell, "D0_BASIC")
    assert set(d0) == {"B"}
    d1 = v2.policy_states(cell, "D1_P6_SELECTIVE")
    assert d1[0] == "B" and d1[1] == "BT" and d1[2] == "BR" and d1[3] == "BTR"
    d2 = v2.policy_states(cell, "D2_ALWAYS_FULL")
    assert set(d2) == {"BTR"}
    d3 = v2.policy_states(cell, "D3_RANDOM_COST_MATCHED")
    assert set(d3) <= {"B", "BT"} and (d3 == "BT").sum() > 0


def test_paired_furk_ci_consistency(tmp_path):
    (tmp_path / "cells").mkdir()
    rng = np.random.default_rng(31)
    for seed in v2.FORMAL_SEEDS:
        for rot in v2.ROTATIONS:
            n = 2000
            groups = rng.integers(0, 200, size=n)
            is_unk = np.zeros(n, dtype=bool)
            role = np.zeros(n, dtype=np.int64)
            role[:600] = 0
            role[600:] = 1
            rec = np.zeros(n, dtype=bool)
            rec[600:750] = True
            s0 = rng.random(n)
            s1 = s0 - 0.25 * rec + 0.01 * rng.random(n)
            key = v2.cell_key(seed, rot)
            (tmp_path / "cells" / key).mkdir()
            np.savez_compressed(tmp_path / "cells" / key / "rows.npz",
                                groups=groups, is_unknown=is_unk,
                                split_role=role, recoverable=rec,
                                score_d0=s0, score_d1=s1,
                                allow_pickle=False)
    mean, lo, hi = v2._furk_paired_ci_v2(tmp_path)
    assert lo <= mean <= hi
    assert mean < 0  # D1 scores reduced for recoverable rows -> FURK drops


def test_specificity_ci_consistency(tmp_path):
    (tmp_path / "cells").mkdir()
    rng = np.random.default_rng(37)
    for seed in v2.FORMAL_SEEDS:
        for rot in v2.ROTATIONS:
            rk_groups = rng.integers(0, 100, size=500)
            tu_groups = rng.integers(0, 50, size=300)
            rk_gain = 0.5 + 0.1 * rng.random(500)
            tu_gain = 0.05 * rng.random(300)
            key = v2.cell_key(seed, rot)
            (tmp_path / "cells" / key).mkdir()
            np.savez_compressed(tmp_path / "cells" / key / "bc_rows.npz",
                                rk_groups=rk_groups, rk_gain=rk_gain,
                                tu_groups=tu_groups, tu_gain=tu_gain,
                                rec_basic=np.zeros(500, dtype=bool),
                                rec_best=np.ones(500, dtype=bool),
                                allow_pickle=False)
    mean, lo, hi = v2._specificity_ci(tmp_path)
    assert lo <= mean <= hi
    assert mean > 0.3  # large positive gap on this fixture


def test_decision_matrix_logic():
    assert v2._decide_v2(False, True, True, True, True) == \
        "GATE_INVALID_OSR_INADEQUATE"
    assert v2._decide_v2(True, True, True, True, True) == "GO"
    assert v2._decide_v2(True, True, True, False, True) == \
        "GO_SIGNAL_EXISTS_ROUTER_LIMITED"
    assert v2._decide_v2(True, True, True, False, False) == \
        "METHOD_DEPENDENT_REVIEW"
    assert v2._decide_v2(True, False, True, True, True) == \
        "NO_GO_CURRENT_EVIDENCE_CONTRACT"
    assert v2._decide_v2(True, True, False, True, True) == \
        "NO_GO_CURRENT_EVIDENCE_CONTRACT"


def test_rf_predict_state_shapes():
    from run_strong_neural_osr_evidence_gate_v1 import known_classes_for
    known = known_classes_for("Credential")
    rng = np.random.default_rng(41)
    n = 40
    feats = {
        "B": rng.standard_normal((n, 47)),
        "BT": rng.standard_normal((n, 63)),
        "BR": rng.standard_normal((n, 65)),
        "BTR": rng.standard_normal((n, 81)),
    }

    class FakeModel:
        def predict(self, matrix):
            return np.array([known[i % 6] for i in range(len(matrix))],
                            dtype=object)
    models = {s: FakeModel() for s in v2.EVIDENCE_STATES}
    for state in v2.EVIDENCE_STATES:
        preds = v2.rf_predict_state(models, feats, state, np.arange(10))
        assert len(preds) == 10
        assert set(preds) <= set(known)


def test_smoke_mode_runs_end_to_end():
    import argparse
    args = argparse.Namespace(mode="smoke")
    assert v2.run_smoke(args) == 0
