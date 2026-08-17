# Core Hypothesis Formal Gate V1B — Conditional Evidence Utility Separability

> Status: `COMPLETE`
>
> Decision: **`CORE_HYPOTHESIS_GATE_1B=PASS`** (Temporal primary gate PASS 7/7;
> Relation conditional value SUPPORTED with strong evidence-diversity signal)
>
> Date: 2026-08-17
>
> Repository: `flow-security-agent` @ `main` `0cb49e31` (working tree — this
> report and all Gate 1B results are intentionally **not committed**)
>
> Scope: Gate 1B (H2 conditional utility separability) ONLY, as a KILL GATE
> follow-up to Gate 1 (which remains **`YELLOW`** — `GATE_1_STATUS_CHANGED=false`).
> Gate 1B is a prospective follow-up; no Gate 1 threshold or result was changed.
> No selector hyperparameter search, no family comparison, no seed or budget
> changes, no HELP/HARM redefinition, no rescue experiments
> (`RESCUE_EXPERIMENTS=false`). No FINAL_TEST row-level data was used for
> modeling. No DeepSeek, no Qwen, no GPU training.

## 1. Question and frozen protocol

Can runtime-visible **pre-acquisition BASIC state alone** predict whether
acquiring Evidence of a family will HELP (B wrong, B+E correct) vs HARM
(B correct, B+E wrong) — i.e., is conditional Evidence utility separable
before the acquisition cost is paid?

Frozen definitions (unchanged from the researcher-authorized protocol):

```text
HELP_E = (B wrong) AND (B+E correct)
HARM_E = (B correct) AND (B+E wrong)
SIGNED  = +1 / -1 / 0
DENOMINATOR = ALL validation targets (56,000 per seed)
OOF_FOLDS = 3 (group-atomic at activity_group_digest, primary (class,
  temporal_block) stratum, chronological largest-remainder chunking)
SELECTOR = RandomForestRegressor(n_estimators=200, max_depth=12,
  min_samples_leaf=20, max_features="sqrt", n_jobs=-1,
  random_state=formal_seed) — exactly one frozen family, one per family
  T/R/TR, trained ONLY on TRAIN OOF signed utility labels
SELECTOR INPUT = pre-acquisition BASIC state only: 47 Basic fields
  (safe_basic transform) + predicted-class one-hot + proba_B vector +
  max proba / margin / entropy + availability mask  (65 features;
  UTILITY_SELECTOR_LEAKAGE_AUDIT=PASS, no Temporal/Relation history,
  no labels, no ids)
BUDGETS = 5 / 10 / 15 / 20 %   (PRIMARY = 15%)
BASELINES: S0 random (500 reps, mean + CI), S1 low-confidence, S2
  high-entropy, S3 selector, S4 oracle (upper bound only)
```

## 2. Authoritative inputs (frozen Gate 1 artifacts, verified)

The Basic probability provider is the deterministically reproduced frozen
BASIC estimator (same frozen config/data/random_state); its hard predictions
were verified to reproduce frozen `pred_B` **exactly** for all 3 seeds
(`GATE_1B_STATUS=BLOCKED_BASIC_REPRODUCTION_MISMATCH` would have aborted
otherwise). Validation labels, predictions, group digests and temporal
blocks come exclusively from the frozen Gate 1 validation artifacts.
`UTILITY_OOF_COVERAGE=100%` (every TRAIN target receives exactly one OOF
prediction set; TRAIN 175,000/seed).

```text
GATE_1_PREVIOUS_STATUS=YELLOW
GATE_1_STATUS_CHANGED=false
GATE_1B_PROSPECTIVE_FOLLOWUP=true
GATE_1_THRESHOLDS_UNCHANGED=true
FINAL_TEST_MODELING_CONTAMINATION=false
```

## 3. Primary gate: Temporal (T1–T7)

| Criterion | Threshold | Value (3 seeds) | Pass |
| --- | --- | --- | --- |
| T1 mean HELP AUROC | ≥ 0.70 | 0.9218 (0.9099 / 0.9214 / 0.9340) | ✔ |
| T2 mean HELP AUPR | ≥ 2× prevalence | 0.3340 (prev ≈ 0.0276 → ~12×) | ✔ |
| T3 top15 HELP capture | ≥ 0.30 in 3/3 | 0.898 / 0.900 / 0.908 | ✔ |
| T4 selector15 net > random15 net | 3/3 | +0.0206 / +0.0219 / +0.0211 vs +0.0012 / +0.0009 / +0.0009 | ✔ |
| T5 mean gain vs random | ≥ 0.002 | +0.02019 | ✔ |
| T6 selector15 macro > basic macro | 3/3 and mean Δ ≥ 0.002 | 0.940 / 0.942 / 0.942 vs 0.920 / 0.920 / 0.921; mean Δ +0.0216 | ✔ |
| T7 aggregate paired group bootstrap CI lower | > 0 (1000 reps) | +0.01386 [+0.01386, +0.02863] | ✔ |

**`GATE_1B_TEMPORAL_STATUS=PASS` (7/7; severe-failure condition not met:
mean AUROC 0.92 ≥ 0.65, mean capture 0.90 ≥ 0.25, mean gain +0.020 ≥ 0.001).**

Per-budget selector15 vs baselines (net recovery / 56,000, T, mean of 3 seeds):

| Budget | S3 selector | S1 confidence | S2 entropy | S0 random | S4 oracle |
| --- | --- | --- | --- | --- | --- |
| 5% | +0.0141 | +0.0112 | +0.0107 | +0.0003 | +0.0276 |
| 10% | +0.0183 | +0.0120 | +0.0115 | +0.0007 | +0.0276 |
| 15% | **+0.0212** | +0.0159 | +0.0160 | +0.0010 | +0.0276 |
| 20% | +0.0211 | +0.0183 | +0.0177 | +0.0013 | +0.0276 |

Selector15 net recovery reaches ≈ 77% of the oracle upper bound (which is
exactly the HELP prevalence, 0.0276) while acquiring only 15% of targets
with top15 harm capture of only 202 / 194 / 233 targets per seed.

## 4. Relation sub-gate (R1–R5 + evidence diversity)

```text
UNIQUE_R_HELP_RATE = 0.0207 / 0.0183 / 0.0186   (mean ≈ 0.0192)
RELATION_DIVERSITY_SIGNAL=true (mean ≥ 0.005 and 3/3 seeds ≥ 0.004)
```

| Criterion | Threshold | Value | Pass |
| --- | --- | --- | --- |
| R1 mean HELP AUROC | ≥ 0.70 | 0.9193 (0.929 / 0.906 / 0.923) | ✔ |
| R2 mean top15 capture | ≥ 0.30 | 0.9078 (0.923 / 0.936 / 0.865) | ✔ |
| R3 selector15 net > 0 | ≥ 2/3 | +0.0162 / +0.0329 / +0.0192 (3/3) | ✔ |
| R4 selector15 > random15 | ≥ 2/3 | random is NEGATIVE everywhere (−0.0008…−0.0023); selector positive 3/3 | ✔ |
| R5 aggregate bootstrap central estimate | > 0 | mean +0.0248 | ✔ |

**`GATE_1B_RELATION_STATUS=CONDITIONALLY_USEFUL`** — this resolves the Gate 1
"Relation conditional value unresolved": **always-on** Relation remains
negative at the frozen RF probe (Gate 1 unchanged), but **conditional**
acquisition at 15% is strongly positive precisely because random acquisition
for Relation is actively *harmful* (harm > help in random draws; random net
negative in 9/9 seed×budget cells) and the selector cleanly separates the
help targets (AUROC 0.92, top15 capture 0.91).

Diversity decomposition (mean rates): UNIQUE_T 0.0018, UNIQUE_R 0.0192,
SHARED_TR 0.0251, FULL_ONLY 0.0005 — the Relation-conditional signal is
substantial and not an artifact of shared T/R recoverability.
`EVIDENCE_DIVERSITY_STATUS=TEMPORAL_PLUS_RELATION_CONDITIONALLY_USEFUL`.

## 5. TR — secondary only

```text
TR_MEAN_HELP_AUROC=0.9175   TR_MEAN_TOP15_CAPTURE=0.9111
TR_MEAN_GAIN_VS_RANDOM_15=+0.0221   SECONDARY_ONLY=true
```

TR is reported but never gates the decision (max
`YELLOW_REQUIRES_RESEARCHER_REVIEW` in a non-primary role).

## 6. Gate 1 aggregate bootstrap (optional completeness, non-gating)

Pooled paired private-group bootstrap over the 3 frozen seeds
(`GATE_1_AGGREGATE_BOOTSTRAP_COMPLETENESS=COMPUTED_OPTIONAL_CHECK`),
delta Macro-F1 B+E vs B: T +0.0059 [−0.0035, +0.0158], R −0.0136
[−0.0428, +0.0185], TR −0.0216 [−0.0390, −0.0002]. Consistent with the
frozen Gate 1 = YELLOW report (Temporal modest positive, Relation/TR
negative at the frozen RF probe); computed from frozen predictions only
and **cannot change** Gate 1.

## 7. Final decision

```text
CORE_HYPOTHESIS_GATE_1B=PASS
GATE_1B_TEMPORAL_STATUS=PASS
GATE_1B_RELATION_STATUS=CONDITIONALLY_USEFUL
EVIDENCE_DIVERSITY_STATUS=TEMPORAL_PLUS_RELATION_CONDITIONALLY_USEFUL
ADAPTIVE_EVIDENCE_ACQUISITION_STATUS=SUPPORTED_FOR_NEXT_OPEN_WORLD_GATE
TEACHER_UTILITY_ALIGNMENT_STATUS=NOT_RUN_OUT_OF_SCOPE
```

Interpretation: conditional Evidence utility is **separable from
pre-acquisition Basic state** with strong, seed-consistent margin (Temporal
primary PASS 7/7; Relation conditional value supported). This is exactly the
prerequisite for the utility-conditioned acquisition arm of the
Evidence-Conditioned Open-World design. It does **not** authorize any Model B
training, RL, continual work, or the Open-World causal gate — those remain
`NOT_STARTED` and require explicit researcher authorization.

## 8. Safety ledger

```text
FINAL_TEST_MODELING_CONTAMINATION=false
DEEPSEEK_API_CALLS=0
QWEN_API_CALLS=0
MODEL_B_TRAINING_STARTED=false
RL_TRAINING_STARTED=false
OPEN_WORLD_GATE_STARTED=false
CONTINUAL_TRAINING_STARTED=false
GATE1B_COMMIT_CREATED=false
GATE1B_PUSHED=false
```

All Gate 1B artifacts (OOF parquets, selector models, per-seed evaluation/
bootstrap JSON, aggregate report JSON) live under the Git-external root
`/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1b/`; the
formal JSON copy of this report is `core_hypothesis_gate_v1b.json` beside
this file (untracked).
