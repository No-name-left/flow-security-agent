# Model B — Recovery-Aware Typed-Evidence Representation V1 (DRAFT)

**STATUS=DRAFT — NOT PREREGISTERED, NOT FROZEN, NO TRAINING AUTHORIZED.**
This document is a design draft for researcher review. It will become a
protocol only after explicit researcher review, revision, freeze, and a
preregistration commit that precedes any evaluation metric. It builds on
the prior Model B program design
(`docs/research_plan/model_b_evidence_openworld_design.md`, DEC-0025/26/27)
and is narrowed to the question justified by the Information Sufficiency
Gate V1 outcome.

## 1. Validated problem statement (grounding)

Recoverability Information Sufficiency Gate V1 (2026-08-20, outcome
`REPRESENTATION_BOTTLENECK_SUPPORTED`, post-run validation PASS) established:

- Target-specific target↔Evidence correspondence information **exists** in
  legal RAW Evidence: REAL material over BOTH BASIC and SHUFFLED on 3/3
  families with cross-rotation consistency (`n_A_RAW=3`, `rotOK_A_RAW=true`).
- A **generic Evidence-distribution signal** exists independently:
  SHUFFLED-over-BASIC is material 3/3 with `rotOK_sb=true`. A model can
  partially infer "Evidence is present" without knowing *which* target.
- The current STATE_TRANSITION (ST) abstraction **loses most of the
  target-specific signal**: only 1/3 families remains material on ST
  (`n_A_ST=1`), median retention `ret_b=0.020151`, `ret_s=0.082691`
  (threshold 0.5). ST absolute AUROC is high (0.91–0.97) while the
  incremental REAL signal is near zero — high absolute AUROC is **not**
  Evidence sufficiency.
- Known-only open-world transfer is **unsolved** at this representation:
  `n_B_RAW=0`, `rotOK_B_RAW=false`.

Therefore: the Evidence stream carries two separable signals, **(A) generic
Evidence-distribution** and **(B) target-specific target↔Evidence
correspondence**, and the current 83-dimension concatenated abstraction
bottlenecks (B). A stronger model must preserve and use (B) while
suppressing (A)'s inducement of *generic* Knownness.

## 2. Primary question

> Can a stronger typed-Evidence representation preserve and use
> target-specific correspondence while suppressing generic
> Evidence-induced Knownness, using Known-only training and generalizing to
> held-out Unknown classes?

## 3. Inputs (runtime-legal RAW)

Only runtime-legal RAW observations, exactly as the frozen OWG/Information
Gate pipelines consume them:

- `BASIC` block (47 dims), `TEMPORAL` block (16), `RELATION` block (18),
  Evidence presence masks (`m_t`, `m_r`) — the RAW_LEGAL view (83 dims).
- Evidence is **typed**: Temporal vs Relation, with per-sample presence
  masks. Type and mask are inputs, not labels.
- Strict past-only availability and the frozen master split apply unchanged.

**Structural requirement:** the target flow and its acquired Evidence are
treated as **related objects** (target + typed Evidence tokens), NOT as one
concatenated 83-vector. Interaction between target and Evidence is the
mechanism that can carry signal (B).

## 4. Architecture (minimal set, to be finalized by researcher review)

Backbone: Qwen as representation backbone or a Qwen-derived representation
module (prior DEC-0025/26/27 decision; smallest scientifically justified
configuration — no broad architecture search). Candidate heads/modules,
from which the final protocol must pick the **minimal set**:

1. Typed Evidence encoding (type-aware embedding of Evidence blocks +
   masks) — required to keep (A) and (B) separable.
2. Target-to-Evidence interaction / cross-attention between the target
   token and typed Evidence tokens — the candidate mechanism for (B).
3. Known classification head (closed-set supervision, Known only).
4. Target–Evidence consistency / recovery head: predict whether the
   Evidence belongs to the target.
5. Contrastive / ranking objective: REAL (target + its own legal Evidence)
   positive vs SHUFFLED (target + another sample's Evidence) negative —
   from Known TRAIN only.
6. Evidential uncertainty head (justified by the OWG failure: post-
   acquisition MSP novelty scoring is misaligned; the interface must model
   recovery state, per V1 attribution F2 / V2 justification).

**SHUFFLED is an auxiliary Known-TRAIN contrast/control — NOT an Unknown
surrogate.** No held-out Unknown labels ever enter training. Held-out
Unknown rotations (whole-class holdout, same split logic as the frozen
gates) are evaluation-only.

## 5. Anticipated gate questions (eventual prospective gate, not yet frozen)

1. **Retention of target-specific signal:** does Model B on RAW retain
   materially more REAL-over-BASIC / REAL-over-SHUFFLED signal than the
   current STATE_TRANSITION representation (which retains median ~2–8%)?
2. **No generic-Knownness inflation:** does Model B avoid simply raising
   generic SHUFFLED-over-BASIC Knownness while leaving target-specific
   increments unchanged?
3. **Known→Unknown transfer of recovery/reliability signal:** can a
   recovery/reliability signal learned on Known TRAIN transfer to
   whole-class-held-out Unknown without any Unknown fitting or calibration?
4. **Deployable open-world performance:** does Model B improve
   recovery-aware open-world performance (e.g. FURK-style false-Unknown on
   recoverable Known, Unknown recognition), not merely closed-set Known
   Macro-F1?
5. **Attribution to correspondence, not scale:** is any gain specifically
   attributable to target–Evidence correspondence rather than model size
   alone? Requires lightweight non-Qwen baselines (e.g. same-head MLP /
   small transformer) as size-control — no broad architecture search.

Criteria thresholds are placeholders here and must be fixed at
preregistration.

## 6. Novelty boundary (CANDIDATE until researcher review)

Built on `docs/research_plan/literature_novelty_reassessment_v1.md` and the
prior design doc. Model B is **explicitly distinguished from**:

- ordinary open-set / OOD representation learning (no recoverable-Known
  distinction; no typed Evidence acquisition),
- evidential uncertainty alone (prior work; the OWG evidence-process
  diagnostic showed readout/interface dependence),
- contrastive learning alone (no recovery semantics, no typed Evidence),
- active feature acquisition alone (AFA is prior art; Model B consumes
  acquired evidence as typed objects, it does not invent acquisition policy),
- ordinary class-incremental / open-world continual learning (Model B has
  no continual-update machinery in scope).

`PRIMARY_NOVELTY_CANDIDATE=RECOVERABILITY_CONDITIONED_OPEN_WORLD_TRAFFIC_RECOGNITION`
(scope: runtime observation acquisition before novelty) remains the only
candidate claim. **No "first" claims.** All novelty statements in this
section are `CANDIDATE` and require researcher review; the ACO_ICML_2024
full-method review remains PENDING before final novelty claims.

## 7. REMAINING_DESIGN_AMBIGUITIES

- Qwen module vs Qwen-derived encoder: exact backbone instantiation and
  whether any Qwen weights are frozen vs trainable-adapted.
- Minimal head set: which of §4.3–4.6 are required; whether heads share
  the representation or are trained jointly with the backbone.
- The exact consistency objective form (head vs ranking vs both) and its
  weighting vs the Known CE loss.
- Evaluation metric set and materiality thresholds for gate questions 1–5.
- Non-Qwen size-control baseline exact configuration.
- Whether SHUFFLED negatives are per-batch random or matched by
  acquisition pattern; both are Known-TRAIN-only.

## 8. Hard boundaries (standing)

- NO Model B training of any kind.
- NO downloading or modifying model weights.
- NO Qwen SFT; no RL/RLAIF.
- NO continual-learning experiments.
- NO FINAL_TEST usage.
- NO modification of frozen Information Gate results.
- NO tuning using held-out Unknown.
- NO push (no GitHub creds; local commits only, and none before review).

**NEXT_ACTION=RESEARCHER_MODEL_B_PROTOCOL_REVIEW · NEXT_ACTION_AUTHORIZED=false**
