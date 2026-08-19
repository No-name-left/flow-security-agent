#!/usr/bin/env python3
"""RECOVERABILITY INFORMATION SUFFICIENCY GATE V1 — frozen runner.

Separates where an Evidence-conditioned open-world recovery failure would
live: (1) information insufficiency in the legal B/T/R observables,
(2) representation / Evidence-processing limitation, (3) open-world
learning / transfer limitation.

Frozen protocol:
  docs/research_plan/recoverability_information_sufficiency_gate_v1_protocol.md
  (STATUS=FROZEN 2026-08-19; sha256 asserted at startup == PROTOCOL_SHA256 ==
  preregistration["protocol_sha256"]).

Scope: diagnostic only; central seed 20260817 x 3 whole-class rotations;
probe A DIAGNOSTIC_SEPARABILITY (views RAW_LEGAL + STATE_TRANSITION) and
probe B KNOWN_ONLY_TRANSFER (RAW_LEGAL only); controls REAL / BASIC /
SHUFFLED / NULL_PRESENT; families RF / LR / fixed 2-layer MLP. 27 fits
(probe A 18 + probe B 9). No FINAL_TEST, no new detector, no deployable
method, no P6 retrain, no Qwen / Model B / RL / continual learning, no
modification of prior results.

Frozen artifacts (read-only, Git-external):
  open_world_recoverability_gate_v1/            eval parquets + models.pkl
  core_gate_v1/                                 master split + features
  strong_hybrid_osr_evidence_gate_v2/cells/     primary encoders model.pt
  strong_hybrid_osr_evidence_gate_v2/validation_v2/primary_replay/{rot}_maha.npz
  strong_hybrid_osr_evidence_gate_v2/validation_v2/safeguards/B_{rot}_scores.npz

The only "training" performed: the frozen B_EDL replay (identical V2 recipe,
rng offset RNG_BASE+200) and the 27 probe fits.

Run modes: formal (default) and --smoke (tiny non-scientific end-to-end).
Restartable: per-mode stage done markers under RUN/stages/; completed
stages are skipped on restart.

Outputs (Git-external):
  processed/dataset_v4_nf3_ton_v1/recoverability_information_sufficiency_gate_v1/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import torch  # noqa: F401 (torch seed used inside fits)

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    average_precision_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler  # noqa: E402
from scipy.stats import rankdata  # noqa: E402

import run_evidence_processing_method_dependence_diagnostic_v1 as diag  # noqa: E402
import run_open_world_recoverability_gate_v1 as owg  # noqa: E402
import run_strong_hybrid_osr_evidence_gate_v2 as v2  # noqa: E402
from run_core_hypothesis_gate_v1 import (  # noqa: E402
    PARTITION_TRAIN,
    build_feature_matrices,
)
from run_core_hypothesis_gate_v1b import (  # noqa: E402
    basic_matrix_for,
    load_basic_features,
    load_history_features,
    load_targets,
)
from run_strong_neural_osr_evidence_gate_v1 import (  # noqa: E402
    ADAMW_LR,
    ADAMW_WEIGHT_DECAY,
    BATCH_SIZE,
    EARLY_STOP_PATIENCE,
    EDLHeadEncoder,
    EVIDENCE_STATES,
    MAX_EPOCHS,
    RNG_BASE,
    ROTATIONS,
    StrongOSREncoder,
    assemble_cell,
    cell_key,
    cell_rng,
    class_codes,
    group_codes,
)
from verify_recoverability_gate_decision_tree import decision  # noqa: E402

# ---------------------------------------------------------------------------
# Frozen protocol identity (execution lock: tool == preregistration == file)
# ---------------------------------------------------------------------------
PROTOCOL_SHA256 = "bd614f046447ac3ed604de96da0e3aa2bcf9d4afc41fd4061d5c355a366ee1ce"
CENTRAL_SEED = 20260817

DATASET = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1")
RUN = DATASET / "recoverability_information_sufficiency_gate_v1"
OWG = DATASET / "open_world_recoverability_gate_v1"
GATE1 = DATASET / "core_gate_v1"
V2RUN = DATASET / "strong_hybrid_osr_evidence_gate_v2"
V2VAL = V2RUN / "validation_v2"

SHUF_RNG_OFFSET = 400                        # SHUFFLED permutations (frozen)
EDL_RETRAIN_RNG_OFFSET = 200                 # B_EDL replay (frozen)
BOOTSTRAP_RNG = 162600                       # np.random.default_rng (frozen)
ST_SPLIT_RNG_OFFSET = 600                    # MLP deterministic 90/10 split
ST_BATCH_RNG_OFFSET = 700                    # MLP batch order

BOOTSTRAP_REPS = 1000
MATERIALITY = 0.02
STRONG_FAMILIES = 2
ROT_OK_MIN = 2
RETENTION_THRESHOLD = 0.5
BOOTSTRAP_PCTS = (2.5, 97.5)
REDRAW_BOUND = 200

TRAIN_PARTITION_N = 175_000
VAL_N = 56_000
TRAIN_BUDGET_UNITS = 26_250              # floor(0.15 x 175,000), frozen §4
CALIB_FALSE_UNKNOWN_RATE = 0.05

REAL_REPRO_TOL = 1e-6                    # maha / EDL identity vs frozen npz
SHUF_MARGINAL_TOL = 1e-9
FURK_V2_TOL = 1e-6                       # vs V2 validation record (floats)

# Frozen §2 central-seed population table (verified, mandatory).
FROZEN_POP = {
    "Credential": {"rk0": 1292, "rk1": 1396, "tu0": 4426, "tu1": 3574},
    "Recon_Scanning": {"rk0": 552, "rk1": 453, "tu0": 3404, "tu1": 4596},
    "Web_Injection": {"rk0": 821, "rk1": 1053, "tu0": 4078, "tu1": 3922},
}
FROZEN_ROLE0_RANGE = (29_931, 31_435)
FROZEN_ROLE1_RANGE = (24_565, 26_069)

VIEWS = ("RAW", "ST")
CONDITIONS = ("REAL", "BASIC", "SHUFFLED", "NULL")
FAMILIES = ("RF", "LR", "MLP")

# Frozen §8 family configs (no search, no selection).
RF_CONFIG = dict(n_estimators=80, max_depth=20, min_samples_leaf=2,
                 class_weight="balanced_subsample", n_jobs=-1,
                 random_state=CENTRAL_SEED)
LR_CONFIG = dict(C=1.0, solver="lbfgs", max_iter=1000)
MLP_HIDDEN = 64

ACTION_MODEL = owg.ACTION_MODEL


# ---------------------------------------------------------------------------
# Determinism / markers / run state
# ---------------------------------------------------------------------------

def set_determinism() -> dict[str, Any]:
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("PYTHONHASHSEED_MUST_BE_0")
    return {"PYTHONHASHSEED": "0", "cudnn_benchmark": False,
            "cudnn_deterministic": True, "numpy_generators_only": True,
            "torch_manual_seed_per_fit": True, "dataloader_workers": 0}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def marker_path(mode: str, stage: str) -> Path:
    return RUN / "stages" / f"{mode}_{stage}_done.json"


def stage_done(mode: str, stage: str) -> bool:
    return marker_path(mode, stage).exists()


def mark_stage(mode: str, stage: str, payload: dict[str, Any]) -> None:
    marker_path(mode, stage).write_text(
        json.dumps({"stage": stage, **payload}, indent=1), encoding="utf-8")


def write_run_state(status: str, mode: str, extra: dict[str, Any] | None = None
                    ) -> None:
    state = {"task": "RECOVERABILITY_INFORMATION_SUFFICIENCY_GATE_V1",
             "mode": mode, "pid": os.getpid(), "status": status,
             "protocol_sha256": PROTOCOL_SHA256}
    if extra:
        state.update(extra)
    (RUN / "run_state.json").write_text(
        json.dumps(state, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Exact fast metrics (rank-based AUROC == sklearn average-tie convention;
# per-sample-step AUPR == sklearn average_precision_score; cross-checked on
# point values at runtime)
# ---------------------------------------------------------------------------

def auroc_fast(y: np.ndarray, scores: np.ndarray) -> float:
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    ranks = rankdata(scores)
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n0 * n1))


def aupr_fast(y: np.ndarray, scores: np.ndarray) -> float:
    n1 = int(y.sum())
    if n1 == 0:
        return float("nan")
    # Tie-collapsed AP: threshold = each DISTINCT score value, with
    # precision/recall measured at the LAST row of the tie group. This is
    # exactly sklearn's average_precision_score (the convention every prior
    # gate in the program uses); per-row processing would measure precision
    # at interior points of tie groups and diverge (up to ~3e-2 with the
    # smoke RF's coarse probabilities).
    order = np.argsort(-scores, kind="mergesort")
    ys = y[order].astype(np.float64)
    tp = np.cumsum(ys)
    fp = np.cumsum(1.0 - ys)
    ss = scores[order]
    ends = np.concatenate((np.flatnonzero(np.diff(ss) != 0),
                           [len(y) - 1]))
    prec = tp[ends] / (tp[ends] + fp[ends])
    rec = tp[ends] / n1
    recall_diff = np.diff(np.concatenate(([0.0], rec)))
    return float(np.dot(prec, recall_diff))


def recall_at_5fur_fast(y: np.ndarray, scores: np.ndarray,
                        threshold: float) -> float:
    if not y.any():
        return float("nan")
    return float((scores[y == 1] >= threshold).mean())


# ---------------------------------------------------------------------------
# Feature views (frozen §5)
# ---------------------------------------------------------------------------

def raw_legal_matrix(feats: dict[str, np.ndarray],
                     states_per_row: np.ndarray) -> np.ndarray:
    """RAW_LEGAL view, 83 dims: basic[47] + T block[16] + R block[18] +
    masks m_t, m_r (1 iff the acquired state includes that type). Blocks are
    the frozen transformed strict-past values; at state B both blocks are
    the neutral all-zero vector and masks are 0."""
    n = len(feats["B"])
    out = np.zeros((n, 83), dtype=np.float64)
    for s in EVIDENCE_STATES:
        mask = states_per_row == s
        if not mask.any():
            continue
        basic = feats[s][:, :47]
        zero16 = np.zeros((n, 16))
        zero18 = np.zeros((n, 18))
        if s == "B":
            blocks = (basic, zero16, zero18)
            m = (np.zeros(n), np.zeros(n))
        elif s == "BT":
            blocks = (basic, feats[s][:, 47:63], zero18)
            m = (np.ones(n), np.zeros(n))
        elif s == "BR":
            blocks = (basic, zero16, feats[s][:, 47:65])
            m = (np.zeros(n), np.ones(n))
        else:  # BTR
            blocks = (basic, feats[s][:, 47:63], feats[s][:, 63:81])
            m = (np.ones(n), np.ones(n))
        out[mask] = np.column_stack(
            [blocks[0][mask], blocks[1][mask], blocks[2][mask],
             m[0][mask], m[1][mask]])
    return out


def raw_legal_for_actions(feats: dict[str, np.ndarray],
                          actions: np.ndarray) -> np.ndarray:
    states = np.array([ACTION_MODEL[a] for a in actions], dtype=object)
    return raw_legal_matrix(feats, states)


def st_view(cond: str, actions: np.ndarray,
            rf_proba_state: dict[str, np.ndarray] | None,
            alpha_state: dict[str, np.ndarray] | None,
            maha_post_state: dict[str, np.ndarray] | None,
            rf_pre: dict[str, np.ndarray], edl_pre: dict[str, np.ndarray],
            maha_pre: np.ndarray) -> np.ndarray:
    """STATE_TRANSITION view, 26 dims (frozen §5):
    RF pre/post (p_top, margin, argmax) + deltas + stability;
    EDL pre/post (S, p_top, p_2nd, argmax) + deltas;
    Mahalanobis pre/post/delta; evidence one-hot (T, R, TR).
    Pre components (B state) are identical across conditions. For BASIC:
    post = pre (deltas 0, stability 1, flags 0)."""
    n = len(actions)
    out = np.zeros((n, 26), dtype=np.float64)
    out[:, 0] = rf_pre["p_top"]
    out[:, 1] = rf_pre["margin"]
    out[:, 2] = rf_pre["argmax"]
    out[:, 9] = edl_pre["S"]
    out[:, 10] = edl_pre["p_top"]
    out[:, 11] = edl_pre["p_2nd"]
    out[:, 12] = edl_pre["argmax"]
    out[:, 20] = maha_pre

    if cond == "BASIC":
        out[:, 3:6] = out[:, 0:3]
        out[:, 13:17] = out[:, 9:13]
        out[:, 21] = maha_pre
        out[:, 8] = 1.0
        return out

    states = np.array([ACTION_MODEL[a] for a in actions], dtype=object)
    p_top = np.empty(n); margin = np.empty(n)
    argmax = np.empty(n, np.int64)
    S = np.empty(n); pt = np.empty(n); p2 = np.empty(n); ea = np.empty(n, np.int64)
    for s in EVIDENCE_STATES:
        mask = states == s
        if not mask.any():
            continue
        proba = rf_proba_state[s]
        p_top[mask] = proba[mask].max(axis=1)
        sorted_p = np.sort(proba[mask], axis=1)
        margin[mask] = sorted_p[:, -1] - sorted_p[:, -2]
        argmax[mask] = proba[mask].argmax(axis=1)
        a = alpha_state[s][mask]
        S[mask] = a.sum(axis=1)
        pt[mask] = a.max(axis=1) / S[mask]
        p2[mask] = np.partition(a, -2, axis=1)[:, -2] / S[mask]
        ea[mask] = a.argmax(axis=1)
    out[:, 3] = p_top; out[:, 4] = margin; out[:, 5] = argmax
    out[:, 13] = S; out[:, 14] = pt; out[:, 15] = p2; out[:, 16] = ea
    mp = np.full(n, np.nan)
    for s in EVIDENCE_STATES:
        mask = states == s
        if mask.any():
            mp[mask] = maha_post_state[s][mask]
    out[:, 21] = mp
    out[:, 6] = out[:, 3] - out[:, 0]
    out[:, 7] = out[:, 4] - out[:, 1]
    out[:, 8] = (out[:, 5] == out[:, 2]).astype(np.float64)
    out[:, 17] = out[:, 13] - out[:, 9]
    out[:, 18] = out[:, 14] - out[:, 10]
    out[:, 19] = out[:, 15] - out[:, 11]
    out[:, 22] = out[:, 21] - out[:, 20]
    out[:, 23] = (actions == "T").astype(np.float64)
    out[:, 24] = (actions == "R").astype(np.float64)
    out[:, 25] = (actions == "TR").astype(np.float64)
    return out


# ---------------------------------------------------------------------------
# Model families (frozen §8)
# ---------------------------------------------------------------------------

def fit_family(name: str, X: np.ndarray, y: np.ndarray, cfg: dict[str, Any]
               ) -> tuple[Any, dict[str, Any]]:
    meta: dict[str, Any] = {}
    if name == "RF":
        config = dict(RF_CONFIG)
        config["n_estimators"] = cfg["rf_est"]
        model = RandomForestClassifier(**config)
        model.fit(X, y)
        return model, meta
    if name == "LR":
        model = LogisticRegression(**LR_CONFIG)
        model.fit(X, y)
        meta["converged"] = bool(model.n_iter_[0] < LR_CONFIG["max_iter"])
        return model, meta
    raise ValueError(name)


class FixedMLP(torch.nn.Module):
    """Fixed 2-layer (input -> 64 ReLU -> 1). Frozen §8 recipe."""

    def __init__(self, in_dim: int):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(in_dim, MLP_HIDDEN),
            torch.nn.ReLU(),
            torch.nn.Linear(MLP_HIDDEN, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


def fit_mlp(X: np.ndarray, y: np.ndarray, test_rot: str,
            epoch_log: Path, max_epochs: int) -> tuple[Any, dict[str, Any]]:
    """AdamW 3e-4 / wd 1e-4, batch 1024, max 20 epochs, early stop patience 3
    on a deterministic 90/10 split of the fit rows (cell_rng offset
    RNG_BASE+600); torch.manual_seed(CENTRAL_SEED); batch order from
    cell_rng offset RNG_BASE+700."""
    torch.manual_seed(CENTRAL_SEED)
    torch.cuda.manual_seed_all(CENTRAL_SEED)
    split_rng = cell_rng(CENTRAL_SEED, test_rot, RNG_BASE + ST_SPLIT_RNG_OFFSET)
    batch_rng = cell_rng(CENTRAL_SEED, test_rot, RNG_BASE + ST_BATCH_RNG_OFFSET)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    perm = split_rng.permutation(len(X))
    n_val = int(round(0.10 * len(X)))
    val_idx, train_idx = perm[:n_val], perm[n_val:]
    Xt = torch.tensor(X[train_idx].astype(np.float32), device=device)
    yt = torch.tensor(y[train_idx].astype(np.float32), device=device)
    Xv = torch.tensor(X[val_idx].astype(np.float32), device=device)
    yv = torch.tensor(y[val_idx].astype(np.float32), device=device)
    model = FixedMLP(X.shape[1]).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=ADAMW_LR,
                            weight_decay=ADAMW_WEIGHT_DECAY)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    best_loss, best_state, stale, epochs_run = float("inf"), None, 0, 0
    records: list[dict[str, Any]] = []
    for epoch in range(max_epochs):
        epochs_run = epoch + 1
        order = batch_rng.permutation(len(train_idx))
        model.train()
        ce_sum = 0.0
        for start in range(0, len(order), BATCH_SIZE):
            pos = order[start:start + BATCH_SIZE]
            opt.zero_grad()
            loss = loss_fn(model(Xt[pos]), yt[pos])
            loss.backward()
            opt.step()
            ce_sum += float(loss.detach()) * len(pos)
        model.eval()
        with torch.no_grad():
            val_loss = float(loss_fn(model(Xv), yv))
        is_best = val_loss < best_loss - 1e-6
        if is_best:
            best_loss, stale = val_loss, 0
            best_state = {k: v.detach().clone()
                          for k, v in model.state_dict().items()}
        else:
            stale += 1
        records.append({"epoch": epoch + 1,
                        "train_ce": ce_sum / len(train_idx),
                        "early_stop_ce": val_loss,
                        "is_best": bool(is_best), "stale": stale})
        if stale >= EARLY_STOP_PATIENCE:
            break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    epoch_log.parent.mkdir(parents=True, exist_ok=True)
    with open(epoch_log, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return model.cpu(), {"epochs_run": epochs_run,
                         "best_early_stop_ce": best_loss}


def family_scores(name: str, model: Any, X: np.ndarray) -> np.ndarray:
    if name == "RF":
        return model.predict_proba(X)[:, 1]
    if name == "LR":
        return model.decision_function(X)
    if name == "MLP":
        model.eval()
        with torch.no_grad():
            logits = model(torch.tensor(X.astype(np.float32)))
        return torch.sigmoid(logits).numpy()
    raise ValueError(name)


# ---------------------------------------------------------------------------
# Probe fit + per-condition scoring
# ---------------------------------------------------------------------------

def probe_fit_and_score(probe: str, fold_rot: str, family: str, view: str,
                        X_fit: np.ndarray, y_fit: np.ndarray,
                        X_test: dict[str, np.ndarray], y_test: np.ndarray,
                        X_thr: dict[str, np.ndarray],
                        cfg: dict[str, Any]) -> dict[str, Any]:
    """Fit on REAL-condition features; score on test rows under every
    condition. Threshold = 95th percentile of the FITTED MODEL's scores over
    the condition's threshold rows (probe A: test RK rows, same-population
    convention §9.1; probe B: rotation-C role-0 Known rows §9.2) ->
    Recall@5%FUR over the TU rows."""
    scale = family in ("LR", "MLP")
    scaler = StandardScaler().fit(X_fit) if scale else None
    Xf = scaler.transform(X_fit) if scale else X_fit
    meta: dict[str, Any] = {}
    if family == "MLP":
        model, meta = fit_mlp(Xf, y_fit, fold_rot,
                              cfg["out"] / "mlp_epochs"
                              / f"{probe}_{fold_rot}_{view}.jsonl",
                              cfg["mlp_epochs"])
    else:
        model, meta = fit_family(family, Xf, y_fit, cfg)
    out: dict[str, Any] = {"probe": probe, "fold": fold_rot, "family": family,
                           "view": view, "fit_meta": meta,
                           "n_fit": int(len(X_fit)), "n_test": int(len(y_test))}
    per_cond: dict[str, Any] = {}
    for cond in CONDITIONS:
        Xc = X_test[cond]
        Xt = X_thr[cond]
        if scale:
            Xc = scaler.transform(Xc)
            Xt = scaler.transform(Xt)
        scores = family_scores(family, model, Xc)
        thr_scores = family_scores(family, model, Xt)
        thr = float(np.quantile(thr_scores, 1.0 - CALIB_FALSE_UNKNOWN_RATE))
        auroc_sk = float(roc_auc_score(y_test, scores))
        auroc_f = auroc_fast(y_test, scores)
        # Crosscheck tolerance is fp-noise headroom, NOT a scientific
        # threshold (materiality floor is +0.02 AUROC). Two implementations
        # of the same statistic agree to ~1e-9 on smoke subsets and ~1e-7 at
        # formal scale; a real definitional divergence (e.g. the AUPR
        # tie-handling bug, ~3e-2) is orders of magnitude larger.
        if abs(auroc_sk - auroc_f) > 1e-6:
            raise SystemExit(f"AUROC_CROSSCHECK_FAIL probe={probe} "
                             f"fold={fold_rot} family={family} view={view} "
                             f"cond={cond} sk={auroc_sk} fast={auroc_f}")
        aupr_sk = float(average_precision_score(y_test, scores))
        aupr_f = aupr_fast(y_test, scores)
        if abs(aupr_sk - aupr_f) > 1e-6:
            raise SystemExit(f"AUPR_CROSSCHECK_FAIL probe={probe} "
                             f"fold={fold_rot} family={family} view={view} "
                             f"cond={cond} sk={aupr_sk} fast={aupr_f}")
        per_cond[cond] = {
            "auroc": auroc_f, "aupr": aupr_f,
            "recall_at_5fur": recall_at_5fur_fast(y_test, scores, thr),
            "threshold": thr,
        }
        out.setdefault("scores", {})[cond] = scores.astype(np.float64)
    out["per_condition"] = per_cond
    return out


# ---------------------------------------------------------------------------
# Bootstrap (frozen §9.3): rotation-stratified group-atomic, 1000 reps,
# default_rng(162600), 2.5/97.5 percentiles, class-coverage guard (>=2 RK
# and >=2 TU per rotation per replicate, bounded seeded redraw). Same draws
# feed pooled AND per-rotation CIs. Fresh default_rng per (probe,family,
# view) key -> identical draws across all fits (fully paired).
# ---------------------------------------------------------------------------

def build_rotation_draws(test_groups: dict[str, np.ndarray],
                         y_test: dict[str, np.ndarray],
                         reps: int, rng: np.random.Generator
                         ) -> tuple[dict[str, np.ndarray], dict[str, int]]:
    draws: dict[str, np.ndarray] = {}
    dropped = {rot: 0 for rot in ROTATIONS}
    for rot in ROTATIONS:
        groups = test_groups[rot]
        y = y_test[rot]
        unique, inverse = np.unique(groups, return_inverse=True)
        g_rows: list[np.ndarray] = []
        for g in range(len(unique)):
            g_rows.append(np.flatnonzero(inverse == g))
        gidx = np.empty((reps, len(unique)), dtype=np.int64)
        for rep in range(reps):
            for _attempt in range(REDRAW_BOUND):
                draw = rng.integers(0, len(unique), size=len(unique))
                rows = np.concatenate([g_rows[g] for g in draw])
                if int(y[rows].sum()) >= 2 and int((~y[rows].astype(bool)).sum()) >= 2:
                    break
            else:
                dropped[rot] += 1
                draw = rng.integers(0, len(unique), size=len(unique))
            gidx[rep] = draw
        draws[rot] = gidx
        if dropped[rot]:
            print(f"[bootstrap {rot}] dropped replicates "
                  f"(class-coverage redraw bound): {dropped[rot]}", flush=True)
    return draws, dropped


def rep_metric_matrix(scores: np.ndarray, y: np.ndarray, groups: np.ndarray,
                      gidx: np.ndarray, threshold: float | None,
                      metric: str) -> np.ndarray:
    """Per-replicate metric over the rotation's sampled rows."""
    unique, inverse = np.unique(groups, return_inverse=True)
    g_rows: list[np.ndarray] = []
    for g in range(len(unique)):
        g_rows.append(np.flatnonzero(inverse == g))
    reps = len(gidx)
    out = np.full(reps, np.nan)
    for rep in range(reps):
        rows = np.concatenate([g_rows[g] for g in gidx[rep]])
        ys = y[rows]
        ss = scores[rows]
        if metric == "auroc":
            out[rep] = auroc_fast(ys, ss)
        elif metric == "aupr":
            out[rep] = aupr_fast(ys, ss)
        elif metric == "recall":
            out[rep] = recall_at_5fur_fast(ys, ss, threshold)
        else:
            raise ValueError(metric)
    return out


def _point_increment(fits: dict[str, Any], metric: str, a: str, b: str,
                     weights: dict[str, float]) -> float:
    va = sum(weights[rot] * fits[rot][a][f"point_{metric}"] for rot in ROTATIONS)
    vb = sum(weights[rot] * fits[rot][b][f"point_{metric}"] for rot in ROTATIONS)
    return float(va - vb)


def bootstrap_pooled_view(fits: dict[str, Any], cfg: dict[str, Any]
                          ) -> dict[str, Any]:
    """Full bootstrap for one (probe, family, view): per-condition pooled
    point estimates, pooled increment points + CIs (AUROC/AUPR/Recall;
    AUROC replicates persisted for retention/tree), per-rotation point
    estimates + increment CIs (reverse check uses CI upper)."""
    rng = np.random.default_rng(BOOTSTRAP_RNG)
    test_groups = {rot: fits[rot]["REAL"]["groups"] for rot in ROTATIONS}
    y_test = {rot: fits[rot]["REAL"]["y"] for rot in ROTATIONS}
    draws, dropped = build_rotation_draws(test_groups, y_test,
                                          cfg["bs_reps"], rng)
    n = {rot: len(y_test[rot]) for rot in ROTATIONS}
    total = sum(n.values())
    weights = {rot: n[rot] / total for rot in ROTATIONS}

    out: dict[str, Any] = {"pooled_point": {}, "increments": {},
                           "per_rotation": {}, "draws_note": dropped}
    for cond in CONDITIONS:
        pooled = {"auroc": 0.0, "aupr": 0.0, "recall": 0.0}
        per_rot = {}
        for rot in ROTATIONS:
            f = fits[rot][cond]
            per_rot[rot] = {"auroc": f["point_auroc"], "aupr": f["point_aupr"],
                            "recall": f["point_recall"], "n": f["n"],
                            "n_rk": int((~f["y"].astype(bool)).sum()),
                            "n_tu": int(f["y"].sum())}
            for key in ("auroc", "aupr", "recall"):
                pooled[key] += weights[rot] * f[f"point_{key}"]
        out["pooled_point"][cond] = pooled
        out["per_rotation"][cond] = per_rot

    rep: dict[str, Any] = {}
    for cond in CONDITIONS:
        for metric in ("auroc", "aupr", "recall"):
            rep.setdefault(metric, {})[cond] = {}
            for rot in ROTATIONS:
                thr = (fits[rot][cond]["threshold"] if metric == "recall"
                       else None)
                rep[metric][cond][rot] = rep_metric_matrix(
                    fits[rot][cond]["scores"], fits[rot][cond]["y"],
                    fits[rot][cond]["groups"], draws[rot], thr, metric)
    INCS = (("real_minus_basic", "REAL", "BASIC"),
            ("real_minus_shuffled", "REAL", "SHUFFLED"),
            ("real_minus_null", "REAL", "NULL"),
            ("shuffled_minus_basic", "SHUFFLED", "BASIC"))
    for metric in ("auroc", "aupr", "recall"):
        pooled_reps = {cond: np.zeros(cfg["bs_reps"]) for cond in CONDITIONS}
        for cond in CONDITIONS:
            for rot in ROTATIONS:
                pooled_reps[cond] += weights[rot] * rep[metric][cond][rot]
        for name, a, b in INCS:
            d = pooled_reps[a] - pooled_reps[b]
            entry = {"point": _point_increment(fits, metric, a, b, weights),
                     "ci95": [float(np.percentile(d, BOOTSTRAP_PCTS[0])),
                              float(np.percentile(d, BOOTSTRAP_PCTS[1]))]}
            if metric == "auroc":
                entry["replicates"] = d.astype(np.float32).tolist()
            out["increments"].setdefault(metric, {})[name] = entry
        for rot in ROTATIONS:
            for name, a, b in INCS:
                d = rep[metric][a][rot] - rep[metric][b][rot]
                out["per_rotation"].setdefault(metric, {})
                out["per_rotation"][metric].setdefault(rot, {})[name] = {
                    "point": float(fits[rot][a][f"point_{metric}"]
                                   - fits[rot][b][f"point_{metric}"]),
                    "ci95": [float(np.percentile(d, BOOTSTRAP_PCTS[0])),
                             float(np.percentile(d, BOOTSTRAP_PCTS[1]))]}
    return out


# ---------------------------------------------------------------------------
# S6: consistency rules, retention, decision tree (frozen §9–§11)
# ---------------------------------------------------------------------------

def material(fams: dict[str, dict[str, Any]]) -> bool:
    """mat(P,v,f): pooled REAL-BASIC AND pooled REAL-SHUFFLED target-
    specific criterion (point >= +0.02 AND 95% CI lower > 0)."""
    inc = fams["increments"]["auroc"]
    for name in ("real_minus_basic", "real_minus_shuffled"):
        if not (inc[name]["point"] >= MATERIALITY and inc[name]["ci95"][0] > 0.0):
            return False
    return True


def shuffled_over_basic_material(fams: dict[str, dict[str, Any]]) -> bool:
    inc = fams["increments"]["auroc"]["shuffled_minus_basic"]
    return bool(inc["point"] >= MATERIALITY and inc["ci95"][0] > 0.0)


def real_over_shuffled_material(fams: dict[str, dict[str, Any]]) -> bool:
    inc = fams["increments"]["auroc"]["real_minus_shuffled"]
    return bool(inc["point"] >= MATERIALITY and inc["ci95"][0] > 0.0)


def rot_ok(boot_by_family: dict[str, dict[str, Any]],
           comparisons: tuple[tuple[str, str], ...]) -> bool:
    """rotOK(P,v): >=2/3 rotations with median-across-families per-rotation
    point increments >= +0.02 on EVERY comparison, AND no rotation with
    median CI upper < 0 on any comparison (clear reverse)."""
    med_pts: dict[str, dict[str, float]] = {}
    med_ups: dict[str, dict[str, float]] = {}
    for rot in ROTATIONS:
        med_pts[rot] = {}
        med_ups[rot] = {}
        for a, b in comparisons:
            key = f"{a.lower()}_minus_{b.lower()}"
            pts = [boot_by_family[f]["per_rotation"]["auroc"][rot][key]["point"]
                   for f in FAMILIES]
            ups = [boot_by_family[f]["per_rotation"]["auroc"][rot][key]["ci95"][1]
                   for f in FAMILIES]
            med_pts[rot][key] = float(np.median(pts))
            med_ups[rot][key] = float(np.median(ups))
    good_rots = sum(
        1 for rot in ROTATIONS
        if all(v >= MATERIALITY for v in med_pts[rot].values()))
    reverse_free = all(
        v >= 0.0 for rot in ROTATIONS
        for v in med_ups[rot].values())
    return bool(good_rots >= ROT_OK_MIN and reverse_free)


def retention(boot_pa: dict[str, dict[str, Any]], passing: list[str]
              ) -> dict[str, Any]:
    """§10.3: ret(f) = inc(ST,f)/inc(RAW,f), f in S(A,RAW); point-estimate
    decision; bootstrap CIs reporting-only with dropped-replicate counts
    (denominator <= 0). Replicates are the pooled AUROC increment
    replicates (same draws)."""
    out: dict[str, Any] = {"families": {}}
    for f in passing:
        st_inc = boot_pa["ST"][f]["increments"]["auroc"]
        ra_inc = boot_pa["RAW"][f]["increments"]["auroc"]
        per: dict[str, Any] = {}
        for suffix, key in (("b", "real_minus_basic"),
                            ("s", "real_minus_shuffled")):
            num = np.array(st_inc[key]["replicates"], dtype=np.float64)
            den = np.array(ra_inc[key]["replicates"], dtype=np.float64)
            valid = den > 0.0
            ratios = num[valid] / den[valid]
            per[suffix] = {
                "point": (st_inc[key]["point"] / ra_inc[key]["point"]
                          if ra_inc[key]["point"] > 0 else None),
                "ci95": ([float(np.percentile(ratios, BOOTSTRAP_PCTS[0])),
                          float(np.percentile(ratios, BOOTSTRAP_PCTS[1]))]
                         if len(ratios) else None),
                "dropped_replicates": int((~valid).sum()),
                "kept_replicates": int(valid.sum())}
        out["families"][f] = per
    med: dict[str, Any] = {}
    for suffix, key in (("b", "real_minus_basic"),
                        ("s", "real_minus_shuffled")):
        points = [out["families"][f][suffix]["point"] for f in passing]
        points = [p for p in points if p is not None]
        n_rep = len(boot_pa["RAW"][passing[0]]["increments"]["auroc"][key]
                    ["replicates"])
        valid = np.ones(n_rep, dtype=bool)
        for f in passing:
            valid &= np.array(
                boot_pa["RAW"][f]["increments"]["auroc"][key]["replicates"],
                dtype=np.float64) > 0.0
        ratios = np.empty((len(passing), int(valid.sum())))
        for i, f in enumerate(passing):
            num = np.array(boot_pa["ST"][f]["increments"]["auroc"][key]
                           ["replicates"], dtype=np.float64)[valid]
            den = np.array(boot_pa["RAW"][f]["increments"]["auroc"][key]
                           ["replicates"], dtype=np.float64)[valid]
            ratios[i] = num / den
        med_ratios = np.median(ratios, axis=0)
        med[suffix] = {
            "point": (float(np.median(points)) if points else None),
            "ci95": [float(np.percentile(med_ratios, BOOTSTRAP_PCTS[0])),
                     float(np.percentile(med_ratios, BOOTSTRAP_PCTS[1]))],
            "dropped_replicates": int((~valid).sum()),
            "kept_replicates": int(valid.sum())}
    out["median_over_families"] = med
    if med["b"]["point"] is not None and med["s"]["point"] is not None:
        out["bottleneck"] = bool(min(med["b"]["point"], med["s"]["point"])
                                 < RETENTION_THRESHOLD)
    else:
        out["bottleneck"] = None
    return out


# ---------------------------------------------------------------------------
# Population + leakage + identity checks (frozen §2, §4, §11 Step 0)
# ---------------------------------------------------------------------------

def population_checks(cells: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"pass": True, "detail": {}}
    for rot in ROTATIONS:
        cell = cells[rot]
        unk = cell["ev_is_unknown"].astype(bool)
        rec = cell["ev_recoverable"].astype(bool)
        role = cell["ev_split_role"]
        rk = rec & (~unk)
        got = {"rk0": int((rk & (role == 0)).sum()),
               "rk1": int((rk & (role == 1)).sum()),
               "tu0": int((unk & (role == 0)).sum()),
               "tu1": int((unk & (role == 1)).sum())}
        role0_n = int((role == 0).sum())
        role1_n = int((role == 1).sum())
        ok = (len(cell["ev_labels"]) == VAL_N and got == FROZEN_POP[rot]
              and FROZEN_ROLE0_RANGE[0] <= role0_n <= FROZEN_ROLE0_RANGE[1]
              and FROZEN_ROLE1_RANGE[0] <= role1_n <= FROZEN_ROLE1_RANGE[1]
              and int(unk.sum()) == 8000)
        out["detail"][rot] = {"expected": FROZEN_POP[rot], "got": got,
                              "role0_n": role0_n, "role1_n": role1_n,
                              "tu_total": int(unk.sum()), "ok": bool(ok)}
        out["pass"] &= bool(ok)
    return out


def leakage_checks(cells: dict[str, Any], train_rows: np.ndarray,
                   train_groups: np.ndarray) -> dict[str, Any]:
    """Frozen §2 mandatory checks: row identity AND group identity zero
    overlap on every dev/test boundary. Check 3: the role-0/role-1 split is
    identical across rotations (A-dev and B-dev are the same physical rows
    with per-rotation labels — the documented dual-labeling design)."""
    out: dict[str, Any] = {"pass": True, "checks": {}}

    def check(name: str, rows_a: np.ndarray, rows_b: np.ndarray,
              groups_a: np.ndarray, groups_b: np.ndarray) -> None:
        row_overlap = int(len(np.intersect1d(rows_a, rows_b)))
        g_overlap = int(len(np.intersect1d(
            np.unique(groups_a), np.unique(groups_b))))
        ok = row_overlap == 0 and g_overlap == 0
        out["checks"][name] = {"row_overlap": row_overlap,
                               "group_overlap": g_overlap, "ok": bool(ok)}
        out["pass"] &= bool(ok)

    role0_rows: dict[str, np.ndarray] = {}
    for rot in ROTATIONS:
        cell = cells[rot]
        role0_rows[rot] = cell["ev_rows"][cell["ev_split_role"] == 0]
    split_same = all(np.array_equal(role0_rows[ROTATIONS[0]], role0_rows[r])
                     for r in ROTATIONS[1:])
    out["checks"]["3_split_identical_across_rotations"] = {
        "same_physical_role0_rows": bool(split_same)}
    out["pass"] &= bool(split_same)

    for fold_rot in ROTATIONS:
        dev_rots = [r for r in ROTATIONS if r != fold_rot]
        dev_rows = np.concatenate([role0_rows[r] for r in dev_rots])
        dev_groups = np.concatenate(
            [cells[r]["ev_groups"][cells[r]["ev_split_role"] == 0]
             for r in dev_rots])
        cell = cells[fold_rot]
        role = cell["ev_split_role"]
        test_rows = cell["ev_rows"][role == 1]
        test_groups = cell["ev_groups"][role == 1]
        check(f"1_probeA_dev_vs_test_{fold_rot}",
              dev_rows, test_rows, dev_groups, test_groups)
        # probe B: TRAIN partition vs test rows and vs threshold rows
        thr_mask = (role == 0) & (~cell["ev_is_unknown"].astype(bool))
        check(f"2a_probeB_train_vs_test_{fold_rot}",
              train_rows, test_rows, train_groups, test_groups)
        check(f"2b_probeB_train_vs_threshold_{fold_rot}",
              train_rows, cell["ev_rows"][thr_mask],
              train_groups, cell["ev_groups"][thr_mask])
    # check 4: TRAIN vs VALIDATION (all 56,000 validation rows)
    val_rows = np.concatenate([cells[r]["ev_rows"] for r in ROTATIONS])
    check("4_train_vs_validation", train_rows, val_rows,
          train_groups, cells[ROTATIONS[0]]["ev_groups"])
    return out


def p6_reproduction(cells: dict[str, Any], pkls: dict[str, Any],
                    basic_val: np.ndarray) -> dict[str, Any]:
    """Frozen §4: reproduce eval-row P6 actions from the frozen selectors
    with the frozen per-population budgets; require 0 mismatches vs stored
    action_P6_UTILITY_TYPED."""
    out: dict[str, Any] = {}
    for rot in ROTATIONS:
        cell = cells[rot]
        rf_b = pkls[rot]["models"]["B"]
        # OWG selector features use the OWG known-class order
        # (owg.known_classes_for, lexicographic) — NOT the V2 cell order
        # (cell["known"]). The frozen selectors were trained with the OWG
        # order; the attribution-verified reproduction
        # (run_open_world_gate_v1_failure_attribution.py, TYPED_ACTIONS_MATCH
        # PASS on record) builds them the same way. The V2 cell tuple
        # swaps Benign/Backdoor and would shift the aligned proba and
        # one-hot columns -> wrong utilities -> wrong actions.
        known_owg = owg.known_classes_for(rot)
        proba_b = owg.align_rotation_proba(
            rf_b.predict_proba(cell["features_ev"]["B"]),
            rf_b.classes_, known_owg)
        pred_b = rf_b.predict(cell["features_ev"]["B"])
        avail = np.ones(len(cell["ev_labels"]))
        sel_feats, names = owg.rotation_selector_features(
            basic_val, pred_b, proba_b, avail, known_owg)
        if owg.selector_leakage_audit(names) != "PASS":
            raise SystemExit(f"SELECTOR_LEAKAGE_AUDIT_FAIL rotation={rot}")
        u_t = pkls[rot]["selectors"]["T"].predict(sel_feats)
        u_r = pkls[rot]["selectors"]["R"].predict(sel_feats)
        u_tr = pkls[rot]["selectors"]["TR"].predict(sel_feats)
        role = cell["ev_split_role"]
        n_eval = int(role.sum())
        n_calib = len(role) - n_eval
        budget_eval = int(np.floor(owg.PRIMARY_COST_BUDGET_FRACTION * n_eval))
        budget_calib = int(np.floor(owg.PRIMARY_COST_BUDGET_FRACTION * n_calib))
        actions = np.full(len(role), "NONE", dtype=object)
        for pop_mask, budget in ((role == 0, budget_calib),
                                 (role == 1, budget_eval)):
            idx = np.flatnonzero(pop_mask)
            actions[idx] = owg.typed_policy_actions(
                u_t[idx], u_r[idx], u_tr[idx], budget, idx)
        stored = cell["ev_action_p6"]
        mism = int((actions != stored).sum())
        out[rot] = {"mismatches": mism, "n": int(len(stored)),
                    "n_eval": n_eval, "n_calib": n_calib,
                    "budget_eval_units": budget_eval,
                    "budget_calib_units": budget_calib,
                    "action_counts": {a: int((actions == a).sum())
                                      for a in ("NONE", "T", "R", "TR")}}
    out["pass"] = all(out[r]["mismatches"] == 0 for r in ROTATIONS)
    return out


def furk_rederivation(scores_by_state: dict[str, np.ndarray], cell: dict,
                      actions: np.ndarray) -> dict[str, Any]:
    """Frozen §11 Step 0: re-derive the V2 deployable P6 FURK — per-row
    Mahalanobis at the acquired state, 95th-percentile threshold over role-0
    Known rows, false-Unknown rate over role-1 recoverable Known rows (the
    exact V2 deployable convention) — for identity vs the V2 validation
    record (furk1)."""
    n = len(cell["ev_labels"])
    states = np.array([ACTION_MODEL[a] for a in actions], dtype=object)
    score_d1 = np.empty(n)
    for s in EVIDENCE_STATES:
        mask = states == s
        if mask.any():
            score_d1[mask] = scores_by_state[s][mask]
    role = cell["ev_split_role"]
    unk = cell["ev_is_unknown"].astype(bool)
    calib_known = (role == 0) & (~unk)
    thr = float(np.quantile(score_d1[calib_known],
                            1.0 - CALIB_FALSE_UNKNOWN_RATE))
    ek = (role == 1) & (~unk)
    rec_rel = cell["ev_recoverable"].astype(bool)[ek]
    furk = float((score_d1[ek] >= thr)[rec_rel].mean()) \
        if rec_rel.sum() else 0.0
    return {"furk": furk,
            "n_recoverable_known_eval": int(rec_rel.sum()),
            "threshold": thr}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true",
                        help="tiny non-scientific end-to-end run")
    args = parser.parse_args()
    mode = "smoke" if args.smoke else "formal"
    cfg: dict[str, Any] = {"smoke": bool(args.smoke),
                           "out": RUN / mode,
                           "bs_reps": 20 if args.smoke else BOOTSTRAP_REPS,
                           "mlp_epochs": 2 if args.smoke else MAX_EPOCHS,
                           "rf_est": 10 if args.smoke
                           else RF_CONFIG["n_estimators"],
                           "dev_max": 3000 if args.smoke else None,
                           "test_max": 1500 if args.smoke else None,
                           "train_max": 30_000 if args.smoke else None}
    RUN.mkdir(parents=True, exist_ok=True)
    cfg["out"].mkdir(parents=True, exist_ok=True)
    for sub in ("b_edl_retrain", "edl", "features", "bootstrap"):
        (cfg["out"] / sub).mkdir(parents=True, exist_ok=True)
    (RUN / "stages").mkdir(parents=True, exist_ok=True)
    write_run_state("RUNNING", mode)
    try:
        run_gate(cfg, mode)
    except BaseException:
        write_run_state("FAILED", mode)
        raise
    return 0


def run_gate(cfg: dict[str, Any], mode: str) -> None:
    det = set_determinism()
    start = time.time()

    # --- Execution lock ---
    protocol = REPO / "docs/research_plan" / \
        "recoverability_information_sufficiency_gate_v1_protocol.md"
    recomputed = sha256_file(protocol)
    reg = json.loads((REPO / "reports/research_audit" /
                      "recoverability_information_sufficiency_gate_v1_preregistration.json").read_text())
    lock = {"protocol_sha256_recomputed": recomputed,
            "preregistration_sha256": reg["protocol_sha256"],
            "match": recomputed == PROTOCOL_SHA256 == reg["protocol_sha256"]}
    if not lock["match"]:
        raise SystemExit("PROTOCOL_HASH_MISMATCH")

    # --- Load frozen artifacts ---
    cells = {rot: assemble_cell(CENTRAL_SEED, rot, OWG, GATE1)
             for rot in ROTATIONS}
    pkls = {}
    for rot in ROTATIONS:
        with open(OWG / "models"
                  / f"owg_v1_seed_{CENTRAL_SEED}_rotation_{rot}_models.pkl",
                  "rb") as handle:
            pkls[rot] = pickle.load(handle)
    primaries = {}
    for rot in ROTATIONS:
        model = StrongOSREncoder()
        model.load_state_dict(torch.load(
            V2RUN / "cells" / cell_key(CENTRAL_SEED, rot) / "model.pt",
            map_location="cpu"))
        model.eval()
        primaries[rot] = model
    maha_npz = {rot: dict(np.load(V2VAL / "primary_replay" / f"{rot}_maha.npz"))
                for rot in ROTATIONS}
    safes = {rot: dict(np.load(V2VAL / "safeguards" / f"B_{rot}_scores.npz"))
             for rot in ROTATIONS}
    # assemble_cell does not carry the eval-row IDs; attach them from the
    # frozen eval parquet (row-identity checks + probe-B train features)
    for rot in ROTATIONS:
        tbl = pq.read_table(
            OWG / f"owg_v1_seed_{CENTRAL_SEED}_rotation_{rot}_eval.parquet")
        cells[rot]["ev_rows"] = tbl["source_row_index"].to_numpy(
            zero_copy_only=False)
    targets = load_targets(GATE1, CENTRAL_SEED)
    train_mask = targets["partition_code"] == PARTITION_TRAIN
    train_rows = targets["source_row_index"][train_mask]
    train_groups = targets["activity_group_digest"][train_mask]
    basic_rows, basic_arrays = load_basic_features(GATE1)
    basic_positions = {int(v): i for i, v in enumerate(basic_rows)}
    basic_val = basic_matrix_for(cells[ROTATIONS[0]]["ev_rows"], basic_arrays,
                                 basic_positions)

    # --- S0: population + leakage + P6 reproduction (always re-run) ---
    pop_ok = population_checks(cells)
    leak = leakage_checks(cells, train_rows, train_groups)
    p6 = p6_reproduction(cells, pkls, basic_val)
    s0 = {"population": pop_ok, "leakage": leak, "p6_reproduction": p6,
          "pass": bool(pop_ok["pass"] and leak["pass"] and p6["pass"])}
    if not s0["pass"]:
        raise SystemExit("STEP0_CHECKS_FAILED "
                         + json.dumps(s0, default=str)[:2000])
    print("[S0] population/leakage/P6 reproduction checks PASS", flush=True)

    # --- S1 per rotation: B_EDL replay + identity; maha REAL identity;
    # frozen P6 FURK re-derivation (V2 deployable convention) ---
    furk_results: dict[str, Any] = {}
    for rot in ROTATIONS:
        key = f"s1_{rot}"
        if stage_done(mode, key):
            furk_results[rot] = json.loads(
                marker_path(mode, key).read_text())["furk"]
            continue
        cell = cells[rot]
        labels_n = class_codes(cell, cell["train_labels"])
        fit_idx = np.flatnonzero(~cell["early"])
        # B_EDL replay identity: the EDL init is drawn from the global torch
        # RNG state at CONSTRUCTION time. The V2 validation process
        # constructed each EDL from the post-manual_seed(seed) state (its A
        # replay's internal manual_seed reset the global RNG; training makes
        # no torch-RNG draws). Reproduce that exact state here, or the
        # replayed head diverges from the frozen safeguards at ~1e-2 and
        # the identity check fails. Verified: 0.0 diffs on all 4 states.
        torch.manual_seed(CENTRAL_SEED)
        torch.cuda.manual_seed_all(CENTRAL_SEED)
        edl = EDLHeadEncoder(StrongOSREncoder())
        edl_rng = cell_rng(CENTRAL_SEED, rot, RNG_BASE + EDL_RETRAIN_RNG_OFFSET)
        logp = cfg["out"] / "b_edl_retrain" / f"{rot}_epochs.jsonl"
        edl_full, epochs_run, _ = v2.train_encoder_v2(
            edl, cell["features_train"], labels_n,
            fit_mask=~cell["early"], early_mask=cell["early"],
            rng=edl_rng, seed=CENTRAL_SEED, use_edl=True,
            epoch_log_path=logp)
        torch.save(edl_full.state_dict(),
                   cfg["out"] / "edl" / f"{rot}_edl_head.pt")
        _, nov = diag.edl_alpha_and_novelty(
            edl_full, cell["features_ev"],
            np.arange(len(cell["features_ev"]["B"])), EVIDENCE_STATES)
        edl_diff = {s: float(np.abs(nov[s] - safes[rot][f"s_{s}"]).max())
                    for s in EVIDENCE_STATES}
        if any(d > REAL_REPRO_TOL for d in edl_diff.values()):
            raise SystemExit(f"B_EDL_IDENTITY_FAIL rotation={rot} "
                             f"max_diff={edl_diff}")
        # maha REAL identity (geometry on TRAIN FIT Known, as in V2)
        train_embs = diag.state_embeddings(
            primaries[rot], cell["features_train"], fit_idx, EVIDENCE_STATES)
        eval_embs = diag.state_embeddings(
            primaries[rot], cell["features_ev"],
            np.arange(len(cell["features_ev"]["B"])), EVIDENCE_STATES)
        scores = diag.maha_scores_from(
            eval_embs, train_embs, cell["train_labels"][fit_idx],
            cell["known"], EVIDENCE_STATES)
        maha_diff = {s: float(np.abs(scores[s] - maha_npz[rot][f"s_{s}"]).max())
                     for s in EVIDENCE_STATES}
        if any(d > REAL_REPRO_TOL for d in maha_diff.values()):
            raise SystemExit(f"MAHA_IDENTITY_FAIL rotation={rot} "
                             f"max_diff={maha_diff}")
        # frozen P6 FURK re-derivation (Step 0) from the recomputed maha
        furk = furk_rederivation(scores, cell, cell["ev_action_p6"])
        expected_v2 = json.loads((REPO / "reports/research_audit" /
                                  "strong_hybrid_osr_evidence_gate_v2_validation.json").read_text())
        expected = expected_v2["primary_rederivation"]["deployable_rederived"] \
            ["per_cell"][cell_key(CENTRAL_SEED, rot)]["furk1"]
        furk["expected_v2_furk1"] = expected
        furk["abs_diff"] = abs(furk["furk"] - expected)
        furk["ok"] = bool(furk["abs_diff"] <= FURK_V2_TOL)
        if not furk["ok"]:
            raise SystemExit(f"FURK_REDERIVATION_FAIL rotation={rot} "
                             f"furk={furk}")
        furk_results[rot] = furk
        np.savez_compressed(
            cfg["out"] / "edl" / f"{rot}_train_embs.npz",
            **{f"h_{s}": train_embs[s].astype(np.float64)
               for s in EVIDENCE_STATES},
            allow_pickle=False)
        mark_stage(mode, key, {"epochs_run": epochs_run,
                               "edl_max_diff": edl_diff,
                               "maha_max_diff": maha_diff,
                               "furk": furk,
                               "edl_ok": all(d <= REAL_REPRO_TOL
                                             for d in edl_diff.values()),
                               "maha_ok": all(d <= REAL_REPRO_TOL
                                              for d in maha_diff.values()),
                               "furk_ok": bool(furk["ok"])})
        print(f"[S1 {rot}] B_EDL + maha identity + FURK re-derivation PASS "
              f"(edl_diff={max(edl_diff.values()):.2e} "
              f"maha_diff={max(maha_diff.values()):.2e} "
              f"furk={furk['furk']:.6f})", flush=True)
    if not all(furk_results[r]["ok"] for r in ROTATIONS):
        raise SystemExit("STEP0_FURK_FAILED")

    # --- S2 per rotation: condition feature views + probe-B TRAIN features ---
    for rot in ROTATIONS:
        key = f"s2_{rot}"
        if stage_done(mode, key):
            continue
        cell = cells[rot]
        n = len(cell["ev_labels"])
        actions = cell["ev_action_p6"]
        shuf_rng = cell_rng(CENTRAL_SEED, rot, RNG_BASE + SHUF_RNG_OFFSET)
        _null_tr, feats_null_ev = diag.null_features(cell)
        feats_shuf_ev = diag.shuffled_features(cell, shuf_rng)
        rk_rows = np.flatnonzero(cell["ev_recoverable"].astype(bool)
                                 & (~cell["ev_is_unknown"].astype(bool)))
        un_rows = np.flatnonzero(cell["ev_is_unknown"].astype(bool))
        btr_r = cell["features_ev"]["BTR"]
        btr_s = feats_shuf_ev["BTR"]
        shuf_ok = True
        for rows in (rk_rows, un_rows):
            for lo, hi in ((47, 63), (63, 81)):
                shuf_ok &= bool(np.allclose(
                    btr_r[rows, lo:hi].mean(axis=0),
                    btr_s[rows, lo:hi].mean(axis=0), atol=SHUF_MARGINAL_TOL))
                shuf_ok &= bool(np.allclose(
                    btr_r[rows, lo:hi].std(axis=0),
                    btr_s[rows, lo:hi].std(axis=0), atol=SHUF_MARGINAL_TOL))
        if not shuf_ok:
            raise SystemExit(f"SHUFFLED_MARGINAL_MISMATCH rotation={rot}")
        if not bool((feats_null_ev["BTR"][:, 47:81] == 0.0).all()):
            raise SystemExit(f"NULL_PRESENT_BLOCK_CHECK_FAILED rotation={rot}")

        # RAW_LEGAL eval per condition
        raw: dict[str, np.ndarray] = {}
        raw["REAL"] = raw_legal_for_actions(cell["features_ev"], actions)
        raw["BASIC"] = raw_legal_matrix(cell["features_ev"],
                                        np.full(n, "B", dtype=object))
        raw["SHUFFLED"] = raw_legal_for_actions(feats_shuf_ev, actions)
        raw["NULL"] = raw_legal_for_actions(feats_null_ev, actions)

        # STATE_TRANSITION per condition (pre components identical)
        edl_state = torch.load(cfg["out"] / "edl" / f"{rot}_edl_head.pt",
                               map_location="cpu")
        edl_head = EDLHeadEncoder(StrongOSREncoder())
        edl_head.load_state_dict(edl_state)
        edl_head.eval()
        maha_pre = maha_npz[rot]["s_B"].astype(np.float64)
        train_embs = dict(np.load(cfg["out"] / "edl" / f"{rot}_train_embs.npz",
                                  allow_pickle=True))
        h_train = {s: train_embs[f"h_{s}"] for s in EVIDENCE_STATES}
        fit_idx_ar = np.flatnonzero(~cell["early"])
        rf_pre = None
        edl_pre = None
        st: dict[str, np.ndarray] = {}
        for cond in ("REAL", "SHUFFLED", "NULL"):
            feats = (cell["features_ev"] if cond == "REAL"
                     else feats_shuf_ev if cond == "SHUFFLED"
                     else feats_null_ev)
            rf_proba_c: dict[str, np.ndarray] = {}
            for s in EVIDENCE_STATES:
                model = pkls[rot]["models"][s]
                rf_proba_c[s] = owg.align_rotation_proba(
                    model.predict_proba(feats[s]), model.classes_, cell["known"])
            alpha_c, _ = diag.edl_alpha_and_novelty(
                edl_head, feats, np.arange(n), EVIDENCE_STATES)
            if cond == "REAL":
                maha_post = {s: maha_npz[rot][f"s_{s}"].astype(np.float64)
                             for s in EVIDENCE_STATES}
            else:
                embs = diag.state_embeddings(primaries[rot], feats,
                                             np.arange(n), EVIDENCE_STATES)
                maha_post = diag.maha_scores_from(
                    embs, h_train, cell["train_labels"][fit_idx_ar],
                    cell["known"], EVIDENCE_STATES)
            if rf_pre is None:
                p = rf_proba_c["B"]
                sorted_p = np.sort(p, axis=1)
                rf_pre = {"p_top": p.max(axis=1),
                          "margin": sorted_p[:, -1] - sorted_p[:, -2],
                          "argmax": p.argmax(axis=1).astype(np.float64)}
            if edl_pre is None:
                a = alpha_c["B"]
                S = a.sum(axis=1)
                edl_pre = {"S": S, "p_top": a.max(axis=1) / S,
                           "p_2nd": np.partition(a, -2, axis=1)[:, -2] / S,
                           "argmax": a.argmax(axis=1).astype(np.float64)}
            st[cond] = st_view(cond, actions, rf_proba_c, alpha_c, maha_post,
                               rf_pre, edl_pre, maha_pre)
        st["BASIC"] = st_view("BASIC", actions, None, None, None,
                              rf_pre, edl_pre, maha_pre)
        np.savez_compressed(
            cfg["out"] / "features" / f"{rot}_cond.npz",
            **{f"raw_{c}": raw[c].astype(np.float64) for c in CONDITIONS},
            **{f"st_{c}": st[c].astype(np.float64) for c in CONDITIONS},
            allow_pickle=False)

        # probe B TRAIN features (frozen §4): all 175,000 TRAIN-partition
        # rows with rotation-C-conditioned features; acquired states from
        # frozen rotation-C selectors + typed_policy_actions, budget 26,250
        # over the full TRAIN partition, order = ascending TRAIN row index.
        train_rows_all = train_rows
        order = np.argsort(train_rows_all, kind="stable")
        basic_tr = basic_matrix_for(train_rows_all, basic_arrays,
                                    basic_positions)
        hist_tr, hnames = load_history_features(GATE1, CENTRAL_SEED,
                                                train_rows_all)
        feats_tr_all = build_feature_matrices(basic_tr, hist_tr, hnames)
        rf_b = pkls[rot]["models"]["B"]
        # OWG known-class order for OWG selector features (see
        # p6_reproduction; the frozen selectors were trained with
        # owg.known_classes_for, not the V2 cell tuple).
        known_owg = owg.known_classes_for(rot)
        proba_b = owg.align_rotation_proba(
            rf_b.predict_proba(feats_tr_all["B"]), rf_b.classes_, known_owg)
        pred_b = rf_b.predict(feats_tr_all["B"])
        sel_feats, names = owg.rotation_selector_features(
            basic_tr, pred_b, proba_b, np.ones(len(train_rows_all)),
            known_owg)
        if owg.selector_leakage_audit(names) != "PASS":
            raise SystemExit(f"SELECTOR_LEAKAGE_AUDIT_FAIL rotation={rot}")
        u_t = pkls[rot]["selectors"]["T"].predict(sel_feats)
        u_r = pkls[rot]["selectors"]["R"].predict(sel_feats)
        u_tr = pkls[rot]["selectors"]["TR"].predict(sel_feats)
        act_tr = owg.typed_policy_actions(u_t, u_r, u_tr,
                                          TRAIN_BUDGET_UNITS, order)
        states_tr = np.array([ACTION_MODEL[a] for a in act_tr], dtype=object)
        x_raw = raw_legal_matrix(feats_tr_all, states_tr)
        labels_tr_all = targets["canonical_label"][train_mask]
        y_correct = np.zeros(len(train_rows_all), dtype=np.int64)
        for s in EVIDENCE_STATES:
            m = states_tr == s
            if not m.any():
                continue
            y_correct[m] = (pkls[rot]["models"][s].predict(
                feats_tr_all[s][m]) == labels_tr_all[m]).astype(np.int64)
        np.savez_compressed(
            cfg["out"] / "features" / f"{rot}_train_probeB.npz",
            x_raw=x_raw.astype(np.float64), y_correct=y_correct,
            actions=np.array([a.encode() for a in act_tr]),
            rows=train_rows_all, allow_pickle=False)
        mark_stage(mode, key, {
            "n_train": int(len(train_rows_all)),
            "train_action_counts": {a: int((act_tr == a).sum())
                                    for a in ("NONE", "T", "R", "TR")},
            "shuffled_marginal_ok": bool(shuf_ok),
            "null_blocks_ok": True,
            "y_correct_pos": float(y_correct.mean())})
        print(f"[S2 {rot}] condition views + probe-B TRAIN features "
              f"(acq={(act_tr != 'NONE').mean():.4f} "
              f"y_pos={y_correct.mean():.4f})", flush=True)

    # --- S3: probe A fits (3 families x 2 views x 3 folds) ---
    if not stage_done(mode, "s3_probeA"):
        for fold_rot in ROTATIONS:
            dev_rots = [r for r in ROTATIONS if r != fold_rot]
            feat_dir = cfg["out"] / "features"
            cond_c = {r: dict(np.load(feat_dir / f"{r}_cond.npz",
                                      allow_pickle=True))
                      for r in ROTATIONS}
            for view in VIEWS:
                prefix = "raw" if view == "RAW" else "st"
                X_dev_parts, y_dev_parts = [], []
                for r in dev_rots:
                    role = cells[r]["ev_split_role"]
                    unk = cells[r]["ev_is_unknown"].astype(bool)
                    rec = cells[r]["ev_recoverable"].astype(bool)
                    dev_mask = (role == 0) & (rec | unk)
                    X_dev_parts.append(
                        cond_c[r][f"{prefix}_REAL"][dev_mask])
                    y_dev_parts.append(unk[dev_mask].astype(np.int64))
                X_fit = np.concatenate(X_dev_parts)
                y_fit = np.concatenate(y_dev_parts)
                cell = cells[fold_rot]
                role = cell["ev_split_role"]
                unk = cell["ev_is_unknown"].astype(bool)
                rec = cell["ev_recoverable"].astype(bool)
                test_mask = (role == 1) & (rec | unk)
                if cfg["test_max"] is not None:      # smoke subset
                    keep = np.flatnonzero(test_mask)[:cfg["test_max"]]
                    test_mask = np.zeros_like(test_mask)
                    test_mask[keep] = True
                if cfg["dev_max"] is not None:       # smoke subset
                    X_fit = X_fit[:cfg["dev_max"]]
                    y_fit = y_fit[:cfg["dev_max"]]
                y_test = unk[test_mask].astype(np.int64)
                X_test = {cond: cond_c[fold_rot][f"{prefix}_{cond}"][test_mask]
                          for cond in CONDITIONS}
                # threshold rows: the test RK rows (same-population
                # convention §9.1)
                X_thr = {cond: X_test[cond][y_test == 0]
                         for cond in CONDITIONS}
                for family in FAMILIES:
                    fit_out = probe_fit_and_score(
                        "A", fold_rot, family, view, X_fit, y_fit, X_test,
                        y_test, X_thr, cfg)
                    d = (cfg["out"] / "probe_A" / fold_rot / family / view)
                    d.mkdir(parents=True, exist_ok=True)
                    np.savez_compressed(
                        d / "scores.npz",
                        **{f"s_{cond}": fit_out["scores"][cond]
                           for cond in CONDITIONS},
                        y=y_test,
                        groups=group_codes(cell["ev_groups"][test_mask]),
                        allow_pickle=False)
                    fit_out.pop("scores")
                    (d / "metrics.json").write_text(
                        json.dumps(fit_out, indent=1, default=str),
                        encoding="utf-8")
        mark_stage(mode, "s3_probeA", {"fits": 18})
        print("[S3] probe A fits complete (18)", flush=True)

    # --- S4: probe B fits (3 families x 3 folds) ---
    if not stage_done(mode, "s4_probeB"):
        for fold_rot in ROTATIONS:
            tr = dict(np.load(cfg["out"] / "features"
                              / f"{fold_rot}_train_probeB.npz",
                              allow_pickle=True))
            cond_c = dict(np.load(cfg["out"] / "features"
                                  / f"{fold_rot}_cond.npz",
                                  allow_pickle=True))
            cell = cells[fold_rot]
            role = cell["ev_split_role"]
            unk = cell["ev_is_unknown"].astype(bool)
            rec = cell["ev_recoverable"].astype(bool)
            test_mask = (role == 1) & (rec | unk)
            if cfg["test_max"] is not None:      # smoke subset
                keep = np.flatnonzero(test_mask)[:cfg["test_max"]]
                test_mask = np.zeros_like(test_mask)
                test_mask[keep] = True
            y_test = unk[test_mask].astype(np.int64)
            thr_mask = (role == 0) & (~unk)      # role-0 Known (Known-only)
            if cfg["train_max"] is not None:     # smoke subset
                X_fit = tr["x_raw"][:cfg["train_max"]]
                y_fit = tr["y_correct"][:cfg["train_max"]]
            else:
                X_fit, y_fit = tr["x_raw"], tr["y_correct"]
            X_test = {cond: cond_c[f"raw_{cond}"][test_mask]
                      for cond in CONDITIONS}
            # threshold rows: rotation-C role-0 Known rows (§9.2)
            X_thr = {cond: cond_c[f"raw_{cond}"][thr_mask]
                     for cond in CONDITIONS}
            for family in FAMILIES:
                fit_out = probe_fit_and_score(
                    "B", fold_rot, family, "RAW", X_fit, y_fit, X_test,
                    y_test, X_thr, cfg)
                d = (cfg["out"] / "probe_B" / fold_rot / family)
                d.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(
                    d / "scores.npz",
                    **{f"s_{cond}": fit_out["scores"][cond]
                       for cond in CONDITIONS},
                    y=y_test,
                    groups=group_codes(cell["ev_groups"][test_mask]),
                    allow_pickle=False)
                fit_out.pop("scores")
                (d / "metrics.json").write_text(
                    json.dumps(fit_out, indent=1, default=str),
                    encoding="utf-8")
        mark_stage(mode, "s4_probeB", {"fits": 9})
        print("[S4] probe B fits complete (9)", flush=True)

    # --- S5: bootstrap per (probe, family, view) ---
    if not stage_done(mode, "s5_bootstrap"):
        for probe, views in (("A", VIEWS), ("B", ("RAW",))):
            for view in views:
                for family in FAMILIES:
                    key = f"P{probe}_{view}_{family}"
                    fits: dict[str, Any] = {}
                    for fold_rot in ROTATIONS:
                        d = (cfg["out"] / f"probe_{probe}" / fold_rot
                             / family / view) if probe == "A" else \
                            (cfg["out"] / f"probe_{probe}" / fold_rot / family)
                        z = np.load(d / "scores.npz", allow_pickle=True)
                        m = json.loads((d / "metrics.json").read_text())
                        fits[fold_rot] = {}
                        for cond in CONDITIONS:
                            y = z["y"]
                            fits[fold_rot][cond] = {
                                "scores": z[f"s_{cond}"], "y": y,
                                "groups": z["groups"],
                                "threshold": m["per_condition"][cond]["threshold"],
                                "point_auroc": m["per_condition"][cond]["auroc"],
                                "point_aupr": m["per_condition"][cond]["aupr"],
                                "point_recall": m["per_condition"][cond]["recall_at_5fur"],
                                "n": int(len(y))}
                    (cfg["out"] / "bootstrap").mkdir(parents=True,
                                                     exist_ok=True)
                    boot = bootstrap_pooled_view(fits, cfg)
                    (cfg["out"] / "bootstrap" / f"{key}.json").write_text(
                        json.dumps(boot, indent=1, default=str),
                        encoding="utf-8")
                    print(f"[S5] bootstrap {key} complete", flush=True)
        mark_stage(mode, "s5_bootstrap", {"keys": 9})
        print("[S5] bootstrap complete (9 keys)", flush=True)

    # --- S6: consistency rules, retention, decision tree, aggregate ---
    if not stage_done(mode, "s6_aggregate"):
        boot: dict[str, Any] = {}
        for probe, views in (("A", VIEWS), ("B", ("RAW",))):
            for view in views:
                boot.setdefault(f"P{probe}_{view}", {})
                for family in FAMILIES:
                    boot[f"P{probe}_{view}"][family] = json.loads(
                        (cfg["out"] / "bootstrap"
                         / f"P{probe}_{view}_{family}.json").read_text())
        n_mat: dict[tuple[str, str], int] = {}
        n_sb: dict[tuple[str, str], int] = {}
        rot_ok_all: dict[tuple[str, str], bool] = {}
        rot_ok_sb: dict[tuple[str, str], bool] = {}
        for probe, views in (("A", VIEWS), ("B", ("RAW",))):
            for view in views:
                fams = boot[f"P{probe}_{view}"]
                n_mat[(probe, view)] = sum(
                    material(fams[f]) for f in FAMILIES)
                n_sb[(probe, view)] = sum(
                    shuffled_over_basic_material(fams[f]) for f in FAMILIES)
                rot_ok_all[(probe, view)] = rot_ok(
                    fams, (("REAL", "BASIC"), ("REAL", "SHUFFLED")))
                rot_ok_sb[(probe, view)] = rot_ok(
                    fams, (("SHUFFLED", "BASIC"),))
        fams_a_raw = boot["PA_RAW"]
        # shortcut criterion D: no family with REAL-SHUFFLED material on A,RAW
        shortcut_d = all(
            not real_over_shuffled_material(fams_a_raw[f])
            for f in FAMILIES)
        n_a_raw = n_mat[("A", "RAW")]
        n_sb_a_raw = n_sb[("A", "RAW")]
        rot_a = rot_ok_all[("A", "RAW")]
        rot_b = rot_ok_all[("B", "RAW")]
        n_b_raw = n_mat[("B", "RAW")]
        shortcut_b = n_sb_a_raw >= STRONG_FAMILIES
        shortcut_c = rot_ok_sb[("A", "RAW")]
        # retention over S(A,RAW)
        passing = [f for f in FAMILIES
                   if material(fams_a_raw[f])]
        ret = retention({"RAW": boot["PA_RAW"], "ST": boot["PA_ST"]},
                        passing) if passing else {
            "families": {}, "median_over_families": {}, "bottleneck": None,
            "note": "S(A,RAW) empty -> retention not computed"}
        bot = bool(ret.get("bottleneck")) if passing else False
        outcome = decision(n_a_raw, rot_a, bot, n_b_raw, rot_b,
                           shortcut_b, shortcut_c, shortcut_d)
        aggregate = {
            "task": "RECOVERABILITY_INFORMATION_SUFFICIENCY_GATE_V1",
            "mode": mode, "protocol_sha256": PROTOCOL_SHA256,
            "execution_lock": lock,
            "determinism": det,
            "head_commit": subprocess.run(
                ["git", "-C", str(REPO), "rev-parse", "HEAD"],
                capture_output=True, text=True).stdout.strip(),
            "step0": {**s0, "furk_rederivation": furk_results},
            "bootstrap_keys": {f"P{p}_{v}_{f}": boot[f"P{p}_{v}"][f]
                               for p, vs in (("A", VIEWS), ("B", ("RAW",)))
                               for v in vs for f in FAMILIES},
            "consistency": {
                "n_A_RAW": n_a_raw, "n_A_ST": n_mat[("A", "ST")],
                "n_B_RAW": n_b_raw,
                "n_sb_A_RAW": n_sb_a_raw,
                "rotOK_A_RAW": rot_a, "rotOK_B_RAW": rot_b,
                "rotOK_sb_A_RAW": shortcut_c,
                "shortcut_B": shortcut_b, "shortcut_C": shortcut_c,
                "shortcut_D": shortcut_d,
                "S_A_RAW": passing},
            "retention": ret,
            "tree_inputs": {"nA": n_a_raw, "rotA": rot_a, "bottleneck": bot,
                            "nB": n_b_raw, "rotB": rot_b, "B": shortcut_b,
                            "C": shortcut_c, "D": shortcut_d},
            "outcome": outcome,
            "manifest_notes": [
                "protocol §2 table 'train_pool_per_rotation: 135000' is an "
                "informational typo; TRAIN_POOL_N=150000 is code-enforced and "
                "no computation uses 135000 (probe B uses the full 175,000 "
                "TRAIN partition per §4).",
                "bootstrap: np.random.default_rng(162600) per (probe,family,"
                "view) key; identical rotation-stratified group-atomic draws "
                "across all 27 fits (fully paired).",
                "thresholds fixed per (fold, family, view, condition) from "
                "full calibration rows; probe A: test RK rows same-population "
                "convention; probe B: role-0 Known rows Known-only.",
                "frozen P6 FURK re-derivation uses the V2 deployable "
                "convention (per-row Mahalanobis at acquired state, 95th-pct "
                "threshold over role-0 Known, role-1 recoverable-Known "
                "denominator) matching strong_hybrid_osr_evidence_gate_v2_"
                "validation.json furk1.",
            ],
        }
        (cfg["out"] / "aggregate.json").write_text(
            json.dumps(aggregate, indent=1, default=str), encoding="utf-8")
        (cfg["out"] / "run_manifest.json").write_text(json.dumps({
            "task": "RECOVERABILITY_INFORMATION_SUFFICIENCY_GATE_V1",
            "mode": mode, "protocol_sha256": PROTOCOL_SHA256,
            "preregistration_sha256": lock["preregistration_sha256"],
            "head_commit": aggregate["head_commit"],
            "determinism": det, "rng_offsets": {
                "shuffled_permutation": SHUF_RNG_OFFSET,
                "b_edl_retrain": EDL_RETRAIN_RNG_OFFSET,
                "bootstrap": BOOTSTRAP_RNG, "rng_base": RNG_BASE},
            "bootstrap_reps": cfg["bs_reps"], "materiality_floor": MATERIALITY,
            "strong_families": STRONG_FAMILIES, "rot_ok_min": ROT_OK_MIN,
            "retention_threshold": RETENTION_THRESHOLD,
            "notes": aggregate["manifest_notes"],
        }, indent=1), encoding="utf-8")
        mark_stage(mode, "s6_aggregate", {"outcome": outcome})
        print(f"[S6] aggregate complete — outcome={outcome}", flush=True)

    outcome = json.loads(marker_path(mode, "s6_aggregate").read_text())["outcome"]
    write_run_state("COMPLETE", mode, {"outcome": outcome})
    print(f"[gate {mode}] FINISHED in {time.time() - start:.0f}s "
          f"— outcome={outcome}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
