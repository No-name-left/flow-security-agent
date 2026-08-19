# Evidence Processing / Method Dependence Diagnostic V1 — Report

Date: 2026-08-18
Status: COMPLETE (preregistered, frozen before evaluation)
Primary interpretation: **READOUT_DOMINANT** (secondary: GENERIC_EVIDENCE_DISTRIBUTION_BIAS)

Companion machine-readable artifact:
`reports/research_audit/evidence_processing_method_dependence_diagnostic_v1.json`
(primary). This MD is the explanatory context.

## 1. Protocol / preregistration identity

- Frozen protocol `docs/research_plan/evidence_processing_method_dependence_diagnostic_v1_protocol.md`
  recomputed SHA256 = `91b8f7db1f0c754ae479f40690b10366835811df75072287942667af1a30e277`
  — **matches** the preregistration record and the tool constant.
- Preregistration
  `reports/research_audit/evidence_processing_method_dependence_diagnostic_v1_preregistration.json`
  committed together with the protocol and the executing tool in commit
  `fd3f4b7` **before any diagnostic metric was computed** (protocol §10
  execution lock).
- `PREREGISTRATION_COMMIT_SHA=fd3f4b7` (local commit only, no push).
- The predecessor V2 decision `METHOD_DEPENDENT_REVIEW` is **not reopened**
  and not relabeled; Evidence scientific status remains
  `METHOD_DEPENDENT_PENDING_RESEARCHER_REVIEW`.

## 2. Chain audit (protocol §2, documented before metrics)

The primary Mahalanobis chain and the EDL safeguard chain differ in
exactly three components: (1) final readout function (per-state LedoitWolf
min-distance geometry on the 128-dim h space vs Dirichlet belief
`1 − max(α)/Σα` from a softplus linear head on h); (2) training objective
(CE + 0.10·SupCon vs Type-II ML + fixed KL λ=0.1); (3) therefore the
trained representation h. Everything upstream — features, frozen
transforms, block stacks, availability masks, architecture, multi-state
exposure schedule, optimizer — is identical. The contradiction was
therefore **not** a priori a pure readout effect; the diagnostic isolates
the three factors empirically.

## 3. Identity checks (all PASS)

- `REAL` Mahalanobis best-legal gains reproduce the persisted V2
  validation same-sample values within 1e-6 (3/3 rotations × RK/TU).
- EDL sanity: α ≥ 1 everywhere (min = 1.0); loss decreases over steps
  (1.28→0.63 / 1.18→0.44 / 1.17→0.49).
- SHUFFLED preserves T/R block marginals (mean/std within 1e-9, RK and TU
  separately); NULL-PRESENT blocks all-zero with masks present.
- Three pure implementation bugfixes were logged post-commit with
  unchanged scientific semantics (protocol §10): frozen primaries now
  `model.eval()` exactly as the validated replay (dropout off); Mahalanobis
  scores and EDL α promoted to float64 before gain subtraction (matching
  the persisted float64 audit convention — the residual 3.4e-6 in the
  first attempt was float32 subtraction noise, not a result difference);
  a missing-condition guard in the bootstrap helper.

## 4. Condition controls (frozen primary encoder, forward passes only)

Per rotation (mean best-legal Knownward gain; positive = moved toward
Known):

| Rotation | Cond | RK gain | TU gain | gap | frac+ RK/TU |
|---|---|---|---|---|---|
| Credential | REAL | 89.61 | 135.74 | −46.13 | 0.96 / 1.00 |
| Credential | NULL-PRESENT | −25.21 | −14.08 | −11.14 | 0.33 / 0.44 |
| Credential | SHUFFLED | 69.63 | 138.08 | −68.44 | 0.82 / 1.00 |
| Recon_Scanning | REAL | 31.32 | 140.18 | −108.86 | 0.69 / 0.94 |
| Recon_Scanning | NULL-PRESENT | −51.30 | −40.57 | −10.73 | 0.02 / 0.03 |
| Recon_Scanning | SHUFFLED | 35.41 | 151.12 | −115.71 | 0.76 / 0.99 |
| Web_Injection | REAL | 68.91 | 98.95 | −30.05 | 0.99 / 0.83 |
| Web_Injection | NULL-PRESENT | −55.44 | −12.49 | −42.95 | 0.09 / 0.43 |
| Web_Injection | SHUFFLED | 72.48 | 97.71 | −25.24 | 0.98 / 0.84 |

Per-Evidence-type gains (BT/BR/BTR) are in the JSON report; the type
structure tracks the best-legal pattern in every condition.

**Pooled (rotation-stratified bootstrap, 1000 reps, 95% CIs):**

| Quantity | Mean | 95% CI |
|---|---|---|
| REAL RK gain | 72.12 | [70.47, 73.91] |
| REAL TU gain | 143.90 | [142.09, 145.74] |
| REAL gap | −71.78 | [−74.14, −69.35] |
| NULL RK gain | −40.08 | [−41.34, −38.81] |
| NULL TU gain | −19.84 | [−21.27, −18.39] |
| SHUFFLED RK gain | 64.43 | [62.66, 66.25] |
| SHUFFLED TU gain | 146.07 | [144.11, 147.95] |
| SHUFFLED gap | −81.64 | [−84.21, −79.00] |
| **NULL_TO_REAL_RK** | **−0.556** | [−0.582, −0.531] |
| **NULL_TO_REAL_TU** | **−0.138** | [−0.148, −0.127] |
| **SHUFFLED_TO_REAL_RK** | **0.893** | [0.877, 0.910] |
| **SHUFFLED_TO_REAL_TU** | **1.015** | [1.009, 1.022] |
| REAL gap − NULL gap | −51.53 | [−54.56, −48.83] |
| REAL gap − SHUFFLED gap | +9.86 | [8.36, 11.35] |

**Key question:** does simply adding an Evidence block, or unrelated
Evidence, produce a generic Knownward shift?

- **Presence alone does the opposite.** NULL-PRESENT (mask present, blocks
  at the training-neutral zero vector) produces **negative** gains for both
  RK (−40.1) and TU (−19.8): an empty Evidence block moves samples *away*
  from Known in Mahalanobis distance. NULL reproduces none of the REAL
  movement (ratios −0.56 / −0.14).
- **Unrelated Evidence reproduces almost all of the magnitude.**
  SHUFFLED (marginal-identical, target↔Evidence correspondence broken)
  reproduces **89.3%** of the REAL RK movement (CI [87.7, 91.0]) and
  **101.5%** of the REAL TU movement (CI [100.9, 102.2]).
- **A modest content-specific component exists.** The REAL gap (−71.78) is
  *less negative* (better RK/TU separation) than the SHUFFLED gap (−81.64);
  paired difference +9.86, CI [8.36, 11.35]. The full content-signal rule
  is not met (the NULL comparison fails because NULL reverses direction).

## 5. Same-representation readout test (rule 1)

On the **same frozen primary h**, one fixed Dirichlet head trained on
frozen h only (trunk fully frozen, eval mode; exact V2 EDL semantics;
Known-only fit/early-stop/calibration; rng offset 300):

| Rotation | Mahalanobis gap (frozen) | EDL-head gap (same h) | Contradiction |
|---|---|---|---|
| Credential | −46.13 | **+0.076** | YES |
| Recon_Scanning | −108.86 | **+0.072** | YES |
| Web_Injection | −30.05 | **+0.148** | YES |

Pooled EDL-head gap **+0.0606** (95% CI [0.0562, 0.0645]).

With representation AND Evidence processing held exactly fixed, the
Mahalanobis-negative / EDL-positive specificity contradiction survives in
**3/3 rotations** → rule 1 fires: **READOUT_DOMINANT**. The sign pattern
of the V2 contradiction lives in the final novelty readout, not in the
representation or the Evidence processing.

## 6. Reverse cross-check (rule 2)

B_EDL retrained with the exact frozen V2 recipe (seed 20260817, rng offset
200 — identical to the validation replay); Mahalanobis geometry fitted on
the frozen EDL trunk's h_EDL:

| Rotation | Mahalanobis gap on h_EDL |
|---|---|
| Credential | −37.10 |
| Recon_Scanning | −63.95 |
| Web_Injection | −26.93 |

Pooled **−58.86** (95% CI [−64.76, −53.32]). The Mahalanobis gap remains
negative on the EDL-trained representation in all three rotations: the
sign follows the **readout**, not the representation. (The magnitude
shrinks from −71.78 to −58.86 — representation choice matters
quantitatively, not sign-wise.) Rule 2 not supported.

## 7. EDL mechanism diagnostics (retrained B_EDL chain)

Deltas (best-legal state − Basic) of Dirichlet strength S = Σα,
uncertainty u = 6/S, top-class evidence concentration p_top = max(α)/S,
and top-1 identity stability:

| Population | ΔS | Δu | Δp_top | Δp_2nd | p_top B→s | stability |
|---|---|---|---|---|---|---|
| Credential RK | +41.3 | −0.14 | +0.237 | −0.141 | 0.65→0.89 | 0.63 |
| Credential TU | +18.0 | −0.08 | +0.073 | −0.021 | 0.75→0.83 | 0.73 |
| Recon RK | +83.5 | −0.22 | +0.281 | −0.137 | 0.63→0.91 | **0.30** |
| Recon TU | +217.5 | −0.10 | +0.084 | −0.015 | 0.89→0.98 | 0.91 |
| Web RK | +36.4 | −0.14 | +0.198 | −0.103 | 0.68→0.88 | 0.67 |
| Web TU | −8.5 | +0.01 | −0.026 | +0.021 | 0.83→0.81 | 0.67 |

EDL PASS is an **Evidence-induced concentration of belief on a single
Known class** for RK (ΔS +36..+84, Δp_top +0.20..+0.28, uncertainty down,
second-largest down) — i.e., the evidential head reads Evidence as
"confirm this row is a specific Known". TU mostly shows weaker or absent
effects, **except Recon TU** (ΔS +217, p_top 0.89→0.98, stability 0.91):
on Recon, TU rows also accumulate Evidence and stay stably confident,
which is why the Recon EDL margin is the thinnest. RK top-1 stability is
materially low on Recon (0.30): RK rows jump between class identities
under Evidence there.

## 8. Interpretation (frozen §8 rule order; labels never stand alone)

Rules fired: **READOUT_DOMINANT** (rule 1, first in order) and
**GENERIC_EVIDENCE_DISTRIBUTION_BIAS** (rule 4). Primary:
`READOUT_DOMINANT_PRIMARY`.

- **READOUT_DOMINANT** — on the identical frozen h, Mahalanobis gap
  negative 3/3 and EDL-head gap positive 3/3: the V2 contradiction is
  reproduced with representation and Evidence processing held fixed.
- **GENERIC_EVIDENCE_DISTRIBUTION_BIAS** — SHUFFLED reproduces ≥ 89% of
  the REAL Knownward movement (CI lower ≥ 0.3); the generic movement is
  dominated by distribution-level shift.
- **GENERIC_EVIDENCE_PRESENCE_BIAS** — not supported (NULL reverses
  direction; ratios negative).
- **RECOVERY_SPECIFIC_CONTENT_SIGNAL** — partial (REAL vs SHUFFLED +9.86,
  CI > 0) but the preregistered rule requires both controls beaten; not
  supported.
- **REPRESENTATION_OR_PROCESSING_DOMINANT** — not supported (Mahalanobis
  stays negative on the EDL-trained representation).

**Consequence rule (preregistered §8):** the "EDL is generally stronger →
recovery-aware hypothesis weakened" consequence does **not** apply: the
fixed-representation contradiction IS reproduced, so EDL's PASS is a
readout-level phenomenon on identical representations, not a
generally-stronger-detector artifact. The distribution control does show
that ~90–100% of the Knownward movement is generic (unrelated Evidence),
with only a modest content-specific separation component (+9.9 of the
gap). The recovery-aware novelty hypothesis is **not weakened** by this
diagnostic, and it is not confirmed at the representation level — the
mechanism is unresolved at the readout level.

## 9. Hard boundaries respected

Diagnostic only: no new detector, no tuning of Mahalanobis or EDL, no
Model B / RL / continual learning, no FINAL_TEST, no router retraining,
no Evidence-contract change, no V1/V2 artifact modification, no use of
controls as deployable policies, no push. The V2 decision and the V2
scientific results are untouched.

## 10. Artifacts

- Run root (Git-external):
  `processed/dataset_v4_nf3_ton_v1/evidence_processing_method_dependence_diagnostic_v1/`
  — `run_manifest.json`, `aggregate.json`, per-rotation condition scores
  npz, same-repr head scores + epoch logs, B_EDL retrain epoch logs,
  `diagnostic_stdout.log`.
- Report pair: `reports/research_audit/evidence_processing_method_dependence_diagnostic_v1.{json,md}`
  (untracked, uncommitted).

## 11. Acceptance block

```
PREREGISTRATION_COMMIT_SHA=fd3f4b7
PROTOCOL_HASH_MATCH=YES
DIAGNOSTIC_STATUS=COMPLETE
IDENTITY_CHECKS=PASS
SAME_REPRESENTATION_CONTRADICTION=3/3
PRIMARY_INTERPRETATION=READOUT_DOMINANT (secondary: GENERIC_EVIDENCE_DISTRIBUTION_BIAS)
REVERSE_CROSSCHECK=COMPLETED (Mahalanobis gap negative 3/3 on EDL-trained representation)
NULL_PRESENT_REPRODUCES_REAL_MOVEMENT=FALSE (ratios -0.556 / -0.138)
SHUFFLED_REPRODUCES_REAL_MOVEMENT=TRUE (ratios 0.893 / 1.015)
CONTENT_SPECIFIC_SEPARATION=PARTIAL (REAL vs SHUFFLED +9.86 CI>0; REAL vs NULL fails)
EDL_GENERALLY_STRONGER_ALONE=FALSE (fixed-representation contradiction reproduced; consequence rule not triggered)
V2_DECISION_NOT_REOPENED=YES
RESULT_COMMITTED=false
RESULT_PUSHED=false
NEXT_PROPOSED_ACTION=RESEARCHER_REVIEW_OF_CAUSAL_DECOMPOSITION
NEXT_ACTION_AUTHORIZED=false
STOP
```
