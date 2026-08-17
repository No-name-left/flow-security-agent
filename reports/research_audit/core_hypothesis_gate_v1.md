# Core Hypothesis Formal Gate V1 — H1 Recoverable-Known Existence Test

> Status: `COMPLETE`
>
> Decision: **`CORE_HYPOTHESIS_GATE_1=YELLOW`** (no `E*` meets all six
> pre-registered criteria; a consistent weak Temporal signal exists)
>
> Date: 2026-08-17
>
> Repository: `flow-security-agent` @ `main` `50fecfb`
>
> Scope: Gate 0 (duplicate-aware target view) + Gate 1 (H1 existence test) ONLY.
> This is a KILL GATE: a FAIL is a valid outcome. No model/family/threshold
> tuning was performed after any result existed. No FINAL_TEST row-level data
> was used for modeling. No DeepSeek, no Qwen, no GPU training.

## 1. Authoritative source hashes

```text
SOURCE_ARTIFACT_SHA256=53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78
SOURCE_ROW_N=27520260
SPLIT_MANIFEST_SHA256=faa5220beae65f06591e7ea399c59092985135b81860fcd2388f20cadaa7c095
```

Master split `GROUPED_TEMPORAL_HASH_70_15_15_V1` (seed `20260816`) is untouched:
`MASTER_SPLIT_MODIFIED=false`. FINAL_TEST partition rows (3,843,430 incl. 1,404
out-of-core) were excluded from every modeling array; only aggregate frozen
counts were used. `FINAL_TEST_MODELING_CONTAMINATION=false`.

## 2. Gate 0 — duplicate-aware derived target view

Frozen semantics verified over the full 27,520,260-row manifest:

```text
DUPLICATE_GROUP_KEY=canonical_row_digest
VERIFIED_DUPLICATE_GROUPS=480040 (matches frozen audit exactly)
VERIFIED_DUPLICATE_COPIES=1816137 (matches frozen audit exactly)
DUPLICATE_LABEL_CONFLICTS=0
REPRESENTATIVE_RULE=earliest flow_start_ms, tie-break minimum source_row_index
GATE_0_STATUS=PASS
```

Duplicate-aware pools: TRAIN `18,113,916` / VALIDATION `3,775,311`
representatives. All 7 classes in both partitions reach the frozen caps
(TRAIN 25,000 / VALIDATION 8,000) with large headroom (min pool: VALIDATION
Backdoor 14,940 ≥ 5,000 minimum).

**Evidence history is NOT deduplicated**: Temporal/Relation features are built
from the full critical-valid split history (all 23,668,250 TRAIN+VALIDATION
rows, including duplicate copies and the 9,984 out-of-core mitm/ransomware
rows). Only the model training/evaluation target view is duplicate-aware.

## 3. Evidence history rule (verified)

```text
EVIDENCE_HISTORY_SCOPE=WITHIN_SPLIT_STRICT_END_BEFORE_TARGET_START_V1
EVIDENCE_STRICT_PAST_ONLY=true
```

- Contributors must be critical-valid rows of the target's own partition with
  `flow_end_ms < target.flow_start_ms` inside fixed 10/60/300s windows.
- Equal-time, future, and cross-split rows are excluded by construction
  (partition-keyed group arrays + `searchsorted(..., side="left")`).
- Independently verified: 50 randomly selected real targets re-computed by
  brute-force full scan of their source groups — 50/50 exact matches.

## 4. Features and forbidden-feature audit

- `BASIC_FEATURE_NAMES` = the 47 frozen `MODEL_VISIBLE` fields of
  `NF3_TON_BASIC_CARD_V1`, pilot-probe transform `sign(x)·log1p(|x|)`
  (identical to the frozen reference pipeline).
- `TEMPORAL_FEATURE_NAMES` (16): `source_flow_count`, `source_flow_rate`,
  `source_packet_rate`, `source_byte_rate`, `destination_flow_count` per
  10/60/300s + `same_source_last_seen_gap_ms`.
- `RELATION_FEATURE_NAMES` (18): `source_unique_destination_count`,
  `source_unique_destination_port_count`, `source_same_destination_port_count`,
  `source_destination_pair_count`, `destination_unique_source_count`,
  `source_unique_neighbor_count` per 10/60/300s.
- History transform: `log1p(clip(x, 0, None))` (reference pipeline).
- `FORBIDDEN_FEATURE_AUDIT=PASS`: no GT label, digest, row identity, group,
  partition/split/fold, rotation, or raw endpoint/time field enters any
  feature matrix. `activity_group_digest` is used only for bootstrap units.

## 5. Sampling

Temporal-block-stratified, duplicate-aware, deterministic per seed:
50 chronological blocks per split × class, proportional allocation, without
replacement. Seed controls only sampling and the estimator `random_state`.

| Seed | TRAIN targets | VALIDATION targets |
| --- | ---: | ---: |
| 20260817 | 175,000 | 56,000 |
| 20260818 | 175,000 | 56,000 |
| 20260819 | 175,000 | 56,000 |

(`IMPLEMENTATION_SMOKE` seed 777001: 14,000 / 7,000 — used only to check the
pipeline; its numbers play no role in any threshold or decision.)

## 6. Estimator (frozen before any formal result)

```text
CORE_GATE_ESTIMATOR=RandomForestClassifier
CORE_GATE_ESTIMATOR_CONFIG=n_estimators=80, max_depth=20, min_samples_leaf=2,
  class_weight=balanced_subsample, random_state=<formal seed>
PROVENANCE=frozen NF3-ToN reference probe config
  (tools/finalize_dataset_v4_split.py); n_jobs=-1 is a speed-only change
```

One estimator family. No hyperparameter search, no threshold tuning, no model
comparison was performed.

## 7. Formal results (3 seeds, validation)

| Seed | Macro-F1 B | BT | BR | BTR | ΔT | ΔR | ΔTR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20260817 | 0.919545 | 0.927756 | 0.901961 | 0.897447 | +0.008210 | −0.017585 | −0.022099 |
| 20260818 | 0.920137 | 0.925688 | 0.913130 | 0.896642 | +0.005551 | −0.007007 | −0.023495 |
| 20260819 | 0.920504 | 0.926225 | 0.901353 | 0.901044 | +0.005721 | −0.019151 | −0.019460 |
| **mean** | **0.920062** | **0.926556** | **0.905481** | **0.898378** | **+0.006494** | **−0.014581** | **−0.021685** |

Balanced accuracy (mean): B 0.9241 / BT 0.9303 / BR 0.9099 / BTR 0.9028.

## 8. Recoverability, harm, net recovery (3-seed means, validation)

| Family | Recoverable rate | Harm rate | Net recovery | Bootstrap ΔF1 mean | 95% CI (ΔF1) |
| --- | ---: | ---: | ---: | ---: | --- |
| T | 0.027637 | 0.021100 | **+0.006625** | +0.006295 | seed-wise: [−0.00014, +0.01522] / [−0.00614, +0.01599] / [−0.00544, +0.01574] |
| R | 0.045530 | 0.055353 | −0.011756 | −0.013796 | includes 0 or negative in all seeds |
| TR | 0.035952 | 0.057399 | −0.021405 | −0.021710 | negative lower bounds in 2/3 seeds |

`RECOVERABLE_KNOWN_RATE_E = #(B wrong ∧ B+E correct) / #validation targets`;
`HARM_RATE_E = #(B correct ∧ B+E wrong) / #validation targets`;
`NET = RECOVERABLE − HARM`. Definitions frozen before any result.

### Per-class recoverability (Temporal, 3-seed mean of per-seed rates)

| Class | T | R | TR |
| --- | ---: | ---: | ---: |
| Backdoor | 0.0003 | 0.0003 | 0.0003 |
| Benign | 0.0816 | 0.2064 | 0.1452 |
| Credential | 0.0011 | 0.0013 | 0.0013 |
| DDoS | 0.0019 | 0.0016 | 0.0017 |
| DoS | 0.0343 | 0.0336 | 0.0342 |
| Recon_Scanning | 0.0065 | 0.0081 | 0.0048 |
| Web_Injection | 0.0679 | 0.0683 | 0.0646 |

Attack classes with per-class recoverable rate ≥ 0.02 (mean): `DoS`,
`Web_Injection` for all three families (2 attack classes → criterion 4 is met
wherever checked). Recovery is NOT Benign-only.

## 9. Bootstrap

Paired private-activity-group bootstrap, 1,000 replicates per seed, the same
group multiset applied to B and every B+E condition (pairing by construction).
Duplicate groups are never split (identical rows share one activity group).
Bootstrap units are the frozen private groups; naive row bootstrap was not
used.

## 10. Frozen criteria application

| Criterion | T | R | TR |
| --- | --- | --- | --- |
| 1: ΔMacroF1 > 0 in 3/3 seeds | **PASS** | FAIL | FAIL |
| 2: 3-seed mean Δ ≥ 0.005 | **PASS** (+0.00649) | FAIL | FAIL |
| 3: 3-seed mean recoverable rate ≥ 0.05 | **FAIL** (0.0276) | FAIL (0.0455) | FAIL (0.0360) |
| 4: ≥2 non-Benign classes with mean per-class rate ≥ 0.02 | **PASS** (DoS, Web_Injection) | PASS | PASS |
| 5: bootstrap 95% CI lower bound > 0 | **FAIL** (seed lower bounds −0.0001/−0.0061/−0.0054) | FAIL | FAIL |
| 6: mean net recovery > 0 | **PASS** (+0.00663) | FAIL | FAIL |

No Evidence condition satisfies all six criteria → **not PASS**.

## 11. Decision

```text
CORE_HYPOTHESIS_GATE_1=YELLOW
CORE_EVIDENCE_FAMILY=NONE (candidate: TEMPORAL)
WHICH_CRITERIA_FAILED=Temporal: Criterion 3 (mean recoverable rate 0.0276 < 0.05)
  and Criterion 5 (bootstrap 95% CI lower bound includes 0)
```

Not FAIL, because: best 3-seed mean recoverable rate (R: 0.0455) is above the
0.02 strong-failure band; Temporal improves Macro-F1 in 3/3 seeds with positive
central estimates; recovery covers two attack classes (DoS, Web_Injection),
not Benign alone; and the paired bootstrap central estimates are positive for
Temporal. The signal is real but **below the pre-registered existence
magnitude** (0.05 recoverable rate) and not yet CI-stable.

## 12. Gate 1.5 — Evidence family interpretation

Closest to category **B-limited**:

```text
TEMPORAL = modest, consistent, positive (Δ +0.0065 mean, net +0.0066, 3/3 seeds)
RELATION = weak/negative at this probe (Δ −0.0146 mean, harm > recovery)
FULL     = does NOT dominate Temporal; adding Relation drags BTR below Basic
           (Δ −0.0217 mean)
```

Interpretation (descriptive only): within the frozen B1 family set, TEMPORAL
is the only family with a consistent positive existence signal; RELATION
aggregates as a negative ablation at the frozen RF probe. No prompt, model,
window, or family was changed after these results. Teacher v1's
`ACQUIRE_RELATION=0` was not used to down-weight Relation a priori (Teacher is
not utility GT).

## 13. Comparison to prior 24k pilot (descriptive only)

| Signal | 24k pilot | Formal Gate (dup-aware, 3 seeds) |
| --- | ---: | ---: |
| Basic Macro-F1 | 0.9241 | 0.9195–0.9205 |
| Full Macro-F1 | 0.9543 | 0.8966–0.9010 (BTR below Basic) |
| Recoverable rate | 0.11996 | T 0.0276 / R 0.0455 / TR 0.0360 |

The pilot's aggregate "Full > Basic" and ~12% recoverability **did not
reproduce** at duplicate-aware formal scale. The recoverable-Known phenomenon
still exists (Temporal: positive deltas in 3/3 seeds, positive net recovery,
two attack classes ≥ 0.02), but its magnitude shrinks by roughly 4× relative
to the pilot and Relation's aggregate contribution is negative at this probe.
No formal threshold was adjusted to match the pilot.

## 14. Limitations

- Single frozen estimator family (RF probe); results are probe-level
  existence evidence, not a model comparison.
- 3 formal seeds; per-class caps (25k/8k); validation-only rates.
- Current Temporal/Relation implementations are the frozen B1 aggregate
  definitions; no alternative windows or definitions were explored.
- No FINAL_TEST usage by construction.
- The 0.05 recoverable-rate threshold and all criteria were pre-registered
  before any formal result existed.

## 15. Artifacts (Git-external, `/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1/`, 125 MB)

| Artifact | SHA256 (prefix) |
| --- | --- |
| duplicate_aware_target_manifest_v1.parquet (21,889,227 reps) | 4bfc3b0dc8d44d79… |
| core_gate_basic_features_v1.parquet (649,724 rows × 47 fields) | 6c79423c4cf9369d… |
| gate_seed_{seed}_targets.parquet ×3 | e294799e… / 47b4af20… / b65d45ea… |
| gate_seed_{seed}_history.parquet ×3 (34 features) | 5713138e… / 2b5d4070… / f365aeb8… |
| gate_seed_{seed}_validation_predictions.parquet ×3 | 9f75b156… / 325c18ad… / b6929d66… |
| gate_seed_{seed}_result.json / _bootstrap.json ×3 | — |
| gate0_summary.json / core_gate_decision.json | — |

Rebuild commands (all deterministic):

```bash
python tools/run_core_hypothesis_gate_v1.py --mode gate0
python tools/run_core_hypothesis_gate_v1.py --mode basic
python tools/run_core_hypothesis_gate_v1.py --mode seed --seed 20260817   # and 18, 19
python tools/run_core_hypothesis_gate_v1.py --mode bootstrap --seed 20260817  # and 18, 19
python tools/run_core_hypothesis_gate_v1.py --mode decide
```

## 16. Safety accounting

```text
DEEPSEEK_API_CALLS=0
QWEN_API_CALLS=0
GPU_TRAINING_STARTED=false
MODEL_B_TRAINING_STARTED=false
RL_TRAINING_STARTED=false
CONTINUAL_TRAINING_STARTED=false
FINAL_TEST_MODELING_CONTAMINATION=false
```

## 17. Explicit next action (depends on decision)

```text
NEXT_ACTION=RESEARCHER_REVIEW_BEFORE_ANY_ADAPTIVE_ACQUISITION_OR_MODEL_B_WORK
```

Per the kill-gate protocol this task STOPS here. No Gate 2, no open-world, no
Qwen, no RL, no adaptive acquisition, no further seeds, no prompt or threshold
changes are authorized by this task.
