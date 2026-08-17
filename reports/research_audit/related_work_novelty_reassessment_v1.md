# Related Work and Novelty Reassessment — V1

> Status: `COMPLETE` (documentation / research-design synchronization ONLY —
> no experiments, no commits, no pushes from the V1 document task)
>
> Date: 2026-08-17
>
> REVISION=1 (2026-08-17): full-text review of RoNeTC / RoeCi / GCLC
> completed externally by the researcher workflow; novelty scope narrowed to
> runtime observation acquisition; access register updated; self-evolution
> framing added.
>
> Repository: `flow-security-agent` @ `main` (working tree; all files from
> this audit are uncommitted, left for researcher review)
>
> Purpose: record prior art that constrains our claims, flag plausible
> novelty gaps, register access-limited papers that must be read before any
> final first-claims, and capture method lessons that revise the prospective
> (not yet run) open-world and continual experiment designs.
>
> Terminology discipline: this audit never writes FIRST / FIRST-EVER /
> UNPRECEDENTED as established fact. Allowed statuses:
> `PLAUSIBLY_NOVEL`, `TO_OUR_KNOWLEDGE_PENDING_FULL_REVIEW`,
> `NOT_A_STANDALONE_NOVELTY`, `PRIOR_ART_EXISTS`,
> `MUST_READ_BEFORE_FINAL_CLAIM`.
>
> Provenance: the RoNeTC / RoeCi / GCLC full-text review was performed
> OUTSIDE this repository by the researcher workflow. The local Agent does
> NOT claim it independently accessed those PDFs.
> `FULL_TEXT_REVIEW_COMPLETED_EXTERNALLY_BY_RESEARCHER_WORKFLOW`.

## 0. Empirical state verification (against formal reports)

Verified from `core_hypothesis_gate_v1.json` and
`core_hypothesis_gate_v1b.json` (formal report JSON is authoritative):

```text
CORE_HYPOTHESIS_GATE_1=YELLOW        (COMPLETE_YELLOW; not relabeled)
CORE_HYPOTHESIS_GATE_1B=PASS         (COMPLETE_PASS)
GATE_1B_TEMPORAL_CONDITIONAL_UTILITY_STATUS=PASS   (T1-T7: 7/7)
GATE_1B_RELATION_CONDITIONAL_VALUE=PASS
EVIDENCE_DIVERSITY_STATUS=TEMPORAL_PLUS_RELATION_CONDITIONALLY_USEFUL
GATE_1_STATUS_CHANGED=false
```

Interpretation discipline:

- Temporal always-on value was modest; Relation always-on value was negative
  (frozen Gate 1).
- Conditional selection strongly improved utility (Gate 1B).
- Relation has stable UNIQUE_R recovery.
- **Gate 1B establishes conditional utility learnability. It does NOT
  establish open-world benefit.** The open-world hypothesis is not yet
  tested; no claim of proven open-world benefit appears anywhere in this
  audit or its downstream documents.

## 0.1 Full-text review sync (revision 1)

Three papers were full-text reviewed externally by the researcher workflow.
Recorded findings:

### RoNeTC — Reliable Open-Set Network Traffic Classification, IEEE TIFS 2025

- All packet views are already observed (IP header / transport header /
  packet payload views).
- Each view produces a classification opinion + uncertainty.
- Final decision dynamically fuses already-observed views.
- RoNeTC does NOT selectively acquire previously unobserved runtime
  evidence.
- Consequences:
  - multi-view dynamic fusion = `PRIOR_ART_EXISTS`;
  - uncertainty-based Known/Unknown classification = `PRIOR_ART_EXISTS`.

### RoeCi — Robust Open-Set Network Traffic Classification, IEEE TMC 2026 (DOI 10.1109/TMC.2026.3715471)

- Constructs an uncertainty / sample-complexity measure.
- Easy / low-complexity samples use fewer experts; hard / high-complexity
  samples invoke additional expert capacity.
- Joint uncertainty is used for Known/Unknown classification.
- Therefore "do more processing before rejecting Unknown" is `PRIOR_ART_EXISTS`.
- Critical boundary — RoeCi adds MODEL CAPACITY / COMPUTE to the SAME
  OBSERVATION; it does NOT acquire previously unobserved Temporal/Relation
  observation evidence before novelty handling:

```text
ROECI:  same observation + adaptive additional model capacity
OURS:   partial/basic observation
        + adaptive acquisition of previously unobserved,
          runtime-legal observation evidence
        + reclassification before novelty
```

### GCLC — Graph-Based Contrastive Learning and Clustering for Open-World Encrypted Traffic Classification, IEEE TIFS 2026 (DOI 10.1109/TIFS.2026.3705313)

- Graph representation; contrastive + center-aware representation learning;
  Mahalanobis new-class detection; clustering of candidate unknowns; human
  semantic confirmation; adaptive/incremental model update.
- Consequences:
  - new-class discovery / clustering / update / generic open-world
    continual evolution = `PRIOR_ART_EXISTS`;
  - GCLC does NOT model Evidence-recoverable Known contamination before
    unknown-candidate admission.

## 1. Verdict categories (summary)

```text
A. PRIOR_ART_THAT_DIRECTLY_LIMITS_OUR_CLAIMS
   generic AFA; AFA+OOD; instance-wise acquisition; cost-aware two-stage
   routing; typed/grouped/temporal acquisition; acquire-before-abstain;
   multi-view dynamic fusion; uncertainty-based rejection; adaptive
   computation before rejection; open-world traffic classification;
   open-world continual traffic learning; new-class discovery/clustering/
   human-confirmation/incremental-update; buffer purification —
   all PRIOR_ART_EXISTS.

B. PLAUSIBLE_NOVELTY_GAPS (candidate, experiment-pending)
   B1 recoverability-conditioned open-world traffic recognition, precisely:
      RUNTIME_OBSERVATION_ACQUISITION_BEFORE_NOVELTY —
      INSUFFICIENT_OBSERVATION_OF_KNOWN != TRUE_NOVELTY
      (unknown handling preceded by adaptive acquisition of previously
      unobserved, runtime-legal observation evidence + reclassification)
   B2 Evidence-gated removal of Recoverable Known before Unknown-candidate
      admission (clustering / human verification / new-class adaptation)
      — conditional continual novelty candidate

C. ACCESS_LIMITED_PAPERS_MUST_READ_BEFORE_FINAL_FIRST_CLAIMS
   ACO ICML 2024 (MEDIUM_HIGH) — the only remaining access-limited paper.
   RoNeTC / RoeCi / GCLC now FULL_TEXT_REVIEW=COMPLETE
   (external researcher workflow). See Section 5.

D. METHOD_LESSONS_THAT_CHANGE_OUR_EXPERIMENTAL_PROTOCOL
   D1 policy-conditioned novelty calibration (post-acquisition score
      distribution differs; never reuse a Basic-only threshold)
   D2 read-only evidence acquisition assumption (NDE/NUC framing)
   D3 acquisition-policy distribution shift at deployment (von Kleist)
   D4 state-conditioned utility must not be claimed as value-of-information
      routing invention (Regol et al.)
   D5 post-acquisition calibration/evaluation observations must traverse
      the same frozen acquisition pipeline; separate held-out calibration
      protocol if the policy/budget is selected on calibration data.
   D6 utility routing must be compared against generic difficulty routing
      (LOW_CONFIDENCE / HIGH_ENTROPY) — RoeCi establishes adaptive
      escalation by uncertainty/sample-complexity as prior art.
```

## 2. Prior-art register

### 2.1 Generic Active Feature Acquisition (AFA)

| Item | Detail |
| --- | --- |
| Paper | Active Feature Acquisition with Generative Surrogate Models, Li & Oliva, ICML 2021, PMLR 139 |
| Key overlap | instance-wise dynamic feature acquisition; prediction-vs-cost tradeoff; MDP formulation; expected information gain / utility; side information; time-series chronological acquisition constraints |
| Consequence | generic dynamic Evidence acquisition is NOT our novelty |

### 2.2 Robust AFA + OOD

| Item | Detail |
| --- | --- |
| Paper | Towards Robust Active Feature Acquisition, Li et al., arXiv:2107.04163 |
| Key overlap | partially observed inputs; AFA; OOD detection for partially observed data |
| Consequence | "AFA + OOD" is NOT by itself novel |

### 2.3 Non-greedy AFA

| Item | Detail |
| --- | --- |
| Paper | Acquisition Conditioned Oracle for Nongreedy Active Feature Acquisition (ACO), Valancius, Lennon, Oliva, ICML 2024, PMLR 235 |
| Key overlap | RL complexity; greedy-acquisition limitations; jointly informative acquisitions; non-greedy acquisition |
| ACCESS_STATUS | `PRIMARY_ABSTRACT_READ`; `FULL_PDF_TOOL_ACCESS_FAILED_MIME`; `FULL_METHOD_REVIEW=PENDING` |
| Flag | `MUST_READ_BEFORE_FINAL_NONGREEDY_BASELINE_CLAIM=true`; does NOT block the next empirical gate (main threat = generic non-greedy AFA novelty, already excluded from our claim) |

### 2.4 Cost-aware two-stage classification

| Item | Detail |
| --- | --- |
| Paper | Is the acquisition worth the cost? Surrogate losses for Consistent Two-stage Classifiers, Regol et al., NeurIPS 2025 |
| Key lessons | stage-1 sees x; stage-2 sees x+z at cost; the router cannot see z before deciding; optimal routing depends on expected future gain minus cost; confidence alone is not the theoretically correct routing rule |
| Consequence | expected future acquisition utility is prior art; our utility must NOT be claimed as an invention of value-of-information routing |

### 2.5 Instance-specific AFA

| Item | Detail |
| --- | --- |
| Papers | Active feature acquisition via explainability-driven ranking, Guney et al., ICML 2025; Stochastic Encodings for Active Feature Acquisition, Norcliffe et al., ICML 2025 |
| Key overlap | feature value varies by instance; instance-wise acquisition; RL may be difficult; greedy CMI may be myopic |
| Consequence | instance-specific Evidence utility is NOT standalone novelty |

### 2.6 Joint / temporal / typed acquisition

| Item | Detail |
| --- | --- |
| Papers | Information Templates: A New Paradigm for Intelligent Active Feature Acquisition, arXiv:2508.18380; NOCTA: Non-Greedy Objective Cost-Tradeoff Acquisition for Longitudinal Data, arXiv:2507.12412; REACT: Relaxed Efficient Acquisition of Context and Temporal Features, arXiv:2603.11370; Active Acquisition for Multimodal Temporal Data, arXiv:2211.05039 |
| Key overlap | typed/grouped acquisition; temporal acquisition; jointly informative subsets |
| Consequence | typed/grouped, temporal, and jointly-informative acquisition are NOT standalone novelty claims |

### 2.7 Offline AFA evaluation (distribution shift)

| Item | Detail |
| --- | --- |
| Paper | Evaluation of Active Feature Acquisition Methods for Time-varying Feature Settings, von Kleist et al., JMLR 26(60), 2025 |
| Key concepts | NDE (No Direct Effect); NUC (No Unobserved Confounding); AFA deployment may induce acquisition-policy distribution shift |
| Protocol impact | add formal assumption `READ_ONLY_EVIDENCE_ACQUISITION_ASSUMPTION=true`: requesting TEMPORAL / RELATION Evidence only reveals already-existing strict-past telemetry and does not causally alter the network traffic being classified. Future: `EVIDENCE_AVAILABILITY_MISSINGNESS_STRESS_TEST=PLANNED` |

### 2.8 Evidence acquisition before abstention

| Item | Detail |
| --- | --- |
| Paper | Look Again Before You Abstain: Budgeted Conformal Evidence Acquisition, Xu et al., arXiv:2606.16667 |
| Key overlap | answer / acquire / abstain |
| Consequence | "look again before reject/abstain" is NOT standalone novelty |
| Critical methodological lesson | post-acquisition score distribution differs from pre-acquisition score distribution → `POLICY_CONDITIONED_NOVELTY_CALIBRATION=MANDATORY`: the deployed novelty threshold must be calibrated after the frozen acquisition policy is applied; never reuse a Basic-only threshold after acquisition; calibration and evaluation observations must traverse the same frozen acquisition pipeline; if the policy/budget is selected using calibration data, require a separate held-out calibration protocol or a pre-specified correction. This calibration principle is also prior art — do not claim it as our novelty. |

### 2.9 Traffic open-set / open-world prior art

| Item | Detail |
| --- | --- |
| Paper 1 | Reliable Open-Set Network Traffic Classification (RoNeTC), IEEE TIFS 2025, DOI 10.1109/TIFS.2025.3544067 |
| Full-text findings | all packet views already observed; per-view opinion + uncertainty; dynamic fusion of observed views; no selective acquisition of previously unobserved evidence |
| Consequences | multi-view dynamic fusion = PRIOR_ART_EXISTS; uncertainty-based Known/Unknown = PRIOR_ART_EXISTS |
| RONETC_FULL_TEXT_REVIEW | `COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW` |
| Paper 2 | Robust Open-Set Network Traffic Classification (RoeCi), Wang et al., IEEE TMC 2026, DOI 10.1109/TMC.2026.3715471 |
| Full-text findings | uncertainty/sample-complexity measure; easy samples use fewer experts; hard samples invoke additional expert capacity; joint uncertainty → Known/Unknown |
| Consequences | "do more processing before rejecting Unknown" = PRIOR_ART_EXISTS; adds capacity/compute to the SAME observation, NOT acquisition of previously unobserved observation evidence |
| ROECI_FULL_TEXT_REVIEW | `COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW` |
| Paper 3 | GCLC — Graph-Based Contrastive Learning and Clustering for Open-World Encrypted Traffic Classification, IEEE TIFS 2026, DOI 10.1109/TIFS.2026.3705313 |
| Full-text findings | graph representation; contrastive + center-aware learning; Mahalanobis new-class detection; candidate clustering; human semantic confirmation; adaptive/incremental update |
| Consequences | new-class discovery / clustering / update / generic open-world continual evolution = PRIOR_ART_EXISTS; no Evidence-recoverable Known contamination modeling before unknown-candidate admission |
| GCLC_FULL_TEXT_REVIEW | `COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW` |

### 2.10 Traffic continual / incremental prior art

| Item | Detail |
| --- | --- |
| Papers | OWETC — Open world encrypted traffic classification based on semi-supervised class incremental learning, IEEE 2023 / Xplore 2024, DOI 10.1109/ISPA-BDCloud-SocialCom-SustainCom59178.2023.00175; SOUL — A Semi-supervised Open-world continUal Learning method for Network Intrusion Detection, arXiv:2412.00911; MI^2DAS — A Multi-Layer Intrusion Detection Framework with Incremental Learning for Securing Industrial IoT Networks, arXiv:2602.23846 |
| Consequence | do NOT claim novelty for: open-world traffic + incremental learning + replay/buffer + new-class adaptation |

### 2.11 Buffer purity prior art

| Item | Detail |
| --- | --- |
| Paper | Continual Learning on Noisy Data Streams via Self-Purified Replay, arXiv:2110.07735 |
| Consequence | "buffer purification" itself is NOT novel. The project-specific candidate gap is narrower: Unknown-candidate contamination caused by KNOWN CLASS + INSUFFICIENT OBSERVATION + PREMATURE NOVELTY REJECTION, and removing such RECOVERABLE KNOWN using legal test-time Evidence BEFORE unknown-buffer admission. |

```text
GENERIC_BUFFER_PURIFICATION_NOVELTY=false
RECOVERABLE_KNOWN_UNKNOWN_BUFFER_PURIFICATION=
PLAUSIBLE_NOVELTY_PENDING_FULL_REVIEW_AND_EXPERIMENT
```

## 3. Claim-safety table

| Claim | Status | Prior art | Safe wording |
| --- | --- | --- | --- |
| Dynamic Evidence acquisition | PRIOR_ART_EXISTS | Li & Oliva ICML 2021; Regol et al. NeurIPS 2025 | "we adopt a learned acquisition policy" / NOT NOVEL |
| Instance-specific Evidence utility | PRIOR_ART_EXISTS | Guney et al. ICML 2025; Norcliffe et al. ICML 2025 | NOT NOVEL |
| Typed / temporal Evidence acquisition | PRIOR_ART_EXISTS | Information Templates; NOCTA; REACT; arXiv:2211.05039 | NOT NOVEL |
| Acquire before abstain/reject | PRIOR_ART_EXISTS | Xu et al. arXiv:2606.16667 | NOT NOVEL |
| Uncertainty before rejection | PRIOR_ART_EXISTS | RoNeTC TIFS 2025; RoeCi TMC 2026 | NOT NOVEL |
| Adaptive computation before rejection | PRIOR_ART_EXISTS | RoeCi TMC 2026 (additional expert capacity on same observation) | NOT NOVEL |
| Dynamic multi-view fusion | PRIOR_ART_EXISTS | RoNeTC TIFS 2025 | NOT NOVEL |
| Open-world traffic recognition | PRIOR_ART_EXISTS | RoNeTC TIFS 2025; RoeCi TMC 2026; GCLC TIFS 2026 | NOT NOVEL |
| New-class discovery / clustering / human confirmation / incremental update | PRIOR_ART_EXISTS | GCLC TIFS 2026 | NOT NOVEL |
| Open-world continual traffic learning | PRIOR_ART_EXISTS | OWETC 2023; SOUL; MI^2DAS; GCLC TIFS 2026 | NOT NOVEL |
| Buffer purification | PRIOR_ART_EXISTS | Self-Purified Replay arXiv:2110.07735 | NOT NOVEL |
| Runtime observation acquisition before novelty handling (recoverability-conditioned false-Unknown handling in traffic) | PLAUSIBLE_NOVELTY_PENDING_FULL_REVIEW | — | "to our knowledge, pending full review, we are not aware of traffic recognition that precedes novelty handling with adaptive acquisition of previously unobserved, runtime-legal observation evidence and reclassification" |
| Evidence-gated removal of Recoverable Known before Unknown-candidate admission | PLAUSIBLE_NOVELTY_PENDING_FULL_REVIEW_AND_EXPERIMENT | — | claim only after open-world + purification validation |
| FURK | PROPOSED_RECOVERABILITY_CONDITIONED_FALSE_UNKNOWN_DIAGNOSTIC | — | "we propose FURK as a diagnostic metric" — not a major independent theoretical contribution |

## 4. Contribution repositioning

Three broad modules are NOT presented as equally novel. Candidate hierarchy
(non-frozen positioning; final first-claims require the remaining
access-limited review of ACO and the empirical gates):

```text
PRIMARY CONTRIBUTION C1
NAME=RECOVERABILITY_CONDITIONED_OPEN_WORLD_TRAFFIC_RECOGNITION
SCOPE=RUNTIME_OBSERVATION_ACQUISITION_BEFORE_NOVELTY (precise scope)
CORE_DISTINCTION=INSUFFICIENT_OBSERVATION_OF_KNOWN != TRUE_NOVELTY
CONCEPTUAL_DECOMPOSITION=
  Known = Basic-sufficient Known
        + Evidence-recoverable Known
        + Residual-hard Known
MECHANISM=partial/basic observation -> adaptive acquisition of previously
  unobserved, runtime-legal observation evidence -> reclassification
  before novelty handling
NOT_CLAIMED=uncertainty before rejection; adaptive computation before
  rejection; dynamic multi-view fusion; open-set traffic; open-world
  traffic; new-class discovery (all PRIOR_ART_EXISTS)
STATUS=PLAUSIBLY_NOVEL_PENDING_FULL_TRAFFIC_OSR_REVIEW
FURK=PROPOSED_RECOVERABILITY_CONDITIONED_FALSE_UNKNOWN_DIAGNOSTIC
  (not an independent major theory)

SUPPORTING METHOD M1
NAME=RECOVERABILITY_AND_HARM_AWARE_TYPED_EVIDENCE_ROUTING
CORE_OBJECT=state-conditioned operational utility U_e(x)
HISTORICAL_FROZEN=Gate 1B diagnostic form HELP/NEUTRAL/HARM (+1/0/-1)
  (do NOT retroactively change Gate 1B)
FUTURE_MODEL_B=PROPOSED_NOT_FROZEN: expected task-loss reduction
  minus evidence acquisition cost
NOT_CLAIMED=generic instance-wise acquisition, typed acquisition,
  expected utility routing, AFA (all PRIOR_ART_EXISTS)
PROJECT_SPECIFIC_USE=utility used to (1) recover under-observed Known,
  (2) reduce recoverability-conditioned false Unknown,
  (3) preserve True Unknown recognition

CONDITIONAL CONTINUAL CANDIDATE C2
NAME=EVIDENCE_GATED_UNKNOWN_CANDIDATE_PURIFICATION_FOR_SELF_EVOLUTION
PRECISE_SCOPE=remove Evidence-recoverable Known from the unknown-candidate
  stream BEFORE clustering, human verification, and new-class adaptation
MECHANISM=uncertain observation -> Evidence recovery -> remove
  Recoverable Known -> residual novelty -> Unknown candidate stream
  -> verified feedback -> new-class adaptation
STATUS=PLAUSIBLE_NOVELTY_PENDING_OPEN_WORLD_AND_CONTINUAL_VALIDATION
NOT_THE_NOVELTY=unknown detection, clustering, human confirmation,
  incremental update, replay, continual learning, buffer purification
  in general (all PRIOR_ART_EXISTS)

SELF_EVOLUTION (system-level mainline)
SELF_EVOLUTION_STATUS=PLANNED_CORE_SYSTEM_LOOP_PENDING_PURIFICATION_AND_CONTINUAL_VALIDATION
SELF_EVOLUTION_NOVELTY_IS_NOT_CONTINUAL_LEARNING_ITSELF=true
PREREQUISITE=before full continual training, first test whether the
  Evidence Gate actually purifies the Unknown candidate stream
  (Unknown-Candidate Purification Gate; no continual model training)
```

## 5. MUST_READ_BEFORE_FINAL_NOVELTY_CLAIMS register

No missing method details are invented for these papers; access is recorded
as-is. RoNeTC, RoeCi, GCLC were full-text reviewed OUTSIDE this repository
by the researcher workflow; the local Agent does not claim independent PDF
access.

```text
1. ACO (Acquisition Conditioned Oracle for Nongreedy Active Feature
   Acquisition), ICML 2024, PMLR 235
   ACO_ICML_2024_FULL_METHOD_REVIEW=PENDING
   PRIMARY_ABSTRACT_READ; OFFICIAL_FULL_PDF_TOOL_ACCESS_FAILED
   PRIORITY=MEDIUM_HIGH
   GATE_BLOCKING=false (main threat = generic non-greedy AFA novelty,
   already excluded from our claim; must still be reviewed before final
   first/novelty claims)

ACCESS_LIMITED_CRITICAL_PAPERS=1
RONETC_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW
ROECI_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW
GCLC_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW
```

## 6. Prospective Open-World Gate design revision (NOT executed)

The next Gate must include the following elements. This section revises the
prospective design only; it does not run the Gate and does not rewrite any
frozen contract.

```text
6.1 INDEPENDENT_NOVELTY_DETECTOR=true
    - utility acquisition policy and novelty detector stay separate;
    - Unknown truth may NOT train the utility selector;
    - whole-class held-out Unknown rotations remain evaluation-only.

6.2 POLICY_CONDITIONED_NOVELTY_CALIBRATION=REQUIRED
    - freeze the acquisition policy first;
    - calibration observation -> same acquisition policy ->
      post-acquisition representation/score -> calibrate novelty threshold;
    - test observation -> same frozen policy -> post-acquisition score ->
      calibrated threshold;
    - do NOT reuse the Basic-only threshold;
    - if policy/budget is selected using calibration data, require a
      separate held-out calibration protocol or pre-specified correction.

6.3 NON_CHEATING_PRE_ACQUISITION_ROUTER=true
    - router uses ONLY pre-acquisition runtime-visible state;
    - never actual T/R Evidence, GT, future correctness, True Unknown
      status, or actual future utility.

6.4 EVIDENCE_SUBSET_ANALYSIS (T and R are the only core families)
    - enumerate analysis states: NONE / T / R / TR;
    - measure unique recovery, shared recovery, TR-only recovery,
      redundancy, synergy;
    - do NOT assume greedy T->R is optimal.

6.5 READ_ONLY_EVIDENCE_ACQUISITION_ASSUMPTION=true
    - Evidence stays same-split, strictly past-only, runtime-legally
      available; acquisition must not causally modify target traffic.

6.6 UNKNOWN_ACQUISITION_BEHAVIOR_METRICS (mandatory)
    TRUE_UNKNOWN_ACQUISITION_RATE
    TRUE_UNKNOWN_POST_ACQUISITION_SCORE_SHIFT
    UNKNOWN_AUROC / UNKNOWN_AUPR / UNKNOWN_RECALL_AT_FIXED_KNOWN_FPR
    KNOWN_MACRO_F1 / FURK / EVIDENCE_RECOVERY_RATE / ACQUISITION_RATE_COST
    Purpose: ensure Known recovery does not simply pull True Unknown
    toward Known.

6.7 REQUIRED_LOW_COST_BASELINES
    BASIC_DIRECT_NOVELTY / ALWAYS_FULL_EVIDENCE /
    RANDOM_COST_MATCHED_ACQUISITION / LOW_CONFIDENCE_ACQUISITION /
    HIGH_ENTROPY_ACQUISITION / SUPERVISED_UTILITY_ACQUISITION /
    ORACLE_ANALYSIS_ONLY
    - an oracle using actual future outcomes must NEVER be described as
      deployable;
    - utility routing MUST be compared against generic difficulty routing
      (LOW_CONFIDENCE / HIGH_ENTROPY) — RoeCi establishes adaptive
      escalation by uncertainty/sample-complexity as prior art;
    - RoNeTC-style multi-view/dynamic-fusion literature: Related Work
      comparator, not necessarily an immediate exact implementation
      requirement.

6.8 FURK_DECOMPOSITION
    - report Known false-Unknown separately as
      RECOVERABLE_KNOWN_FALSE_UNKNOWN and RESIDUAL_KNOWN_FALSE_UNKNOWN;
    - do not report only the aggregate Known rejection error.
```

## 7. Prospective Continual experiment design revision (NOT executed)

Isolate Unknown-buffer purification with matched systems (same replay,
adaptation, training budget, label budget, update schedule):

```text
A. DIRECT_UNKNOWN_BUFFER + SAME_CONTINUAL_LEARNER
B. EVIDENCE_GATED_UNKNOWN_BUFFER + SAME_CONTINUAL_LEARNER
C. ORACLE_CLEAN_UNKNOWN_BUFFER + SAME_CONTINUAL_LEARNER

PRIMARY_PURIFICATION_METRICS=
  BUFFER_PURITY
  RECOVERABLE_KNOWN_CONTAMINATION
  TRUE_UNKNOWN_RETENTION
  LABEL_QUERY_EFFICIENCY
  NEW_CLASS_F1 / OLD_CLASS_F1 / ALL_CLASS_F1
  FORGETTING_BWT
  ADAPTATION_COUNT

Requirement: any gain must be attributable to Unknown-stream quality,
not to a different continual algorithm.
```

Prerequisite (before any full continual training): test whether the
Evidence Gate actually purifies the Unknown candidate stream
(Unknown-Candidate Purification Gate V1 — buffer-purity analysis only, no
continual model training).

## 8. RL status revision

```text
RL_IS_NOT_CORE_NOVELTY=true
RL_OPTIONAL=true
- the supervised utility selector (Gate 1B) is already strong;
- RL may be retained only if it improves the quality-cost/open-world
  frontier over: supervised utility selector + simple heuristic baselines;
- PPO/DQN/GRPO are NOT mandatory for paper validity.
```

## 9. Model B utility design note (future, non-frozen)

```text
MODEL_B_CONTINUOUS_UTILITY_STATUS=PROPOSED_NOT_FROZEN
CANDIDATE=expected post-acquisition task-loss improvement
          - lambda * acquisition cost
- the historical Gate 1B utility (HELP/NEUTRAL/HARM, +1/0/-1) is NOT
  changed;
- for open-world use, do NOT introduce an Unknown-dependent training
  target until the Open-World Gate establishes a leakage-safe formulation;
- Teacher remains NOT_UTILITY_GT.
```

## 10. Secondary analysis (not main novelty)

```text
EVIDENCE_SPECIALIZATION_AUDIT=PLANNED
PURPOSE=measure true-known-class x Evidence family x
  HELP/HARM/UNIQUE_HELP/NET_UTILITY; inspect within-class heterogeneity
INTERPRETATION_CANDIDATE=traffic Evidence utility may be mechanism-
  dependent AND instance-dependent
STATUS=EMPIRICAL_ANALYSIS_NOT_STANDALONE_NOVELTY
```

## 11. Plan-document policy applied

`docs/research_plan/experiment_protocol_v1.md` (Status: `FROZEN DESIGN /
NOT RUN`, DEC-0027) and `docs/research_plan/model_b_evidence_openworld_design.md`
(DEC-0025 source) are frozen historical contracts. They were **not
rewritten**. Per repository conventions (Material Deviation and Decision
Log in `research_plan_detailed.md`), this audit and a new non-frozen
addendum record the literature constraints and prospective design
revisions:

- `docs/research_plan/literature_novelty_reassessment_v1.md` — addendum
  (non-frozen draft; supersedes nothing).

## 12. Safety ledger

```text
OPEN_WORLD_GATE_STARTED=false
MODEL_B_TRAINING_STARTED=false
QWEN_API_CALLS=0
DEEPSEEK_API_CALLS=0
RL_TRAINING_STARTED=false
CONTINUAL_TRAINING_STARTED=false
COMMIT_CREATED=false
PUSHED=false
HISTORICAL_FORMAL_REPORTS_MODIFIED=false
```
