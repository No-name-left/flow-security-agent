# Recoverability Information Sufficiency Gate V1 — Protocol (FROZEN)

```
FREEZE_RECORD
STATUS=FROZEN
FROZEN_DATE=2026-08-19
FREEZE_TASK=FREEZE_AND_RUN_RECOVERABILITY_INFORMATION_SUFFICIENCY_GATE_V1
RESEARCHER_REVIEW_COMPLETE=YES
FINAL_DECISIONS_APPLIED=YES (rotation consistency on BOTH REAL-BASIC and
  REAL-SHUFFLED; retention point-estimate rule with reporting-only
  bootstrap uncertainty; absolute-AUROC rule removed;
  GENERIC_EVIDENCE_SHORTCUT_DOMINANT defined directly; exhaustive and
  mutually exclusive decision tree)
PREFREEZE_IDENTITY_CHECK=PASS (12/12: metrics not viewed; tree exhaustive
  and mutually exclusive; synthetic dry-run preserved; no absolute-AUROC
  threshold; REAL support requires material increment over BOTH BASIC and
  SHUFFLED; pooled rule point >= +0.02 AND CI lower > 0; strong family
  support >= 2/3 families; rotation consistency on both comparisons;
  shortcut defined by material SHUFFLED-over-BASIC gain; retention
  min(median ret_b, median ret_s) < 0.5; probe B target = frozen
  post-Evidence Known correctness; row AND group zero-overlap mandatory)
DECISION_TREE_VERIFICATION=tools/verify_recoverability_gate_decision_tree.py
  (synthetic-only dry-run: 1,024 hypothetical metric combinations, exactly
  one outcome per combination, all six outcomes reachable, zero
  definition-consistency violations, no absolute-AUROC condition)
CLAIRIFICATIONS_PINNED_BEFORE_FREEZE=YES (TRAIN population for probe B P6
  reproduction = full 175,000-row TRAIN partition, budget
  floor(0.15 x 175,000) = 26,250; bootstrap class-coverage guard for
  AUROC replicates)
SECTION_16_NOTES=FROZEN DESIGN NOTES (not unresolved blockers)
```

No gate metric has been viewed. This protocol is frozen; no scientific rule
may change after this point. Prior results are untouched (Strong Hybrid OSR
V2 decision `METHOD_DEPENDENT_REVIEW`; Method-Dependence Diagnostic V1
primary `READOUT_DOMINANT_PRIMARY`).

## 1. Purpose and scope

The final bounded feasibility gate before Model B / Qwen / RL / continual
learning is an Evidence-conditioned open-world recovery method. Before any
recovery-aware interface is built, this gate separates **where the failure
would live**:

1. **Information insufficiency in the legal B/T/R observables** — the
   strict-past runtime-legal Evidence does not contain enough signal to
   separate Recoverable Known (RK) from True Unknown (TU) at all.
2. **Representation / Evidence-processing limitation** — the signal exists
   in the legal observables but the frozen processing chain (RF / neural /
   EDL / Mahalanobis) does not expose it.
3. **Open-world learning / transfer limitation** — the signal exists and is
   processable, but it cannot be learned under an open-world-compatible
   condition (Known-only training, never-seen Unknown at test).

Scope: diagnostic only, central seed 20260817 × 3 whole-class rotations
(Credential / Recon_Scanning / Web_Injection). No FINAL_TEST. No new
detector. No deployable method is produced by this gate.

## 2. Frozen populations and partitions (verified by feasibility audit)

All rows are frozen master-split rows (`core_gate_v1/gate_seed_20260817_targets.parquet`
and `open_world_recoverability_gate_v1/owg_v1_seed_20260817_rotation_*_eval.parquet`).

| Partition | Rows | Definition |
|---|---|---|
| TRAIN (partition 0) | 175,000 | frozen master TRAIN rows; per rotation the TRAIN pool is the 135,000 rows whose label is in the rotation's 6 Known classes |
| VALIDATION (partition 1) | 56,000 | all eval rows; identical row set in every rotation's eval parquet (rotation changes only the `is_unknown` mask) |
| role 0 (VAL_CALIB) | 29,931–31,435 per rotation | group-atomic calib subset of VALIDATION; per rotation contains 3,279–4,668 TU rows |
| role 1 (VAL_GATE_EVAL) | 24,565–26,069 per rotation | group-atomic eval subset; per rotation contains 3,332–4,721 TU rows; RK counts 435–1,633 |

Central-seed populations (frozen):

| Rotation | RK role0 | RK role1 | TU role0 | TU role1 |
|---|---|---|---|---|
| Credential | 1,292 | 1,396 | 4,426 | 3,574 |
| Recon_Scanning | 552 | 453 | 3,404 | 4,596 |
| Web_Injection | 821 | 1,053 | 4,078 | 3,922 |

Frozen Recoverable-Known definition (OWG gate, unchanged): `recoverable =
(pred_B != label) & (pred_BT == label | pred_BR == label | pred_BTR == label)`
computed by the frozen OWG chain on VALIDATION rows — i.e., RK = Basic-wrong
acquired-Known rows that a legal Evidence state recovers. Frozen TU: the
rotation's `is_unknown` mask (8,000 rows per rotation across both roles).
Frozen Evidence: strict-past T/R history with the frozen log1p transforms.

### Cross-rotation disjointness audit (feasibility audit, completed)

- All three rotations' eval parquets draw from the **same** 56,000-row
  VALIDATION pool; only the class-wise `is_unknown` mask differs.
- Therefore **rotation masks alone do not define disjoint dev/test sets**:
  a row that is TU in rotation C appears as Known (and possibly RK) in
  rotations A and B. Any construction that trains on rotation A/B eval rows
  and evaluates on rotation C eval rows without a within-VALIDATION split
  would leak (same rows, contradictory labels).
- Verified group atomicity: 0 of 11,459 master groups straddle partitions
  0/1 (seed 20260817); 0 of 2,256 eval groups straddle role 0/1 (each
  rotation). TRAIN-partition rows never appear in any eval parquet.
- **Leakage-safe construction (this protocol):** dev/train always uses
  TRAIN-partition rows (probe B) or role-0 rows (probe A); test always
  uses role-1 rows. Dev and test are fully row- and group-disjoint in
  every fold. Feasible — no STOP_NEEDS_REVIEW condition triggered.

### Leakage identity checks (frozen, mandatory before any gate metric)

Zero-overlap is verified on **both** identities, never on rotation-specific
record IDs alone:

- **Row identity:** the underlying frozen master-split row ID (identical
  across rotations' eval parquets; TRAIN-partition IDs are disjoint from
  VALIDATION-partition IDs by the master split).
- **Group identity:** the frozen group ID column.

Mandatory checks (each must count 0 overlapping rows AND 0 overlapping
groups, otherwise the gate does not proceed):

1. Probe A dev (role-0 rows of rotations A and B) vs Probe A test (role-1
   rows of rotation C), per fold.
2. Probe B train (TRAIN-partition rows) vs Probe B test (role-1 rows of
   rotation C), per fold; and Probe B train vs Probe B threshold rows
   (role-0 Known rows of rotation C).
3. Probe A dev across rotations uses the SAME physical VALIDATION rows with
   per-rotation labels — the documented dual-labeling design of probe A
   (feasibility audit). Precondition verified: the frozen role-0/role-1
   split is identical across rotations (same physical split), so A-dev and
   B-dev row sets coincide by construction; the overlap that must be zero
   is dev-vs-test (check 1).
4. TRAIN vs VALIDATION (the master split's own guarantee, re-verified).

## 3. Frozen components (all read-only; nothing retrained except noted replays)

| Component | Source | Use |
|---|---|---|
| RF Known family B/BT/BR/BTR | `open_world_recoverability_gate_v1/models/owg_v1_seed_20260817_rotation_{rot}_models.pkl` (frozen; `predict_proba` available) | RF pre/post state features |
| Utility selectors T/R/TR | same pkl, `selectors` key (frozen RandomForestRegressors, config n_estimators=200, max_depth=12, min_samples_leaf=20, max_features=sqrt, random_state=seed) | P6 policy reproduction for TRAIN rows (see §4) |
| Primary neural encoder | `strong_hybrid_osr_evidence_gate_v2/cells/20260817_{rot}/model.pt` (frozen, eval mode) | Mahalanobis per-state scores |
| Mahalanobis geometry | per-state LedoitWolf on TRAIN FIT Known h, frozen recipe `fit_osr_geometry` | `validation_v2/primary_replay/{rot}_maha.npz` already contains per-state float64 scores for all 56k eval rows — frozen source for eval-row Mahalanobis features; TRAIN-row scores recomputed with the identical frozen recipe (identity check below) |
| B_EDL head | NOT persisted → replayed per rotation with the exact frozen V2 recipe (`train_encoder_v2(use_edl=True)`, rng offset `RNG_BASE+200`, central seed) — identical to the V2 validation replay | EDL per-state alpha for eval and TRAIN rows; identity check vs `validation_v2/safeguards/B_{rot}_scores.npz` (novelty = 1 − max(α)/S per state) |
| P6 actions | stored per eval row (`action_P6_UTILITY_TYPED`); TRAIN-row actions reproduced by the frozen policy machinery (§4) with a mandatory reproduction check | acquired Evidence type/mask per row |
| Eval features | `assemble_cell` frozen construction (B=47 basic, T block 47:63, R block 63:81, strict-past transforms) | RAW_LEGAL view |

All forward passes on frozen models; the only "training" performed by this
gate is the B_EDL replay (identical frozen recipe, verification-locked) and
the two probes' own fits. No frozen model is modified, tuned, or retrained
for selection.

## 4. Frozen P6 policy reproduction (TRAIN rows only)

Probe B needs the acquired Evidence state for TRAIN rows; it is not stored.
Reproduction (all frozen):

1. Selector features on TRAIN rows: `rotation_selector_features(basic_train,
   pred_b, proba_b, availability=1, known)` where `pred_b`/`proba_b` come
   from the frozen B RF on TRAIN rows (in-sample, exactly as the frozen OWG
   chain's own selector-training features).
2. `u_t/u_r/u_tr` = frozen selectors' predictions.
3. `typed_policy_actions(u_t, u_r, u_tr, budget, order)` with the frozen
   greedy typed rule and `budget = floor(0.15 × n)` (population-relative
   budget semantics; costs T=1, R=1, TR=2; priority T,R,TR; fallback T,R).
   **TRAIN population (frozen clarification):** probe B fold C reproduces
   TRAIN-row actions over the full 175,000-row TRAIN partition — the
   probe's training population — with `budget = floor(0.15 × 175,000) =
   26,250` units and `order = ascending TRAIN row index`, mirroring the
   eval-row rule of running the policy over the population it serves.
4. **Verification (mandatory, before any gate metric):** reproduce eval-row
   actions from the frozen selectors with the frozen per-population budgets
   (`budget_calib = floor(0.15 × n_role0)`, `budget_eval = floor(0.15 ×
   n_role1)`) and require 0 mismatches vs stored `action_P6_UTILITY_TYPED`.
   Only then apply the identical code path to TRAIN rows.

## 5. Feature views (no GT-derived input features)

### View 1 — RAW_LEGAL (runtime-legal observables only), 83 dims

`concat(basic[47], T_block[16], R_block[18], m_t, m_r)` where T/R blocks are
the frozen strict-past legal Evidence values and `m_t, m_r ∈ {0,1}` are the
frozen state-availability masks (1 iff the acquired state includes that
type). At state B both blocks are the neutral all-zero vector and masks are
0 — exactly what the frozen models receive at B.

### View 2 — STATE_TRANSITION (frozen pre/post/delta signals), 26 dims

Per row at pre = B and post = acquired state (frozen P6 action):

- RF: top-1 probability, top1−top2 margin, argmax class code (pre 3, post 3);
  deltas Δp_top, Δmargin (2); top-1 stability indicator (1).
- EDL (replayed B_EDL alpha): Dirichlet strength S=Σα, top-class
  concentration p_top=max(α)/S, second-class p_2nd, argmax code (pre 4,
  post 4); deltas ΔS, Δp_top, Δp_2nd (3).
- Mahalanobis: pre score, post score, delta (3).
- Evidence type: one-hot (T, R, TR) (3).

Excluded: ground-truth class, Unknown truth, Recoverable-Known truth,
future information, raw labels, FINAL_TEST information, and any label- or
group-derived input feature.

### View × probe assignment (frozen)

- Probe A runs on BOTH views (needed for the bottleneck rule, §10.3).
- Probe B runs on RAW_LEGAL only. The decision tree (§11) needs only the
  RAW_LEGAL transfer result; probe-B STATE_TRANSITION is not computed.

## 6. Probes

Both probes are trained ONCE per (fold, family, view) on REAL-condition
features and evaluated by forward scoring under every condition
(§7). The two probes differ only in training supervision and folds.

### Probe A — DIAGNOSTIC_SEPARABILITY (diagnostic only, not deployable)

- Supervision: RK-vs-TU binary labels (TU positive) from the frozen rotation
  masks; RK/TU rows only (non-recoverable Known rows excluded from dev and
  test).
- Fold for target rotation C (A, B = the two other rotations):
  - dev = role-0 rows of rotation A (labels from A's mask, features from
    A's frozen chain) ∪ role-0 rows of rotation B (labels from B's mask,
    features from B's frozen chain). ~10k labeled rows per fold.
  - test = role-1 rows of rotation C (labels from C's mask, features from
    C's frozen chain).
- **Interpretation (frozen, see also §12):** probe A is a diagnostic
  separability probe, not a deployable method. High BASIC-only RK-vs-TU
  AUROC does NOT support Evidence sufficiency. Probe A supports the
  Evidence hypothesis only through incremental target-matched REAL
  Evidence beyond BASIC AND beyond SHUFFLED (§9, §10). Diagnostic TU
  supervision (role-0 Unknown truth) is used only for this diagnostic
  probe and is never described as deployable open-world learning and never
  reused as training or calibration for any deployable method.

### Probe B — KNOWN_ONLY_TRANSFER (open-world-compatible, RAW_LEGAL only)

- **Target (frozen, exact):** per Known TRAIN example,
  `Y_correct_post = 1` iff the frozen post-Evidence Known prediction
  (`pred_{state}` of the frozen RF at the acquired state) equals the
  Known ground-truth class; `Y_correct_post = 0` otherwise. Ground truth
  is used only as TRAIN supervision on Known TRAIN rows, never as an input
  feature.
- **Training set:** the 175,000 TRAIN-partition Known rows with
  rotation-C-conditioned features (per fold C, the frozen chain of
  rotation C, including the reproduced P6 actions of §4). TU examples are
  never used for fitting and never for threshold selection.
- Threshold: per fold, 95th percentile of the probe's score over rotation
  C's role-0 Known rows only (Known-only calibration).
- Test: role-1 rows of rotation C (RK vs TU), exactly as probe A.
- Overall Known correctness (e.g., TRAIN-fit accuracy, role-0 Known
  calibration accuracy) may be reported as a diagnostic, but the primary
  recovery evaluation is separately computed on **frozen RK / Basic-wrong
  acquired Known vs held-out TU** rows only (role-1 RK + role-1 TU), so
  easy Known samples (already-correct-at-Basic rows) cannot dominate the
  conclusion.
- Purpose: does recovery information survive when TU truth is never seen
  in training or threshold selection?

## 7. Controls (diagnostic only, forward scoring only)

Both probes are scored on the test rows under four conditions; no control
ever enters training and no model is retrained on a control:

| Condition | Construction (frozen) |
|---|---|
| REAL | acquired-state features exactly as stored/frozen |
| BASIC | state-B features (T/R neutral, masks 0); STATE_TRANSITION at BASIC sets post = pre (deltas 0, stability 1, evidence flags 0) |
| SHUFFLED | T/R blocks (47:63, 63:81) permuted within (RK rows, TU rows) separately, `rng = cell_rng(20260817, rot, RNG_BASE+400)` — identical to the completed diagnostic's construction; STATE_TRANSITION recomputed from frozen components on the shuffled features |
| NULL_PRESENT | T/R blocks set to the neutral all-zero vector with masks present (= 1 for the acquired types) — identical to the diagnostic's NULL-PRESENT |

The central comparison is NOT classification performance alone: it is
whether target-matched REAL Evidence carries incremental, generalizable
recovery information beyond (a) Basic-only (REAL vs BASIC), (b) generic
Evidence presence (REAL vs NULL_PRESENT), and (c) generic Evidence
distribution (REAL vs SHUFFLED, SHUFFLED vs BASIC).

## 8. Model families (pre-frozen; no search, no selection)

Three families with materially different inductive biases:

1. **RF** — `RandomForestClassifier(n_estimators=80, max_depth=20,
   min_samples_leaf=2, class_weight="balanced_subsample", n_jobs=-1,
   random_state=20260817)` — the frozen OWG Known-estimator config.
2. **LR** — L2-regularized logistic regression (`C=1.0`, lbfgs,
   `max_iter=1000`), features standardized with statistics fitted on dev
   (probe A) / TRAIN (probe B) rows only.
3. **MLP** — fixed 2-layer feed-forward (input → 64 ReLU → 1), AdamW
   3e-4 / weight decay 1e-4, batch 1024, max 20 epochs, early stop
   patience 3 (on a deterministic 90/10 split of the fit rows), mirrors the
   repository's frozen optimizer conventions; `torch.manual_seed(20260817)`
   and seeded Generators; features standardized as for LR.

Fits: probe A 3 families × 2 views × 3 folds = 18; probe B 3 families × 1
view × 3 folds = 9; 27 fits total. No hyperparameter search; no model
comparison for selection; no best-model selection; all families are
reported.

## 9. Metrics, materiality floor, and bootstrap

### 9.1 Primary and supporting metrics (frozen)

- **PRIMARY: pooled AUROC** of RK-vs-TU scoring (TU positive) on the test
  rows. Every scientific claim in §11 is decided on pooled AUROC
  increments.
- Supporting (reported, never substitutable for a failed primary
  criterion): **AUPR** (TU positive) and **Recall@5% FUR** (threshold =
  95th percentile of Known-row scores; probe A: RK rows of the test set,
  same-population convention; probe B: role-0 Known rows, Known-only
  calibration). Supporting metrics cannot rescue any claim whose primary
  AUROC criterion failed.

### 9.2 Materiality floor (frozen, preregistered project threshold)

The evaluation populations are large, so a statistically nonzero increment
alone is not evidence of materially useful Evidence. Before any metric:

- **material AUROC increment = +0.02 absolute AUROC**, applied to
  `REAL − BASIC`, `REAL − SHUFFLED`, and (for the shortcut rule) `SHUFFLED − BASIC`.
- A **material increment** holds iff BOTH:
  - point estimate ≥ +0.02, AND
  - 95% bootstrap CI lower > 0.
- At the **pooled** family level this is the rule above (point ≥ +0.02 AND
  pooled CI lower > 0), unchanged. At the **per-rotation** level, material
  direction uses the point estimate ≥ +0.02 only; per-rotation CI lower > 0
  is NOT required (per-rotation CIs enter only the reverse-effect check,
  §10.2).

+0.02 is a **preregistered project feasibility threshold** (the magnitude
of incremental AUROC this program would treat as a usable recovery lever),
not a universal statistical standard. The statement of the +0.02 rationale
is part of the frozen record.

### 9.3 Bootstrap

Paired within fold (identical test rows across conditions/families/views),
pooled across the 3 folds via rotation-stratified group-atomic bootstrap:
per replicate, sample groups with replacement within each fold's test set,
recompute the per-fold metric, average across folds. 1,000 replicates,
`np.random.default_rng(162600)`, 2.5/97.5 percentiles. Per-rotation
increments and CIs use the same group-atomic procedure restricted to that
rotation's test rows.

**Class-coverage guard (frozen clarification):** an AUROC replicate
requires ≥ 2 RK rows and ≥ 2 TU rows in the sampled rows of a rotation;
if a draw lacks either, that rotation's draw is redrawn (bounded, seeded
through the same Generator). This is a pure bootstrap implementation guard
and does not change any point estimate.

**Retention-ratio uncertainty (reporting only):** for each family in
S(A,RAW) (§10.3), per-replicate ratios `inc_b(A,ST,f,r)/inc_b(A,RAW,f,r)`
and `inc_s(A,ST,f,r)/inc_s(A,RAW,f,r)` are formed on the same 1,000
replicates; 2.5/97.5 percentiles are reported per family and for the
median-over-families ratios, together with the count of dropped replicates
(denominator ≤ 0). These CIs are reported so the strength of the bottleneck
interpretation is visible; they are NOT a decision threshold (the decision
remains the point-estimate rule of §10.3).

## 10. Consistency rules (frozen; define every claim's aggregation)

Notation — probe P ∈ {A, B}, view v ∈ {RAW, ST}, family f ∈ {LR, RF, MLP};
increments `inc_b(P,v,f)` = pooled REAL − BASIC AUROC,
`inc_s(P,v,f)` = pooled REAL − SHUFFLED AUROC,
`inc_sb(P,v,f)` = pooled SHUFFLED − BASIC AUROC, with CI lower L and upper
U from §9.3. For probe B only v = RAW.

### 10.1 Family-level materiality (pooled rule, unchanged)

`mat(P,v,f)` iff `inc_b ≥ +0.02 ∧ L_b > 0` AND `inc_s ≥ +0.02 ∧ L_s > 0`
(both controls, material floor §9.2). A REAL-Evidence information claim
requires incremental target-matched value over BOTH BASIC and SHUFFLED —
never over either alone.

`n(P,v) = #{f : mat(P,v,f)}`; `S(P,v) = {f : mat(P,v,f)}` (the passing
families).

Shortcut materiality: `mat_sb(P,v,f)` iff `inc_sb ≥ +0.02 ∧ L_sb > 0`
(SHUFFLED − BASIC materiality, pooled rule); `n_sb(P,v) = #{f : mat_sb(P,v,f)}`.

### 10.2 Rotation consistency (frozen; strong claims only; BOTH comparisons)

For rotation C of probe P, view v, the rotation-level increment is the
**median over the three frozen model families** of the per-rotation point
increment:

- `inc_bC(P,v,C) = median_f` of per-rotation REAL − BASIC increments;
- `inc_sC(P,v,C) = median_f` of per-rotation REAL − SHUFFLED increments.

Rotation-level CI uppers (median over families, per comparison):

- `U_bC(P,v,C) = median_f` of per-rotation REAL − BASIC CI uppers;
- `U_sC(P,v,C) = median_f` of per-rotation REAL − SHUFFLED CI uppers.

`rotOK(P,v)` iff BOTH:

1. ≥ 2/3 held-out rotations have `inc_bC ≥ +0.02` AND `inc_sC ≥ +0.02`
   (material direction on BOTH comparisons; per-rotation point estimates;
   per-rotation CI lower NOT required), AND
2. no rotation shows a statistically clear reverse effect for EITHER
   comparison: `U_bC ≥ 0` and `U_sC ≥ 0` for every rotation C (a rotation
   with CI upper < 0 on either comparison is a clear reverse).

Shortcut rotation consistency: `rotOK_sb(P,v)` uses the same definition on
the SHUFFLED − BASIC comparison alone: ≥ 2/3 rotations with
`inc_sbC(P,v,C) = median_f` of per-rotation SHUFFLED − BASIC increments
≥ +0.02, and `U_sbC ≥ 0` (median over families of per-rotation SHUFFLED −
BASIC CI uppers) for every rotation.

### 10.3 RAW-vs-STATE retention statistic (frozen, point-estimate decision)

For each family f ∈ S(A,RAW) (guaranteed `inc_b(A,RAW,f) ≥ +0.02` and
`inc_s(A,RAW,f) ≥ +0.02` with CI lower > 0 — denominator supported by
material RAW signal):

- `ret_b(f) = inc_b(A,ST,f) / inc_b(A,RAW,f)`
- `ret_s(f) = inc_s(A,ST,f) / inc_s(A,RAW,f)`

`BOTTLENECK` holds iff `min(median_f ret_b, median_f ret_s) < 0.5` — the
matched STATE_TRANSITION view retains less than half of the
target-specific REAL-over-BASIC or REAL-over-SHUFFLED signal under the
same probe and the same folds. Decision rule is point-estimate (no
CI-based decision threshold; uncertainty reported per §9.3). The bottleneck
rule is never inferred from a single family's lower performance: it
requires RAW_LEGAL strong under §10.1–§10.2 and compares the matched views
family-by-family.

## 11. Decision matrix (frozen; exhaustive mechanical tree, no overlapping rules)

Every outcome is mechanically determined by §9–§10; no interpretation
choice remains. The tree is a partition: exactly one outcome per metric
realization; if multiple scientific interpretations were compatible with
the same metrics, the tree defaults to MIXED_OR_UNRESOLVED by construction
(the inconsistent branches are exactly the MIXED leaves). No absolute-AUROC
threshold appears anywhere in this tree — no decision depends on the
absolute level of RK-vs-TU AUROC.

Step 0 — required verification (frozen, before any metric): leakage checks
(§2), identity checks (§2), P6 action reproduction (§4), B_EDL replay
identity, Mahalanobis identity vs `validation_v2/primary_replay`, frozen
P6 FURK re-derivation vs the V2 validation record. Any failure = gate does
not proceed (report, no interpretation).

Step 1 — Probe A, RAW_LEGAL family materiality (target-specific):

- `n(A,RAW) = 0` (no family material over BOTH controls):
  - **Shortcut criterion** (all of A–D): A) target-specific support absent
    (`n(A,RAW) = 0` — the current branch); B) SHUFFLED itself materially
    improves over BASIC: `n_sb(A,RAW) ≥ 2` (SHUFFLED − BASIC ≥ +0.02 with
    pooled CI lower > 0 in ≥ 2/3 families); C) the SHUFFLED-over-BASIC
    effect is rotation-consistent: `rotOK_sb(A,RAW)`; D) REAL does not
    materially outperform SHUFFLED under the frozen target-specific
    criterion (for every family, `inc_s(A,RAW,f) < +0.02` or `L_s ≤ 0`).
    Note: D mechanically implies A (the target-specific criterion includes
    the REAL − SHUFFLED condition); both are retained verbatim.
    → **OUTCOME: GENERIC_EVIDENCE_SHORTCUT_DOMINANT** (generic
    Evidence-distribution information is useful while target matching is
    not established).
  - Shortcut criterion NOT satisfied →
    **OUTCOME: INFORMATION_SUFFICIENCY_NOT_ESTABLISHED** (the sufficiency
    concern is strong: all three materially different model families fail
    to recover target-specific REAL-over-SHUFFLED/BASIC signal, and no
    rotation-consistent SHUFFLED-over-BASIC effect is established).
    High BASIC-only or high absolute REAL AUROC must NOT change this
    outcome.
- `n(A,RAW) = 1` (only one family material) →
  **OUTCOME: MIXED_OR_UNRESOLVED** (model-family inconsistency: a result
  supported by only one model family is not a claim).
- `n(A,RAW) ≥ 2` → Step 2.

Step 2 — Probe A, RAW_LEGAL rotation consistency (BOTH comparisons):

- `¬rotOK(A,RAW)` → **OUTCOME: MIXED_OR_UNRESOLVED** (rotation
  inconsistency on REAL − BASIC or REAL − SHUFFLED; no other earlier rule
  applies).
- `rotOK(A,RAW)` → RAW_LEGAL is STRONG (target-specific REAL Evidence
  signal, family- and rotation-consistent) → Step 3.

Step 3 — Representation bottleneck (matched views, same probe/folds):

- `BOTTLENECK` (§10.3) → **OUTCOME: REPRESENTATION_BOTTLENECK_SUPPORTED**
  (legal observables contain strong target-specific signal; the frozen
  processing chain fails to retain a material portion of it).
- not BOTTLENECK → Step 4.

Step 4 — Open-world transfer (Probe B, RAW_LEGAL):

- `n(B,RAW) = 1` → **OUTCOME: MIXED_OR_UNRESOLVED** (single-family
  transfer support).
- `n(B,RAW) = 0` → **OUTCOME: INFORMATION_EXISTS_BUT_OPEN_WORLD_TRANSFER_WEAK**
  (information exists and is processable — Step 3 did not fire — but
  Known-only open-world learning/transfer is not solved: no family
  achieves material target-specific increments under Known-only training).
- `n(B,RAW) ≥ 2`:
  - `¬rotOK(B,RAW)` → **OUTCOME: MIXED_OR_UNRESOLVED** (rotation
    inconsistency in transfer).
  - `rotOK(B,RAW)` → **OUTCOME: INFORMATION_SIGNAL_SUPPORTED** (strong
    cross-Unknown-family claim: family-consistent, rotation-consistent
    material REAL-Evidence increment over both controls, in both probes).

Outcome taxonomy preserved in full: INFORMATION_SIGNAL_SUPPORTED,
INFORMATION_EXISTS_BUT_OPEN_WORLD_TRANSFER_WEAK,
REPRESENTATION_BOTTLENECK_SUPPORTED, GENERIC_EVIDENCE_SHORTCUT_DOMINANT,
INFORMATION_SUFFICIENCY_NOT_ESTABLISHED, MIXED_OR_UNRESOLVED.

## 12. Interpretation statements (frozen, non-negotiable)

1. High BASIC-only RK-vs-TU AUROC does NOT support Evidence sufficiency —
   only material REAL − BASIC AND REAL − SHUFFLED increments do.
2. GENERIC_EVIDENCE_SHORTCUT_DOMINANT is defined directly by §11 Step 1
   (A–D): generic Evidence-distribution information is useful while target
   matching is not established. High absolute RK-vs-TU separability — which
   can come entirely from BASIC — does not, by itself, indicate any
   Evidence shortcut and never changes the Step-1 outcome.
3. A representation bottleneck is NEVER inferred merely because one
   downstream model performs worse: §10.3 requires RAW_LEGAL strong and a
   sub-50% retention of the same probe's signal in the matched view.
4. Probe A is a diagnostic separability probe with diagnostic TU
   supervision (role-0 Unknown truth) and is not deployable; it must not
   be described as, or reused for, deployable open-world learning.

## 13. Model-selection safety

Everything in §2–§12 is frozen before any gate metric is computed:
populations, rotations, views, controls, families, hyperparameters/training
recipes, metrics, materiality floor, consistency rules, retention
statistic, decision tree, and thresholds. No model shopping; no tuning on
held-out rotation metrics; no re-entry after the first formal metric; no
post-result modification of thresholds, aggregation, or rules.

## 14. Execution and preregistration (for the future run — NOT this task)

The eventual execution task will: (1) freeze this protocol and write its
preregistration JSON with the protocol SHA256; (2) implement the gate tool;
(3) commit protocol + preregistration + tool **before** computing any gate
metric; (4) run with `PYTHONHASHSEED=0`, cudnn deterministic, seeded
Generators; (5) verify the mandatory identity checks (§11 Step 0); (6)
write `reports/research_audit/recoverability_information_sufficiency_gate_v1.{json,md}`.

## 15. Hard boundaries

No FINAL_TEST. No commit of this draft. No recovery-aware interface V1
(stopped task stays stopped). No new novelty detector. No P6 router
retrain, no selector retrain, no RF retrain, no encoder retrain (B_EDL
replay is the frozen recipe, not a new model). No Qwen / Model B / RL /
RLAIF / continual learning. No modification of any prior V1/V2/Diagnostic
result or decision. Probe A is a diagnostic probe and is not deployable;
its Unknown supervision is never reused for a deployable method. No push.

## 16. Revision record and residual ambiguity notes

Revision 3 (final decisions) vs Revision 2:
1. Rotation consistency now gates BOTH REAL − BASIC and REAL − SHUFFLED:
   ≥ 2/3 rotations with median-across-families per-rotation point increment
   ≥ +0.02 on both comparisons, and no rotation with a clear reverse effect
   (CI upper < 0) on either comparison (§10.2). Per-rotation CI lower is
   NOT required (resolves revision-2 note 1 and 2).
2. Retention decision rule kept as point-estimate
   `min(median ret_b, median ret_s) < 0.5`; bootstrap uncertainty for
   retention ratios added as reporting-only (§9.3, §10.3) (resolves
   revision-2 note 3).
3. Absolute-AUROC rule removed entirely: no median REAL AUROC ≥ 0.70 (or
   any other absolute threshold) determines any outcome (resolves
   revision-2 note 4).
4. GENERIC_EVIDENCE_SHORTCUT_DOMINANT defined directly by conditions A–D
   (§11 Step 1); without them, n(A,RAW) = 0 →
   INFORMATION_SUFFICIENCY_NOT_ESTABLISHED regardless of absolute AUROC.
5. Decision tree rewritten as an exhaustive, mutually exclusive partition;
   MIXED_OR_UNRESOLVED is the default leaf for every inconsistent branch.

Residual ambiguity notes (decisions taken in this revision, listed for
the record; none is expected to change):

1. **Reverse-effect check is median-based**: a rotation's "clear reverse"
   is decided on the median over the three families of the per-rotation CI
   upper (matching the median aggregation of the direction rule). A single
   family's CI upper < 0 does not by itself veto; per-family per-rotation
   CIs are reported as diagnostics.
2. **Rotation direction uses medians over all three families** (including
   non-passing families), per the researcher's wording "the median across
   the three frozen model families"; non-passing families' per-rotation
   values are reported as diagnostics.
3. **Shortcut condition D mechanically implies condition A** (the
   target-specific criterion contains the REAL − SHUFFLED condition); both
   are retained verbatim and evaluated as A ∧ B ∧ C ∧ D — the conjunction
   equals B ∧ C ∧ D given the Step-1 branch, so no outcome changes.
4. **Retention-ratio bootstrap is reporting-only**; dropped-replicate
   counts (denominator ≤ 0) are reported; no CI-based decision threshold is
   added.

No other rules are ambiguous: every branch of §11 is mechanically
determined by preregistered quantities, and the logical dry-run (protocol
addendum) verified that every branch yields exactly one outcome.
