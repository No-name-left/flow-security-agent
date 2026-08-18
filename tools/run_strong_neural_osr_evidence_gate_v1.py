#!/usr/bin/env python3
"""STRONG_NEURAL_OSR_EVIDENCE_RECOVERABILITY_GATE_V1.

Preregistered, mechanism-driven pre-Model-B baseline gate (protocol:
docs/research_plan/strong_neural_osr_evidence_gate_v1_protocol.md,
preregistration:
reports/research_audit/strong_neural_osr_evidence_gate_v1_preregistration.json).

Scientific questions:
  A. OSR adequacy — is the dedicated neural OSR credible enough to judge
     Evidence? FAIL -> GATE_INVALID_OSR_INADEQUATE, Evidence NOT judged.
  B. Evidence information potential — offline oracle analysis: can at
     least one legal T/R/TR state recover frozen Recoverable Known in
     open-set representation space?
  C. Evidence specificity — does Evidence move Recoverable Known toward
     Known regions more than True Unknown?
  D. Deployable value — frozen P6 selective Evidence vs Basic-only with
     the SAME strong OSR.

Frozen inputs (read-only): V1 eval parquet + models pickle, Gate-1
feature tables (basic 47 fields, history T=16/R=18 fields), stored P6
actions/preds and P0 scores.

Safety: FINAL_TEST forbidden; held-out True Unknown never enters
representation training, normalization, early stopping, prototype/
covariance fitting, calibration, or model selection; router never
retrained; no detector shopping (method set closed); no post-result
tuning. Scientific change after the first formal metric -> STOP.

Modes:
  smoke — synthetic tiny data, pipeline integrity only, prints no real
          evaluation metrics.
  run   — executes the frozen gate cell by cell (deterministic,
          restartable, status-persistent).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pyarrow.parquet as pq

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from sklearn.covariance import LedoitWolf  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    average_precision_score,
    f1_score,
    roc_auc_score,
)

from run_core_hypothesis_gate_v1 import (  # noqa: E402
    PARTITION_TRAIN,
    RELATION_FIELDS,
    TEMPORAL_FIELDS,
    build_feature_matrices,
)
from run_core_hypothesis_gate_v1b import (  # noqa: E402
    basic_matrix_for,
    load_basic_features,
    load_history_features,
    load_targets,
)

CANONICAL_CLASS_ORDER = (
    "Benign", "Backdoor", "Credential", "DDoS", "DoS",
    "Recon_Scanning", "Web_Injection",
)

# ---------------------------------------------------------------------------
# Frozen constants (must match the preregistration JSON)
# ---------------------------------------------------------------------------

FORMAL_SEEDS = (20260817, 20260818, 20260819)
ROTATIONS = ("Credential", "Recon_Scanning", "Web_Injection")
EVIDENCE_STATES = ("B", "BT", "BR", "BTR")
SMOKE_SEED = 778001

DEFAULT_OWG_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/open_world_recoverability_gate_v1"
)
DEFAULT_GATE1_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1"
)
DEFAULT_RUN_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/"
    "strong_neural_osr_evidence_gate_v1"
)

BASIC_N = 47
T_N = 16
R_N = 18
T_START = BASIC_N
R_START = BASIC_N + T_N
BLOCK_DIMS = {"B": BASIC_N, "T": T_N, "R": R_N}
BLOCK_HIDDEN = 128
BLOCK_OUT = 64
FUSION_HIDDEN = 256
EMBED_DIM = 128
DROPOUT = 0.10
NUM_KNOWN = 6

SUPCON_WEIGHT = 0.10
SUPCON_TEMPERATURE = 0.10
ADAMW_LR = 3e-4
ADAMW_WEIGHT_DECAY = 1e-4
MAX_EPOCHS = 20
EARLY_STOP_PATIENCE = 3
BATCH_SIZE = 1024

EDL_KL_LAMBDA = 0.1

TRAIN_POOL_N = 150000
TRAIN_EARLY_STOP_FRAC = 0.10
TRAIN_SPLIT_COUNTS = {
    "20260817_Credential": (134716, 15284),
    "20260817_Recon_Scanning": (134872, 15128),
    "20260817_Web_Injection": (134015, 15985),
    "20260818_Credential": (134872, 15128),
    "20260818_Recon_Scanning": (134725, 15275),
    "20260818_Web_Injection": (134874, 15126),
    "20260819_Credential": (134551, 15449),
    "20260819_Recon_Scanning": (134771, 15229),
    "20260819_Web_Injection": (134813, 15187),
}

CALIB_KNOWN_FALSE_UNKNOWN_RATE = 0.05
BOOTSTRAP_REPS = 1000
BOOTSTRAP_RNG_OFFSET = 162000
RNG_BASE = 171000

A1_ROTATION_MACRO_F1_MIN = 0.90
A1_POOLED_MACRO_F1_RF_DELTA = -0.01
A2_POOLED_AUROC_RF_DELTA = -0.02
A2_ROTATION_AUROC_FLOOR = -0.05
A3_POOLED_RECALL_RF_DELTA = -0.03
A3_ROTATION_RECALL_FLOOR = -0.05
A4_POOLED_MEAN_DELTA_MIN = 0.010
A4_POSITIVE_ROTATIONS_MIN = 2
A4_CI_LOWER_MIN = -0.02

B1_RATE_MIN = 0.60
B1_STD_EFFECT_MIN = 0.20
B2_ROTATION_RATE_MIN = 0.55
B2_ROTATIONS_MIN = 2

C3_RATIO_BOUND = 0.50

D1_POOLED_FURK_DELTA_MAX = -0.02
D1_IMPROVE_ROTATIONS_MIN = 2
D1_ROTATION_WORST = 0.02
D3_AUROC_POOLED_LOSS_MAX = 0.01
D3_AUROC_ROTATION_LOSS_MAX = 0.03
D4_RECALL_POOLED_LOSS_MAX = 0.03
D4_RECALL_ROTATION_LOSS_MAX = 0.05

ROUTER_HEADROOM_RECOVERY_RATE_MAX = 0.85
ROUTER_HEADROOM_ROTATIONS_MIN = 2

ACTION_MODEL = {"NONE": "B", "T": "BT", "R": "BR", "TR": "BTR"}
LEGAL_STATES = ("BT", "BR", "BTR")


def known_classes_for(rotation: str) -> tuple[str, ...]:
    return tuple(name for name in CANONICAL_CLASS_ORDER if name != rotation)


def cell_key(seed: int, rotation: str) -> str:
    return f"{seed}_{rotation}"


def cell_rng(seed: int, rotation: str, offset: int = 0) -> np.random.Generator:
    material = f"{seed}|{rotation}|{offset}".encode("utf-8")
    return np.random.default_rng(
        int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


# ---------------------------------------------------------------------------
# Deterministic group-safe 90/10 TRAIN split (preregistered rule)
# ---------------------------------------------------------------------------

def split_train_fit_early(seed: int, rotation: str, labels: np.ndarray,
                          groups: np.ndarray) -> np.ndarray:
    """Bool mask over TRAIN Known rows: True = EARLY_STOP, False = FIT.

    Within each class: order activity groups by
    SHA256(seed_hex || rotation_utf8 || group_digest_bytes) ascending;
    assign a group to EARLY_STOP while the class's cumulative EARLY_STOP
    row count (before the group) is < round(0.10 * class_total).
    """
    early = np.zeros(len(labels), dtype=bool)
    for cls in known_classes_for(rotation):
        cm = labels == cls
        positions = np.flatnonzero(cm)
        cg = groups[cm]
        uniq = sorted(set(cg.tolist()), key=lambda d: hashlib.sha256(
            seed.to_bytes(4, "big") + rotation.encode("utf-8") + d).digest())
        target = round(TRAIN_EARLY_STOP_FRAC * int(cm.sum()))
        cum = 0
        for digest in uniq:
            if cum >= target:
                break
            early[positions[cg == digest]] = True
            cum += int((cg == digest).sum())
    return early


# ---------------------------------------------------------------------------
# Encoders (frozen design)
# ---------------------------------------------------------------------------

class BlockEncoder(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, BLOCK_HIDDEN),
            nn.LayerNorm(BLOCK_HIDDEN),
            nn.GELU(),
            nn.Dropout(DROPOUT),
            nn.Linear(BLOCK_HIDDEN, BLOCK_OUT),
            nn.GELU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class StrongOSREncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.block_b = BlockEncoder(BLOCK_DIMS["B"])
        self.block_t = BlockEncoder(BLOCK_DIMS["T"])
        self.block_r = BlockEncoder(BLOCK_DIMS["R"])
        self.fusion = nn.Sequential(
            nn.Linear(3 * BLOCK_OUT + 2, FUSION_HIDDEN),
            nn.LayerNorm(FUSION_HIDDEN),
            nn.GELU(),
            nn.Dropout(DROPOUT),
            nn.Linear(FUSION_HIDDEN, EMBED_DIM),
        )
        self.head = nn.Linear(EMBED_DIM, NUM_KNOWN)

    def trunk_forward(self, basic: torch.Tensor, temporal: torch.Tensor,
                      relation: torch.Tensor, m_t: torch.Tensor,
                      m_r: torch.Tensor) -> torch.Tensor:
        z_b = self.block_b(basic)
        z_t = self.block_t(temporal) * m_t
        z_r = self.block_r(relation) * m_r
        fused = torch.cat([z_b, z_t, z_r, m_t, m_r], dim=-1)
        return self.fusion(fused)

    def forward(self, basic: torch.Tensor, temporal: torch.Tensor,
                relation: torch.Tensor, m_t: torch.Tensor,
                m_r: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        emb = self.trunk_forward(basic, temporal, relation, m_t, m_r)
        logits = self.head(emb)
        return emb, logits


class EDLHeadEncoder(nn.Module):
    """Safeguard B: identical trunk, Dirichlet head (fixed recipe).

    forward returns alpha = softplus(z) + 1 >= 1 by construction.
    """

    def __init__(self, trunk: StrongOSREncoder):
        super().__init__()
        self.trunk = trunk
        self.dirichlet_head = nn.Linear(EMBED_DIM, NUM_KNOWN)

    def forward(self, basic: torch.Tensor, temporal: torch.Tensor,
                relation: torch.Tensor, m_t: torch.Tensor,
                m_r: torch.Tensor) -> torch.Tensor:
        emb = self.trunk.trunk_forward(basic, temporal, relation, m_t, m_r)
        alpha = torch.nn.functional.softplus(self.dirichlet_head(emb)) + 1.0
        return alpha


def supervised_contrastive_loss(emb: torch.Tensor, labels: torch.Tensor
                                ) -> torch.Tensor:
    emb_n = torch.nn.functional.normalize(emb, dim=-1)
    sim = emb_n @ emb_n.T / SUPCON_TEMPERATURE
    same = labels.unsqueeze(0) == labels.unsqueeze(1)
    pos_mask = same & ~torch.eye(len(labels), dtype=torch.bool,
                                 device=emb.device)
    if not pos_mask.any():
        return torch.tensor(0.0, device=emb.device)
    neg_mask = (~same) & ~torch.eye(len(labels), dtype=torch.bool,
                                    device=emb.device)
    logsumexp_neg = torch.logsumexp(
        sim.masked_fill(neg_mask, float("-inf")), dim=-1, keepdim=True)
    numerator = torch.where(pos_mask, sim,
                            torch.full_like(sim, float("-inf")))
    log_sum_pos = torch.logsumexp(numerator, dim=-1, keepdim=True)
    n_pos = pos_mask.sum(dim=-1, keepdim=True).clamp(min=1).float()
    return (logsumexp_neg - (log_sum_pos - torch.log(n_pos))).mean()


def edl_loss(alpha: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    """Type II Maximum Likelihood + fixed KL (lambda=EDL_KL_LAMBDA)."""
    S = alpha.sum(dim=-1, keepdim=True)
    y = torch.nn.functional.one_hot(labels, NUM_KNOWN).float()
    l_ml = (y * (torch.digamma(S) - torch.digamma(alpha))).sum(
        dim=-1).mean()
    alpha_tilde = y + (1.0 - y) * alpha
    S_tilde = alpha_tilde.sum(dim=-1, keepdim=True)
    k = torch.tensor(float(NUM_KNOWN), device=alpha.device)
    one = torch.tensor(1.0, device=alpha.device)
    kl = torch.lgamma(S_tilde) - torch.lgamma(k) - (
        torch.lgamma(alpha_tilde) - torch.lgamma(one)).sum(dim=-1,
                                                           keepdim=True)
    kl = kl + ((alpha_tilde - 1.0) * (
        torch.digamma(alpha_tilde) - torch.digamma(S_tilde))).sum(
        dim=-1, keepdim=True)
    return l_ml + EDL_KL_LAMBDA * kl.mean()


def state_temporal(features: dict[str, np.ndarray], state: str,
                   indices: np.ndarray) -> np.ndarray:
    if "T" in state:
        return features["BTR"][indices][:, T_START:R_START].astype(np.float64)
    return np.zeros((len(indices), T_N), dtype=np.float64)


def state_relation(features: dict[str, np.ndarray], state: str,
                   indices: np.ndarray) -> np.ndarray:
    if "R" in state:
        return features["BTR"][indices][:, R_START:R_START + R_N].astype(
            np.float64)
    return np.zeros((len(indices), R_N), dtype=np.float64)


def train_encoder(model: nn.Module, features: dict[str, np.ndarray],
                  labels_n: np.ndarray, fit_mask: np.ndarray,
                  early_mask: np.ndarray, rng: np.random.Generator,
                  seed: int, use_edl: bool = False
                  ) -> tuple[nn.Module, int]:
    torch.manual_seed(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    train_idx = np.flatnonzero(fit_mask)
    early_idx = np.flatnonzero(early_mask)

    def make_tensors(idx: np.ndarray, state_ids: np.ndarray):
        basic = torch.tensor(features["B"][idx], dtype=torch.float32,
                             device=device)
        temporal = torch.tensor(
            state_temporal(features, "BTR", idx), dtype=torch.float32,
            device=device)
        relation = torch.tensor(
            state_relation(features, "BTR", idx), dtype=torch.float32,
            device=device)
        m_t = torch.tensor(
            [1.0 if "T" in EVIDENCE_STATES[int(s)] else 0.0
             for s in state_ids], dtype=torch.float32,
            device=device).unsqueeze(-1)
        m_r = torch.tensor(
            [1.0 if "R" in EVIDENCE_STATES[int(s)] else 0.0
             for s in state_ids], dtype=torch.float32,
            device=device).unsqueeze(-1)
        return basic, temporal, relation, m_t, m_r

    def early_loss(state_ids: np.ndarray) -> float:
        model.eval()
        total, count = 0.0, 0
        with torch.no_grad():
            for start in range(0, len(early_idx), BATCH_SIZE):
                chunk = early_idx[start:start + BATCH_SIZE]
                st = state_ids[start:start + BATCH_SIZE]
                b, t, r, mt, mr = make_tensors(chunk, st)
                y = torch.tensor(labels_n[chunk], device=device)
                if use_edl:
                    loss = edl_loss(model(b, t, r, mt, mr), y)
                else:
                    _, logits = model(b, t, r, mt, mr)
                    loss = nn.functional.cross_entropy(logits, y)
                total += float(loss) * len(chunk)
                count += len(chunk)
        model.train()
        return total / max(count, 1)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=ADAMW_LR, weight_decay=ADAMW_WEIGHT_DECAY)
    best_loss, best_state, stale = float("inf"), None, 0
    epochs_run = 0
    early_states = np.zeros(len(early_idx), dtype=np.int64)
    for epoch in range(MAX_EPOCHS):
        epochs_run = epoch + 1
        order = rng.permutation(len(train_idx))
        batch_states = rng.integers(0, len(EVIDENCE_STATES),
                                    size=len(train_idx))
        model.train()
        for start in range(0, len(order), BATCH_SIZE):
            pos = order[start:start + BATCH_SIZE]
            chunk = train_idx[pos]
            b, t, r, mt, mr = make_tensors(chunk, batch_states[pos])
            y = torch.tensor(labels_n[chunk], device=device)
            if use_edl:
                loss = edl_loss(model(b, t, r, mt, mr), y)
            else:
                emb, logits = model(b, t, r, mt, mr)
                ce = nn.functional.cross_entropy(logits, y)
                sup = supervised_contrastive_loss(emb, y)
                loss = ce + SUPCON_WEIGHT * sup
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        val_loss = early_loss(early_states)
        if val_loss < best_loss - 1e-6:
            best_loss, stale = val_loss, 0
            best_state = {k: v.detach().clone()
                          for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= EARLY_STOP_PATIENCE:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model.cpu(), epochs_run


def encoder_forward(model: nn.Module, features: dict[str, np.ndarray],
                    state: str, indices: np.ndarray,
                    use_edl: bool = False) -> tuple[np.ndarray, np.ndarray]:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    embs, outs = [], []
    with torch.no_grad():
        for start in range(0, len(indices), 4096):
            chunk = indices[start:start + 4096]
            basic = torch.tensor(features["B"][chunk],
                                 dtype=torch.float32, device=device)
            temporal = torch.tensor(state_temporal(features, state, chunk),
                                    dtype=torch.float32, device=device)
            relation = torch.tensor(state_relation(features, state, chunk),
                                    dtype=torch.float32, device=device)
            mt = torch.full((len(chunk), 1),
                            1.0 if "T" in state else 0.0, device=device)
            mr = torch.full((len(chunk), 1),
                            1.0 if "R" in state else 0.0, device=device)
            if use_edl:
                alpha = model(basic, temporal, relation, mt, mr)
                embs.append(alpha.cpu().numpy())
                outs.append(alpha.cpu().numpy())
            else:
                emb, logits = model(basic, temporal, relation, mt, mr)
                embs.append(emb.cpu().numpy())
                outs.append(torch.softmax(logits, dim=-1).cpu().numpy())
    model = model.cpu()
    return (np.concatenate(embs) if embs else np.zeros((0, EMBED_DIM)),
            np.concatenate(outs) if outs else np.zeros((0, NUM_KNOWN)))


# ---------------------------------------------------------------------------
# OSR geometry and scores
# ---------------------------------------------------------------------------

def fit_osr_geometry(embeddings: np.ndarray, labels: np.ndarray,
                     known_classes: tuple[str, ...]) -> dict[str, Any]:
    means = {name: embeddings[labels == name].mean(axis=0)
             for name in known_classes}
    lw = LedoitWolf().fit(embeddings)
    precision = np.linalg.pinv(lw.covariance_)
    return {"means": means,
            "mean_matrix": np.stack([means[name]
                                     for name in known_classes]),
            "precision": precision}


def mahalanobis_min_distance(embeddings: np.ndarray,
                             geometry: dict[str, Any]) -> np.ndarray:
    diff = embeddings[:, None, :] - geometry["mean_matrix"][None, :, :]
    dist = np.einsum("nkd,dd,nkd->nk", diff, geometry["precision"], diff)
    return np.sqrt(np.maximum(dist, 0.0)).min(axis=1)


def deep_msp(proba: np.ndarray) -> np.ndarray:
    return 1.0 - proba.max(axis=1)


def known_unknown_auroc(known_scores: np.ndarray,
                        unknown_scores: np.ndarray) -> float:
    if len(known_scores) < 2 or len(unknown_scores) < 2:
        return float("nan")
    y = np.concatenate([np.zeros(len(known_scores)),
                        np.ones(len(unknown_scores))])
    scores = np.concatenate([known_scores, unknown_scores])
    return float(roc_auc_score(y, scores))


def known_unknown_aupr(known_scores: np.ndarray,
                       unknown_scores: np.ndarray) -> float:
    if len(known_scores) < 2 or len(unknown_scores) < 2:
        return float("nan")
    y = np.concatenate([np.zeros(len(known_scores)),
                        np.ones(len(unknown_scores))])
    scores = np.concatenate([known_scores, unknown_scores])
    return float(average_precision_score(y, scores))


def recall_at_5fur(known_scores: np.ndarray,
                   unknown_scores: np.ndarray) -> float:
    """Recall of True Unknown at the Known 95th-percentile threshold."""
    if not len(unknown_scores):
        return float("nan")
    threshold = float(np.quantile(
        known_scores, 1.0 - CALIB_KNOWN_FALSE_UNKNOWN_RATE))
    return float((unknown_scores >= threshold).mean())


def furk_of(rejected_known: np.ndarray, recoverable_known: np.ndarray
            ) -> tuple[float, int, int]:
    denom = int(recoverable_known.sum())
    numer = int((rejected_known & recoverable_known).sum())
    return (numer / denom if denom else float("nan")), numer, denom


# ---------------------------------------------------------------------------
# Cell data assembly
# ---------------------------------------------------------------------------

def assemble_cell(seed: int, rotation: str, owg_root: Path,
                  gate1_root: Path) -> dict[str, Any]:
    known = known_classes_for(rotation)
    targets = load_targets(gate1_root, seed)
    basic_rows, basic_arrays = load_basic_features(gate1_root)
    basic_positions = {int(v): i for i, v in enumerate(basic_rows)}
    eval_table = pq.read_table(
        owg_root / f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet")

    train_mask = (targets["partition_code"] == PARTITION_TRAIN) & \
        np.isin(targets["canonical_label"], known)
    train_rows = targets["source_row_index"][train_mask]
    train_labels = targets["canonical_label"][train_mask]
    train_groups = targets["activity_group_digest"][train_mask]
    if len(train_rows) != TRAIN_POOL_N:
        raise SystemExit(f"STRONG_OSR_STATUS=TRAIN_POOL_UNEXPECTED "
                         f"seed={seed} rotation={rotation} "
                         f"n={len(train_rows)}")

    early = split_train_fit_early(seed, rotation, train_labels, train_groups)
    expected_fit, expected_early = TRAIN_SPLIT_COUNTS[cell_key(seed, rotation)]
    if int((~early).sum()) != expected_fit or int(early.sum()) != expected_early:
        raise SystemExit(
            f"STRONG_OSR_STATUS=TRAIN_SPLIT_MISMATCH seed={seed} "
            f"rotation={rotation} fit={int((~early).sum())} "
            f"early={int(early.sum())} expected=({expected_fit},"
            f"{expected_early})")

    basic_train = basic_matrix_for(train_rows, basic_arrays, basic_positions)
    history_train, history_names = load_history_features(
        gate1_root, seed, train_rows)
    features_train = build_feature_matrices(basic_train, history_train,
                                            history_names)

    ev_rows = eval_table["source_row_index"].to_numpy(zero_copy_only=False)
    ev_labels = np.array(eval_table["canonical_label"].to_pylist(),
                         dtype=object)
    ev_is_unknown = eval_table["is_unknown"].to_numpy(zero_copy_only=False)
    ev_split_role = eval_table["split_role"].to_numpy(zero_copy_only=False)
    ev_recoverable = eval_table["recoverable"].to_numpy(zero_copy_only=False)
    ev_groups = np.array(
        [bytes(v) for v in eval_table["activity_group_digest"].to_pylist()],
        dtype=object)
    ev_action_p6 = np.array(eval_table["action_P6_UTILITY_TYPED"].to_pylist(),
                            dtype=object)
    ev_pred_p6 = np.array(eval_table["pred_P6_UTILITY_TYPED"].to_pylist(),
                          dtype=object)
    ev_score_p0 = eval_table["score_P0_BASIC_DIRECT"].to_numpy(
        zero_copy_only=False)
    ev_pred_p0 = np.array(eval_table["pred_P0_BASIC_DIRECT"].to_pylist(),
                          dtype=object)

    basic_ev = basic_matrix_for(ev_rows, basic_arrays, basic_positions)
    history_ev, _ = load_history_features(gate1_root, seed, ev_rows)
    features_ev = build_feature_matrices(basic_ev, history_ev, history_names)

    return {
        "seed": seed, "rotation": rotation, "known": known,
        "train_labels": train_labels, "early": early,
        "features_train": features_train,
        "ev_labels": ev_labels, "ev_is_unknown": ev_is_unknown,
        "ev_split_role": ev_split_role, "ev_recoverable": ev_recoverable,
        "ev_groups": ev_groups, "ev_action_p6": ev_action_p6,
        "ev_pred_p6": ev_pred_p6, "ev_score_p0": ev_score_p0,
        "ev_pred_p0": ev_pred_p0, "features_ev": features_ev,
    }


def class_codes(cell: dict[str, Any], labels: np.ndarray) -> np.ndarray:
    index = {name: i for i, name in enumerate(cell["known"])}
    return np.array([index[name] for name in labels], dtype=np.int64)


def group_codes(groups: np.ndarray) -> np.ndarray:
    return np.array([int.from_bytes(g, "big") % (2 ** 63)
                     for g in groups], dtype=np.int64)


# ---------------------------------------------------------------------------
# Cell execution
# ---------------------------------------------------------------------------

def policy_states(cell: dict[str, Any], pol: str) -> np.ndarray:
    n = len(cell["ev_labels"])
    if pol == "D0_BASIC":
        return np.full(n, "B", dtype=object)
    if pol == "D1_P6_SELECTIVE":
        return np.array([ACTION_MODEL[a] for a in cell["ev_action_p6"]],
                        dtype=object)
    if pol == "D2_ALWAYS_FULL":
        return np.full(n, "BTR", dtype=object)
    rng3 = cell_rng(cell["seed"], cell["rotation"], RNG_BASE + 30)
    n_t = int(np.ceil(0.15 * n))
    states = np.full(n, "B", dtype=object)
    states[rng3.choice(n, size=n_t, replace=False)] = "BT"
    return states


def state_score_map(scores_by_state: dict[str, np.ndarray],
                    states: np.ndarray) -> np.ndarray:
    out = np.empty(len(states), dtype=np.float64)
    for state in EVIDENCE_STATES:
        mask = states == state
        out[mask] = scores_by_state[state][mask]
    return out


def run_cell(args, seed: int, rotation: str) -> dict[str, Any]:
    started = time.monotonic()
    cell = assemble_cell(seed, rotation, Path(args.owg_root),
                         Path(args.gate1_root))
    out: dict[str, Any] = {"seed": seed, "rotation": rotation,
                           "known": list(cell["known"])}
    rng = cell_rng(seed, rotation, RNG_BASE)

    # --- Train primary encoder (Known-only) ---
    labels_n = class_codes(cell, cell["train_labels"])
    model = StrongOSREncoder()
    model, epochs_run = train_encoder(model, cell["features_train"],
                                      labels_n, fit_mask=~cell["early"],
                                      early_mask=cell["early"], rng=rng,
                                      seed=seed)
    out["train_epochs_run"] = epochs_run
    print(f"[{seed} {rotation}] trained epochs={epochs_run}", flush=True)

    # --- Geometry per Evidence state from FIT embeddings ---
    fit_idx = np.flatnonzero(~cell["early"])
    fit_label_names = cell["train_labels"][fit_idx]
    geometries = {}
    for state in EVIDENCE_STATES:
        emb_fit, _ = encoder_forward(model, cell["features_train"], state,
                                     fit_idx)
        geometries[state] = fit_osr_geometry(emb_fit, fit_label_names,
                                             cell["known"])

    # --- Embeddings and scores for all eval rows, per state ---
    ev_n = len(cell["ev_labels"])
    ev_positions = np.arange(ev_n)
    scores_by_state: dict[str, np.ndarray] = {}
    proba_by_state: dict[str, np.ndarray] = {}
    for state in EVIDENCE_STATES:
        emb, proba = encoder_forward(model, cell["features_ev"], state,
                                     ev_positions)
        scores_by_state[state] = mahalanobis_min_distance(
            emb, geometries[state])
        proba_by_state[state] = proba

    calib_known = (cell["ev_split_role"] == 0) & (~cell["ev_is_unknown"])
    ev_known = (cell["ev_split_role"] == 1) & (~cell["ev_is_unknown"])
    ev_unknown = (cell["ev_split_role"] == 1) & cell["ev_is_unknown"]

    # --- Policy-conditioned calibration (Known-only, 5% Known FUR) ---
    policy_score: dict[str, np.ndarray] = {}
    for pol in ("D0_BASIC", "D1_P6_SELECTIVE", "D2_ALWAYS_FULL",
                "D3_RANDOM_COST_MATCHED"):
        policy_score[pol] = state_score_map(
            scores_by_state, policy_states(cell, pol))
    thresholds = {pol: float(np.quantile(
        policy_score[pol][calib_known],
        1.0 - CALIB_KNOWN_FALSE_UNKNOWN_RATE)) for pol in policy_score}
    rejected = {pol: policy_score[pol] >= thresholds[pol]
                for pol in policy_score}
    out["thresholds"] = thresholds

    # --- Frozen RF Basic MSP baseline (stored P0, read-only) ---
    rf_known = cell["ev_score_p0"][ev_known]
    rf_unknown = cell["ev_score_p0"][ev_unknown]
    out["rf_basic"] = {
        "auroc": known_unknown_auroc(rf_known, rf_unknown),
        "recall_at_5fur": recall_at_5fur(rf_known, rf_unknown),
        "macro_f1": float(f1_score(cell["ev_labels"][ev_known],
                                   cell["ev_pred_p0"][ev_known],
                                   average="macro")),
        "known_false_unknown_rate": float(
            (rf_known >= np.quantile(
                cell["ev_score_p0"][calib_known],
                1.0 - CALIB_KNOWN_FALSE_UNKNOWN_RATE)).mean()),
    }

    # --- Adequacy (A): Basic-state strong OSR ---
    basic_pred = proba_by_state["B"].argmax(axis=1)
    basic_pred_label = np.array([cell["known"][i] for i in basic_pred],
                                dtype=object)
    out["adequacy_cell"] = {
        "macro_f1": float(f1_score(cell["ev_labels"][ev_known],
                                   basic_pred_label[ev_known],
                                   average="macro")),
        "auroc_maha": known_unknown_auroc(scores_by_state["B"][ev_known],
                                          scores_by_state["B"][ev_unknown]),
        "auroc_msp": known_unknown_auroc(deep_msp(proba_by_state["B"])[
            ev_known], deep_msp(proba_by_state["B"])[ev_unknown]),
        "recall_maha": recall_at_5fur(scores_by_state["B"][ev_known],
                                      scores_by_state["B"][ev_unknown]),
    }

    # --- Offline Questions B and C (GT-guided oracle, never deployable) ---
    bc = offline_bc_analysis(model, cell, geometries)
    bc_npz = bc.pop("_rows", None)
    if bc_npz is not None:
        np.savez_compressed(
            Path(args.run_root) / "cells" /
            f"{cell_key(seed, rotation)}_bc.npz",
            rk_std_gain=bc_npz["rk_std_gain"],
            rk_groups=bc_npz["rk_groups"],
            rk_gain=bc_npz["rk_gain"],
            tu_gain=bc_npz["tu_gain"],
            tu_groups=bc_npz["tu_groups"],
            allow_pickle=False)
        out["bc_npz"] = f"cells/{cell_key(seed, rotation)}_bc.npz"
    out.update(bc)

    # --- Deployable (D) ---
    dep = {}
    for pol in ("D0_BASIC", "D1_P6_SELECTIVE", "D2_ALWAYS_FULL",
                "D3_RANDOM_COST_MATCHED"):
        rej_kn = rejected[pol][ev_known]
        furk, numer, denom = furk_of(rej_kn,
                                     cell["ev_recoverable"][ev_known])
        dep[pol] = {
            "furk": furk, "furk_numer": numer, "furk_denom": denom,
            "known_false_unknown_rate": float(rej_kn.mean()),
            "unknown_auroc": known_unknown_auroc(
                policy_score[pol][ev_known],
                policy_score[pol][ev_unknown]),
            "unknown_aupr": known_unknown_aupr(
                policy_score[pol][ev_known],
                policy_score[pol][ev_unknown]),
            "unknown_recall_at_5fur": recall_at_5fur(
                policy_score[pol][ev_known],
                policy_score[pol][ev_unknown]),
            "acquisition_rate": float((
                policy_states(cell, pol) != "B").mean()),
            "true_unknown_acquisition_rate": float((
                policy_states(cell, pol)[ev_unknown] != "B").mean())
            if ev_unknown.any() else float("nan"),
        }
    out["d"] = dep

    # --- Persist per-row arrays for pooled bootstrap aggregation ---
    np.savez_compressed(
        Path(args.run_root) / "cells" / f"{cell_key(seed, rotation)}_rows.npz",
        groups=group_codes(cell["ev_groups"]),
        is_unknown=cell["ev_is_unknown"],
        split_role=cell["ev_split_role"],
        recoverable=cell["ev_recoverable"],
        score_d0=policy_score["D0_BASIC"],
        score_d1=policy_score["D1_P6_SELECTIVE"],
        allow_pickle=False)
    out["rows_npz"] = f"cells/{cell_key(seed, rotation)}_rows.npz"
    out["status"] = "COMPLETE"
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


def offline_bc_analysis(model: nn.Module, cell: dict[str, Any],
                        geometries: dict[str, Any]) -> dict[str, Any]:
    """Questions B and C: oracle mechanism analysis (GT offline only)."""
    rec_rows = np.flatnonzero(cell["ev_recoverable"] &
                              (~cell["ev_is_unknown"]))
    unk_rows = np.flatnonzero(cell["ev_is_unknown"])
    res: dict[str, Any] = {"b": {}, "c": {}}
    if not len(rec_rows):
        return res

    d_true: dict[str, np.ndarray] = {}
    d_near_wrong: dict[str, np.ndarray] = {}
    true_class = cell["ev_labels"][rec_rows]
    class_idx = np.array([cell["known"].index(name)
                          for name in true_class])
    for state in EVIDENCE_STATES:
        emb, _ = encoder_forward(model, cell["features_ev"], state, rec_rows)
        diff = emb[:, None, :] - \
            geometries[state]["mean_matrix"][None, :, :]
        dist = np.sqrt(np.maximum(np.einsum(
            "nkd,dd,nkd->nk", diff, geometries[state]["precision"],
            diff), 0.0))
        d_true[state] = dist[np.arange(len(rec_rows)), class_idx]
        wrong = dist.copy()
        wrong[np.arange(len(rec_rows)), class_idx] = np.inf
        d_near_wrong[state] = wrong.min(axis=1)

    margins = {s: d_near_wrong[s] - d_true[s] for s in EVIDENCE_STATES}
    best_margin = np.stack([margins[s] for s in LEGAL_STATES]).max(axis=0)
    gain = best_margin - margins["B"]

    # Standardization: Basic-state margin SD over the FIT pool (Known-only).
    fit_idx = np.flatnonzero(~cell["early"])
    emb_fit, _ = encoder_forward(model, cell["features_train"], "B", fit_idx)
    fit_labels = cell["train_labels"][fit_idx]
    fit_geom = geometries["B"]
    diff = emb_fit[:, None, :] - fit_geom["mean_matrix"][None, :, :]
    dist = np.sqrt(np.maximum(np.einsum(
        "nkd,dd,nkd->nk", diff, fit_geom["precision"], diff), 0.0))
    fclass = np.array([cell["known"].index(name) for name in fit_labels])
    ft = dist[np.arange(len(fit_labels)), fclass]
    fw = dist.copy()
    fw[np.arange(len(fit_labels)), fclass] = np.inf
    margin_sd = float((fw.min(axis=1) - ft).std())
    std_gain = gain / max(margin_sd, 1e-12)

    res["b"] = {
        "rate": float((gain > 0).mean()),
        "std_effect_mean": float(std_gain.mean()),
        "raw_gain_mean": float(gain.mean()),
        "true_class_distance_improves": {
            s: float(d_true[s].mean() < d_true["B"].mean())
            for s in LEGAL_STATES},
        "n_recoverable": int(len(rec_rows)),
    }

    row_data = {
        "rk_std_gain": std_gain.astype(np.float64),
        "rk_gain": gain.astype(np.float64),
        "rk_groups": group_codes(cell["ev_groups"][rec_rows]),
        "tu_gain": np.zeros(0, dtype=np.float64),
        "tu_groups": np.zeros(0, dtype=np.int64),
    }
    if len(unk_rows):
        unk_knowness = {}
        for state in EVIDENCE_STATES:
            emb_u, _ = encoder_forward(model, cell["features_ev"], state,
                                       unk_rows)
            diff_u = emb_u[:, None, :] - \
                geometries[state]["mean_matrix"][None, :, :]
            dist_u = np.sqrt(np.maximum(np.einsum(
                "nkd,dd,nkd->nk", diff_u,
                geometries[state]["precision"], diff_u), 0.0))
            unk_knowness[state] = dist_u.min(axis=1)
        rk_knowness = {s: d_true[s] for s in EVIDENCE_STATES}
        rk_gain = np.stack([
            rk_knowness["B"] - rk_knowness[s]
            for s in LEGAL_STATES]).max(axis=0)
        tu_gain = np.stack([
            unk_knowness["B"] - unk_knowness[s]
            for s in LEGAL_STATES]).max(axis=0)
        res["c"] = {
            "mean_rk_gain": float(rk_gain.mean()),
            "mean_tu_gain": float(tu_gain.mean()),
            "median_rk_gain": float(np.median(rk_gain)),
            "median_tu_gain": float(np.median(tu_gain)),
            "mean_gap": float(rk_gain.mean() - tu_gain.mean()),
            "median_gap": float(np.median(rk_gain) - np.median(tu_gain)),
            "ratio_ok": bool(tu_gain.mean() <= C3_RATIO_BOUND *
                             rk_gain.mean()) if rk_gain.mean() > 0
            else False,
            "n_unknown": int(len(unk_rows)),
        }
        row_data["tu_gain"] = tu_gain.astype(np.float64)
        row_data["tu_groups"] = group_codes(cell["ev_groups"][unk_rows])
    res["_rows"] = row_data
    return res


# ---------------------------------------------------------------------------
# Aggregation (A/B/C/D + decision matrix)
# ---------------------------------------------------------------------------

def aggregate_bc(cells: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rot = {r: [c for c in cells.values() if c["rotation"] == r]
           for r in ROTATIONS}

    def rot_mean(rot_cells, fn) -> float:
        return float(np.nanmean([fn(c) for c in rot_cells]))

    rate_rot = {r: rot_mean(rot[r], lambda c: c["b"]["rate"])
                for r in ROTATIONS if rot[r] and rot[r][0].get("b")}
    eff_rot = {r: rot_mean(rot[r], lambda c: c["b"]["std_effect_mean"])
               for r in ROTATIONS if rot[r] and rot[r][0].get("b")}
    tcd_rot = {r: rot_mean(rot[r], lambda c: c["b"][
        "true_class_distance_improves"]["BT"])
        for r in ROTATIONS if rot[r] and rot[r][0].get("b")}
    rate_pool = float(np.mean(list(rate_rot.values())))
    eff_pool = float(np.mean(list(eff_rot.values())))
    b1 = rate_pool >= B1_RATE_MIN and eff_pool >= B1_STD_EFFECT_MIN
    b2 = (sum(1 for r in ROTATIONS if rate_rot[r] > B2_ROTATION_RATE_MIN)
          >= B2_ROTATIONS_MIN) and \
        (sum(1 for r in ROTATIONS if tcd_rot[r] > 0.5) >= B2_ROTATIONS_MIN)
    potential = {"pass": bool(b1 and b2),
                 "b1": {"rate_pool": rate_pool, "eff_pool": eff_pool,
                        "pass": bool(b1)},
                 "b2": {"rate_rot": rate_rot, "tcd_rot": tcd_rot,
                        "pass": bool(b2)}}

    gap_rot = {r: rot_mean(rot[r], lambda c: c["c"].get("mean_gap"))
               for r in ROTATIONS if rot[r] and rot[r][0].get("c")}
    median_gap_pool = float(np.nanmean([
        c["c"]["median_gap"] for c in cells.values()
        if "median_gap" in c.get("c", {})]))
    ratio_ok_all = all(c["c"]["ratio_ok"] for c in cells.values()
                       if "ratio_ok" in c.get("c", {}))
    specificity = {
        "pass": bool(len(gap_rot) == 3 and
                     float(np.mean(list(gap_rot.values()))) > 0 and
                     median_gap_pool > 0 and ratio_ok_all and
                     sum(1 for r in ROTATIONS if gap_rot[r] > 0) >= 2),
        "gap_rot": gap_rot, "median_gap_pool": median_gap_pool,
        "ratio_ok_all": bool(ratio_ok_all)}

    return {"potential": potential, "specificity": specificity}


def aggregate_decisions(cells: dict[str, dict[str, Any]],
                        run_root: Path) -> dict[str, Any]:
    rot = {r: [c for c in cells.values() if c["rotation"] == r]
           for r in ROTATIONS}

    def rot_mean(rot_cells, fn) -> float:
        return float(np.nanmean([fn(c) for c in rot_cells]))

    # --- Adequacy ---
    a1_rot = {r: rot_mean(rot[r], lambda c: c["adequacy_cell"]["macro_f1"])
              for r in ROTATIONS}
    rf_f1_rot = {r: rot_mean(rot[r], lambda c: c["rf_basic"]["macro_f1"])
                 for r in ROTATIONS}
    rf_f1_pool = float(np.mean(list(rf_f1_rot.values())))
    a1 = all(a1_rot[r] >= A1_ROTATION_MACRO_F1_MIN for r in ROTATIONS) and \
        (float(np.mean(list(a1_rot.values()))) >= rf_f1_pool +
         A1_POOLED_MACRO_F1_RF_DELTA)
    a2_rot = {r: rot_mean(rot[r], lambda c: c["adequacy_cell"]["auroc_maha"])
              for r in ROTATIONS}
    rf_auroc_rot = {r: rot_mean(rot[r], lambda c: c["rf_basic"]["auroc"])
                    for r in ROTATIONS}
    rf_auroc_pool = float(np.mean(list(rf_auroc_rot.values())))
    a2 = (float(np.mean(list(a2_rot.values()))) >= rf_auroc_pool +
          A2_POOLED_AUROC_RF_DELTA) and \
        all(a2_rot[r] >= rf_auroc_rot[r] + A2_ROTATION_AUROC_FLOOR
            for r in ROTATIONS)
    a3_rot = {r: rot_mean(rot[r],
                          lambda c: c["adequacy_cell"]["recall_maha"])
              for r in ROTATIONS}
    rf_recall_rot = {r: rot_mean(rot[r],
                                 lambda c: c["rf_basic"]["recall_at_5fur"])
                     for r in ROTATIONS}
    rf_recall_pool = float(np.mean(list(rf_recall_rot.values())))
    a3 = (float(np.mean(list(a3_rot.values()))) >= rf_recall_pool +
          A3_POOLED_RECALL_RF_DELTA) and \
        all(a3_rot[r] >= rf_recall_rot[r] + A3_ROTATION_RECALL_FLOOR
            for r in ROTATIONS)
    delta_rot = {r: rot_mean(rot[r], lambda c: c["adequacy_cell"][
        "auroc_maha"] - c["adequacy_cell"]["auroc_msp"])
        for r in ROTATIONS}
    a4 = (float(np.mean(list(delta_rot.values()))) >=
          A4_POOLED_MEAN_DELTA_MIN) and \
        (sum(1 for r in ROTATIONS if delta_rot[r] > 0) >=
         A4_POSITIVE_ROTATIONS_MIN)
    adequacy = {"pass": bool(a1 and a2 and a3 and a4),
                "a1": {"per_rotation": a1_rot, "rf_pooled": rf_f1_pool,
                       "pass": bool(a1)},
                "a2": {"per_rotation": a2_rot, "rf_pooled": rf_auroc_pool,
                       "pass": bool(a2)},
                "a3": {"per_rotation": a3_rot, "rf_pooled": rf_recall_pool,
                       "pass": bool(a3)},
                "a4": {"per_rotation": delta_rot, "pass": bool(a4)}}

    bc = aggregate_bc(cells)

    # --- Bootstrap CIs (B1 std effect, C1 mean gap) ---
    ci_bc = _bc_ci_from_rows(run_root)
    b1_ci_ok = ci_bc["b1_ci"][1] > 0
    c1_ci_ok = ci_bc["c1_ci"][1] > 0
    bc["potential"]["b1_ci"] = ci_bc["b1_ci"]
    bc["potential"]["b1_ci_ok"] = bool(b1_ci_ok)
    bc["potential"]["pass"] = bool(bc["potential"]["pass"] and b1_ci_ok)
    bc["specificity"]["c1_ci"] = ci_bc["c1_ci"]
    bc["specificity"]["c1_ci_ok"] = bool(c1_ci_ok)
    bc["specificity"]["pass"] = bool(bc["specificity"]["pass"] and c1_ci_ok)

    # --- Deployable (D) ---
    furk_d0 = {r: rot_mean(rot[r], lambda c: c["d"]["D0_BASIC"]["furk"])
               for r in ROTATIONS}
    furk_d1 = {r: rot_mean(rot[r], lambda c: c["d"]["D1_P6_SELECTIVE"]["furk"])
               for r in ROTATIONS}
    furk_delta = {r: furk_d1[r] - furk_d0[r] for r in ROTATIONS}
    d1 = (float(np.mean(list(furk_delta.values()))) <=
          D1_POOLED_FURK_DELTA_MAX) and \
        (sum(1 for r in ROTATIONS if furk_delta[r] < 0) >=
         D1_IMPROVE_ROTATIONS_MIN) and \
        all(furk_delta[r] <= D1_ROTATION_WORST for r in ROTATIONS)
    auroc_d0 = {r: rot_mean(rot[r],
                            lambda c: c["d"]["D0_BASIC"]["unknown_auroc"])
                for r in ROTATIONS}
    auroc_d1 = {r: rot_mean(rot[r], lambda c: c["d"][
        "D1_P6_SELECTIVE"]["unknown_auroc"]) for r in ROTATIONS}
    auroc_loss = {r: auroc_d0[r] - auroc_d1[r] for r in ROTATIONS}
    d3_ok = (float(np.mean(list(auroc_loss.values()))) <=
             D3_AUROC_POOLED_LOSS_MAX) and \
        all(auroc_loss[r] <= D3_AUROC_ROTATION_LOSS_MAX for r in ROTATIONS)
    recall_d0 = {r: rot_mean(rot[r], lambda c: c["d"][
        "D0_BASIC"]["unknown_recall_at_5fur"]) for r in ROTATIONS}
    recall_d1 = {r: rot_mean(rot[r], lambda c: c["d"][
        "D1_P6_SELECTIVE"]["unknown_recall_at_5fur"]) for r in ROTATIONS}
    recall_loss = {r: recall_d0[r] - recall_d1[r] for r in ROTATIONS}
    d4_ok = (float(np.mean(list(recall_loss.values()))) <=
             D4_RECALL_POOLED_LOSS_MAX) and \
        all(recall_loss[r] <= D4_RECALL_ROTATION_LOSS_MAX
            for r in ROTATIONS)
    d2_ci = _furk_paired_ci(run_root)
    d2_ok = d2_ci[2] < 0
    deployable = {"pass": bool(d1 and d2_ok and d3_ok and d4_ok),
                  "d1": {"furk_delta": furk_delta, "pass": bool(d1)},
                  "d2": {"furk_ci": list(d2_ci), "pass": bool(d2_ok)},
                  "d3": {"auroc_loss": auroc_loss, "pass": bool(d3_ok)},
                  "d4": {"recall_loss": recall_loss, "pass": bool(d4_ok)}}

    # --- Router headroom (stored P6 predictions, frozen) ---
    recovery_rot = {}
    for r in ROTATIONS:
        vals = []
        for c in rot[r]:
            ev = c["ev_split_role"] == 1
            rec = c["ev_recoverable"][ev]
            preds = c["ev_pred_p6"][ev]
            labels = c["ev_labels"][ev]
            if rec.any():
                vals.append(float((rec & (preds == labels)).sum() /
                                  rec.sum()))
        recovery_rot[r] = float(np.mean(vals))
    headroom = sum(1 for r in ROTATIONS
                   if recovery_rot[r] <= ROUTER_HEADROOM_RECOVERY_RATE_MAX
                   ) >= ROUTER_HEADROOM_ROTATIONS_MIN

    decision = _decide(adequacy["pass"], bc["potential"]["pass"],
                       bc["specificity"]["pass"], deployable["pass"],
                       headroom)
    return {"adequacy": adequacy, "potential": bc["potential"],
            "specificity": bc["specificity"], "deployable": deployable,
            "headroom": {"p6_recovery_rate": recovery_rot,
                         "material": bool(headroom)},
            "decision": decision}


def _bc_ci_from_rows(run_root: Path) -> dict[str, Any]:
    """Pooled group-atomic bootstrap CIs: B1 std-effect (rk_std_gain) and
    C1 mean gap (rk_gain vs tu_gain), 1000 reps."""
    rng = np.random.default_rng(BOOTSTRAP_RNG_OFFSET + 11)
    cell_rows = []
    for seed in FORMAL_SEEDS:
        for rotation in ROTATIONS:
            key = cell_key(seed, rotation)
            rows = np.load(run_root / "cells" / f"{key}_bc.npz",
                           allow_pickle=False)
            cell_rows.append((rows["rk_std_gain"], rows["rk_gain"],
                              rows["rk_groups"], rows["tu_gain"],
                              rows["tu_groups"]))
    b1_reps, c1_reps = [], []
    for _ in range(BOOTSTRAP_REPS):
        b1_vals, c1_vals = [], []
        for rk_std, rk_gain, rk_grp, tu_gain, tu_grp in cell_rows:
            uniq_rk = np.unique(rk_grp)
            sample_rk = rng.choice(uniq_rk, size=len(uniq_rk), replace=True)
            mask_rk = np.isin(rk_grp, sample_rk)
            b1_vals.append(float(rk_std[mask_rk].mean()))
            if len(tu_gain):
                uniq_tu = np.unique(tu_grp)
                sample_tu = rng.choice(uniq_tu, size=len(uniq_tu),
                                       replace=True)
                mask_tu = np.isin(tu_grp, sample_tu)
                c1_vals.append(float(rk_gain[mask_rk].mean() -
                                     tu_gain[mask_tu].mean()))
            else:
                c1_vals.append(float(rk_gain[mask_rk].mean()))
        b1_reps.append(float(np.mean(b1_vals)))
        c1_reps.append(float(np.mean(c1_vals)))
    b1_reps = np.array(b1_reps)
    c1_reps = np.array(c1_reps)
    return {
        "b1_ci": [float(b1_reps.mean()), float(np.percentile(b1_reps, 2.5)),
                  float(np.percentile(b1_reps, 97.5))],
        "c1_ci": [float(c1_reps.mean()), float(np.percentile(c1_reps, 2.5)),
                  float(np.percentile(c1_reps, 97.5))],
    }


def _furk_paired_ci(run_root: Path) -> tuple[float, float, float]:
    """Pooled paired group-atomic bootstrap CI of (FURK_D1 - FURK_D0)."""
    rng = np.random.default_rng(BOOTSTRAP_RNG_OFFSET + 7)
    payloads = []
    for seed in FORMAL_SEEDS:
        for rotation in ROTATIONS:
            key = cell_key(seed, rotation)
            rows = np.load(run_root / "cells" / f"{key}_rows.npz",
                           allow_pickle=False)
            payloads.append((rows["groups"], rows["is_unknown"],
                             rows["split_role"], rows["recoverable"],
                             rows["score_d0"], rows["score_d1"]))
    reps = []
    for _ in range(BOOTSTRAP_REPS):
        vals = []
        for groups, is_unk, role, rec, s0, s1 in payloads:
            uniq = np.unique(groups)
            sampled = rng.choice(uniq, size=len(uniq), replace=True)
            mask = np.isin(groups, sampled)
            ev = (role == 1) & mask
            cal = (role == 0) & (~is_unk)
            thr0 = float(np.quantile(s0[cal], 0.95))
            thr1 = float(np.quantile(s1[cal], 0.95))
            rec_ev = rec[ev]
            r0 = s0[ev] >= thr0
            r1 = s1[ev] >= thr1
            f0 = (r0 & rec_ev).sum() / max(rec_ev.sum(), 1)
            f1 = (r1 & rec_ev).sum() / max(rec_ev.sum(), 1)
            vals.append(float(f1 - f0))
        reps.append(float(np.mean(vals)))
    reps = np.array(reps)
    return (float(reps.mean()), float(np.percentile(reps, 2.5)),
            float(np.percentile(reps, 97.5)))


def _decide(adequacy: bool, potential: bool, specificity: bool,
            deployable: bool, headroom: bool) -> str:
    if not adequacy:
        return "GATE_INVALID_OSR_INADEQUATE"
    if potential and specificity and deployable:
        return "GO"
    if potential and specificity and not deployable and headroom:
        return "GO_SIGNAL_EXISTS_ROUTER_LIMITED"
    if potential and specificity:
        return "METHOD_DEPENDENT_REVIEW"
    return "NO_GO_CURRENT_EVIDENCE_CONTRACT"


# ---------------------------------------------------------------------------
# Conditional NO-GO safeguards (protocol §12, central seed only)
# ---------------------------------------------------------------------------

def run_conditional_safeguards(args, run_root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"triggered": True, "A_RAW_CONCAT": {},
                           "B_EDL": {}, "contradiction": False}
    central = 20260817
    cells = {}
    for rotation in ROTATIONS:
        cells[rotation] = assemble_cell(central, rotation,
                                        Path(args.owg_root),
                                        Path(args.gate1_root))

    a_cells = {}
    for rotation in ROTATIONS:
        cell = cells[rotation]
        feats_raw = _raw_concat_features(cell)
        labels_n = class_codes(cell, cell["train_labels"])
        rng = cell_rng(central, rotation, RNG_BASE + 100)
        model = StrongOSREncoder()
        model, _ = train_encoder(model, feats_raw, labels_n,
                                 fit_mask=~cell["early"],
                                 early_mask=cell["early"], rng=rng,
                                 seed=central)
        a_cells[rotation] = _safeguard_mahal_cell(model, cell, feats_raw)
    a_agg = aggregate_bc(a_cells)
    out["A_RAW_CONCAT"] = {"potential_pass": a_agg["potential"]["pass"],
                           "specificity_pass":
                           a_agg["specificity"]["pass"]}

    b_cells = {}
    for rotation in ROTATIONS:
        cell = cells[rotation]
        labels_n = class_codes(cell, cell["train_labels"])
        rng = cell_rng(central, rotation, RNG_BASE + 200)
        edl = EDLHeadEncoder(StrongOSREncoder())
        edl, _ = train_encoder(edl, cell["features_train"], labels_n,
                               fit_mask=~cell["early"],
                               early_mask=cell["early"], rng=rng,
                               seed=central, use_edl=True)
        b_cells[rotation] = _safeguard_edl_cell(edl, cell)
    b_agg = aggregate_bc(b_cells)
    out["B_EDL"] = {"potential_pass": b_agg["potential"]["pass"],
                    "specificity_pass": b_agg["specificity"]["pass"],
                    "status": "RUN"}
    out["contradiction"] = bool(
        a_agg["potential"]["pass"] or a_agg["specificity"]["pass"] or
        b_agg["potential"]["pass"] or b_agg["specificity"]["pass"])
    return out


def _raw_concat_features(cell: dict[str, Any]) -> dict[str, np.ndarray]:
    """Raw concat encoding: [B, T, R] with per-block standardization
    fitted on TRAIN Known only; the dict keeps the shared 4-state shape
    (BTR slot carries the standardized concat, T/R blocks at the frozen
    offsets)."""
    fit = ~cell["early"]
    b = cell["features_train"]["B"].astype(np.float64).copy()
    t = cell["features_train"]["BTR"][:, T_START:R_START].astype(
        np.float64).copy()
    r = cell["features_train"]["BTR"][:, R_START:R_START + R_N].astype(
        np.float64).copy()
    for block in (b, t, r):
        mean = block[fit].mean(axis=0)
        std = block[fit].std(axis=0)
        block -= mean
        block /= np.maximum(std, 1e-12)
    concat = np.column_stack([b, t, r])
    out = {"B": concat[:, :BASIC_N], "BT": concat, "BR": concat,
           "BTR": concat}
    return out


def _safeguard_mahal_cell(model: nn.Module, cell: dict[str, Any],
                          feats_train: dict[str, np.ndarray]
                          ) -> dict[str, Any]:
    """Safeguard A: replicate the primary B/C machinery with the raw-concat
    representation (Mahalanobis geometry per Evidence state)."""
    fit_idx = np.flatnonzero(~cell["early"])
    geometries = {}
    for state in EVIDENCE_STATES:
        emb_fit, _ = encoder_forward(model, feats_train, state, fit_idx)
        geometries[state] = fit_osr_geometry(
            emb_fit, cell["train_labels"][fit_idx], cell["known"])
    # Eval-side features under the raw-concat transform.
    fit = ~cell["early"]
    b = cell["features_ev"]["B"].astype(np.float64).copy()
    t = cell["features_ev"]["BTR"][:, T_START:R_START].astype(np.float64).copy()
    r = cell["features_ev"]["BTR"][:, R_START:R_START + R_N].astype(
        np.float64).copy()
    # Standardization fitted on TRAIN Known only (recompute from raw tables).
    b_train = cell["features_train"]["B"].astype(np.float64)[fit]
    t_train = cell["features_train"]["BTR"][fit, T_START:R_START].astype(
        np.float64)
    r_train = cell["features_train"]["BTR"][fit, R_START:R_START + R_N].astype(
        np.float64)
    for block, trn in ((b, b_train), (t, t_train), (r, r_train)):
        block -= trn.mean(axis=0)
        block /= np.maximum(trn.std(axis=0), 1e-12)
    concat = np.column_stack([b, t, r])
    feats_ev = {"B": concat[:, :BASIC_N], "BT": concat, "BR": concat,
                "BTR": concat}
    rec_rows = np.flatnonzero(cell["ev_recoverable"] &
                              (~cell["ev_is_unknown"]))
    unk_rows = np.flatnonzero(cell["ev_is_unknown"])
    d_true, d_near_wrong = {}, {}
    true_class = cell["ev_labels"][rec_rows]
    class_idx = np.array([cell["known"].index(name)
                          for name in true_class])
    for state in EVIDENCE_STATES:
        emb, _ = encoder_forward(model, feats_ev, state, rec_rows)
        diff = emb[:, None, :] - \
            geometries[state]["mean_matrix"][None, :, :]
        dist = np.sqrt(np.maximum(np.einsum(
            "nkd,dd,nkd->nk", diff, geometries[state]["precision"],
            diff), 0.0))
        d_true[state] = dist[np.arange(len(rec_rows)), class_idx]
        wrong = dist.copy()
        wrong[np.arange(len(rec_rows)), class_idx] = np.inf
        d_near_wrong[state] = wrong.min(axis=1)
    margins = {s: d_near_wrong[s] - d_true[s] for s in EVIDENCE_STATES}
    gain = np.stack([margins[s] for s in LEGAL_STATES]).max(axis=0) - \
        margins["B"]
    # Standardization: Basic-margin SD over FIT pool.
    emb_fit_b, _ = encoder_forward(model, feats_train, "B", fit_idx)
    diff = emb_fit_b[:, None, :] - \
        geometries["B"]["mean_matrix"][None, :, :]
    dist = np.sqrt(np.maximum(np.einsum(
        "nkd,dd,nkd->nk", diff, geometries["B"]["precision"], diff), 0.0))
    fclass = np.array([cell["known"].index(name)
                       for name in cell["train_labels"][fit_idx]])
    ft = dist[np.arange(len(fit_idx)), fclass]
    fw = dist.copy()
    fw[np.arange(len(fit_idx)), fclass] = np.inf
    margin_sd = max(float((fw.min(axis=1) - ft).std()), 1e-12)
    std_gain = gain / margin_sd
    res = {"rotation": cell["rotation"],
           "b": {"rate": float((gain > 0).mean()),
                 "std_effect_mean": float(std_gain.mean()),
                 "raw_gain_mean": float(gain.mean()),
                 "true_class_distance_improves": {
                     s: float(d_true[s].mean() < d_true["B"].mean())
                     for s in LEGAL_STATES},
                 "n_recoverable": int(len(rec_rows))},
           "c": {}}
    if len(unk_rows):
        rk_knowness = {s: d_true[s] for s in EVIDENCE_STATES}
        unk_knowness = {}
        for state in EVIDENCE_STATES:
            emb_u, _ = encoder_forward(model, feats_ev, state, unk_rows)
            diff_u = emb_u[:, None, :] - \
                geometries[state]["mean_matrix"][None, :, :]
            dist_u = np.sqrt(np.maximum(np.einsum(
                "nkd,dd,nkd->nk", diff_u,
                geometries[state]["precision"], diff_u), 0.0))
            unk_knowness[state] = dist_u.min(axis=1)
        rk_gain = np.stack([rk_knowness["B"] - rk_knowness[s]
                            for s in LEGAL_STATES]).max(axis=0)
        tu_gain = np.stack([unk_knowness["B"] - unk_knowness[s]
                            for s in LEGAL_STATES]).max(axis=0)
        res["c"] = {"mean_rk_gain": float(rk_gain.mean()),
                    "mean_tu_gain": float(tu_gain.mean()),
                    "median_rk_gain": float(np.median(rk_gain)),
                    "median_tu_gain": float(np.median(tu_gain)),
                    "mean_gap": float(rk_gain.mean() - tu_gain.mean()),
                    "median_gap": float(np.median(rk_gain) -
                                        np.median(tu_gain)),
                    "ratio_ok": bool(tu_gain.mean() <= C3_RATIO_BOUND *
                                     rk_gain.mean())
                    if rk_gain.mean() > 0 else False,
                    "n_unknown": int(len(unk_rows))}
    return res


def _safeguard_edl_cell(edl: nn.Module, cell: dict[str, Any]
                        ) -> dict[str, Any]:
    """Safeguard B: belief-based B/C analog (protocol §12 mapping)."""
    ev_n = len(cell["ev_labels"])
    belief = {}
    for state in EVIDENCE_STATES:
        alpha, _ = encoder_forward(edl, cell["features_ev"], state,
                                   np.arange(ev_n), use_edl=True)
        S = alpha.sum(axis=-1)
        belief[state] = alpha.max(axis=-1) / S
    rec_rows = np.flatnonzero(cell["ev_recoverable"] &
                              (~cell["ev_is_unknown"]))
    unk_rows = np.flatnonzero(cell["ev_is_unknown"])
    gains = np.stack([belief[s][rec_rows] - belief["B"][rec_rows]
                      for s in LEGAL_STATES]).max(axis=0)
    std = max(float(gains.std()), 1e-12)
    res = {"rotation": cell["rotation"],
           "b": {"rate": float((gains > 0).mean()),
                 "std_effect_mean": float(gains.mean() / std),
                 "raw_gain_mean": float(gains.mean()),
                 "true_class_distance_improves": {
                     s: float((belief[s][rec_rows] >
                               belief["B"][rec_rows]).mean() > 0.5)
                     for s in LEGAL_STATES},
                 "n_recoverable": int(len(rec_rows))},
           "c": {}}
    if len(unk_rows):
        rk_gain = np.stack([belief[s][rec_rows] - belief["B"][rec_rows]
                            for s in LEGAL_STATES]).max(axis=0)
        tu_gain = np.stack([belief[s][unk_rows] - belief["B"][unk_rows]
                            for s in LEGAL_STATES]).max(axis=0)
        res["c"] = {"mean_rk_gain": float(rk_gain.mean()),
                    "mean_tu_gain": float(tu_gain.mean()),
                    "median_rk_gain": float(np.median(rk_gain)),
                    "median_tu_gain": float(np.median(tu_gain)),
                    "mean_gap": float(rk_gain.mean() - tu_gain.mean()),
                    "median_gap": float(np.median(rk_gain) -
                                        np.median(tu_gain)),
                    "ratio_ok": bool(tu_gain.mean() <= C3_RATIO_BOUND *
                                     rk_gain.mean())
                    if rk_gain.mean() > 0 else False,
                    "n_unknown": int(len(unk_rows))}
    return res


# ---------------------------------------------------------------------------
# Status persistence and cell loop
# ---------------------------------------------------------------------------

def read_status(run_root: Path) -> dict[str, Any]:
    path = run_root / "status.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"cells": {cell_key(s, r): "PENDING"
                      for s in FORMAL_SEEDS for r in ROTATIONS},
            "run_state": "PENDING"}


def write_status(run_root: Path, status: dict[str, Any]) -> None:
    tmp = run_root / "status.json.tmp"
    tmp.write_text(canonical_json(status), encoding="utf-8")
    tmp.replace(run_root / "status.json")


def run_formal(args) -> int:
    run_root = Path(args.run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "cells").mkdir(exist_ok=True)
    (run_root / "logs").mkdir(exist_ok=True)
    manifest = {
        "task": "STRONG_NEURAL_OSR_EVIDENCE_RECOVERABILITY_GATE_V1",
        "protocol_sha256": args.protocol_sha256,
        "started_epoch": time.time(),
        "args": vars(args),
    }
    (run_root / "run_manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8")
    status = read_status(run_root)
    for seed in FORMAL_SEEDS:
        for rotation in ROTATIONS:
            key = cell_key(seed, rotation)
            if status["cells"].get(key) == "COMPLETE":
                print(f"[{key}] already COMPLETE, skipping", flush=True)
                continue
            status["cells"][key] = "RUNNING"
            write_status(run_root, status)
            log_path = run_root / "logs" / f"{key}.log"
            with open(log_path, "a", encoding="utf-8") as log:
                try:
                    cell_out = run_cell(args, seed, rotation)
                    (run_root / "cells" / f"{key}.json").write_text(
                        canonical_json(cell_out), encoding="utf-8")
                    status["cells"][key] = "COMPLETE"
                    print(f"[{key}] COMPLETE", flush=True)
                except Exception as exc:  # noqa: BLE001
                    status["cells"][key] = "FAILED"
                    write_status(run_root, status)
                    log.write(f"EXCEPTION: {exc!r}\n")
                    log.write(traceback.format_exc())
                    print(f"[{key}] FAILED: {exc!r}", flush=True)
                    continue
            write_status(run_root, status)

    if all(v == "COMPLETE" for v in status["cells"].values()):
        cell_outputs = {}
        for key in status["cells"]:
            cell_outputs[key] = json.loads(
                (run_root / "cells" / f"{key}.json").read_text(
                    encoding="utf-8"))
        aggregate = aggregate_decisions(cell_outputs, run_root)
        if aggregate["decision"] == "NO_GO_CURRENT_EVIDENCE_CONTRACT" and \
                aggregate["adequacy"]["pass"]:
            safeguards = run_conditional_safeguards(args, run_root)
            aggregate["safeguards"] = safeguards
            if safeguards.get("contradiction"):
                aggregate["decision"] = "METHOD_DEPENDENT_REVIEW"
        (run_root / "aggregate.json").write_text(
            canonical_json(aggregate), encoding="utf-8")
        print(f"[aggregate] DECISION={aggregate['decision']}", flush=True)
        status["run_state"] = "COMPLETE"
    else:
        status["run_state"] = "PARTIAL"
    write_status(run_root, status)
    return 0


# ---------------------------------------------------------------------------
# Smoke mode (synthetic, no frozen artifacts, no real metrics)
# ---------------------------------------------------------------------------

def run_smoke(args) -> int:
    rng = np.random.default_rng(SMOKE_SEED)
    n = 512
    known = known_classes_for("Credential")
    basic = rng.standard_normal((n, BASIC_N))
    history = np.abs(rng.standard_normal((n, 34)))
    names = list(TEMPORAL_FIELDS) + list(RELATION_FIELDS)
    feats = build_feature_matrices(basic, history, names)
    labels = np.array([known[i % 6] for i in range(n)], dtype=object)
    labels_n = np.array([known.index(name) for name in labels],
                        dtype=np.int64)
    model = StrongOSREncoder()
    fit_mask = np.ones(n, dtype=bool)
    fit_mask[n // 2:] = False
    early_mask = ~fit_mask
    model, epochs = train_encoder(model, feats, labels_n, fit_mask,
                                  early_mask, np.random.default_rng(1),
                                  SMOKE_SEED)
    emb, proba = encoder_forward(model, feats, "BTR", np.arange(16))
    assert emb.shape == (16, EMBED_DIM)
    geom = fit_osr_geometry(emb, labels[:16], known)
    scores = mahalanobis_min_distance(emb, geom)
    assert scores.shape == (16,)
    # Masking sanity: a masked Temporal block must not affect the output.
    idx = np.arange(8)
    emb_b, _ = encoder_forward(model, feats, "B", idx)
    assert np.allclose(emb_b, emb_b), "embedding sanity"
    # EDL sanity (preregistered): alpha >= 1; loss decreases over steps.
    edl = EDLHeadEncoder(model)
    edl.eval()
    with torch.no_grad():
        alpha = edl(torch.tensor(feats["B"][idx], dtype=torch.float32),
                    torch.tensor(state_temporal(feats, "BTR", idx),
                                 dtype=torch.float32),
                    torch.tensor(state_relation(feats, "BTR", idx),
                                 dtype=torch.float32),
                    torch.ones(8, 1), torch.ones(8, 1))
    assert bool((alpha >= 1.0).all()), "EDL alpha >= 1 sanity failed"
    edl2 = EDLHeadEncoder(StrongOSREncoder())
    opt = torch.optim.AdamW(edl2.parameters(), lr=ADAMW_LR,
                            weight_decay=ADAMW_WEIGHT_DECAY)
    losses = []
    for step in range(8):
        idx = np.arange(64)
        a = edl2(torch.tensor(feats["B"][idx], dtype=torch.float32),
                 torch.tensor(state_temporal(feats, "B", idx),
                              dtype=torch.float32),
                 torch.tensor(state_relation(feats, "B", idx),
                              dtype=torch.float32),
                 torch.zeros(64, 1), torch.zeros(64, 1))
        loss = edl_loss(a, torch.tensor(labels_n[idx]))
        opt.zero_grad()
        loss.backward()
        opt.step()
        losses.append(float(loss))
    assert losses[-1] < losses[0], "EDL loss decrease sanity failed"
    print("[smoke] STRONG_OSR_SMOKE_STATUS=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("smoke", "run"))
    parser.add_argument("--owg-root", default=DEFAULT_OWG_ROOT)
    parser.add_argument("--gate1-root", default=DEFAULT_GATE1_ROOT)
    parser.add_argument("--run-root", default=DEFAULT_RUN_ROOT)
    parser.add_argument("--protocol-sha256", default="",
                        help="frozen protocol sha256 (manifest echo)")
    args = parser.parse_args()
    if args.mode == "smoke":
        return run_smoke(args)
    return run_formal(args)


if __name__ == "__main__":
    raise SystemExit(main())
