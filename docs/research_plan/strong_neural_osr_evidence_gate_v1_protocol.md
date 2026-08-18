# Strong Neural OSR Evidence Recoverability Gate V1 — Protocol

Status: FROZEN_BEFORE_EVALUATION (sha256 recorded in the preregistration JSON)
Date: 2026-08-18
Schema: STRONG_NEURAL_OSR_EVIDENCE_GATE_V1_PROTOCOL_V1
Authorization: DEC-0028 (2026-08-18) — preregistered pre-Model-B baseline.

This document is the preregistered, frozen protocol for the Strong
Neural OSR Evidence Recoverability Gate V1.

Pre-freeze feasibility correction (2026-08-18, researcher decision,
BEFORE any formal evaluation metric was viewed — not post-result
tuning): the TRAIN target is the COMPLETE frozen eligible Known TRAIN
population of 150,000 rows per (rotation, seed) with a deterministic
group-safe approximate 90/10 OSR_TRAIN_FIT / OSR_TRAIN_EARLY_STOP
split. This replaces the infeasible 200,000-row target. No cross-seed
supplementation, no replacement sampling, no additional TRAIN
materialization, no change to frozen target artifacts.

## 0. Authorization boundary

AUTHORIZED (DEC-0028 + researcher freeze/launch instruction
2026-08-18): freezing and executing this protocol exactly as
specified, only after the preregistration/implementation commit.
NOT AUTHORIZED: executing any evaluation BEFORE that commit; Qwen /
Model B; RL; continual learning; purification; FINAL_TEST; modifying
frozen V1/V2 results, frozen datasets, manifests, or frozen protocols;
detector shopping (the method set below is closed); post-result
tuning.

## 1. Scientific questions

- **A. OSR adequacy** — is the dedicated neural OSR sufficiently
  credible to judge Evidence? If not, Evidence may NOT be declared
  failed (GATE_INVALID_OSR_INADEQUATE).
- **B. Evidence information potential** — ignoring router mistakes
  (offline mechanism analysis), can at least one legal T/R/TR Evidence
  state recover frozen Recoverable Known samples in open-set
  representation space?
- **C. Evidence specificity** — does Evidence move Recoverable Known
  toward Known regions more than it moves True Unknown toward Known
  regions?
- **D. Deployable value** — with the exact frozen P6 Utility Typed
  router, does selective Evidence improve open-world performance
  relative to the SAME strong OSR using Basic only?

## 2. Frozen experimental population

Preserved exactly from the frozen V1/V2 artifacts:

- Rotations (whole-class held-out Unknown): Credential,
  Recon_Scanning, Web_Injection.
- Seeds: 20260817, 20260818, 20260819.
- Evidence states: B, BT, BR, BTR.
- Primary Recoverable-Known population: exact frozen V1 definition and
  row identities — `recoverable = Basic prediction wrong AND at least
  one legal Evidence state among BT/BR/BTR predicts correctly` under
  the frozen Gate-1-compatible classifiers. Residual-hard =
  Basic wrong AND all of BT/BR/BTR wrong. The stored `recoverable`
  column in the frozen V1 eval parquet is authoritative; no
  recomputation may replace it.
- FINAL_TEST excluded entirely.
- Held-out True Unknown excluded from: representation training;
  normalization; early stopping; prototype/covariance fitting;
  threshold calibration; model/hyperparameter selection. True Unknown
  labels are used ONLY for final evaluation metrics.

### Frozen read-only inputs

Per (seed, rotation):

- `open_world_recoverability_gate_v1/owg_v1_seed_<s>_rotation_<r>_eval.parquet`
  — frozen VALIDATION table (split_role 0=CALIB, 1=EVAL) with
  canonical_label, is_unknown, recoverable, residual_hard,
  activity_group_digest, temporal_block, and per-policy stored
  action/score/pred/rejected columns for P0/P1/P3/P4/P5/P6/P7.
- `open_world_recoverability_gate_v1/models/owg_v1_seed_<s>_rotation_<r>_models.pkl`
  — frozen B/BT/BR/BTR classifiers and T/R/TR utility selectors.
- Gate-1 / Gate-1B roots — frozen feature tables and targets (TRAIN
  Known rows with safe_basic 47 fields; T = 16 temporal history
  fields; R = 18 relation history fields; log1p(clip) transforms).
- Frozen P6 UTILITY_TYPED router (exact definition below); frozen
  RF Basic MSP baseline (P0 stored scores) as historical comparison.

### Training / calibration / evaluation populations

- TRAIN sample: the COMPLETE frozen eligible Known TRAIN population per
  (rotation, seed): partition_code == 0 (PARTITION_TRAIN) rows whose
  canonical_label is one of the six rotation Known classes —
  6 classes × 25,000 rows/class = 150,000 rows per cell. No cross-seed
  supplementation, no replacement sampling, no additional row
  materialization. If the frozen TRAIN population for a cell deviates
  from 6 × 25,000, STOP_NEEDS_REVIEW.
- OSR_TRAIN_FIT / OSR_TRAIN_EARLY_STOP: deterministic group-safe
  approximate 90/10 split of the 150,000 pool. Within each class,
  order activity groups by
  SHA256(seed_hex || rotation_utf8 || group_digest_bytes) ascending;
  walking in that order, assign a group to EARLY_STOP while the
  class's cumulative EARLY_STOP row count (before the group) is
  < round(0.10 × class_total); all remaining rows go to FIT. No group
  may cross FIT/EARLY_STOP roles; no RNG. Actual per-cell counts are
  recorded in the preregistration JSON (TRAIN_FIT_N ≈ 134,000–134,900;
  TRAIN_EARLY_STOP_N ≈ 15,100–16,000); the runner must reproduce them
  exactly and STOP_NEEDS_REVIEW on any mismatch BEFORE training.
- Early stopping: monitoring metric = validation CrossEntropy loss on
  OSR_TRAIN_EARLY_STOP (Known-only, group-atomic).
- Calibration: VAL_CALIB Known = split_role==0 AND is_unknown==0 in
  the frozen eval parquet, per policy (see §7).
- Evaluation: VAL_GATE_EVAL = split_role==1 (outer True Unknown
  exposed ONLY for final evaluation metrics).

## 3. Evidence representation

Primary input is structured numerical Evidence, not natural-language
cards. Runtime-legal strict-past blocks only: Basic / Temporal /
Relation (same frozen feature transforms as Gate 1).

Typed-block masked fusion:

- Separate block encoders for Basic / Temporal / Relation with
  explicit availability masks mT (1 iff Temporal block is present,
  i.e. states BT/BTR) and mR (1 iff Relation block present, i.e.
  states BR/BTR).
- One set of shared parameters handles all of B/BT/BR/BTR; no encoder
  per Evidence state.
- Training must expose all four legal states: per epoch, each sampled
  row is presented in one state drawn uniformly from {B, BT, BR, BTR}
  (deterministic seeded sampling), so the model sees masked and
  unmasked Temporal/Relation blocks.

## 4. Strong neural encoder (preferred frozen design)

Block encoder (identical for Basic 47-dim, Temporal 16-dim,
Relation 18-dim inputs):

```text
Linear(input_dim, 128) → LayerNorm → GELU → Dropout(0.10)
  → Linear(128, 64) → GELU
```

Fusion:

```text
[z_B, mT*z_T, mR*z_R, mT, mR]      # 128*3 + 2 = 386
  → Linear(386, 256) → LayerNorm → GELU → Dropout(0.10)
  → Linear(256, 128)
```

- Embedding dimension = 128.
- Known classification head: Linear(128, 6) (six rotation Known
  classes per rotation).
- Loss: CrossEntropy + 0.10 * SupervisedContrastiveLoss
  (temperature = 0.10; contrastive unit = batch, labels = Known
  class).
- Optimizer: AdamW, lr = 3e-4, weight_decay = 1e-4.
- Max epochs = 20; Known-only early stopping, patience = 3.
- One model per (rotation, seed), trained ONLY on the 200k TRAIN
  Known sample. No post-result tuning; no Unknown anywhere in
  training/selection.

## 5. Primary OSR and diagnostics

- Class means: estimated from OSR_TRAIN_FIT Known embeddings, per
  class, SEPARATELY for each Evidence state s ∈ {B, BT, BR, BTR}
  (implementation clarification of the frozen spec: a state-s
  embedding is the shared encoder applied to the state-s feature
  blocks; the deployable comparison in §10 requires state-specific
  geometry). Known-only.
- Covariance: ONE tied pooled LedoitWolf covariance shared by all
  classes, fitted on the OSR_TRAIN_FIT Known embeddings, separately
  per Evidence state (four fits total). Known-only.
- **Primary novelty score: minimum Mahalanobis distance to any Known
  class mean.** Higher = more novel. Unknown is never a K+1 class.
- Diagnostic baseline 1 — same-encoder Deep MSP: 1 − max softmax of
  the same encoder's Known head (on the relevant Evidence state).
  Fixed diagnostic; never selected over Mahalanobis after results.
- Diagnostic baseline 2 — frozen historical RF Basic MSP: stored P0
  scores from the frozen V1 artifacts (read-only comparison, no
  recomputation).

## 6. Calibration

Policy-conditioned, Known-only, at 5% Known false-Unknown rate
(threshold = 95th percentile of Known post-policy scores; rejection
tie semantics `score >= threshold`, frozen V1). True Unknown never
participates in calibration.

Calibrate SEPARATELY for every observation policy whose score
distribution differs:

- D0_BASIC: Basic state only;
- D1_P6_SELECTIVE: frozen P6 actions, score from the encoder on the
  actually acquired Evidence state (NONE→B, T→BT, R→BR, TR→BTR);
- D2_ALWAYS_FULL: TR for all rows (descriptive);
- D3_RANDOM_COST_MATCHED: frozen P2-style random cost-matched
  acquisition (descriptive).

The D0 threshold is never reused for other policies.

### Frozen P6 UTILITY_TYPED (exact, do not retrain)

Eligible targets have max(u_T, u_R, u_TR) > 0; sort by max utility
descending (tie: ascending target order); ideal family = argmax with
tie-break priority T, R, TR; if remaining budget >= cost(ideal) select
ideal, else fall back to the cheapest affordable family with positive
predicted utility in priority order T then R, else NONE; stop at budget
exhaustion. Unit costs NONE=0, T=1, R=1, TR=2; budget = 0.15 × N_targets
applied separately to the calibration and evaluation populations.
Use the frozen stored P6 action/score/pred columns; if recomputation is
ever required it must be deterministic from the frozen selectors/models
and cross-verified against the stored columns BEFORE any metric. The
router is never retrained.

## 7. OSR adequacy gate (Question A)

Evaluated with the Basic-state encoder on VAL_GATE_EVAL. Adequacy PASS
iff ALL of:

- **A1 Known classification**: per-rotation Known Macro-F1 ≥ 0.90 AND
  pooled mean ≥ frozen RF Basic pooled mean − 0.01.
- **A2 Unknown discrimination**: pooled mean Unknown AUROC ≥ frozen RF
  Basic pooled mean − 0.02 AND no rotation more than 0.05 below that
  rotation's frozen RF Basic AUROC.
- **A3 Recall**: pooled mean Unknown Recall@5% Known FUR ≥
  frozen RF Basic pooled mean − 0.03 AND no rotation more than 0.05
  below that rotation's frozen RF Basic recall.
- **A4 Dedicated open-set value over same-encoder Deep MSP**:
  pooled paired bootstrap mean (Mahalanobis AUROC − Deep MSP AUROC)
  ≥ +0.010, positive in ≥ 2/3 rotations, pooled 95% CI lower bound
  > −0.02.

If adequacy FAILS: decision = GATE_INVALID_OSR_INADEQUATE. Evidence
may NOT be declared failed.

## 8. Offline Evidence information potential (Question B)

Mechanism analysis on frozen Recoverable Known rows, GT used ONLY for
analysis (never deployable). For each Recoverable Known row with true
class y, for each legal state s ∈ {B, BT, BR, BTR}:

```text
d_true(s)      = Mahalanobis distance of the state-s embedding to y's class mean
d_near_wrong(s)= minimum Mahalanobis distance to any OTHER Known class mean
geometry_margin(s) = d_near_wrong(s) − d_true(s)
```

Best-legal oracle state = argmax over {BT, BR, BTR} of
geometry_margin(s) (GT-guided; NEVER a deployable policy).

Per-row margin gain = margin(best_legal) − margin(Basic). Standardize
per cell by the Basic-state margin SD computed on the 200k TRAIN Known
sample of that (rotation, seed).

Potential PASS iff BOTH (strengthened because BEST_LEGAL {T,R,TR} is an
optimistic offline oracle analysis; thresholds must NOT be weakened
after evaluation begins):

- **B1 pooled**: pooled BEST_LEGAL_MARGIN_GAIN > 0 rate (fraction of
  Recoverable Known with best-legal margin gain > 0) ≥ 0.60; AND
  pooled mean standardized best-legal margin gain ≥ +0.20 with paired
  group/temporal-block bootstrap 95% CI lower bound > 0.
- **B2 cross-rotation**: BEST_LEGAL_MARGIN_GAIN > 0 rate > 0.55 in
  ≥ 2/3 rotations; AND mean true-class Mahalanobis distance improves
  (decreases, best-legal state vs Basic) in ≥ 2/3 rotations.

## 9. Evidence specificity (Question C)

KNOWNNESS(s) = minimum Mahalanobis distance to any Known class
(lower = more Known-ward). Known-ward gain of state s vs Basic =
KNOWNNESS(Basic) − KNOWNNESS(s) (positive = moved toward Known).

- Recoverable Known: best-legal Known-ward gain = max over legal
  states {BT, BR, BTR}.
- True Unknown (conservative stress test): most Known-ward legal
  state = max over {BT, BR, BTR} of its Known-ward gain.

Specificity PASS iff ALL:

- **C1**: pooled mean specificity gap
  (mean RK best-legal gain − mean TU most-Known-ward gain) > 0 with
  group/temporal-block paired bootstrap 95% CI lower bound > 0.
- **C2**: pooled median gap > 0.
- **C3 ratio bound**: pooled mean TU most-Known-ward gain ≤ 0.50 ×
  pooled mean RK best-legal gain (applies only when the RK gain is
  > 0).
- **C4 cross-rotation**: ≥ 2/3 rotations have mean gap > 0.

## 10. Deployable comparison (Question D)

Same strong OSR, two primary arms:

- D0_BASIC: Basic-only embeddings and Mahalanobis scores.
- D1_P6_SELECTIVE: exact frozen P6 selective acquisition; score from
  the encoder on the actually acquired state.

Descriptive (reported, non-gating): D2_ALWAYS_FULL,
D3_RANDOM_COST_MATCHED.

Mandatory metrics (per rotation, per seed, pooled): FURK; raw FURK
numerator/denominator; Known Macro-F1; Known false-Unknown rate;
Unknown AUROC; Unknown AUPR; Unknown Recall@5% Known FUR; Evidence
acquisition rate/cost; True Unknown acquisition rate. Paired
group/temporal-block bootstrap.

Deployable-gain PASS iff ALL:

- **D1**: pooled FURK(D1) ≤ FURK(D0) − 0.02 AND FURK improves in
  ≥ 2/3 rotations AND no rotation worsens by > 0.02.
- **D2**: pooled paired bootstrap 95% CI upper bound of
  (FURK(D1) − FURK(D0)) < 0.
- **D3**: pooled mean Unknown AUROC loss ≤ 0.01 AND no rotation loss
  > 0.03.
- **D4**: pooled mean Unknown Recall@5% Known FUR loss ≤ 0.03 AND no
  rotation loss > 0.05.

## 11. Decision matrix (preregistered, exhaustive)

- **GO**: adequacy PASS + potential PASS + specificity PASS +
  deployable PASS.
- **GO_SIGNAL_EXISTS_ROUTER_LIMITED**: adequacy PASS + potential PASS +
  specificity PASS + deployable FAIL + material frozen-router headroom,
  where material headroom = frozen P6 Evidence Recovery Rate ≤ 0.85 in
  ≥ 2/3 rotations (computed from frozen stored P6 predictions; no new
  training).
- **GATE_INVALID_OSR_INADEQUATE**: adequacy FAIL. Evidence may NOT be
  declared failed.
- **NO_GO_CURRENT_EVIDENCE_CONTRACT**: adequacy PASS AND (potential
  FAIL OR specificity FAIL) AND the §12 safeguard stage does not
  contradict. NO-GO requires substantially more evidence than failure
  of the primary detector alone (a deployable-only failure is
  ROUTER_LIMITED, never NO-GO).
- **METHOD_DEPENDENT_REVIEW**: every remaining combination, and every
  safeguard contradiction.

## 12. Conditional NO-GO safeguard stage (preregistered, bounded)

Runs ONLY if OSR_ADEQUACY=PASS and the primary result would otherwise
justify NO_GO_CURRENT_EVIDENCE_CONTRACT. At most two safeguards:

- **A. Raw normalized concat encoding**: raw concatenated Basic/Temporal/
  Relation features with mask indicators, per-block standardization
  fitted on TRAIN Known only, same MLP recipe and training config,
  central seed 20260817 only, all three rotations.

- **B. Dirichlet / evidential-uncertainty confirmation (EDL, fixed)**
  — ONE preregistered evidential deep-learning model. Central seed
  20260817 only, all three rotations.

  Frozen EDL implementation (exact, fixed before evaluation):
  - Trunk: identical typed-block masked-fusion block encoders and
    fusion (§4), sharing the exact architecture; the Known head is
    replaced by a Dirichlet head: evidence e = softplus(Linear(128,6)) + 1,
    Dirichlet parameters alpha = e (>= 1 by construction).
  - Loss: Type II Maximum Likelihood (Sensoy et al. 2018)
    L = sum_k y_k (psi(S) - psi(alpha_k)), S = sum_k alpha_k, plus a
    FIXED KL term to the uniform Dirichlet with constant lambda = 0.1
    (no annealing): KL[Dir(alpha_tilde) || Dir(1)] with
    alpha_tilde = y + (1 - y) * alpha.
  - Optimizer: AdamW, lr = 3e-4, weight_decay = 1e-4; max 20 epochs;
    Known-only early stopping patience = 3 on the same early-stop
    slice (monitor validation EDL loss).
  - Training data: the same TRAIN sample rule as the primary encoder;
    Known-only. True Unknown NEVER enters fitting or calibration.
  - EDL novelty score: 1 - max_k(alpha_k / S) (top-class belief mass;
    higher = more novel). S is recorded descriptively.
  - Calibration: Known-only 5% false-Unknown, policy-conditioned (§6).
  - Confirmatory analyses: re-evaluate Questions B and C with the EDL
    score, where margin gain is replaced by belief gain
    (belief(state) - belief(Basic)) and true-class Mahalanobis
    distance is replaced by true-class belief; same thresholds as
    §8/§9.
  - Sanity tests (preregistered, before any confirmation metric):
    (i) alpha >= 1 on a synthetic forward pass; (ii) training loss
    decreases over a few steps on synthetic data; (iii) EDL belief
    score separates synthetic inliers from outliers; (iv) no Unknown
    row in the fit set. If ANY sanity test fails:
    CONFIRMATORY_EDL_STATUS=IMPLEMENTATION_INVALID — the safeguard is
    skipped (does not block the gate; the NO-GO decision then rests on
    safeguard A and the primary analyses). No tuning beyond this fixed
    recipe; no replacement with another detector.

Both safeguards re-evaluate ONLY Questions B and C offline analyses
with their own representation/score. They are false-NO-GO safeguards,
NOT a pool from which to pick the best result. If either safeguard
yields a materially contradictory strong positive on the criterion
that failed in the primary (i.e., its own PASS criteria are met):
decision = METHOD_DEPENDENT_REVIEW instead of NO-GO. No further
methods may be added.

## 13. Statistical rules

- Primary paired effects: ≥ 1000 group-atomic AND temporal-block-aware
  bootstrap replicates; pooled over 9 cells (3 rotations × 3 seeds).
- Report per-seed, per-rotation, and pooled; effect sizes; 95% CIs;
  raw counts where relevant.
- Statistical significance alone never decides a gate; effect
  magnitudes and preregistered thresholds decide.

## 14. Claim boundary

This Gate determines whether the CURRENT strict-past T/R Evidence
contract has sufficient open-world recoverability value to justify
expensive Model-B development. A NO-GO is a project research decision,
not a mathematical proof that no possible model could ever use
Evidence. A GATE_INVALID_OSR_INADEQUATE says nothing about Evidence;
it only says the chosen OSR is not adequate to judge it.

## 15. Execution lock and artifact policy

- This protocol is FROZEN before evaluation. Its sha256 is recorded in
  the preregistration JSON and in the result-report header.
- Formal evaluation may begin only after the local
  preregistration/implementation commit exists (protocol +
  preregistration JSON + runner + tests). From that commit, scientific
  semantics are locked.
- After the first formal metric is visible, only pure implementation
  bugfixes with unchanged scientific semantics are allowed and must be
  logged; any scientific change requires STOP_NEEDS_REVIEW.
- All large artifacts (embeddings, features, model checkpoints,
  bootstrap outputs, statuses, logs) stay Git-external under
  `processed/dataset_v4_nf3_ton_v1/strong_neural_osr_evidence_gate_v1/`.
- Scientific result artifacts remain uncommitted/unpushed until a
  later researcher-authorized validation task.
- No FINAL_TEST. No Qwen / Model B / RL / continual / purification.
- No push without explicit researcher authorization.
