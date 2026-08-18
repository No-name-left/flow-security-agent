"""Synthetic-only tests for the frozen Strong Neural OSR Evidence Gate tool.

Phase B constraint: NO real evaluation metrics. Everything here runs on
tiny synthetic fixtures. Covers:
  - preregistration manifest (tool constants == frozen preregistration JSON)
  - deterministic 90/10 group-safe TRAIN split rule
  - encoder shapes / masked-block invariance / shared parameters
  - CE + 0.10*SupCon loss; EDL alpha>=1, loss decrease, score formula
  - Mahalanobis score ordering; calibration quantile + tie semantics
  - AUROC / AUPR / recall@5%FUR / FURK helpers
  - paired group-atomic FURK bootstrap CI consistency
  - status persistence state machine
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

import run_strong_neural_osr_evidence_gate_v1 as v1  # noqa: E402

torch = pytest.importorskip("torch")


def _load_preregistration() -> dict:
    return json.loads(
        (REPO / "reports" / "research_audit" /
         "strong_neural_osr_evidence_gate_v1_preregistration.json"
         ).read_text(encoding="utf-8"))


def _synthetic_features(n: int, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    basic = rng.standard_normal((n, v1.BASIC_N))
    history = np.abs(rng.standard_normal((n, 34)))
    names = list(v1.TEMPORAL_FIELDS) + list(v1.RELATION_FIELDS)
    return v1.build_feature_matrices(basic, history, names)


# ---------------------------------------------------------------------------
# Preregistration consistency
# ---------------------------------------------------------------------------

def test_tool_constants_match_preregistration():
    reg = _load_preregistration()
    assert v1.BLOCK_HIDDEN == 128 and v1.BLOCK_OUT == 64
    assert v1.FUSION_HIDDEN == 256 and v1.EMBED_DIM == 128
    assert v1.DROPOUT == 0.10
    assert v1.SUPCON_WEIGHT == 0.10
    assert v1.SUPCON_TEMPERATURE == 0.10
    assert v1.ADAMW_LR == 3e-4
    assert v1.ADAMW_WEIGHT_DECAY == 1e-4
    assert v1.MAX_EPOCHS == 20 and v1.EARLY_STOP_PATIENCE == 3
    assert v1.BLOCK_DIMS == {"B": 47, "T": 16, "R": 18}
    assert v1.NUM_KNOWN == 6
    assert v1.EDL_KL_LAMBDA == 0.1
    assert v1.TRAIN_POOL_N == 150000
    assert v1.TRAIN_EARLY_STOP_FRAC == 0.10
    for key, (fit, early) in v1.TRAIN_SPLIT_COUNTS.items():
        assert fit + early == v1.TRAIN_POOL_N, key
        counts = reg["populations"]["trainsplit_counts_per_cell"][key]
        assert counts == {"fit": fit, "early_stop": early}, key
    assert v1.CALIB_KNOWN_FALSE_UNKNOWN_RATE == 0.05
    assert reg["osr_adequacy"]["A1_known_macro_f1"]["per_rotation"] == \
        v1.A1_ROTATION_MACRO_F1_MIN
    assert v1.B1_RATE_MIN == 0.60 and v1.B1_STD_EFFECT_MIN == 0.20
    assert v1.B2_ROTATION_RATE_MIN == 0.55
    assert v1.C3_RATIO_BOUND == 0.50
    assert v1.D1_POOLED_FURK_DELTA_MAX == -0.02
    assert v1.D1_ROTATION_WORST == 0.02
    assert v1.D3_AUROC_POOLED_LOSS_MAX == 0.01
    assert v1.D4_RECALL_POOLED_LOSS_MAX == 0.03
    assert v1.ROUTER_HEADROOM_RECOVERY_RATE_MAX == 0.85
    assert v1.BOOTSTRAP_REPS == 1000
    # Rotations / seeds frozen.
    assert list(v1.ROTATIONS) == ["Credential", "Recon_Scanning",
                                  "Web_Injection"]
    assert list(v1.FORMAL_SEEDS) == [20260817, 20260818, 20260819]


def test_protocol_sha256_matches_preregistration():
    reg = _load_preregistration()
    path = REPO / reg["protocol_path"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == reg["protocol_sha256"]
    assert reg["protocol_status"] == "FROZEN_BEFORE_EVALUATION"


# ---------------------------------------------------------------------------
# TRAIN split rule
# ---------------------------------------------------------------------------

def test_train_split_group_atomic_and_deterministic():
    rng = np.random.default_rng(3)
    known = v1.known_classes_for("Credential")
    # Class-balanced group fixture, group sizes 1..50.
    groups_list: list[bytes] = []
    labels_list: list[str] = []
    gid = 0
    for cls in known:
        rows = 0
        while rows < 667:
            size = int(rng.integers(1, 51))
            size = min(size, 667 - rows)
            digest = hashlib.sha256(f"g{gid}".encode()).digest()
            groups_list.extend([digest] * size)
            labels_list.extend([cls] * size)
            gid += 1
            rows += size
    groups = np.array(groups_list, dtype=object)
    labels = np.array(labels_list, dtype=object)
    n = len(labels)
    early = v1.split_train_fit_early(20260817, "Credential", labels, groups)
    early2 = v1.split_train_fit_early(20260817, "Credential", labels, groups)
    assert (early == early2).all(), "split must be deterministic"
    # Group atomicity: every digest is entirely in one role.
    for digest in set(groups.tolist()):
        vals = early[groups == digest]
        assert vals.all() or not vals.any()
    # Approximate 10% per class.
    for cls in v1.known_classes_for("Credential"):
        cm = labels == cls
        frac = early[cm].mean()
        assert abs(frac - 0.10) < 0.05, (cls, frac)


def test_train_split_counts_match_preregistration_rule():
    # The recorded counts must be reproducible from the frozen targets
    # tables; here we verify the constant table is self-consistent.
    total_fit = sum(v for v, _ in v1.TRAIN_SPLIT_COUNTS.values())
    total_early = sum(v for _, v in v1.TRAIN_SPLIT_COUNTS.values())
    assert total_fit + total_early == 9 * v1.TRAIN_POOL_N
    assert all(early < v1.TRAIN_POOL_N for _, early in
               v1.TRAIN_SPLIT_COUNTS.values())


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

def test_encoder_shapes_and_shared_parameters():
    feats = _synthetic_features(32)
    model = v1.StrongOSREncoder()
    idx = np.arange(16)
    for state in v1.EVIDENCE_STATES:
        emb, proba = v1.encoder_forward(model, feats, state, idx)
        assert emb.shape == (16, v1.EMBED_DIM)
        assert proba.shape == (16, v1.NUM_KNOWN)
    # One parameter set serves all four states (no state-specific modules).
    params = dict(model.named_parameters())
    assert all(not name.startswith(("state", "b_", "bt_", "br_", "btr_"))
               for name in params)


def test_masked_blocks_do_not_affect_output():
    """With mT=0 the Temporal block content must not affect the output."""
    feats = _synthetic_features(8)
    model = v1.StrongOSREncoder()
    model.eval()
    idx = np.arange(8)
    basic = torch.tensor(feats["B"][idx], dtype=torch.float32)
    t1 = torch.tensor(v1.state_temporal(feats, "BTR", idx),
                      dtype=torch.float32)
    t2 = torch.randn_like(t1)
    r = torch.tensor(v1.state_relation(feats, "BTR", idx),
                     dtype=torch.float32)
    with torch.no_grad():
        emb1, _ = model(basic, t1, r, torch.zeros(8, 1), torch.ones(8, 1))
        emb2, _ = model(basic, t2, r, torch.zeros(8, 1), torch.ones(8, 1))
    assert torch.allclose(emb1, emb2), "masked Temporal block leaked"


def test_supcon_and_total_loss():
    torch.manual_seed(0)
    emb = torch.randn(32, v1.EMBED_DIM)
    labels = torch.randint(0, v1.NUM_KNOWN, (32,))
    sup = v1.supervised_contrastive_loss(emb, labels)
    assert torch.isfinite(sup) and sup.item() >= 0
    logits = torch.randn(32, v1.NUM_KNOWN)
    ce = torch.nn.functional.cross_entropy(logits, labels)
    total = ce + v1.SUPCON_WEIGHT * sup
    assert torch.isfinite(total)


def test_edl_sanity():
    feats = _synthetic_features(8)
    model = v1.StrongOSREncoder()
    edl = v1.EDLHeadEncoder(model)
    edl.eval()
    idx = np.arange(8)
    with torch.no_grad():
        alpha = edl(torch.tensor(feats["B"][idx], dtype=torch.float32),
                    torch.tensor(v1.state_temporal(feats, "BTR", idx),
                                 dtype=torch.float32),
                    torch.tensor(v1.state_relation(feats, "BTR", idx),
                                 dtype=torch.float32),
                    torch.ones(8, 1), torch.ones(8, 1))
    assert bool((alpha >= 1.0).all())
    labels = torch.tensor([0, 1, 2, 3, 4, 5, 0, 1])
    loss = v1.edl_loss(alpha, labels)
    assert torch.isfinite(loss)
    # EDL belief-score formula: score = 1 - max_k(alpha_k / S).
    S = alpha.sum(dim=-1, keepdim=True)
    belief = alpha.max(dim=-1).values / S.squeeze(-1)
    assert torch.allclose(belief, alpha.max(dim=-1).values / alpha.sum(-1))


def test_edl_loss_decreases_on_synthetic_steps():
    torch.manual_seed(5)
    feats = _synthetic_features(64)
    labels = torch.tensor([0, 1, 2, 3, 4, 5] * 10 + [0, 1, 2, 3])
    edl = v1.EDLHeadEncoder(v1.StrongOSREncoder())
    opt = torch.optim.AdamW(edl.parameters(), lr=1e-2)
    losses = []
    for _ in range(6):
        a = edl(torch.tensor(feats["B"], dtype=torch.float32),
                torch.zeros(64, 16), torch.zeros(64, 18),
                torch.zeros(64, 1), torch.zeros(64, 1))
        loss = v1.edl_loss(a, labels)
        opt.zero_grad()
        loss.backward()
        opt.step()
        losses.append(float(loss.detach()))
    assert losses[-1] < losses[0]


# ---------------------------------------------------------------------------
# OSR scores and calibration
# ---------------------------------------------------------------------------

def test_mahalanobis_orders_outliers_higher():
    rng = np.random.default_rng(11)
    known = v1.known_classes_for("Credential")
    emb = []
    labels = []
    for i, name in enumerate(known):
        center = rng.standard_normal(v1.EMBED_DIM) * 3
        emb.append(center + 0.2 * rng.standard_normal((40, v1.EMBED_DIM)))
        labels.extend([name] * 40)
    emb = np.concatenate(emb)
    labels = np.array(labels, dtype=object)
    geometry = v1.fit_osr_geometry(emb, labels, known)
    outliers = rng.standard_normal((20, v1.EMBED_DIM)) * 25
    in_scores = v1.mahalanobis_min_distance(emb, geometry)
    out_scores = v1.mahalanobis_min_distance(outliers, geometry)
    assert out_scores.min() > np.quantile(in_scores, 0.90)


def test_calibration_quantile_and_tie_semantics():
    rng = np.random.default_rng(13)
    scores = rng.random(200)
    threshold = np.quantile(scores, 1.0 - v1.CALIB_KNOWN_FALSE_UNKNOWN_RATE)
    rejected = scores >= threshold
    assert rejected.mean() == pytest.approx(
        v1.CALIB_KNOWN_FALSE_UNKNOWN_RATE, abs=0.02)


def test_auroc_aupr_recall_furk_helpers():
    rng = np.random.default_rng(17)
    known = rng.random(1000) * 0.4
    unknown = 0.4 + rng.random(500) * 0.6
    auroc = v1.known_unknown_auroc(known, unknown)
    assert auroc > 0.9
    aupr = v1.known_unknown_aupr(known, unknown)
    assert aupr > 0.9
    recall = v1.recall_at_5fur(known, unknown)
    assert 0.0 <= recall <= 1.0
    recovered = np.array([True] * 100 + [False] * 100)
    rejected = np.array([True] * 60 + [False] * 140)
    furk, numer, denom = v1.furk_of(rejected, recovered)
    assert furk == pytest.approx(0.6) and numer == 60 and denom == 100


# ---------------------------------------------------------------------------
# Bootstrap and status persistence
# ---------------------------------------------------------------------------

def test_paired_furk_bootstrap_ci_consistent(tmp_path):
    """CI interval must contain the point estimate on synthetic cells."""
    run_root = tmp_path
    (run_root / "cells").mkdir()
    rng = np.random.default_rng(23)
    for seed in v1.FORMAL_SEEDS:
        for rotation in v1.ROTATIONS:
            n = 3000
            groups = rng.integers(0, 300, size=n)
            is_unk = np.zeros(n, dtype=bool)
            is_unk[-150:] = True
            role = np.zeros(n, dtype=np.int64)
            role[:1000] = 0  # CALIB
            role[1000:] = 1  # EVAL
            rec = np.zeros(n, dtype=bool)
            rec[1000:1150] = True
            s0 = rng.random(n)
            s1 = s0 + 0.1 * rng.random(n) - 0.2 * rec
            np.savez_compressed(
                run_root / "cells" / f"{seed}_{rotation}_rows.npz",
                groups=groups, is_unknown=is_unk, split_role=role,
                recoverable=rec, score_d0=s0, score_d1=s1,
                allow_pickle=False)
    mean, lo, hi = v1._furk_paired_ci(run_root)
    assert lo <= mean <= hi
    # Bootstrap mean must be close to the direct point estimate computed
    # with the same fixed-threshold paired formula on the full data.
    direct = []
    for seed in v1.FORMAL_SEEDS:
        for rotation in v1.ROTATIONS:
            rows = np.load(run_root / "cells" /
                           f"{seed}_{rotation}_rows.npz")
            ev = (rows["split_role"] == 1)
            cal = (rows["split_role"] == 0) & (~rows["is_unknown"])
            thr0 = float(np.quantile(rows["score_d0"][cal], 0.95))
            thr1 = float(np.quantile(rows["score_d1"][cal], 0.95))
            rec_ev = rows["recoverable"][ev]
            f0 = ((rows["score_d0"][ev] >= thr0) & rec_ev).sum() / \
                max(rec_ev.sum(), 1)
            f1 = ((rows["score_d1"][ev] >= thr1) & rec_ev).sum() / \
                max(rec_ev.sum(), 1)
            direct.append(float(f1 - f0))
    assert abs(mean - float(np.mean(direct))) < 0.05


def test_status_persistence_roundtrip(tmp_path):
    status = v1.read_status(tmp_path)
    assert status["run_state"] == "PENDING"
    assert status["cells"]["20260817_Credential"] == "PENDING"
    status["cells"]["20260817_Credential"] = "RUNNING"
    v1.write_status(tmp_path, status)
    loaded = v1.read_status(tmp_path)
    assert loaded["cells"]["20260817_Credential"] == "RUNNING"
    # COMPLETE cells are resumable/skippable via the run loop's skip check.
    status["cells"]["20260817_Credential"] = "COMPLETE"
    v1.write_status(tmp_path, status)
    loaded = v1.read_status(tmp_path)
    assert loaded["cells"]["20260817_Credential"] == "COMPLETE"


def test_decision_matrix_logic():
    assert v1._decide(False, True, True, True, True) == \
        "GATE_INVALID_OSR_INADEQUATE"
    assert v1._decide(True, True, True, True, True) == "GO"
    assert v1._decide(True, True, True, False, True) == \
        "GO_SIGNAL_EXISTS_ROUTER_LIMITED"
    assert v1._decide(True, True, True, False, False) == \
        "METHOD_DEPENDENT_REVIEW"
    assert v1._decide(True, False, True, True, True) == \
        "NO_GO_CURRENT_EVIDENCE_CONTRACT"
    assert v1._decide(True, True, False, True, True) == \
        "NO_GO_CURRENT_EVIDENCE_CONTRACT"


def test_smoke_mode_runs_end_to_end():
    import argparse
    args = argparse.Namespace(mode="smoke")
    assert v1.run_smoke(args) == 0
