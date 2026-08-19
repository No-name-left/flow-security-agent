#!/usr/bin/env python3
"""STRONG_NEURAL_OSR_V1 A1 DIAGNOSTIC REPLAY.

Diagnostic-only replay of the frozen Strong Neural OSR Gate V1 training
procedure for three representative cells. The ONLY change versus the
frozen runner is additional measurement/logging; every scientific
parameter is imported from the frozen implementation
(run_strong_neural_osr_evidence_gate_v1 at commit 0fd06ca).

Frozen V1 remains: GATE_INVALID_OSR_INADEQUATE,
EVIDENCE_SCIENTIFIC_STATUS=NOT_JUDGED. This tool does not retrain for
selection, does not tune, does not judge Evidence, and does not
overwrite the formal V1 run artifacts.

Replayed cells:
  Credential/20260817   (primary A1 failure)
  Recon_Scanning/20260817 (passing control)
  Web_Injection/20260818  (secondary sub-0.90 case)

Outputs (Git-external):
  processed/dataset_v4_nf3_ton_v1/strong_neural_osr_evidence_gate_v1/
    diagnostic_a1_v1/<cell>/epochs.jsonl  (per-epoch losses/F1/LR/best)
    diagnostic_a1_v1/<cell>/final.json     (final metrics per class)
    diagnostic_a1_v1/<cell>/predictions.npz
    diagnostic_a1_v1/<cell>/model.pt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from sklearn.metrics import confusion_matrix, f1_score  # noqa: E402

from run_strong_neural_osr_evidence_gate_v1 import (  # noqa: E402
    ADAMW_LR,
    ADAMW_WEIGHT_DECAY,
    BATCH_SIZE,
    EARLY_STOP_PATIENCE,
    EVIDENCE_STATES,
    MAX_EPOCHS,
    RNG_BASE,
    SUPCON_WEIGHT,
    StrongOSREncoder,
    assemble_cell,
    cell_key,
    cell_rng,
    class_codes,
    encoder_forward,
    split_train_fit_early,
    supervised_contrastive_loss,
    train_encoder,
)

DEFAULT_OWG_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/open_world_recoverability_gate_v1"
)
DEFAULT_GATE1_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1"
)
DEFAULT_OUT_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/"
    "strong_neural_osr_evidence_gate_v1/diagnostic_a1_v1"
)

REPLAY_CELLS = ((20260817, "Credential"), (20260817, "Recon_Scanning"),
                (20260818, "Web_Injection"))


def macro_f1(pred_labels: np.ndarray, true_labels: np.ndarray,
             known: tuple[str, ...]) -> float:
    return float(f1_score(true_labels, pred_labels, labels=list(known),
                          average="macro", zero_division=0))


def per_class_metrics(pred_labels: np.ndarray, true_labels: np.ndarray,
                      known: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    for name in known:
        tp = int(((pred_labels == name) & (true_labels == name)).sum())
        fp = int(((pred_labels == name) & (true_labels != name)).sum())
        fn = int(((pred_labels != name) & (true_labels == name)).sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) \
            if precision + recall else 0.0
        out[name] = {"precision": precision, "recall": recall, "f1": f1,
                     "tp": tp, "fp": fp, "fn": fn, "n": int(
                         (true_labels == name).sum())}
    cm = confusion_matrix(true_labels, pred_labels, labels=list(known))
    pairs = []
    for i, name_i in enumerate(known):
        for j, name_j in enumerate(known):
            if i != j and cm[i, j] > 0:
                pairs.append({"true": name_i, "pred": name_j,
                              "n": int(cm[i, j])})
    pairs.sort(key=lambda p: -p["n"])
    return {"per_class": out, "confusion": cm.tolist(),
            "top_confusion_pairs": pairs[:10]}


def predict_basic(model: nn.Module, features: dict, known: tuple,
                  rows: np.ndarray) -> np.ndarray:
    """Basic-state argmax predictions as class names."""
    _, proba = encoder_forward(model, features, "B", rows)
    preds = proba.argmax(axis=1)
    return np.array([known[i] for i in preds], dtype=object)


def replay_cell(seed: int, rotation: str, out_root: Path,
                owg_root: Path, gate1_root: Path) -> dict[str, Any]:
    """Exact frozen training loop + per-epoch diagnostics."""
    cell = assemble_cell(seed, rotation, owg_root, gate1_root)
    known = cell["known"]
    labels_n = class_codes(cell, cell["train_labels"])
    early = cell["early"]
    fit_idx = np.flatnonzero(~early)
    early_idx = np.flatnonzero(early)
    rng = cell_rng(seed, rotation, RNG_BASE)
    torch.manual_seed(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = StrongOSREncoder().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=ADAMW_LR,
                                  weight_decay=ADAMW_WEIGHT_DECAY)
    cell_dir = out_root / cell_key(seed, rotation)
    cell_dir.mkdir(parents=True, exist_ok=True)
    epoch_log_path = cell_dir / "epochs.jsonl"
    with open(epoch_log_path, "w", encoding="utf-8") as log:
        best_loss, best_state, stale = float("inf"), None, 0
        best_epoch = -1
        epoch_records = []
        for epoch in range(MAX_EPOCHS):
            order = rng.permutation(len(fit_idx))
            batch_states = rng.integers(0, len(EVIDENCE_STATES),
                                        size=len(fit_idx))
            ce_sum, sup_sum, n_batches = 0.0, 0.0, 0
            model.train()
            for start in range(0, len(order), BATCH_SIZE):
                pos = order[start:start + BATCH_SIZE]
                chunk = fit_idx[pos]
                st = batch_states[pos]
                basic = torch.tensor(cell["features_train"]["B"][chunk],
                                     dtype=torch.float32, device=device)
                temporal = torch.tensor(
                    cell["features_train"]["BTR"][chunk][:, 47:63],
                    dtype=torch.float32, device=device)
                relation = torch.tensor(
                    cell["features_train"]["BTR"][chunk][:, 63:81],
                    dtype=torch.float32, device=device)
                m_t = torch.tensor(
                    [1.0 if "T" in EVIDENCE_STATES[int(s)] else 0.0
                     for s in st], dtype=torch.float32,
                    device=device).unsqueeze(-1)
                m_r = torch.tensor(
                    [1.0 if "R" in EVIDENCE_STATES[int(s)] else 0.0
                     for s in st], dtype=torch.float32,
                    device=device).unsqueeze(-1)
                y = torch.tensor(labels_n[chunk], device=device)
                emb, logits = model(basic, temporal, relation, m_t, m_r)
                ce = nn.functional.cross_entropy(logits, y)
                sup = supervised_contrastive_loss(emb, y)
                loss = ce + SUPCON_WEIGHT * sup
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                ce_sum += float(ce) * len(chunk)
                sup_sum += float(sup) * len(chunk)
                n_batches += 1
            # Frozen early-stop: validation CE on EARLY_STOP slice, B state.
            model.eval()
            with torch.no_grad():
                val_total, val_count = 0.0, 0
                for start in range(0, len(early_idx), BATCH_SIZE):
                    chunk = early_idx[start:start + BATCH_SIZE]
                    basic = torch.tensor(
                        cell["features_train"]["B"][chunk],
                        dtype=torch.float32, device=device)
                    temporal = torch.zeros(len(chunk), 16, dtype=torch.float32,
                                           device=device)
                    relation = torch.zeros(len(chunk), 18, dtype=torch.float32,
                                           device=device)
                    _, logits = model(basic, temporal, relation,
                                      torch.zeros(len(chunk), 1,
                                                  device=device),
                                      torch.zeros(len(chunk), 1,
                                                  device=device))
                    val_loss = nn.functional.cross_entropy(
                        logits, torch.tensor(labels_n[chunk], device=device))
                    val_total += float(val_loss) * len(chunk)
                    val_count += len(chunk)
            val_loss = val_total / max(val_count, 1)
            is_best = val_loss < best_loss - 1e-6
            if is_best:
                best_loss, stale = val_loss, 0
                best_epoch = epoch + 1
                best_state = {k: v.detach().clone()
                              for k, v in model.state_dict().items()}
            else:
                stale += 1
            # Per-epoch diagnostics (B state, no grad).
            train_preds = predict_basic(model, cell["features_train"],
                                        known, fit_idx)
            early_preds = predict_basic(model, cell["features_train"],
                                        known, early_idx)
            record = {
                "epoch": epoch + 1,
                "train_ce": ce_sum / len(fit_idx),
                "train_supcon": sup_sum / len(fit_idx),
                "train_total_loss": (ce_sum + SUPCON_WEIGHT * sup_sum)
                / len(fit_idx),
                "early_stop_ce": val_loss,
                "train_macro_f1": macro_f1(train_preds,
                                           cell["train_labels"][fit_idx],
                                           known),
                "early_stop_macro_f1": macro_f1(
                    early_preds, cell["train_labels"][early_idx], known),
                "learning_rate": float(optimizer.param_groups[0]["lr"]),
                "is_best": bool(is_best),
                "stale": stale,
            }
            epoch_records.append(record)
            log.write(json.dumps(record) + "\n")
            log.flush()
            model = model.to(device)
            model.train()
            if stale >= EARLY_STOP_PATIENCE:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()

    # Final frozen-checkpoint diagnostics.
    ev_table = pq.read_table(
        owg_root / f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet")
    ev_labels = np.array(ev_table["canonical_label"].to_pylist(),
                         dtype=object)
    ev_is_unknown = ev_table["is_unknown"].to_numpy(
        zero_copy_only=False).astype(bool)
    ev_split_role = ev_table["split_role"].to_numpy(zero_copy_only=False)
    ev_known = (ev_split_role == 1) & (~ev_is_unknown)
    eval_preds = predict_basic(model, cell["features_ev"], known,
                               np.flatnonzero(ev_known))
    train_preds = predict_basic(model, cell["features_train"], known,
                                fit_idx)
    early_preds = predict_basic(model, cell["features_train"], known,
                                early_idx)
    eval_true = ev_labels[ev_known]
    final = {
        "seed": seed, "rotation": rotation,
        "best_epoch": best_epoch,
        "epochs_run": len(epoch_records),
        "train_macro_f1": macro_f1(train_preds,
                                   cell["train_labels"][fit_idx], known),
        "early_stop_macro_f1": macro_f1(early_preds,
                                        cell["train_labels"][early_idx],
                                        known),
        "eval_macro_f1": macro_f1(eval_preds, eval_true, known),
        "train": per_class_metrics(train_preds,
                                   cell["train_labels"][fit_idx], known),
        "early_stop": per_class_metrics(early_preds,
                                        cell["train_labels"][early_idx],
                                        known),
        "eval": per_class_metrics(eval_preds, eval_true, known),
        "n_eval_known": int(ev_known.sum()),
    }
    (cell_dir / "final.json").write_text(json.dumps(final, indent=1),
                                         encoding="utf-8")
    np.savez_compressed(
        cell_dir / "predictions.npz",
        train_true=np.array(cell["train_labels"][fit_idx], dtype=object),
        train_pred=train_preds,
        early_true=np.array(cell["train_labels"][early_idx], dtype=object),
        early_pred=early_preds,
        eval_true=eval_true, eval_pred=eval_preds,
        allow_pickle=True)
    torch.save(model.state_dict(), cell_dir / "model.pt")
    return final


def rf_frozen_comparison(seed: int, rotation: str, owg_root: Path
                         ) -> dict[str, Any]:
    """Descriptive per-class metrics of the frozen RF Basic baseline from
    the stored P0 predictions (no retraining)."""
    from run_strong_neural_osr_evidence_gate_v1 import known_classes_for
    table = pq.read_table(
        owg_root / f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet")
    labels = np.array(table["canonical_label"].to_pylist(), dtype=object)
    unk = table["is_unknown"].to_numpy(zero_copy_only=False).astype(bool)
    role = table["split_role"].to_numpy(zero_copy_only=False)
    preds = np.array(table["pred_P0_BASIC_DIRECT"].to_pylist(), dtype=object)
    ek = (role == 1) & (~unk)
    known = known_classes_for(rotation)
    return per_class_metrics(preds[ek], labels[ek], known)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owg-root", default=DEFAULT_OWG_ROOT)
    parser.add_argument("--gate1-root", default=DEFAULT_GATE1_ROOT)
    parser.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    args = parser.parse_args()
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    results = {}
    for seed, rotation in REPLAY_CELLS:
        started = time.monotonic()
        print(f"[replay {seed} {rotation}] start", flush=True)
        final = replay_cell(seed, rotation, out_root, Path(args.owg_root),
                            Path(args.gate1_root))
        final["seconds"] = round(time.monotonic() - started, 1)
        results[cell_key(seed, rotation)] = final
        print(f"[replay {seed} {rotation}] best_epoch={final['best_epoch']} "
              f"train_f1={final['train_macro_f1']:.4f} "
              f"early_f1={final['early_stop_macro_f1']:.4f} "
              f"eval_f1={final['eval_macro_f1']:.4f}", flush=True)
    # Frozen RF descriptive comparison.
    for seed, rotation in REPLAY_CELLS:
        results[cell_key(seed, rotation)]["rf_frozen_eval"] = \
            rf_frozen_comparison(seed, rotation, Path(args.owg_root))
    (out_root / "diagnostic_summary.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8")
    print("[replay] DIAGNOSTIC_REPLAY_STATUS=COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
