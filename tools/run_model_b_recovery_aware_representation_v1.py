#!/usr/bin/env python3
"""MODEL B V1 — Recovery-Aware Typed-Evidence Representation, formal runner.

Frozen protocol: docs/research_plan/model_b_recovery_aware_representation_v1_protocol.md
(STATUS=FROZEN_DESIGN_NOT_RUN; sha256 asserted at startup).
Frozen input contract: tools/model_b_input_serializer_v1.py (sha256 asserted).

This runner implements the frozen scientific contract ONLY (protocol s1-s16):
  * per-rotation FIT (3 rotations x 3 objectives; Qwen LoRA fits + the
    non-Qwen baseline), 2 fixed epochs, MATCHED_SHUFFLED_TRAIN pair per
    micro-batch (batch 2 rows = one pair), grad accum 4, AdamW lr 1e-4
    wd 0.01 warmup 100, bf16 (Qwen) / fp32 (baseline), checkpoint/resume
    (exact continuation);
  * EXPORT of the frozen representation e = concat(u, v) for ALL probe rows
    (role-0 Known x REAL/BASIC/UNRESTRICTED_SHUFFLED_EVAL for probe-B
    fit+threshold rows; role-1 (rec|unk) test rows x 3 conditions; the two
    dev rotations' role-0 (rec|unk) rows under REAL for probe-A fit rows;
    probe-B targets y = (argmax == canonical label at acquired state));
  * PROBE fits (RF/LR/MLP, frozen gate s8 recipes) + per-condition
    thresholds (95th percentile -> Recall@5%FUR), AUROC/AUPR crosschecks;
  * BOOTSTRAP (group-atomic 1000 reps, default_rng(162600) per
    (probe,family,objective) key -> identical draws across objectives);
  * AGGREGATE: MODEL_B_RET_B/RET_S vs the frozen Information-Gate RAW
    denominators, transfer increments, frozen rule evaluations.

Restartable: run_state.json + per-stage markers; completed fits/stages are
skipped. Fail-closed: protocol/serializer/data/model identity locks; no
FINAL_TEST anywhere in the data path; held-out Unknown is evaluation-only
(never in fitting, thresholds, checkpoints, loss weighting, or early
stopping); UNRESTRICTED_SHUFFLED_EVAL is eval-only and distinct from
MATCHED_SHUFFLED_TRAIN in code/artifacts/reports.

Allowed modes for the PREPARE task: --dry-run (static validation only) and
--smoke (tiny NON-SCIENTIFIC synthetic-data shape check). Formal launch is
a SEPARATE task; the recorded launch command is
  PYTHONHASHSEED=0 python tools/run_model_b_recovery_aware_representation_v1.py --all --resume
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# ---------------------------------------------------------------------------
# Frozen constants (protocol s3-s11; values locked by the preregistration)
# ---------------------------------------------------------------------------
PROTOCOL_SHA256 = "3479f1a5eb1027452a5dea9152ebf4a82a55b27572905fbfa84097431f665576"
SERIALIZER_SHA256 = "95d159fab5a3c73943fb25153a771d0d8c9d5aab8435642dbd22922036218e6f"
CENTRAL_SEED = 20260817
FIT_SEED_BASE = 20260817
FIT_SEED_STEP = 100
EPOCHS = 2
BATCH_ROWS = 2            # one MATCHED_SHUFFLED_TRAIN pair per micro-batch
GRAD_ACCUM = 4            # effective 8 rows per optimizer step
LR = 1e-4
WEIGHT_DECAY = 0.01
WARMUP_STEPS = 100
CHECKPOINT_EVERY = 500
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
                "in_proj_qkv", "out_proj"]
PROJ_DIM = 256            # Qwen readout projection (4096 -> 256)
BASELINE_HIDDEN = 512
BASELINE_PROJ_DIM = 128
BASELINE_LAYERS = 6
BASELINE_HEADS = 8
BASELINE_FFN = 2048
EXPORT_BATCH = 16
EXPECTED_K = 6

# Frozen bootstrap / gates (protocol s10/s11; identical to the frozen gates)
BOOTSTRAP_RNG = 162600
BOOTSTRAP_REPS = 1000
MATERIALITY = 0.02
STRONG_FAMILIES = 2
ROT_OK_MIN = 2
RETENTION_THRESHOLD = 0.5
BOOTSTRAP_PCTS = (2.5, 97.5)
REDRAW_BOUND = 200
CALIB_FALSE_UNKNOWN_RATE = 0.05
SHUF_RNG_OFFSET = 900      # Model B eval-shuffle rng offset (frozen)

CONDITIONS = ("REAL", "BASIC", "UNRESTRICTED_SHUFFLED_EVAL")
FAMILIES = ("RF", "LR", "MLP")
OBJECTIVES = ("QWEN_CE_ONLY", "QWEN_CE_PLUS_CORR", "NON_QWEN_BASELINE")

DATASET = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1")
OWG = DATASET / "open_world_recoverability_gate_v1"
GATE1 = DATASET / "core_gate_v1"
RUN = DATASET / "model_b_recovery_aware_representation_v1"
INFOSUFF = DATASET / "recoverability_information_sufficiency_gate_v1"
INFOSUFF_AGGREGATE = INFOSUFF / "formal" / "aggregate.json"
QWEN_PATH = Path("/root/autodl-tmp/models/Qwen3.5-9B")

# Frozen baseline tokenizer charset (protocol s12): the exact ASCII alphabet
# of the serializer template, computed 2026-08-20 from the frozen serializer
# output (31 distinct chars). ids 0..30, pad id 31.
CHAR_VOCAB = "\n./0123456789<=>ABCEGIKLMNOPRTm"
CHAR_PAD_ID = len(CHAR_VOCAB)


# ---------------------------------------------------------------------------
# Heavy imports (frozen machinery reuse; must stay after constants)
# ---------------------------------------------------------------------------
import torch  # noqa: E402

from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

import model_b_input_serializer_v1 as ser  # noqa: E402
import run_evidence_processing_method_dependence_diagnostic_v1 as diag  # noqa: E402
from run_recoverability_information_sufficiency_gate_v1 import (  # noqa: E402
    LR_CONFIG,
    RF_CONFIG,
    build_rotation_draws,
    family_scores,
    fit_family,
    fit_mlp,
    raw_legal_for_actions,
    raw_legal_matrix,
    recall_at_5fur_fast,
    rep_metric_matrix,
    auroc_fast,
    aupr_fast,
    rot_ok,
)
from run_strong_neural_osr_evidence_gate_v1 import (  # noqa: E402
    RNG_BASE,
    ROTATIONS,
    assemble_cell,
    cell_rng,
    group_codes,
)
from run_open_world_recoverability_gate_v1 import ACTION_MODEL  # noqa: E402


# ---------------------------------------------------------------------------
# Determinism / hashing / run state
# ---------------------------------------------------------------------------

def set_determinism() -> None:
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("PYTHONHASHSEED_MUST_BE_0")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fit_seed(rot: str) -> int:
    return FIT_SEED_BASE + FIT_SEED_STEP * ROTATIONS.index(rot)


def fit_id(rot: str, obj: str) -> str:
    return f"{rot}:{obj}"


def write_run_state(status: str) -> None:
    path = RUN / "run_state.json"
    state = json.loads(path.read_text()) if path.exists() else {
        "task": "MODEL_B_RECOVERY_AWARE_REPRESENTATION_V1",
        "protocol_sha256": PROTOCOL_SHA256,
        "serializer_sha256": SERIALIZER_SHA256,
        "fits": {}, "stages": {}}
    state["status"] = status
    path.write_text(json.dumps(state, indent=1), encoding="utf-8")


def get_run_state() -> dict[str, Any]:
    return json.loads((RUN / "run_state.json").read_text())


def marker_path(stage: str) -> Path:
    return RUN / "stages" / f"{stage}_done.json"


def stage_done(stage: str) -> bool:
    return marker_path(stage).exists()


def mark_stage(stage: str, payload: dict[str, Any]) -> None:
    marker_path(stage).write_text(json.dumps({"stage": stage, **payload},
                                             indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Identity locks (fail-closed; recomputed every run)
# ---------------------------------------------------------------------------

def execution_locks() -> dict[str, Any]:
    protocol = REPO / "docs/research_plan" / \
        "model_b_recovery_aware_representation_v1_protocol.md"
    serializer = TOOLS / "model_b_input_serializer_v1.py"
    reg = json.loads((REPO / "reports/research_audit" /
                      "model_b_recovery_aware_representation_v1_preregistration.json").read_text())
    lock = {
        "protocol_sha256_recomputed": sha256_file(protocol),
        "protocol_sha256_preregistration": reg["protocol_sha256"],
        "protocol_match": sha256_file(protocol) == PROTOCOL_SHA256
                          == reg["protocol_sha256"],
        "serializer_sha256_recomputed": sha256_file(serializer),
        "serializer_sha256_preregistration": reg["serializer_sha256"],
        "serializer_match": sha256_file(serializer) == SERIALIZER_SHA256
                            == reg["serializer_sha256"],
    }
    if not lock["protocol_match"] or not lock["serializer_match"]:
        raise SystemExit("IDENTITY_LOCK_FAIL " + json.dumps(lock))
    return lock


def data_identity() -> dict[str, Any]:
    """SHA256 of every consumed data/split parquet (computed once, cached
    with size guards so a changed file is detected)."""
    cache = RUN / "identity" / "data_identity.json"
    files = [
        OWG / f"owg_v1_seed_{CENTRAL_SEED}_rotation_{rot}_eval.parquet"
        for rot in ROTATIONS
    ] + [
        OWG / f"owg_v1_seed_{CENTRAL_SEED}_split.parquet",
        GATE1 / "gate_seed_20260817_targets.parquet",
        GATE1 / "gate_seed_20260817_history.parquet",
        GATE1 / "core_gate_basic_features_v1.parquet",
    ]
    if cache.exists():
        c = json.loads(cache.read_text())
        if all(c["files"][f.name]["size"] == f.stat().st_size
               for f in files if f.name in c["files"]):
            return c
    out = {"files": {}}
    for f in files:
        out["files"][f.name] = {"path": str(f), "size": f.stat().st_size,
                                "sha256": sha256_file(f)}
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "identity").mkdir(exist_ok=True)
    cache.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def model_identity() -> dict[str, Any]:
    """Identity of the frozen Qwen checkpoint (config + index + shards)."""
    cache = RUN / "identity" / "qwen_identity.json"
    small = ["config.json", "model.safetensors.index.json"]
    shards = sorted(QWEN_PATH.glob("model.safetensors-*.safetensors"))
    if cache.exists():
        c = json.loads(cache.read_text())
        if all(c["files"][p]["size"] == (QWEN_PATH / p).stat().st_size
               for p in small if p in c["files"]) and \
                all(c["files"][s.name]["size"] == s.stat().st_size
                    for s in shards if s.name in c["files"]):
            return c
    out = {"files": {p: {"size": (QWEN_PATH / p).stat().st_size,
                         "sha256": sha256_file(QWEN_PATH / p)}
                     for p in small}}
    for s in shards:
        out["files"][s.name] = {"size": s.stat().st_size,
                                "sha256": sha256_file(s)}
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "identity").mkdir(exist_ok=True)
    cache.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def infosuff_denominators() -> dict[str, Any]:
    """Frozen Information-Gate RAW + ST increments per family, identity-
    locked against the frozen gate aggregate (outcome must match)."""
    if not INFOSUFF_AGGREGATE.exists():
        raise SystemExit("FROZEN_INFOSUFF_AGGREGATE_MISSING "
                         + str(INFOSUFF_AGGREGATE))
    agg = json.loads(INFOSUFF_AGGREGATE.read_text())
    if agg.get("outcome") != "REPRESENTATION_BOTTLENECK_SUPPORTED":
        raise SystemExit("FROZEN_INFOSUFF_OUTCOME_MISMATCH "
                         + str(agg.get("outcome")))
    keys = agg.get("bootstrap_keys", {})
    out: dict[str, Any] = {"aggregate_sha256": sha256_file(INFOSUFF_AGGREGATE),
                           "families": {}, "st_families": {}}
    for f in FAMILIES:
        raw = keys.get(f"PA_RAW_{f}")
        st = keys.get(f"PA_ST_{f}")
        if raw is None or st is None:
            raise SystemExit(f"FROZEN_INFOSUFF_BOOTSTRAP_KEY_MISSING {f}")
        out["families"][f] = {
            k: raw["increments"]["auroc"][k]
            for k in ("real_minus_basic", "real_minus_shuffled")}
        out["st_families"][f] = {
            k: st["increments"]["auroc"][k]
            for k in ("real_minus_basic", "real_minus_shuffled")}
    return out


# ---------------------------------------------------------------------------
# Tokenization (frozen s4: content-token spans; frozen s12: char baseline)
# ---------------------------------------------------------------------------

def block_content_ranges(text: str) -> dict[str, tuple[int, int]]:
    """(start, end) char offsets of the VALUE-LINE region inside each
    block (protocol s4: header, `m=` and close lines are excluded).
    Empty for m=0 blocks -> h_e = 0 at state B (frozen)."""
    out = {}
    for header in ("<TARGET>", "<TEMPORAL>", "<RELATION>"):
        h0 = text.index(header)
        pos = h0
        while True:                        # skip header line, then m= line
            next_nl = text.index("\n", pos + 1)
            if text[pos + 1:next_nl].startswith("m="):
                break
            pos = next_nl
        close = text.index("</BLOCK>", next_nl)
        out[header] = (next_nl + 1, close)
    return out


def tokenize_row_qwen(text: str, tok) -> dict[str, Any]:
    """One serialized row with the Qwen tokenizer: ids + per-block
    content-token masks (tokens whose offsets fall fully inside value
    lines and whose decoded text is non-blank). Deterministic."""
    enc = tok(text, add_special_tokens=True, return_offsets_mapping=True)
    ids = enc["input_ids"]
    offs = enc["offset_mapping"]
    n_tok = len(ids)
    masks = {}
    for header, (start, end) in block_content_ranges(text).items():
        m = np.zeros(n_tok, dtype=bool)
        for t, (a, b) in enumerate(offs):
            if a >= start and b <= end and text[a:b].strip():
                m[t] = True
        masks[header] = m
    return {"ids": np.array(ids, dtype=np.int32), "masks": masks}


def tokenize_row_char(text: str) -> dict[str, Any]:
    """Char-level tokenization (frozen s12): one id per char over the
    frozen charset; per-block masks from the char offsets."""
    ids = np.array([CHAR_VOCAB.index(c) if c in CHAR_VOCAB else CHAR_PAD_ID
                    for c in text], dtype=np.int32)
    masks = {}
    for header, (start, end) in block_content_ranges(text).items():
        m = np.zeros(len(text), dtype=bool)
        for pos in range(start, end):
            if text[pos].strip():
                m[pos] = True
        masks[header] = m
    return {"ids": ids, "masks": masks}


# ---------------------------------------------------------------------------
# Data prep (frozen s7/s9 populations, pair file, token cache)
# ---------------------------------------------------------------------------

def build_pairs(n: int, lab: np.ndarray, st: np.ndarray, grp: np.ndarray,
                raw_t: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """One MATCHED_SHUFFLED_TRAIN negative per positive (protocol s7):
    same class, same availability state, different activity group,
    different row, no bit-identical serialization. Deterministic cyclic
    permutation from the fit seed; exactly one negative per positive."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    i = np.empty(n, dtype=np.int64)
    j = np.empty(n, dtype=np.int64)
    for pos in range(n):
        found = -1
        for step in range(1, n + 1):
            cand = perm[(pos + step) % n]
            if (lab[cand] == lab[pos] and st[cand] == st[pos]
                    and grp[cand] != grp[pos]
                    and not np.array_equal(raw_t[cand], raw_t[pos])):
                found = cand
                break
        if found < 0:
            raise SystemExit(f"MATCHED_SHUFFLED_PAIR_FAIL pos={pos}")
        i[pos] = pos
        j[pos] = found
    return i, j


def cache_rotation_tokens(rot: str, cell: dict[str, Any], raw: np.ndarray,
                          raw_shuf: np.ndarray, raw_basic: np.ndarray,
                          train_idx: np.ndarray, stats: dict[str, Any],
                          out: Path) -> dict[str, Any]:
    """Tokenize every row/condition this rotation will consume, once
    (protocol s4: spans computed at data prep and cached). Qwen tokenizer
    caches: train rows x {REAL, BASIC, SHUF}, test rows x {REAL, BASIC,
    SHUF}, and dev rows (role-0 (rec|unk)) x REAL for probe-A fit rows."""
    from transformers import AutoTokenizer  # noqa: PLC0415
    cache_dir = out / "tokens"
    cache_dir.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(QWEN_PATH, trust_remote_code=True)
    pad_id = int(tok.pad_token_id)
    role = cell["ev_split_role"]
    unk = cell["ev_is_unknown"].astype(bool)
    rec = cell["ev_recoverable"].astype(bool)
    test_idx = np.flatnonzero((role == 1) & (rec | unk))
    dev_idx = np.flatnonzero((role == 0) & (rec | unk))
    conds = {"REAL": raw, "BASIC": raw_basic, "SHUF": raw_shuf}
    for name, rows in (("train", train_idx), ("test", test_idx)):
        for cond, base in conds.items():
            key = f"{rot}_{name}_{cond}"
            if (cache_dir / f"{key}.npz").exists():
                continue
            maxlen = 0
            rows_ids = []
            rows_masks = []
            for r in rows:
                text = ser.serialize(base[r], stats)
                rec_ = tokenize_row_qwen(text, tok)
                if len(rec_["ids"]) > ser.MAX_SEQ_LEN:
                    raise SystemExit(f"SEQ_OVER_CAP key={key} "
                                     f"len={len(rec_['ids'])}")
                maxlen = max(maxlen, len(rec_["ids"]))
                rows_ids.append(rec_["ids"])
                rows_masks.append(rec_["masks"])
            ids = np.zeros((len(rows), maxlen), dtype=np.int32)
            tm = np.zeros((len(rows), maxlen), dtype=np.uint8)
            em = np.zeros((len(rows), maxlen), dtype=np.uint8)
            for i, rid in enumerate(rows_ids):
                ids[i, :len(rid)] = rid
                tm[i, :len(rows_masks[i]["<TARGET>"])] = \
                    rows_masks[i]["<TARGET>"].astype(np.uint8)
                em[i, :len(rows_masks[i]["<TEMPORAL>"]
                           | rows_masks[i]["<RELATION>"])] = \
                    (rows_masks[i]["<TEMPORAL>"]
                     | rows_masks[i]["<RELATION>"]).astype(np.uint8)
            np.savez_compressed(cache_dir / f"{key}.npz", ids=ids,
                                target_mask=tm, evidence_mask=em, rows=rows,
                                pad_id=pad_id, allow_pickle=False)
            print(f"[tokens {key}] rows={len(rows)} maxlen={maxlen} "
                  f"pad_id={pad_id}", flush=True)
    if not (cache_dir / f"{rot}_dev_REAL.npz").exists():
        maxlen = 0
        rows_ids = []
        rows_masks = []
        for r in dev_idx:
            text = ser.serialize(raw[r], stats)
            rec_ = tokenize_row_qwen(text, tok)
            if len(rec_["ids"]) > ser.MAX_SEQ_LEN:
                raise SystemExit(f"SEQ_OVER_CAP key={rot}_dev_REAL "
                                 f"len={len(rec_['ids'])}")
            maxlen = max(maxlen, len(rec_["ids"]))
            rows_ids.append(rec_["ids"])
            rows_masks.append(rec_["masks"])
        ids = np.zeros((len(dev_idx), maxlen), dtype=np.int32)
        tm = np.zeros((len(dev_idx), maxlen), dtype=np.uint8)
        em = np.zeros((len(dev_idx), maxlen), dtype=np.uint8)
        for i, rid in enumerate(rows_ids):
            ids[i, :len(rid)] = rid
            tm[i, :len(rows_masks[i]["<TARGET>"])] = \
                rows_masks[i]["<TARGET>"].astype(np.uint8)
            em[i, :len(rows_masks[i]["<TEMPORAL>"]
                       | rows_masks[i]["<RELATION>"])] = \
                (rows_masks[i]["<TEMPORAL>"
                              ] | rows_masks[i]["<RELATION>"]).astype(np.uint8)
        np.savez_compressed(cache_dir / f"{rot}_dev_REAL.npz", ids=ids,
                            target_mask=tm, evidence_mask=em, rows=dev_idx,
                            pad_id=pad_id, allow_pickle=False)
        print(f"[tokens {rot}_dev_REAL] rows={len(dev_idx)}", flush=True)
    return {"pad_id": pad_id, "n_dev": int(len(dev_idx))}


def load_token_cache(out: Path, rot: str, name: str, cond: str) -> dict:
    z = np.load(out / "tokens" / f"{rot}_{name}_{cond}.npz")
    return {"ids": z["ids"], "tm": z["target_mask"], "em": z["evidence_mask"],
            "rows": z["rows"], "pad_id": int(z["pad_id"])}


def prep_rotation(rot: str, out: Path) -> dict[str, Any]:
    """Assemble the rotation's frozen row universe once; write the raw
    matrix, labels, pair file, eval-shuffle matrix, stats and Qwen token
    caches. Deterministic; re-runnable (stage-gated)."""
    stage = f"prep_{rot}"
    if stage_done(stage):
        return json.loads(marker_path(stage).read_text())
    cell = assemble_cell(CENTRAL_SEED, rot, OWG, GATE1)
    n = len(cell["ev_labels"])
    actions = cell["ev_action_p6"]
    states = np.array([ACTION_MODEL[a] for a in actions], dtype=object)
    raw = raw_legal_matrix(cell["features_ev"], states)      # n x 83
    role = cell["ev_split_role"]
    unk = cell["ev_is_unknown"].astype(bool)
    rec = cell["ev_recoverable"].astype(bool)
    class_map = {c: i for i, c in enumerate(cell["known"])}
    if len(class_map) != EXPECTED_K:
        raise SystemExit(f"K_UNEXPECTED rotation={rot} K={len(class_map)}")
    train_idx = np.flatnonzero((role == 0) & (~unk))
    # fail-closed role separation L1 (Unknown never in training)
    if unk[train_idx].any() or (role[train_idx] != 0).any():
        raise SystemExit(f"LEAKAGE_L1_FAIL rotation={rot}")
    labels = np.array([class_map.get(l, -1) for l in cell["ev_labels"]],
                      dtype=np.int64)
    if (labels[train_idx] < 0).any():
        raise SystemExit(f"TRAIN_LABEL_OUT_OF_KNOWN rotation={rot}")
    stats = ser.fit_stats(raw[train_idx])
    grp = cell["ev_groups"][train_idx]
    st = states[train_idx]
    lab = labels[train_idx]
    raw_t = raw[train_idx]
    pi, pj = build_pairs(len(train_idx), lab, st, grp, raw_t, fit_seed(rot))
    shuf_rng = cell_rng(CENTRAL_SEED, rot, RNG_BASE + SHUF_RNG_OFFSET)
    raw_shuf = raw_legal_for_actions(diag.shuffled_features(cell, shuf_rng),
                                     actions)
    raw_basic = raw_legal_matrix(
        cell["features_ev"], np.full(n, "B", dtype=object))
    (out / "features").mkdir(parents=True, exist_ok=True)
    (out / "pairs").mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "features" / f"{rot}_raw.npz", raw=raw,
                        allow_pickle=False)
    np.savez_compressed(out / "features" / f"{rot}_labels.npz",
                        labels=labels, train_idx=train_idx, allow_pickle=False)
    np.savez_compressed(out / "features" / f"{rot}_stats.npz",
                        mean=stats["mean"], scale=stats["scale"],
                        allow_pickle=False)
    np.savez_compressed(out / "pairs" / f"{rot}_pairs.npz", i=pi, j=pj,
                        allow_pickle=False)
    np.savez_compressed(out / "pairs" / f"{rot}_eval_shuffle_evidence.npz",
                        raw=raw_shuf, allow_pickle=False)
    tok = cache_rotation_tokens(rot, cell, raw, raw_shuf, raw_basic,
                                train_idx, stats, out)
    meta = {
        "rotation": rot, "n_rows": int(n),
        "n_train": int(len(train_idx)),
        "n_role0": int((role == 0).sum()), "n_role1": int((role == 1).sum()),
        "n_unknown": int(unk.sum()),
        "n_recoverable_known": int((rec & ~unk).sum()),
        "train_state_counts": {s: int((st == s).sum()) for s in
                               ("B", "BT", "BR", "BTR")},
        "train_class_counts": {c: int((lab == i).sum())
                               for c, i in class_map.items()},
        "k": len(class_map), "known": list(cell["known"]),
        "pair_file": f"pairs/{rot}_pairs.npz",
        "pair_constraints_ok": True,
        "pad_id": tok["pad_id"], "n_dev": tok["n_dev"],
        "eval_shuffle": "UNRESTRICTED_SHUFFLED_EVAL (eval-only, "
                        "distinct artifact)"}
    mark_stage(stage, meta)
    print(f"[prep {rot}] rows={n} train={len(train_idx)} "
          f"states={meta['train_state_counts']}", flush=True)
    return meta


# ---------------------------------------------------------------------------
# Model construction (frozen s3-s5) + training loop (frozen s8/s9)
# ---------------------------------------------------------------------------

def build_qwen(seed: int, device: str):
    import peft  # noqa: PLC0415
    from transformers import AutoModelForCausalLM  # noqa: PLC0415
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    base = AutoModelForCausalLM.from_pretrained(
        QWEN_PATH, torch_dtype=torch.bfloat16, device_map=device,
        trust_remote_code=True, low_cpu_mem_usage=True)
    cfg = peft.LoraConfig(r=LORA_R, lora_alpha=LORA_ALPHA,
                          lora_dropout=LORA_DROPOUT, bias="none",
                          target_modules=LORA_TARGETS)
    model = peft.get_peft_model(base, cfg).to(device)
    return model


class Readout(torch.nn.Module):
    """u = W_u h_t, v = W_v h_e (4096 -> 256); e = concat(u, v)."""

    def __init__(self, dim: int, proj: int, dtype: torch.dtype = torch.float32):
        super().__init__()
        self.wu = torch.nn.Linear(dim, proj, dtype=dtype)
        self.wv = torch.nn.Linear(dim, proj, dtype=dtype)

    def forward(self, h_t: torch.Tensor, h_e: torch.Tensor):
        u = self.wu(h_t)
        v = self.wv(h_e)
        return u, v, torch.cat([u, v], dim=-1)


def make_qwen_heads(model, k: int, corr: bool, device: str):
    """Readout + classification head in the backbone dtype (bf16 for the
    Qwen fits, fp32 for the baseline) so forward runs dtype-consistent
    with and without autocast."""
    dtype = torch.bfloat16 if any(
        p.dtype == torch.bfloat16 for p in model.parameters()) \
        else torch.float32
    model.readout = Readout(4096, PROJ_DIM, dtype).to(device)
    model.cls_head = torch.nn.Linear(2 * PROJ_DIM, k, dtype=dtype).to(device)
    model.corr_enabled = corr
    return model


def cosine(u: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    """s(u,v) = dot(u,v) / (||u||2 * ||v||2), norms sqrt(sum(sq)) + 1e-8.
    At state B (v=0) the score is 0 (frozen s4)."""
    un = torch.nn.functional.normalize(u, dim=-1, eps=1e-8)
    vn = torch.nn.functional.normalize(v, dim=-1, eps=1e-8)
    return (un * vn).sum(dim=-1)


class CharBaseline(torch.nn.Module):
    """Frozen non-Qwen baseline (protocol s12): 6-layer transformer
    encoder (hidden 512, 8 heads, GELU, norm_first), char-level frozen
    tokenizer ids, learned position embeddings (max 1536), same readout
    (512 -> 128, e in R^256), same two heads, same objective."""

    def __init__(self, k: int, corr: bool, seed: int, device: str):
        super().__init__()
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        self.emb = torch.nn.Embedding(CHAR_PAD_ID + 1, BASELINE_HIDDEN)
        self.pos = torch.nn.Embedding(ser.MAX_SEQ_LEN, BASELINE_HIDDEN)
        layer = torch.nn.TransformerEncoderLayer(
            d_model=BASELINE_HIDDEN, nhead=BASELINE_HEADS,
            dim_feedforward=BASELINE_FFN, dropout=0.1, activation="gelu",
            batch_first=True, norm_first=True)
        self.enc = torch.nn.TransformerEncoder(layer, BASELINE_LAYERS)
        self.wu = torch.nn.Linear(BASELINE_HIDDEN, BASELINE_PROJ_DIM)
        self.wv = torch.nn.Linear(BASELINE_HIDDEN, BASELINE_PROJ_DIM)
        self.head = torch.nn.Linear(2 * BASELINE_PROJ_DIM, k)
        self.corr_enabled = corr
        self.to(device)

    def forward(self, iid, tm, em):
        b, s = iid.shape
        x = self.emb(iid) + self.pos(
            torch.arange(s, device=iid.device).unsqueeze(0))
        pad = (iid == CHAR_PAD_ID)
        hs = self.enc(x, src_key_padding_mask=pad)

        def pool(mask: torch.Tensor) -> torch.Tensor:
            counts = mask.sum(dim=1).clamp(min=1)
            return (hs * mask.unsqueeze(-1).float()).sum(dim=1) \
                / counts.unsqueeze(-1)

        h_t, h_e = pool(tm.float()), pool(em.float())
        u, v = self.wu(h_t), self.wv(h_e)
        e = torch.cat([u, v], dim=-1)
        return self.head(e), u, v, e


def qwen_forward(model, iid: torch.Tensor, attn: torch.Tensor,
                 tm: torch.Tensor, em: torch.Tensor):
    out = model(input_ids=iid, attention_mask=attn,
                output_hidden_states=True)
    hs = out.hidden_states[-1]                                   # B x S x 4096

    def pool(mask: torch.Tensor) -> torch.Tensor:
        counts = mask.sum(dim=1).clamp(min=1)
        return (hs * mask.unsqueeze(-1).to(hs.dtype)).sum(dim=1) \
            / counts.unsqueeze(-1)

    h_t, h_e = pool(tm), pool(em)
    u, v, e = model.readout(h_t, h_e)
    return model.cls_head(e), u, v, e


def trainable_state(model) -> dict[str, torch.Tensor]:
    """Trainable-only state dict (LoRA adapters + readout + head; the
    frozen base is never stored) — keeps checkpoints at ~100 MB."""
    return {k: v.detach().cpu() for k, v in model.named_parameters()
            if v.requires_grad}


def load_trainable(model, state: dict[str, torch.Tensor]) -> None:
    missing = []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        if name not in state:
            missing.append(name)
            continue
        param.data.copy_(state[name])
    if missing:
        raise SystemExit(f"CHECKPOINT_MISSING_TRAINABLE {missing}")


def run_fit(rot: str, obj: str, cfg: dict[str, Any]) -> None:
    """Frozen FIT stage for one (rotation, objective); resume-aware with
    exact continuation (protocol s9)."""
    fid = fit_id(rot, obj)
    state = get_run_state()
    fits = state.setdefault("fits", {})
    if fits.get(fid, {}).get("status") == "COMPLETE":
        print(f"[fit {fid}] already complete — skip", flush=True)
        return
    execution_locks()
    data_identity()
    model_identity()
    out = RUN / "fits" / fid.replace(":", "_")
    out.mkdir(parents=True, exist_ok=True)
    prep = prep_rotation(rot, RUN)
    seed = fit_seed(rot)
    device = "cuda:0"
    is_qwen = obj != "NON_QWEN_BASELINE"
    fits[fid] = {"status": "RUNNING", "seed": seed, "objective": obj,
                 "rotation": rot, "n_train": prep["n_train"],
                 "epochs": EPOCHS, "steps_completed": 0,
                 "checkpoint": str(out / "latest.pt")}
    write_run_state("RUNNING")

    # --- frozen data (pair file shared by all objectives of the rotation)
    z = np.load(RUN / "features" / f"{rot}_labels.npz")
    y_train = z["labels"][z["train_idx"]].astype(np.int64)
    pairs = np.load(RUN / "pairs" / f"{rot}_pairs.npz")
    n_pairs = len(pairs["i"])
    if n_pairs != prep["n_train"]:
        raise SystemExit(f"PAIR_COUNT_MISMATCH {n_pairs} != "
                         f"{prep['n_train']}")
    if is_qwen:
        tok = load_token_cache(RUN, rot, "train", "REAL")
        ids_all, tm_all, em_all = tok["ids"], tok["tm"], tok["em"]
        pad_id = tok["pad_id"]
    else:
        # baseline: char tokens computed on the fly (deterministic)
        raw = np.load(RUN / "features" / f"{rot}_raw.npz")["raw"]
        zt = np.load(RUN / "features" / f"{rot}_labels.npz")
        train_idx = zt["train_idx"]
        zs = np.load(RUN / "features" / f"{rot}_stats.npz")
        stats = {"mean": zs["mean"], "scale": zs["scale"]}
        ids_all = []
        tm_all = []
        em_all = []
        for r in train_idx:
            rec_ = tokenize_row_char(ser.serialize(raw[r], stats))
            ids_all.append(rec_["ids"])
            tm_all.append(rec_["masks"]["<TARGET>"])
            em_all.append(rec_["masks"]["<TEMPORAL>"]
                          | rec_["masks"]["<RELATION>"])
        mx = max(len(t) for t in ids_all)
        ids_all = np.zeros((len(train_idx), mx), dtype=np.int32)
        tm_all = np.zeros((len(train_idx), mx), dtype=np.uint8)
        em_all = np.zeros((len(train_idx), mx), dtype=np.uint8)
        for i, r in enumerate(train_idx):
            rec_ = tokenize_row_char(ser.serialize(raw[r], stats))
            ids_all[i, :len(rec_["ids"])] = rec_["ids"]
            tm_all[i, :len(rec_["masks"]["<TARGET>"])] = \
                rec_["masks"]["<TARGET>"].astype(np.uint8)
            em_all[i, :len(rec_["masks"]["<TEMPORAL>"]
                           | rec_["masks"]["<RELATION>"])] = \
                (rec_["masks"]["<TEMPORAL>"]
                 | rec_["masks"]["<RELATION>"]).astype(np.uint8)
        pad_id = CHAR_PAD_ID

    # --- model (seeded construction; deterministic LoRA init)
    if is_qwen:
        model = build_qwen(seed, device)
        model = make_qwen_heads(model, prep["k"],
                                obj == "QWEN_CE_PLUS_CORR", device)
        model.train()
        model.gradient_checkpointing_enable()
    else:
        model = CharBaseline(prep["k"], obj == "QWEN_CE_PLUS_CORR", seed,
                             device)
        model.train()
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=LR, weight_decay=WEIGHT_DECAY)
    ce_fn = torch.nn.CrossEntropyLoss()
    softplus = torch.nn.Softplus()
    jp = pairs["j"]

    # --- resume (exact continuation: weights, optimizer, RNGs, position)
    ckpt = out / "latest.pt"
    epoch0, step_global, order_pos = 0, 0, 0
    if ckpt.exists():
        saved = torch.load(ckpt, map_location="cpu")
        load_trainable(model, saved["model_state"])
        opt.load_state_dict(saved["opt_state"])
        epoch0, step_global, order_pos = (saved["epoch"],
                                          saved["global_step"],
                                          saved["order_pos"])
        torch.set_rng_state(saved["torch_rng"])
        if torch.cuda.is_available():
            torch.cuda.set_rng_state(saved["cuda_rng"])
        print(f"[fit {fid}] resume epoch={epoch0} step={step_global} "
              f"order_pos={order_pos}", flush=True)

    def checkpoint(epoch: int, step: int, pos: int) -> None:
        save = {"model_state": trainable_state(model),
                "opt_state": opt.state_dict(),
                "epoch": epoch, "global_step": step, "order_pos": pos,
                "torch_rng": torch.get_rng_state(),
                "cuda_rng": torch.cuda.get_rng_state() if
                torch.cuda.is_available() else None}
        tmp = out / "latest.pt.tmp"
        torch.save(save, tmp)
        tmp.replace(ckpt)
        fits = get_run_state()["fits"]
        fits[fid]["steps_completed"] = step
        write_run_state("RUNNING")

    # --- training loop (frozen s8/s9; one pair per micro-batch)
    t_start = time.time()
    for epoch in range(epoch0, EPOCHS):
        order = np.random.default_rng(seed + 7919 * (epoch + 1)).permutation(
            n_pairs)
        opt.zero_grad(set_to_none=True)
        for pos in range(order_pos, len(order)):
            pi_ = int(order[pos])
            pj_ = int(jp[pi_])
            iid = torch.tensor([ids_all[pi_], ids_all[pj_]], device=device,
                               dtype=torch.long)
            im = torch.tensor([tm_all[pi_], tm_all[pj_]], device=device)
            emm = torch.tensor([em_all[pi_], em_all[pj_]], device=device)
            attn = (iid != pad_id).long()
            yb = torch.tensor([y_train[pi_], y_train[pj_]], device=device,
                              dtype=torch.long)
            autocast = (torch.autocast("cuda", dtype=torch.bfloat16)
                        if is_qwen else torch.nullcontext())
            with autocast:
                if is_qwen:
                    logits, u, v, e = qwen_forward(model, iid, attn, im, emm)
                else:
                    logits, u, v, e = model(iid, im, emm)
                ce = ce_fn(logits, yb)
                if model.corr_enabled:
                    s_real = cosine(u[0], v[0])
                    s_neg = cosine(u[0], v[1])   # target_i vs Evidence_j
                    lcorr = softplus(-(s_real - s_neg))
                    loss = (ce + lcorr) / GRAD_ACCUM
                else:
                    loss = ce / GRAD_ACCUM
            loss.backward()
            is_tail = pos == len(order) - 1
            if (pos - order_pos + 1) % GRAD_ACCUM == 0 or is_tail:
                for g in opt.param_groups:
                    g["lr"] = LR * min(1.0, step_global / WARMUP_STEPS)
                opt.step()
                step_global += 1
                opt.zero_grad(set_to_none=True)
                if step_global % CHECKPOINT_EVERY == 0:
                    checkpoint(epoch, step_global, pos + 1)
                    print(f"[fit {fid}] epoch={epoch} step={step_global} "
                          f"ce={float(ce.detach()):.4f} "
                          f"({(time.time()-t_start)/60:.1f} min)",
                          flush=True)
        checkpoint(epoch, step_global, len(order))
        order_pos = 0
    final = out / "final.pt"
    torch.save({"model_state": trainable_state(model)}, final)
    fits = get_run_state()["fits"]
    fits[fid] = {"status": "COMPLETE", "seed": seed, "objective": obj,
                 "rotation": rot, "n_train": prep["n_train"],
                 "epochs": EPOCHS, "steps_completed": step_global,
                 "checkpoint": str(final),
                 "final_wall_min": round((time.time() - t_start) / 60, 1)}
    write_run_state("RUNNING")
    print(f"[fit {fid}] COMPLETE in {(time.time()-t_start)/3600:.1f} h "
          f"({step_global} steps)", flush=True)


# ---------------------------------------------------------------------------
# Export (frozen s4/s10/s11): e for every probe row + probe-B targets
# ---------------------------------------------------------------------------

def _model_for(fold_rot: str, obj: str, device: str):
    is_qwen = obj != "NON_QWEN_BASELINE"
    if is_qwen:
        model = build_qwen(fit_seed(fold_rot), device)
        model = make_qwen_heads(model, EXPECTED_K,
                                obj == "QWEN_CE_PLUS_CORR", device)
    else:
        model = CharBaseline(EXPECTED_K, obj == "QWEN_CE_PLUS_CORR",
                             fit_seed(fold_rot), device)
    saved = torch.load(RUN / "fits" / fit_id(fold_rot, obj).replace(":", "_")
                       / "final.pt", map_location="cpu")
    load_trainable(model, saved["model_state"])
    model.eval()
    return model, is_qwen


def export_fit(rot: str, obj: str) -> None:
    """Frozen EXPORT: eval mode, no grad, batch 16; one model load per fit.
    Writes exports/{fid}/export.npz (e for role-0 Known x 3 conditions,
    role-1 (rec|unk) x 3 conditions, probe-B targets for fit+test rows)
    and dev e-vectors for probe-A fit rows (other rotations' role-0
    (rec|unk) rows under REAL)."""
    fid = fit_id(rot, obj)
    stage = f"export_{fid.replace(':', '_')}"
    if stage_done(stage):
        return
    if get_run_state()["fits"].get(fid, {}).get("status") != "COMPLETE":
        raise SystemExit(f"EXPORT_BEFORE_FIT_COMPLETE {fid}")
    model, is_qwen = _model_for(rot, obj, "cuda:0")
    out_dir = RUN / "exports" / fid.replace(":", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    cell = assemble_cell(CENTRAL_SEED, rot, OWG, GATE1)
    role = cell["ev_split_role"]
    unk = cell["ev_is_unknown"].astype(bool)
    rec = cell["ev_recoverable"].astype(bool)
    class_map = {c: i for i, c in enumerate(cell["known"])}
    train_idx = np.flatnonzero((role == 0) & (~unk))
    test_idx = np.flatnonzero((role == 1) & (rec | unk))
    zl = np.load(RUN / "features" / f"{rot}_labels.npz")
    labels = zl["labels"]
    zs = np.load(RUN / "features" / f"{rot}_stats.npz")
    stats = {"mean": zs["mean"], "scale": zs["scale"]}
    raw = np.load(RUN / "features" / f"{rot}_raw.npz")["raw"]
    raw_shuf = np.load(RUN / "pairs" / f"{rot}_eval_shuffle_evidence.npz")["raw"]
    raw_basic = raw_legal_matrix(
        cell["features_ev"], np.full(len(labels), "B", dtype=object))
    conds = {"REAL": raw, "BASIC": raw_basic,
             "UNRESTRICTED_SHUFFLED_EVAL": raw_shuf}

    def rows_tokens(rows: np.ndarray, cond: str):
        """(ids, tm, em, pad) for a row set under one condition. Qwen rows
        come from the token cache; baseline rows are char-tokenized on the
        fly (deterministic)."""
        if is_qwen:
            if np.array_equal(rows, train_idx):
                c = load_token_cache(RUN, rot, "train", cond)
            elif np.array_equal(rows, test_idx):
                c = load_token_cache(RUN, rot, "test", cond)
            else:
                raise SystemExit(f"UNKNOWN_ROW_SET cond={cond}")
            return c["ids"], c["tm"], c["em"], c["pad_id"]
        ids_l, tm_l, em_l = [], [], []
        for r in rows:
            rec_ = tokenize_row_char(ser.serialize(conds[cond][r], stats))
            ids_l.append(rec_["ids"])
            tm_l.append(rec_["masks"]["<TARGET>"])
            em_l.append(rec_["masks"]["<TEMPORAL>"]
                        | rec_["masks"]["<RELATION>"])
        mx = max(len(t) for t in ids_l)
        ids = np.zeros((len(rows), mx), dtype=np.int32)
        tm = np.zeros((len(rows), mx), dtype=np.uint8)
        em = np.zeros((len(rows), mx), dtype=np.uint8)
        for i, t in enumerate(ids_l):
            ids[i, :len(t)] = t
            tm[i, :len(tm_l[i])] = tm_l[i]
            em[i, :len(em_l[i])] = em_l[i]
        return ids, tm, em, CHAR_PAD_ID

    def extract(rows: np.ndarray, cond: str,
                need_logits: bool = False) -> tuple[np.ndarray, Any]:
        ids_all, tm_all, em_all, pad = rows_tokens(rows, cond)
        es, ps = [], []
        with torch.no_grad():
            for s in range(0, len(rows), EXPORT_BATCH):
                iid = torch.tensor(ids_all[s:s + EXPORT_BATCH], device="cuda:0",
                                   dtype=torch.long)
                im = torch.tensor(tm_all[s:s + EXPORT_BATCH], device="cuda:0")
                emm = torch.tensor(em_all[s:s + EXPORT_BATCH], device="cuda:0")
                attn = (iid != pad).long()
                with (torch.autocast("cuda", dtype=torch.bfloat16)
                      if is_qwen else torch.nullcontext()):
                    if is_qwen:
                        logits, u, v, e = qwen_forward(model, iid, attn, im, emm)
                    else:
                        logits, u, v, e = model(iid, im, emm)
                es.append(e.detach().cpu().numpy().astype(np.float64))
                if need_logits:
                    ps.append(logits.argmax(dim=-1).cpu().numpy())
        e_all = np.concatenate(es, axis=0)
        p_all = np.concatenate(ps, axis=0) if need_logits else None
        return e_all, p_all

    e_train = {c: extract(train_idx, c)[0] for c in CONDITIONS}
    e_test = {c: extract(test_idx, c)[0] for c in CONDITIONS}
    # probe-B targets: y = 1 iff argmax(head-logits) == canonical label at
    # the acquired state (REAL); computed once, same y across conditions
    _, p_fit = extract(train_idx, "REAL", need_logits=True)
    _, p_test = extract(test_idx, "REAL", need_logits=True)
    y_corr_train = (p_fit == labels[train_idx]).astype(np.int64)
    y_corr_test = (p_test == labels[test_idx]).astype(np.int64)
    dev = {}
    for r in ROTATIONS:
        if r == rot:
            continue
        c = load_token_cache(RUN, r, "dev", "REAL")
        es = []
        with torch.no_grad():
            for s in range(0, len(c["rows"]), EXPORT_BATCH):
                iid = torch.tensor(c["ids"][s:s + EXPORT_BATCH],
                                   device="cuda:0", dtype=torch.long)
                im = torch.tensor(c["tm"][s:s + EXPORT_BATCH], device="cuda:0")
                emm = torch.tensor(c["em"][s:s + EXPORT_BATCH], device="cuda:0")
                attn = (iid != c["pad_id"]).long()
                with (torch.autocast("cuda", dtype=torch.bfloat16)
                      if is_qwen else torch.nullcontext()):
                    if is_qwen:
                        _, _, _, e = qwen_forward(model, iid, attn, im, emm)
                    else:
                        _, _, _, e = model(iid, im, emm)
                es.append(e.detach().cpu().numpy().astype(np.float64))
        e_dev = np.concatenate(es, axis=0)
        np.save(out_dir / f"dev_{r}_real.npy", e_dev)
        dev[r] = e_dev
    np.savez_compressed(
        out_dir / "export.npz",
        e_train_REAL=e_train["REAL"], e_train_BASIC=e_train["BASIC"],
        e_train_UNRESTRICTED_SHUFFLED_EVAL=e_train[
            "UNRESTRICTED_SHUFFLED_EVAL"],
        e_test_REAL=e_test["REAL"], e_test_BASIC=e_test["BASIC"],
        e_test_UNRESTRICTED_SHUFFLED_EVAL=e_test[
            "UNRESTRICTED_SHUFFLED_EVAL"],
        train_idx=train_idx, test_idx=test_idx,
        test_unk=unk[test_idx].astype(np.uint8),
        test_rec=rec[test_idx].astype(np.uint8),
        test_groups=group_codes(cell["ev_groups"][test_idx]),
        y_correct_train=y_corr_train, y_correct_test=y_corr_test,
        allow_pickle=False)
    mark_stage(stage, {"rows_train": int(len(train_idx)),
                       "rows_test": int(len(test_idx)),
                       "e_dim": e_train["REAL"].shape[1],
                       "dev_rotations": list(dev)})
    print(f"[export {fid}] e dim={e_train['REAL'].shape[1]} "
          f"train={len(train_idx)} test={len(test_idx)}", flush=True)


# ---------------------------------------------------------------------------
# Probes (frozen s10/s11): mirror of the gate's probe_fit_and_score with
# Model B condition names and probe-B target semantics
# ---------------------------------------------------------------------------

def probe_fit_and_score_b(probe: str, fold_rot: str, family: str, view: str,
                          X_fit: np.ndarray, y_fit: np.ndarray,
                          X_test: dict[str, np.ndarray], y_test: np.ndarray,
                          X_thr: dict[str, np.ndarray],
                          cfg: dict[str, Any]) -> dict[str, Any]:
    """Mirror of the frozen gate probe_fit_and_score (exact family recipes,
    scaler, threshold = 95th percentile of the condition's threshold rows,
    AUROC/AUPR sklearn crosschecks at 1e-6) iterating the Model B frozen
    condition names."""
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


def run_probes(obj: str, cfg: dict[str, Any]) -> None:
    for fold_rot in ROTATIONS:
        stage = f"probe_{obj}_{fold_rot}"
        if stage_done(stage):
            continue
        fid = fit_id(fold_rot, obj)
        z = np.load(RUN / "exports" / fid.replace(":", "_") / "export.npz",
                    allow_pickle=True)
        X_test = {c: z[f"e_test_{c}"] for c in CONDITIONS}
        X_train = {c: z[f"e_train_{c}"] for c in CONDITIONS}
        y_unk = z["test_unk"].astype(np.int64)
        y_corr_test = z["y_correct_test"].astype(np.int64)
        y_corr_train = z["y_correct_train"].astype(np.int64)
        groups = z["test_groups"]
        dev_dir = RUN / "exports" / fid.replace(":", "_")
        dev_parts = [np.load(dev_dir / f"dev_{r}_real.npy")
                     for r in ROTATIONS if r != fold_rot]
        # probe A: y = is_unknown; fit = dev rotations' role-0 (rec|unk)
        # under REAL; threshold = test RK rows (same-population convention
        # mirror of the gate probe A)
        y_dev = []
        for r in ROTATIONS:
            if r == fold_rot:
                continue
            c = assemble_cell(CENTRAL_SEED, r, OWG, GATE1)
            mask = (c["ev_split_role"] == 0) & (
                c["ev_is_unknown"].astype(bool)
                | c["ev_recoverable"].astype(bool))
            y_dev.append(c["ev_is_unknown"].astype(bool)[mask].astype(np.int64))
        probes = {
            "A": {"X_fit": np.concatenate(dev_parts),
                  "y_fit": np.concatenate(y_dev),
                  "X_thr": {c: X_test[c][y_unk == 0] for c in CONDITIONS},
                  "y_test": y_unk},
            # probe B: y = acquired-state classification correctness;
            # fit + threshold rows = the SAME role-0 Known rows
            "B": {"X_fit": X_train["REAL"], "y_fit": y_corr_train,
                  "X_thr": X_train, "y_test": y_corr_test},
        }
        for probe, spec in probes.items():
            for family in FAMILIES:
                d = (RUN / "probes" / obj / fold_rot / probe / family / "E")
                d.mkdir(parents=True, exist_ok=True)
                fit_out = probe_fit_and_score_b(
                    probe, fold_rot, family, "E", spec["X_fit"],
                    spec["y_fit"], X_test, spec["y_test"], spec["X_thr"],
                    cfg)
                np.savez_compressed(
                    d / "scores.npz",
                    **{f"s_{c}": fit_out["scores"][c] for c in CONDITIONS},
                    y=spec["y_test"], groups=groups, allow_pickle=False)
                fit_out.pop("scores")
                (d / "metrics.json").write_text(
                    json.dumps(fit_out, indent=1, default=str),
                    encoding="utf-8")
        mark_stage(stage, {"probes": 2, "families": 3})
        print(f"[probe {obj} {fold_rot}] A+B x 3 families complete",
              flush=True)


# ---------------------------------------------------------------------------
# Bootstrap (frozen s10/s11 machinery; identical draws across objectives)
# ---------------------------------------------------------------------------

def bootstrap_objective(obj: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Mirror of the frozen gate bootstrap_pooled_view over the Model B
    condition names and increments; per (probe,family,objective) key with
    fresh default_rng(BOOTSTRAP_RNG) -> identical draws across objectives
    (fully paired comparisons)."""
    out: dict[str, Any] = {}
    for probe in ("A", "B"):
        for family in FAMILIES:
            fits: dict[str, Any] = {}
            for fold_rot in ROTATIONS:
                d = (RUN / "probes" / obj / fold_rot / probe / family / "E")
                z = np.load(d / "scores.npz", allow_pickle=True)
                m = json.loads((d / "metrics.json").read_text())
                fits[fold_rot] = {
                    c: {"scores": z[f"s_{c}"], "y": z["y"],
                        "groups": z["groups"],
                        "threshold": m["per_condition"][c]["threshold"],
                        "point_auroc": m["per_condition"][c]["auroc"],
                        "n": int(len(z["y"]))}
                    for c in CONDITIONS}
            rng = np.random.default_rng(BOOTSTRAP_RNG)
            test_groups = {r: fits[r]["REAL"]["groups"] for r in ROTATIONS}
            y_test = {r: fits[r]["REAL"]["y"] for r in ROTATIONS}
            draws, dropped = build_rotation_draws(test_groups, y_test,
                                                  cfg["bs_reps"], rng)
            n = {r: len(y_test[r]) for r in ROTATIONS}
            total = sum(n.values())
            weights = {r: n[r] / total for r in ROTATIONS}
            b = {"pooled_point": {}, "increments": {}, "per_rotation": {},
                 "draws_note": dropped}
            for cond in CONDITIONS:
                pooled = {"auroc": 0.0}
                per_rot = {}
                for rot in ROTATIONS:
                    f = fits[rot][cond]
                    per_rot[rot] = {"auroc": f["point_auroc"], "n": f["n"],
                                    "n_rk": int((~f["y"].astype(bool)).sum()),
                                    "n_tu": int(f["y"].sum())}
                    pooled["auroc"] += weights[rot] * f["point_auroc"]
                b["pooled_point"][cond] = pooled
                b["per_rotation"][cond] = per_rot
            rep = {"auroc": {}}
            for cond in CONDITIONS:
                rep["auroc"][cond] = {}
                for rot in ROTATIONS:
                    f = fits[rot][cond]
                    rep["auroc"][cond][rot] = rep_metric_matrix(
                        f["scores"], f["y"], f["groups"], draws[rot], None,
                        "auroc")
            INCS = (("real_minus_basic", "REAL", "BASIC"),
                    ("real_minus_unrestricted_shuffled_eval", "REAL",
                     "UNRESTRICTED_SHUFFLED_EVAL"))
            pooled_reps = {cond: np.zeros(cfg["bs_reps"])
                           for cond in CONDITIONS}
            for cond in CONDITIONS:
                for rot in ROTATIONS:
                    pooled_reps[cond] += weights[rot] * rep["auroc"][cond][rot]
            for name, a, b_ in INCS:
                d_ = pooled_reps[a] - pooled_reps[b_]
                b["increments"].setdefault("auroc", {})[name] = {
                    "point": float(sum(weights[r]
                                       * (fits[r][a]["point_auroc"]
                                          - fits[r][b_]["point_auroc"])
                                       for r in ROTATIONS)),
                    "ci95": [float(np.percentile(d_, BOOTSTRAP_PCTS[0])),
                             float(np.percentile(d_, BOOTSTRAP_PCTS[1]))],
                    "replicates": d_.astype(np.float32).tolist()}
                for rot in ROTATIONS:
                    dr = rep["auroc"][a][rot] - rep["auroc"][b_][rot]
                    b["per_rotation"].setdefault("auroc", {})
                    b["per_rotation"]["auroc"].setdefault(rot, {})[name] = {
                        "point": float(fits[rot][a]["point_auroc"]
                                       - fits[rot][b_]["point_auroc"]),
                        "ci95": [float(np.percentile(dr, BOOTSTRAP_PCTS[0])),
                                 float(np.percentile(dr, BOOTSTRAP_PCTS[1]))]}
            out[f"P{probe}_{family}"] = b
    return out


def retention_ratios(boot_obj: dict[str, Any], den: dict[str, Any]
                     ) -> dict[str, Any]:
    """ret_b/ret_s per family and median-over-families: Model B probe-A
    increments on e divided by the frozen Information-Gate RAW increments
    (point ratio; replicate ratios where denominator replicate > 0, same
    draws convention)."""
    out: dict[str, Any] = {"families": {}}
    for f in FAMILIES:
        num = boot_obj[f"PA_{f}"]["increments"]["auroc"]
        den_f = den["families"][f]
        per: dict[str, Any] = {}
        for suffix, num_key, den_key in (("b", "real_minus_basic",
                                          "real_minus_basic"),
                                         ("s",
                                          "real_minus_unrestricted_shuffled_eval",
                                          "real_minus_shuffled")):
            n_rep = np.array(num[num_key]["replicates"], dtype=np.float64)
            d_rep = np.array(den_f[den_key]["replicates"], dtype=np.float64)
            valid = d_rep > 0.0
            ratios = n_rep[valid] / d_rep[valid]
            per[suffix] = {
                "point": (num[num_key]["point"] / den_f[den_key]["point"]
                          if den_f[den_key]["point"] > 0 else None),
                "ci95": ([float(np.percentile(ratios, BOOTSTRAP_PCTS[0])),
                          float(np.percentile(ratios, BOOTSTRAP_PCTS[1]))]
                         if len(ratios) else None),
                "dropped_replicates": int((~valid).sum()),
                "kept_replicates": int(valid.sum())}
        out["families"][f] = per
    med: dict[str, Any] = {}
    for suffix, num_key, den_key in (("b", "real_minus_basic",
                                      "real_minus_basic"),
                                     ("s", "real_minus_unrestricted_shuffled_eval",
                                      "real_minus_shuffled")):
        points = [out["families"][f][suffix]["point"] for f in FAMILIES]
        points = [p for p in points if p is not None]
        n_rep = BOOTSTRAP_REPS
        valid = np.ones(n_rep, dtype=bool)
        for f in FAMILIES:
            valid &= np.array(den["families"][f][den_key]["replicates"],
                              dtype=np.float64) > 0.0
        ratios = np.empty((len(FAMILIES), int(valid.sum())))
        for i, f in enumerate(FAMILIES):
            n_ = np.array(boot_obj[f"PA_{f}"]["increments"]["auroc"]
                          [num_key]["replicates"],
                          dtype=np.float64)[valid]
            d_ = np.array(den["families"][f][den_key]["replicates"],
                          dtype=np.float64)[valid]
            ratios[i] = n_ / d_
        med_ratios = np.median(ratios, axis=0)
        med[suffix] = {
            "point": (float(np.median(points)) if points else None),
            "ci95": [float(np.percentile(med_ratios, BOOTSTRAP_PCTS[0])),
                     float(np.percentile(med_ratios, BOOTSTRAP_PCTS[1]))],
            "dropped_replicates": int((~valid).sum()),
            "kept_replicates": int(valid.sum())}
    out["median_over_families"] = med
    return out


def run_aggregate(cfg: dict[str, Any]) -> None:
    if stage_done("aggregate"):
        return
    den = infosuff_denominators()
    boot_all: dict[str, Any] = {}
    for obj in OBJECTIVES:
        boot_all[obj] = bootstrap_objective(obj, cfg)
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    aggs: dict[str, Any] = {
        "task": "MODEL_B_RECOVERY_AWARE_REPRESENTATION_V1",
        "mode": "formal",
        "protocol_sha256": PROTOCOL_SHA256,
        "serializer_sha256": SERIALIZER_SHA256,
        "execution_lock": execution_locks(),
        "data_identity": data_identity(),
        "model_identity": model_identity(),
        "infosuff_denominator_source": {
            "path": str(INFOSUFF_AGGREGATE),
            "sha256": den["aggregate_sha256"]},
        "head_commit": head,
        "objectives": {}}
    for obj in OBJECTIVES:
        boot = boot_all[obj]
        ret = retention_ratios(boot, den)
        med = ret["median_over_families"]
        ret_pass = None
        if med["b"]["point"] is not None and med["s"]["point"] is not None:
            ret_pass = bool(med["b"]["point"] >= RETENTION_THRESHOLD
                            and med["s"]["point"] >= RETENTION_THRESHOLD)
        fams_b = {f: boot[f"PB_{f}"] for f in FAMILIES}
        mat = {}
        for f in FAMILIES:
            inc = fams_b[f]["increments"]["auroc"]
            mat[f] = {"real_minus_basic": bool(
                inc["real_minus_basic"]["point"] >= MATERIALITY
                and inc["real_minus_basic"]["ci95"][0] > 0.0),
                "real_minus_unrestricted_shuffled_eval": bool(
                    inc["real_minus_unrestricted_shuffled_eval"]["point"]
                    >= MATERIALITY
                    and inc["real_minus_unrestricted_shuffled_eval"]
                    ["ci95"][0] > 0.0)}
        transfer_pass = bool(
            sum(1 for f in FAMILIES
                if mat[f]["real_minus_basic"]
                and mat[f]["real_minus_unrestricted_shuffled_eval"])
            >= STRONG_FAMILIES
            and rot_ok(fams_b, (("REAL", "BASIC"),
                                ("REAL", "UNRESTRICTED_SHUFFLED_EVAL"))))
        ret_rot = rot_ok({f: boot[f"PA_{f}"] for f in FAMILIES},
                         (("REAL", "BASIC"),
                          ("REAL", "UNRESTRICTED_SHUFFLED_EVAL")))
        if ret_pass is not None:
            ret_pass = bool(ret_pass and ret_rot)
        aggs["objectives"][obj] = {
            "retention": ret,
            "retention_rot_ok": ret_rot,
            "retention_success": ret_pass,
            "transfer_probe": {"families": mat,
                               "n_families_material_on_both": int(sum(
                                   1 for f in FAMILIES
                                   if mat[f]["real_minus_basic"]
                                   and mat[f]["real_minus_unrestricted_shuffled_eval"]))},
            "transfer_rot_ok": rot_ok(fams_b, (("REAL", "BASIC"),
                                               ("REAL",
                                                "UNRESTRICTED_SHUFFLED_EVAL"))),
            "transfer_success": transfer_pass,
            "attribution_real_minus_basic_point": {
                "A_CURRENT_STATE_TRANSITION_frozen": {
                    f: den["st_families"][f]["real_minus_basic"]["point"]
                    for f in FAMILIES},
                "B_CURRENT": {f: boot[f"PA_{f}"]["increments"]["auroc"]
                              ["real_minus_basic"]["point"]
                              for f in FAMILIES}},
            "note": ("retention rule: MODEL_B_RET_B >= 0.50 AND "
                     "MODEL_B_RET_S >= 0.50 (median over S(A,RAW)) + rotOK "
                     ">=2/3 both comparisons no reversed; transfer rule: "
                     ">=2/3 families material (point >= +0.02 AND CI lower "
                     "> 0) on BOTH comparisons + rotOK; if the exact "
                     "statistic makes a threshold mathematically "
                     "inappropriate -> STOP_NEEDS_REVIEW, never silently "
                     "reuse")}
    formal = RUN / "formal"
    formal.mkdir(parents=True, exist_ok=True)
    (formal / "aggregate.json").write_text(json.dumps(aggs, indent=1,
                                                      default=str),
                                           encoding="utf-8")
    (formal / "run_manifest.json").write_text(json.dumps({
        "task": "MODEL_B_RECOVERY_AWARE_REPRESENTATION_V1",
        "mode": "formal", "protocol_sha256": PROTOCOL_SHA256,
        "serializer_sha256": SERIALIZER_SHA256,
        "head_commit": head,
        "bootstrap_reps": cfg["bs_reps"], "materiality_floor": MATERIALITY,
        "strong_families": STRONG_FAMILIES, "rot_ok_min": ROT_OK_MIN,
        "retention_threshold": RETENTION_THRESHOLD,
        "epochs": EPOCHS, "batch_rows": BATCH_ROWS, "grad_accum": GRAD_ACCUM,
        "epoch_permutation": "default_rng(fit_seed + 7919*(epoch+1))",
        "notes": ["identity locks asserted at startup (protocol/serializer/"
                  "data/model)", "UNRESTRICTED_SHUFFLED_EVAL is evaluation-"
                  "only and distinct from MATCHED_SHUFFLED_TRAIN (distinct "
                  "name in code, artifacts, reports)",
                  "bootstrap draws: fresh default_rng(162600) per "
                  "(probe,family,objective) key -> identical draws across "
                  "objectives (fully paired)",
                  "probe thresholds are per-condition (mirror of the frozen "
                  "gate's probe conventions: probe A = test RK rows, "
                  "probe B = role-0 Known rows, per condition)",
                  "retention probe A fit rows are the dev rotations' role-0 "
                  "(rec|unk) rows under REAL (mirror of the frozen gate)",
                  "runtime estimate ~215-225 h total: per-fit ~27.5 h "
                  "(measured 1.8 s per batch-2 pair micro-batch x 55k "
                  "micro-batches incl. the matched-negative forwards) "
                  "+ baseline fits ~7 h + export ~35-45 h + probes ~10 h "
                  "+ bootstrap/aggregate ~2 h"]}, indent=1),
        encoding="utf-8")
    mark_stage("aggregate", {"objectives": list(OBJECTIVES)})
    print("[aggregate] complete", flush=True)


# ---------------------------------------------------------------------------
# Dry run + smoke (non-scientific; allowed in the PREPARE task)
# ---------------------------------------------------------------------------

def dry_run_main() -> int:
    print("=== MODEL B V1 — DRY RUN (static validation only) ===")
    lock = execution_locks()
    print("protocol_match:", lock["protocol_match"],
          lock["protocol_sha256_recomputed"][:16])
    print("serializer_match:", lock["serializer_match"],
          lock["serializer_sha256_recomputed"][:16])
    did = data_identity()
    print("data_identity files:", len(did["files"]), "OK")
    mid = model_identity()
    print("model_identity files:", len(mid["files"]), "OK; shards:",
          sorted(k for k in mid["files"] if k.endswith(".safetensors")
                 and "index" not in k))
    reg = json.loads((REPO / "reports/research_audit" /
                      "model_b_recovery_aware_representation_v1_preregistration.json").read_text())
    print("prereg status:", reg["status"],
          "protocol sha:", reg["protocol_sha256"][:16])
    print("plan: 9 fits =", [fit_id(r, o) for r in ROTATIONS for o in
                             OBJECTIVES])
    for r in ROTATIONS:
        print(f"  {r}: seed={fit_seed(r)} K={EXPECTED_K} epochs={EPOCHS} "
              f"batch={BATCH_ROWS} accum={GRAD_ACCUM}")
    print("formal launch command: PYTHONHASHSEED=0 python tools/"
          "run_model_b_recovery_aware_representation_v1.py --all --resume")
    print("DRY_RUN_PASS (no model load, no training, no scientific output)")
    return 0


def smoke_main() -> int:
    """Tiny NON-SCIENTIFIC synthetic-data shape check (no real rows, no
    scientific metrics): serializer -> tokenize -> spans -> forward ->
    readout -> heads -> losses, LoRA injection, pair constraints,
    checkpoint round-trip."""
    print("=== MODEL B V1 — SMOKE (synthetic, non-scientific) ===")
    execution_locks()
    rng = np.random.default_rng(0)
    n = 48
    raw = rng.normal(size=(n, 83))
    raw[:, 81] = rng.integers(0, 2, size=n)      # mask cols never scaled
    raw[:, 82] = rng.integers(0, 2, size=n)
    stats = ser.fit_stats(raw)
    # pair constraints on synthetic rows
    lab = rng.integers(0, 3, size=n)
    st = np.array(["B", "BT", "BR", "BTR"])[rng.integers(0, 4, size=n)]
    grp = rng.integers(0, 8, size=n)
    pi, pj = build_pairs(n, lab, st, grp, raw, 20260817)
    for p in range(n):
        assert lab[pi[p]] == lab[pj[p]]
        assert st[pi[p]] == st[pj[p]]
        assert grp[pi[p]] != grp[pj[p]]
        assert not np.array_equal(raw[pi[p]], raw[pj[p]])
    print("pairs:", n, "all constraints verified")
    # content-span sanity: state-B row -> empty evidence mask (h_e=0 path)
    b_row = raw[0].copy()
    b_row[81] = 0
    b_row[82] = 0
    rec_c = tokenize_row_char(ser.serialize(b_row, stats))
    assert not (rec_c["masks"]["<TEMPORAL>"] | rec_c["masks"]["<RELATION>"]).any()
    print("content spans: state-B evidence mask empty (h_e=0 path OK)")
    from transformers import AutoTokenizer  # noqa: PLC0415
    tok = AutoTokenizer.from_pretrained(QWEN_PATH, trust_remote_code=True)
    rec_q = tokenize_row_qwen(ser.serialize(b_row, stats), tok)
    assert not (rec_q["masks"]["<TEMPORAL>"] | rec_q["masks"]["<RELATION>"]).any()
    print("content spans (Qwen tokenizer): state-B evidence mask empty")
    device = "cuda:0"
    y = rng.integers(0, 3, size=n)
    for obj in OBJECTIVES:
        is_qwen = obj != "NON_QWEN_BASELINE"
        if is_qwen:
            model = build_qwen(7, device)
            model = make_qwen_heads(model, 3, obj == "QWEN_CE_PLUS_CORR",
                                    device)
            model.train()
            model.gradient_checkpointing_enable()
            toks = [tokenize_row_qwen(ser.serialize(raw[i], stats), tok)
                    for i in range(n)]
        else:
            model = CharBaseline(3, obj == "QWEN_CE_PLUS_CORR", 7, device)
            model.train()
            toks = [tokenize_row_char(ser.serialize(raw[i], stats))
                    for i in range(n)]
        opt = torch.optim.AdamW([p for p in model.parameters()
                                 if p.requires_grad], lr=LR)
        ce_fn = torch.nn.CrossEntropyLoss()
        mx = max(len(t["ids"]) for t in toks)
        ids = np.zeros((n, mx), dtype=np.int32)
        tm = np.zeros((n, mx), dtype=np.uint8)
        em = np.zeros((n, mx), dtype=np.uint8)
        for i, t in enumerate(toks):
            ids[i, :len(t["ids"])] = t["ids"]
            tm[i, :len(t["masks"]["<TARGET>"])] = \
                t["masks"]["<TARGET>"].astype(np.uint8)
            em[i, :len(t["masks"]["<TEMPORAL>"]
                       | t["masks"]["<RELATION>"])] = \
                (t["masks"]["<TEMPORAL>"]
                 | t["masks"]["<RELATION>"]).astype(np.uint8)
        e_out = None
        for step in range(2):
            idx = [step * 2, step * 2 + 1]
            iid = torch.tensor(ids[idx], device=device, dtype=torch.long)
            im = torch.tensor(tm[idx], device=device)
            emm = torch.tensor(em[idx], device=device)
            if is_qwen:
                logits, u, v, e = qwen_forward(
                    model, iid, (iid != tok.pad_token_id).long(), im, emm)
            else:
                logits, u, v, e = model(iid, im, emm)
            e_out = e
            loss = ce_fn(logits, torch.tensor(y[idx], device=device))
            if model.corr_enabled:
                s_real = cosine(u[0], v[0])
                s_neg = cosine(u[0], v[1])
                loss = loss + torch.nn.functional.softplus(-(s_real - s_neg))
            loss.backward()
            opt.step()
            opt.zero_grad()
            assert torch.isfinite(loss).item(), "non-finite loss"
        assert e_out.shape[1] == (512 if is_qwen else 256), e_out.shape
        # checkpoint round-trip (trainable-only state)
        torch.save({"model_state": trainable_state(model)},
                   "/tmp/modelb_smoke_ckpt.pt")
        m2 = build_qwen(7, device) if is_qwen else CharBaseline(3, True, 7,
                                                                device)
        if is_qwen:
            m2 = make_qwen_heads(m2, 3, True, device)
        load_trainable(m2, torch.load("/tmp/modelb_smoke_ckpt.pt",
                                      map_location="cpu")["model_state"])
        diff = max((a - b).abs().max().item() for a, b in zip(
            m2.state_dict().values(), model.state_dict().values()))
        assert diff == 0.0, diff
        print(f"[smoke {obj}] fwd/bwd OK, e={e_out.shape[1]}, "
              f"ckpt round-trip diff={diff:.2e}", flush=True)
        del model, m2, opt
        torch.cuda.empty_cache()
    print("SMOKE COMPLETE — synthetic only, no scientific metrics computed")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true",
                        help="run all pending fits then full evaluation")
    parser.add_argument("--rotation", choices=ROTATIONS)
    parser.add_argument("--objective", choices=OBJECTIVES)
    parser.add_argument("--eval-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="accepted; resume is the default behavior")
    args = parser.parse_args()

    if args.dry_run:
        return dry_run_main()
    if args.smoke:
        return smoke_main()
    if not (args.all or (args.rotation and args.objective) or args.eval_only):
        parser.error("need --all | --rotation/--objective | --eval-only "
                     "| --dry-run | --smoke")
    set_determinism()
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF",
                          "expandable_segments:True")
    RUN.mkdir(parents=True, exist_ok=True)
    for sub in ("fits", "exports", "probes", "logs", "stages", "identity",
                "formal", "pairs", "features", "tokens", "mlp_epochs"):
        (RUN / sub).mkdir(exist_ok=True)
    write_run_state("RUNNING")
    cfg: dict[str, Any] = {"bs_reps": BOOTSTRAP_REPS, "mlp_epochs": 20,
                           "rf_est": RF_CONFIG["n_estimators"],
                           "out": RUN}
    t0 = time.time()
    try:
        if args.all or (args.rotation and args.objective):
            fits = [(args.rotation, args.objective)] if args.rotation \
                else [(r, o) for r in ROTATIONS for o in OBJECTIVES]
            for rot, obj in fits:
                run_fit(rot, obj, cfg)
        if args.all or args.eval_only:
            for rot in ROTATIONS:
                for obj in OBJECTIVES:
                    export_fit(rot, obj)
            for obj in OBJECTIVES:
                run_probes(obj, cfg)
            run_aggregate(cfg)
    except BaseException:
        write_run_state("FAILED")
        raise
    write_run_state("COMPLETE")
    print(f"[model-b] FINISHED in {(time.time() - t0) / 3600:.1f} h",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
