# Evidence Processing / Method Dependence Diagnostic V1 — Protocol

Status: FROZEN_BEFORE_EVALUATION (sha256 recorded in the preregistration JSON)
Date: 2026-08-18
Schema: EVIDENCE_PROCESSING_METHOD_DEPENDENCE_DIAGNOSTIC_V1_PROTOCOL_V1
Predecessor: Strong Hybrid OSR Evidence Gate V2 (validated 2026-08-18,
immutable: decision METHOD_DEPENDENT_REVIEW, Evidence scientific status
METHOD_DEPENDENT_PENDING_RESEARCHER_REVIEW). This diagnostic does NOT
reopen, reinterpret, or modify the V2 decision.

## 0. Motivation and authorization

Strong Hybrid OSR V2 produced, on the same central-seed rows:
strong Evidence recovery (oracle best-legal accept-correct pooled 0.951),
Mahalanobis specificity FAIL (gap −54.2 pooled, negative 3/3 rotations),
EDL specificity PASS (gap +0.199 pooled, positive 3/3 rotations). The
preregistered contradiction rule therefore produced
METHOD_DEPENDENT_REVIEW. This diagnostic decomposes the contradiction
causally/mechanistically into:

1. generic Evidence-presence / Evidence-distribution bias;
2. representation / Evidence-processing effects;
3. final novelty-readout effects.

The purpose is causal/mechanistic decomposition, NOT detector selection.
No new detectors are introduced; no performance tuning of Mahalanobis or
EDL is performed; no scientific change to V1/V2 frozen results.

NOT authorized: additional novelty detectors (Energy/OpenMax/kNN/…),
Mahalanobis or EDL tuning for performance, Qwen/Model B/RL/continual
learning, FINAL_TEST, router retraining, Evidence-contract changes,
interpreting diagnostic controls as deployable policies, claiming a new
method, selecting EDL as a final detector.

## 1. Frozen populations

- Rotations: Credential / Recon_Scanning / Web_Injection.
- Seed: central seed **20260817** only, × all three rotations (new
  diagnostic head training/replay is limited to this seed per the
  authorized scope; the frozen primary encoder forward passes also use
  the central-seed persisted weights).
- Evidence states: B / BT / BR / BTR; legal states BT / BR / BTR.
- Recoverable-Known rows (RK): frozen stored `recoverable == 1 AND
  is_unknown == 0` rows of the frozen eval parquet (matches the V2
  validation same-sample populations: 2,688 / 1,005 / 1,874).
- True-Unknown rows (TU): frozen stored `is_unknown == 1` rows of the
  frozen eval parquet (8,000 per rotation).
- Geometry fitting population: the frozen TRAIN FIT Known rows
  (`early == 0`, Known-only; 135,000-row pool per cell under the frozen
  90/10 group-safe split) — same recipe as the primary V2 chain.
- EDL-head / B-EDL training populations: the same frozen TRAIN pool
  (FIT for training, EARLY_STOP for the early-stopping criterion),
  Known-only; True Unknown excluded from all fitting, normalization,
  calibration, and early stopping.
- Strict-past Evidence contract and frozen feature transforms
  (`safe_basic`, `log1p∘clip` on T/R history) are reused verbatim from
  the frozen V1/V2 machinery.
- FINAL_TEST forbidden.

## 2. Chain audit (documented exactly, before metrics)

**A. Primary Mahalanobis chain** (V2 primary; frozen weights
`cells/20260817_<rot>/model.pt`):

```text
raw B (47 Basic fields) -> safe_basic (sign(x)*log1p(|x|), nan->0)
raw T (16) / R (18) -> log1p(clip(x,0,None))
state block stack s in {B,BT,BR,BTR} (column stacks of the fixed transforms)
state masks m_t, m_r in {0,1} (1 iff the state contains T / R)
StrongOSREncoder: z_b=block_b(B); z_t=block_t(T)*m_t; z_r=block_r(R)*m_r;
  h(s) = fusion(cat[z_b, z_t, z_r, m_t, m_r])   (128-dim embedding)
per-state geometry: class means + one tied pooled LedoitWolf covariance
  fitted on TRAIN FIT Known h(s); precision = pinv(cov)
score(s) = min Mahalanobis distance of h(s) to any Known class mean
  (higher = more novel)
```

**B. EDL safeguard chain** (V2 safeguard B recipe; retrained in this
diagnostic with the exact frozen recipe, seed 20260817):

```text
identical raw features, transforms, block stacks, masks, trunk
EDLHeadEncoder: alpha(s) = softplus(dirichlet_head(h(s))) + 1  (>= 1)
loss: Type-II ML + fixed KL lambda = 0.1; AdamW 3e-4 / 1e-4;
  max 20 epochs, patience 3, Known-only fit + early stop
belief(s) = max(alpha(s))/sum(alpha(s)); novelty(s) = 1 - belief(s)
  (higher = more novel)
```

**Components that differ between the two chains (exhaustive):**
1. Final readout function: parametric Mahalanobis min-distance (LedoitWolf
   geometry on the 128-dim h space, fitted per state) vs Dirichlet belief
   from a softplus linear head on h.
2. Head/trunk training objective: the primary trunk is trained with CE +
   0.10·SupCon (linear head auxiliary only); the EDL trunk + Dirichlet
   head are trained with Type-II ML + KL(λ=0.1). Both use the same
   multi-state exposure schedule.
3. Therefore the representations h differ between the two chains
   (different trained weights); the EDL chain's trunk is retrained
   identically to the V2 safeguard B replay.

Everything upstream (features, transforms, block stacks, masks,
architecture, exposure schedule, optimizer) is identical. The
contradiction is therefore NOT explainable a priori as a pure readout
effect; the diagnostic below isolates readout vs representation vs
generic Evidence bias empirically.

## 3. Evidence-presence / content controls (primary frozen encoder only)

Three conditions evaluated on the **frozen primary encoder** (forward
passes only; no retraining):

- **REAL**: the target sample's true legal T/R Evidence blocks (deployed
  semantics; masks as in the state). Must reproduce the persisted V2
  validation same-sample Mahalanobis gains within 1e-6 (identity check).
- **NULL-PRESENT**: for legal state s, the relevant availability mask is
  set present (1) but the T/R Evidence block values are replaced by the
  training-normalized neutral vector — the all-zero vector in the frozen
  fixed-transform space (`log1p(0)=0`; zero is the neutral point of the
  training-time nonnegative log1p transform). Isolates "Evidence is
  present" / mask semantics with no content.
- **SHUFFLED**: deterministic permutation of the corresponding T/R
  Evidence blocks among samples within the same rotation, seed,
  evaluation population, and Evidence block type (T block among RK rows;
  T block among TU rows; R block among RK rows; R block among TU rows —
  RK and TU shuffled separately). Permutations via the seeded
  per-cell Generator (`cell_rng(seed, rot, RNG_BASE + 400)`); masks and
  availability identical to REAL. Preserves the marginal Evidence
  distribution but breaks the target↔Evidence correspondence. Offline
  mechanism control ONLY — not a deployable or runtime-legal policy; no
  scientific performance claims from it.

Per condition c, per state s: geometry is fitted per state on that
condition's own TRAIN FIT Known h(s) (for SHUFFLED, train h is
unaffected by the eval-only permutation, so its geometry equals REAL's;
for NULL-PRESENT the train h(s) changes and the geometry is refitted).
This mirrors the deployed chain's per-state geometry contract.

**Reported per condition, separately for RK and True Unknown** (per
rotation and pooled): mean Knownward gain, fraction positive, specificity
gap (RK mean gain − TU mean gain), and per Evidence type T / R / TR (the
legal states BT / BR / BTR separately, not only best-legal).

Key question preregistered: does simply adding an Evidence block
(NULL-PRESENT) or adding unrelated Evidence (SHUFFLED) produce a generic
Knownward shift, and does it reproduce the REAL movement?

## 4. Metric definitions (frozen)

Knownward gain per row i, interface I (Mahalanobis or EDL novelty),
condition c, legal state s:

```text
gain(c, I, s, i) = score(c, I, B, i) - score(c, I, s, i)
   (positive = moved toward Known; both interfaces use novelty scores,
    higher = more novel, so the formula is identical)
```

Best-legal / most-Known-ward gain per row:

```text
g(c, I, i) = max over s in {BT, BR, BTR} of gain(c, I, s, i)
```

- RK mean gain = mean of g over RK rows; TU mean gain = mean of g over
  TU rows; specificity gap = RK mean gain − TU mean gain (per rotation
  and pooled; pooled = sample-pooled over all rows of the three
  rotations).
- Fraction positive = fraction of rows with g > 0 (RK and TU separately).
- Per-type gains = gain(c, I, s, ·) for each legal state s, per rotation
  and pooled.
- Effect ratios (pooled, signed, denominator = REAL pooled mean gain;
  REAL means are far from zero for both populations):

```text
NULL_TO_REAL_RK      = mean_g(RK, NULL) / mean_g(RK, REAL)
NULL_TO_REAL_UNKNOWN = mean_g(TU, NULL) / mean_g(TU, REAL)
SHUFFLED_TO_REAL_RK      = mean_g(RK, SHUFFLED) / mean_g(RK, REAL)
SHUFFLED_TO_REAL_UNKNOWN = mean_g(TU, SHUFFLED) / mean_g(TU, REAL)
```

- Bootstrap: 1,000 rotation-stratified sample replicates (samples drawn
  with replacement within each rotation at the rotation's population
  size; same draw used for numerator and denominator of each ratio);
  seeded Generator; report 2.5/97.5 percentile 95% CIs for pooled means,
  gaps, and ratios. Statistical significance alone never decides; the
  interpretation uses the support rules in §8 with continuous values.

## 5. Same-representation readout test

On the **SAME frozen primary representation h** (persisted primary
weights, central seed, all three rotations), on exactly the same saved h
states:

- **A. frozen Mahalanobis readout**: per-state geometry on TRAIN FIT
  Known h(s) + min-distance scores (identical to §3 REAL; identity check
  against the persisted V2 validation values).
- **B. one fixed evidential uncertainty head trained on frozen h only**:
  `EDLHeadEncoder(StrongOSREncoder())` with the trunk replaced by the
  FROZEN primary weights; the trunk is completely frozen (all trunk
  parameters `requires_grad=False`); only the Dirichlet head parameters
  are trained with the exact validated V2 EDL semantics — Type-II ML +
  fixed KL λ=0.1, AdamW 3e-4/1e-4, 20-epoch cap, patience 3, Known-only
  FIT/EARLY_STOP populations, Known-only calibration (95th-percentile
  thresholds over VAL_CALIB Known per state, audit quantity), no
  representation update, no performance tuning. The multi-state exposure
  schedule and optimizer seeding match the frozen recipe
  (`cell_rng(seed, rot, RNG_BASE + 300)`; `torch.manual_seed(seed)`).
  Purpose: with representation AND Evidence processing held fixed, does
  the Mahalanobis-vs-EDL specificity contradiction remain?
- V1 §12 EDL sanity checks are prerequisites: alpha ≥ 1 everywhere; loss
  decreases over training steps. Failure → STOP_NEEDS_REVIEW for this
  subtest (no alternative EDL architecture will be invented).
- Same-repr contradiction reproduced = Mahalanobis gap negative AND
  EDL-head gap positive on the same h in ≥ 2/3 rotations (3/3 = broadly
  across rotations).

## 6. Optional reverse cross-check

The validated EDL chain exposes a frozen penultimate representation
naturally: the trunk's `trunk_forward` output h_EDL(s). This diagnostic
retrains the B_EDL safeguard chain with the exact frozen V2 recipe
(seed 20260817, three rotations — identical to the validation replay)
and then, on that frozen EDL trunk:

- fits per-state Mahalanobis geometry on the EDL chain's TRAIN FIT Known
  h_EDL(s);
- computes Mahalanobis min-distance scores, gains, and specificity gaps
  on the same RK and TU rows.

No encoder retraining, no model redesign. A Mahalanobis readout on the
EDL-trained representation asks whether the contradiction follows the
representation (h) or the readout. If this were not naturally available
it would be marked REVERSE_CROSSCHECK=NOT_IDENTIFIABLE; it IS available
via `trunk_forward`, so it runs.

## 7. EDL mechanism diagnostics

On the retrained B_EDL chain (§6), for the SAME RK and TU rows, per row,
at state B (before Evidence) and at the row's own best-legal state
(argmax-legal of its gain):

- total nonnegative Evidence sum S = Σ alpha (equals the Dirichlet
  strength);
- uncertainty u = K / S (K = NUM_KNOWN = 6);
- top-class expected probability p_top = max(alpha) / S (by the
  Dirichlet identity this equals the top-class Evidence concentration;
  the second-largest expected probability p_2nd is also reported to
  characterize concentration shape);
- top-1 class identity = argmax alpha;
- top-1 stability pre/post = fraction of rows whose argmax at the
  best-legal state equals their argmax at Basic.

Reported as means/fractions for RK vs True Unknown, per rotation and
pooled, with deltas (after − before): ΔS, Δu, Δp_top, Δp_2nd, and the
stability fraction. Question: is EDL PASS associated with increased
total Evidence, increased concentration on one Known class, reduced
uncertainty, and stable class identity for RK (relative to TU), rather
than merely generic score improvement?

## 8. Interpretation rules (descriptive; no performance winner forced)

Continuous effect ratios and bootstrap intervals are reported
throughout; labels never stand alone. Support rules:

1. **READOUT_DOMINANT** — supported iff on the SAME frozen h (§5), the
   Mahalanobis readout gap is negative and the EDL-head readout gap is
   positive in ≥ 2/3 rotations (contradiction reproduced with
   representation and Evidence processing held fixed).
2. **REPRESENTATION_OR_PROCESSING_DOMINANT** — supported iff the
   contradiction does NOT survive fixed representation (rule 1 fails)
   and the Mahalanobis readout on the EDL-trained representation (§6)
   flips the primary gap's sign (or materially changes it, CI-separated),
   i.e., the sign pattern follows the representation.
3. **GENERIC_EVIDENCE_PRESENCE_BIAS** — supported iff pooled
   NULL_TO_REAL ratio ≥ 0.5 for the RK or TU mean gain, with bootstrap CI
   lower ≥ 0.3 (mask presence alone reproduces ≥ 50% of the REAL
   movement).
4. **GENERIC_EVIDENCE_DISTRIBUTION_BIAS** — supported iff pooled
   SHUFFLED_TO_REAL ratio ≥ 0.5 (RK or TU), CI lower ≥ 0.3 (unrelated
   Evidence reproduces ≥ 50% of the REAL movement).
5. **RECOVERY_SPECIFIC_CONTENT_SIGNAL** — supported iff REAL target
   matched Evidence separates RK from True Unknown materially better than
   BOTH controls: pooled REAL gap > pooled NULL gap AND pooled REAL gap >
   pooled SHUFFLED gap, each with paired bootstrap CI lower > 0 on the
   difference.
6. **MIXED_OR_UNRESOLVED** — default when no rule is supported, or
   multiple conflicting rules fire.

Primary interpretation = the first supported rule in the order
1, 2, 3, 4, 5; all supported rules are reported. Consequence rule
(preregistered): if the result shows only that EDL is a generally
stronger detector (no fixed-representation contradiction and no content
signal), the report must state that the recovery-aware novelty
innovation hypothesis is weakened.

The recorded V2 decision METHOD_DEPENDENT_REVIEW is NOT reopened and is
not relabeled into PASS or FAIL.

## 9. Hard boundaries

Diagnostic only. No new method claim; no Model B authorization; no EDL
selection as final detector; no Energy/OpenMax/kNN/etc.; no Evidence
modification; no router retraining; no use of diagnostic controls as
deployable policies; no continual-learning/evolution experiments; no
V1/V2 artifact modification; no FINAL_TEST; no push.

## 10. Execution lock

Freeze before metrics: this protocol finalized + sha256 recorded in a
preregistration JSON; the protocol, preregistration, and the executing
tool committed BEFORE any diagnostic metric is computed; tool constants
asserted equal to the preregistration at startup. After the first
diagnostic metric: only pure implementation bugfixes with unchanged
scientific semantics, logged; any scientific change → STOP_NEEDS_REVIEW.
Large artifacts persist under the Git-external directory
`processed/dataset_v4_nf3_ton_v1/evidence_processing_method_dependence_diagnostic_v1/`.
Formal report pair under `reports/research_audit/`, uncommitted until
researcher validation.

## 11. Outputs

- `processed/.../evidence_processing_method_dependence_diagnostic_v1/`:
  run_manifest.json, per-rotation condition scores npz (per-state
  Mahalanobis scores per condition; EDL alpha diagnostics), same-repr
  head scores, aggregate.json (all reported quantities).
- `reports/research_audit/evidence_processing_method_dependence_diagnostic_v1.{json,md}`.
- Final acceptance block per the authorized task (printed at the end of
  the run report).
