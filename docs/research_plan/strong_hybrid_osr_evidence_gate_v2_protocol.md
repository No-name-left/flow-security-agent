# Strong Hybrid OSR Evidence Recoverability Gate V2 — Protocol

Status: FROZEN_BEFORE_EVALUATION (sha256 recorded in the preregistration JSON)
Date: 2026-08-18
Schema: STRONG_HYBRID_OSR_EVIDENCE_GATE_V2_PROTOCOL_V1
Predecessor: Strong Neural OSR Evidence Gate V1 (frozen, immutable:
GATE_INVALID_OSR_INADEQUATE, EVIDENCE_SCIENTIFIC_STATUS=NOT_JUDGED).

## 0. Motivation and authorization

V1 diagnostic established: the neural Known classification head lagged
the frozen RF family in 9/9 cells; the failing cells plateaued; V1
A2/A3/A4 passed (useful neural open-set geometry). V2 therefore
isolates the Evidence question from the weaker neural closed-set
classifier by building a HYBRID system: the frozen RF family provides
Known-class prediction; the V1 neural typed-block representation +
Mahalanobis geometry provides novelty. This is a new prospective
experiment; V1 is not reinterpreted or overwritten.

NOT authorized here: more epochs alone, SupCon-weight tuning, multiple
neural architectures, detector shopping, any post-result tuning.

## 1. Hybrid system

For observation state s ∈ {B, BT, BR, BTR}:

```text
HYBRID_CLASS(s)   = frozen RF family prediction for state s
HYBRID_NOVELTY(s) = neural Mahalanobis novelty score for state s
                    (V1 architecture: typed-block masked fusion; class
                     means + one tied pooled LedoitWolf covariance per
                     state, fitted on OSR_TRAIN_FIT Known embeddings;
                     score = min Mahalanobis distance to any Known
                     class mean; higher = more novel)
```

- RF family: the exact frozen B/BT/BR/BTR classifier family and its
  stored per-policy outputs. D0 uses the frozen stored
  `pred_P0_BASIC_DIRECT` (Basic state). D1 uses the frozen stored
  `pred_P6_UTILITY_TYPED` (prediction of the classifier matching the
  Evidence state selected by the frozen P6 router). No RF recreation,
  retraining, or tuning based on V2 results. If exact stored outputs
  are unavailable for a needed quantity: STOP_NEEDS_REVIEW.
- Neural component: identical V1 training semantics (same 150,000-row
  TRAIN pool, same group-safe 90/10 FIT/EARLY_STOP split, same
  features/transforms, same multi-state exposure schedule, CE +
  0.10·SupCon with the linear head as a TRAINING AUXILIARY ONLY, AdamW
  3e-4/1e-4, batch 1024, seed, max 20 epochs, patience-3 Known-only
  early stopping). The linear head is NOT the deployed Known
  classifier.
- Neural embeddings, geometry, and the deployed novelty scores are
  computed from the V1-frozen representation; per-state geometry is
  fitted on OSR_TRAIN_FIT Known embeddings (implementation
  clarification carried over from V1).

## 2. Frozen populations

Rotations Credential / Recon_Scanning / Web_Injection; seeds
20260817/20260818/20260819; states B/BT/BR/BTR; TRAIN pool 150,000
(6 × 25,000) Known rows per cell with the V1-frozen deterministic
group-safe 90/10 FIT/EARLY_STOP split and the V1-preregistered per-cell
counts; VAL_CALIB Known (split_role==0, is_unknown==0) for calibration;
VAL_GATE_EVAL (split_role==1) for evaluation; frozen V1 Recoverable
identities (stored recoverable column); frozen P6 UTILITY_TYPED router
(stored actions; never retrained); FINAL_TEST forbidden; True Unknown
excluded from representation training, normalization, early stopping,
geometry fitting, calibration, and model selection. No cross-seed
supplementation; no new data materialization.

## 3. Determinism strengthening

Before formal evaluation, set and record: fixed Python hash seed;
seeded numpy Generators only (no global RNG); torch.manual_seed +
torch.cuda.manual_seed_all; torch.backends.cudnn.deterministic=True;
torch.backends.cudnn.benchmark=False; deterministic state-exposure
schedule (cell_rng, V1-frozen); no DataLoader workers. If any required
operation cannot be made strictly deterministic, document the source;
never silently change the scientific model. Persist per cell: trained
weights, embeddings, predictions, thresholds, per-cell metrics,
training curves.

## 4. V2 OSR adequacy (H1–H4)

HYBRID_OSR_ADEQUACY=PASS iff H1 AND H2 AND H3 AND H4.

- **H1 RF reproduction**: Known Macro-F1 computed from the frozen
  stored P0 and P6 predictions on VAL_GATE_EVAL Known must reproduce
  the frozen historical per-cell values (authority: the frozen V1
  open-world result JSONs) within tolerance ±1e-3. Material failure →
  GATE_INVALID_IMPLEMENTATION.
- **H2 Basic Unknown AUROC** (frozen V1 A2 intent/thresholds): pooled
  mean ≥ frozen RF Basic pooled − 0.02 AND no rotation more than 0.05
  below that rotation's frozen RF Basic AUROC (frozen RF Basic values
  computed from the frozen stored P0 scores — deterministic, no
  tuning).
- **H3 Basic Unknown AUPR / operating recall** (frozen V1 A3 intent):
  pooled Recall@5% Known FUR ≥ frozen RF Basic pooled − 0.03 AND no
  rotation more than 0.05 below; AND pooled Unknown AUPR ≥ frozen RF
  Basic pooled AUPR − 0.03 AND no rotation more than 0.05 below.
- **H4 dedicated geometry value** (frozen V1 A4 intent/thresholds):
  pooled paired bootstrap mean (Mahalanobis AUROC − same-encoder Deep
  MSP AUROC) ≥ +0.010, positive in ≥ 2/3 rotations, pooled 95% CI
  lower bound > −0.02.

Adequacy failure (H2–H4) → GATE_INVALID_OSR_INADEQUATE; Evidence
remains NOT_JUDGED.

## 5. Primary deployable comparison

- D0_BASIC: RF Basic prediction (stored P0) + neural Basic Mahalanobis
  novelty.
- D1_P6_SELECTIVE: exact frozen P6 policy; for the Evidence state
  selected by P6, RF prediction from that same observation state
  (stored P6 preds) + neural Mahalanobis novelty from that same
  observation state.
- Descriptive only: D2_ALWAYS_FULL, D3_RANDOM_COST_MATCHED (same
  policy state maps as V1).
- Calibration: policy-conditioned, Known-only, 5% Known false-Unknown
  rate (95th percentile), tie semantics `rejected = score >=
  threshold`. True Unknown never calibrates.

Primary metrics (per rotation/seed/pooled): FURK; Recoverable-Known
accepted-and-correct rate; Known Macro-F1; Known false-Unknown rate;
Unknown AUROC; Unknown AUPR; Unknown Recall@5% Known FUR; Evidence
acquisition rate/cost; True Unknown acquisition rate.

DEPLOYABLE_EVIDENCE_GAIN=PASS iff ALL (practical thresholds carried
over from the V1 preregistration, not weakened):

1. pooled FURK(D1) ≤ FURK(D0) − 0.02 AND FURK improves in ≥ 2/3
   rotations AND no rotation worsens > +0.02;
2. pooled paired group/temporal-block bootstrap 95% CI upper bound of
   (FURK(D1) − FURK(D0)) < 0;
3. pooled mean Unknown AUROC loss ≤ 0.01 AND no rotation loss > 0.03;
4. pooled mean Unknown Recall@5% Known FUR loss ≤ 0.03 AND no rotation
   loss > 0.05;
5. pooled mean Known Macro-F1 loss ≤ 0.01 AND no rotation loss > 0.02.

## 6. Recovery / specificity analysis (offline, oracle, never deployed)

For frozen Recoverable Known and each legal state s ∈ {BT, BR, BTR}:
RECOVERED(s) = RF_s prediction correct AND neural-Mahal(s) accepted
(below the Known-only 5%-FUR threshold fitted for state s on VAL_CALIB
Known). Best-legal oracle = max over legal states (GT-guided,
analysis-only).

- EVIDENCE_RECOVERY_SIGNAL=PASS iff: pooled best-legal accept-correct
  rate ≥ 0.60 AND ≥ 2/3 rotations have rate > 0.55 AND pooled paired
  group/temporal-block bootstrap 95% CI lower bound of
  (best-legal rate − Basic accept-correct rate) > 0.
- For True Unknown: most Known-ward legal Evidence state =
  max over legal states of the Known-ward gain
  (KNOWNNESS(Basic) − KNOWNNESS(s), KNOWNNESS = min Mahalanobis
  distance). Conservative stress test (V1 philosophy preserved).
- EVIDENCE_SPECIFICITY=PASS iff (V1 C1–C4 structure): pooled mean gap
  (Recoverable-Known best-legal gain − True-Unknown most-Known-ward
  gain) > 0 with bootstrap 95% CI lower bound > 0; pooled median gap
  > 0; pooled mean TU gain ≤ 0.50 × pooled mean RK gain (when RK gain
  > 0); ≥ 2/3 rotations have mean gap > 0.

## 7. Decision matrix (preregistered, exhaustive)

- **GO**: adequacy PASS + recovery PASS + specificity PASS +
  deployable PASS.
- **GO_SIGNAL_EXISTS_ROUTER_LIMITED**: adequacy PASS + recovery PASS +
  specificity PASS + deployable FAIL + material frozen-router headroom
  (frozen P6 Evidence Recovery Rate ≤ 0.85 in ≥ 2/3 rotations, from
  stored P6 predictions).
- **GATE_INVALID_IMPLEMENTATION**: H1 fails materially.
- **GATE_INVALID_OSR_INADEQUATE**: H2–H4 fail; Evidence NOT_JUDGED.
- **NO_GO_CURRENT_EVIDENCE_CONTRACT**: adequacy PASS AND (recovery
  FAIL OR specificity FAIL) AND the conditional safeguards do not
  contradict. A practical NO-GO may only be issued under the strict
  false-negative protection rules below.
- **METHOD_DEPENDENT_REVIEW**: all remaining combinations and every
  safeguard contradiction.

## 8. Conditional NO-GO safeguards (bounded, V1-frozen recipes)

Run ONLY if a valid primary result would otherwise produce NO-GO:

- A. raw normalized concat encoding, central seed 20260817, all three
  rotations (V1 recipe);
- B. fixed Dirichlet/evidential uncertainty confirmation (V1-frozen
  EDL recipe: identical trunk, Dirichlet head alpha = softplus(z)+1,
  Type-II ML loss + fixed KL λ=0.1, AdamW 3e-4/1e-4, 20 epochs,
  patience 3, Known-only; belief score 1 − max(α/S)), central seed
  20260817, all three rotations; sanity tests as in V1 §12;
  CONFIRMATORY_EDL_STATUS=IMPLEMENTATION_INVALID if sanity fails.

Both re-evaluate ONLY the recovery/specificity offline analyses. A
materially contradictory strong positive (safeguard's own PASS
criteria met on the failed criterion) → METHOD_DEPENDENT_REVIEW
instead of NO-GO. No further methods.

## 9. Statistical rules

≥ 1000 group-atomic AND temporal-block-aware paired bootstrap
replicates, pooled over 9 cells; report per-seed, per-rotation,
pooled, effect sizes, 95% CIs, raw counts. Statistical significance
alone never decides.

## 10. Claim boundary

This Gate determines whether the CURRENT strict-past T/R Evidence
contract has sufficient open-world recoverability value under a
strong-hybrid OSR to justify expensive Model-B development. NO-GO is a
project research decision, not a proof that no model could use
Evidence. GATE_INVALID_* says nothing about Evidence.

## 11. Execution lock and artifact policy

- Freeze before metrics: protocol finalized + sha256 recorded; a
  preregistration JSON committed BEFORE any evaluation metric; tool +
  tests asserting implementation == preregistration; only
  non-reportable smoke/leakage/reproduction checks run before the
  freeze commit. Scientific semantics locked from that commit.
- After the first formal metric: only pure implementation bugfixes
  with unchanged scientific semantics, logged; any scientific change →
  STOP_NEEDS_REVIEW.
- Large artifacts (weights, embeddings, predictions, statuses, logs,
  curves) under a separate Git-external V2 directory; V1 artifacts
  untouched. Formal result JSON/MD under reports/research_audit/,
  uncommitted until researcher validation. No push.

## 12. Hard boundaries

FINAL_TEST forbidden. No Qwen/Model B, no DeepSeek research calls, no
RL, no continual learning, no router retraining, no Evidence-contract
changes, no additional detector search, no post-result
threshold/model tuning.
