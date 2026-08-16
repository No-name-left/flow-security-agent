# Dataset-v4 / Model B Formal Experiment Protocol v1

> Status: `FROZEN DESIGN / NOT RUN`
>
> Decision: DEC-0027, 2026-08-16
>
> Scope: paper experiments, derived data views, evaluation isolation,
> baselines, metrics, statistical reporting, and low-cost Agent-policy gates.
> The canonical research meaning remains in
> [research_plan_detailed.md](research_plan_detailed.md); Dataset identity and
> split semantics remain frozen by
> [dataset_v4_split_protocol.md](dataset_v4_split_protocol.md).

## 1. Research question and contribution boundary

The paper studies an **Open-World Continually Evolving LLM Traffic Agent** whose
method core is:

```text
Evidence-Conditioned Open-World Traffic Recognition
+ Empirically Grounded Typed-Evidence Acquisition
+ Evidence-Gated Continual Evolution
```

It separates three states that a closed-set confidence score conflates:

- `BASIC_SUFFICIENT_KNOWN`: Basic is sufficient for a reliable Known decision;
- `RECOVERABLE_KNOWN`: Basic is under-observed, but legal typed Evidence can
  recover a Known decision;
- `TRUE_UNKNOWN`: a whole semantic class is held out and remains outside Known
  after useful Evidence recovery is completed or declined.

The three candidate contributions are therefore:

1. evidence-conditioned open-world recognition, measured especially by False
   Unknown on Recoverable Known (`FURK`) and Evidence Recovery Rate;
2. typed-Evidence acquisition whose operational targets come from OOF/
   cross-fitted predictive improvement and cost, not Teacher semantics;
3. continual evolution whose unknown buffer is cleaned by the Evidence gate
   before verified feedback, class registration, supervised adaptation, replay,
   and release testing.

These are candidate claims, not “first” claims. Closed-set classification,
open-set recognition, RL, continual learning, active acquisition, LLM use, and
an Agent wrapper are not individually claimed as novel.

## 2. Frozen data foundation

### 2.1 Source and taxonomy

```text
DATASET_V4_CORE=NF3-ToN-IoT
SOURCE_ARTIFACT_SHA256=53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78
SOURCE_ROW_ID_CONTRACT=NF3_TON_OBSERVATION_V1
CANONICAL_TAXONOMY_V1=Backdoor,Benign,Credential,DDoS,DoS,Recon_Scanning,Web_Injection
RAW_REPROCESSING_REQUIRED=false
```

Official labels are the classification oracle. DeepSeek/Teacher never creates
or repairs NF3 labels. The source mappings are frozen in the split protocol.
`mitm` and `ransomware` remain outside the core target taxonomy and may only
contribute legal label-free history.

The historical manifest field `UNKNOWN_CANONICAL_LABEL_N=9984` means
`OUT_OF_CORE_FINE_LABEL_POOL_N=9984`; it is not a Model B True-Unknown count or
prediction.

### 2.2 Immutable master split

```text
SPLIT_PROTOCOL=GROUPED_TEMPORAL_HASH_70_15_15_V1
SPLIT_SEED=20260816
ROW_MANIFEST_SHA256=faa5220beae65f06591e7ea399c59092985135b81860fcd2388f20cadaa7c095
TRAIN=19858267
VALIDATION=3809983
FINAL_TEST=3842026
```

The master split is immutable. Its private activity group is the frozen
five-minute block plus unordered endpoint pair; source-row, exact-duplicate
group, and activity-group cross-split overlaps are zero. It is a grouped hash
split with local temporal grouping, not a global chronological holdout.

Every later train, threshold, OOF, RL, or continual artifact is a **derived
view** of exactly one master partition. No experiment may rewrite master split
membership.

### 2.3 History scope

```text
EVIDENCE_HISTORY_SCOPE=WITHIN_SPLIT_STRICT_END_BEFORE_TARGET_START_V1
HORIZONS_SECONDS=10,60,300
```

Temporal and Relation contributors must be in the target's master split and
must satisfy `contributor.end < target.start`. Equal-time, overlapping, future,
and cross-split contributors are forbidden. Target GT, attack intervals,
rotation roles, and downstream outcomes never select history.

### 2.4 Duplicate-aware derived views

The master artifact contains `1,816,137` duplicate copies beyond the first
member in `480,040` exact groups. Group leakage is already prevented; prevalence
and optimization dominance are a separate question.

Before formal Model B fitting, materialize `DUPLICATE_AWARE_TRAINING_VIEW_V1`
from TRAIN only and compare:

1. one deterministic representative per exact group; and
2. duplicate-group weighting in which a group's total optimization weight is
   bounded independently of its multiplicity.

The low-cost B2 gate selects the primary optimization view before formal model
training. The untouched raw-prevalence view remains a secondary weighted
sensitivity analysis. Primary evaluation must report duplicate-group-balanced
metrics or an exact-deduplicated evaluation view in addition to raw-prevalence
metrics; repeated rows must not dominate the paper conclusion.

### 2.5 Feasibility evidence is not a formal result

The deterministic 24,000-row pilot reported:

```text
OOF_BASIC_MACRO_F1=0.9241027728324086
OOF_FULL_MACRO_F1=0.9542507313534688
RECOVERABLE_KNOWN_N=2879
RECOVERABLE_KNOWN_RATE=0.11995833333333333
UTILITY_AUROC=0.9559201214445113
UTILITY_AUPR=0.6823986368255095
DIRECT_UNKNOWN_AUROC=0.7583657442883499
EVIDENCE_CONDITIONED_UNKNOWN_AUROC=0.7683698955976005
DIRECT_FURK=0.3062080536912752
EVIDENCE_CONDITIONED_FURK=0.24161073825503357
ACQUISITION_RATE=0.1459902525476296
```

This is `PASS_WITH_LIMITATIONS`, not a paper benchmark. Recon_Scanning Unknown
separation was weak; Web_Injection improved Unknown AUROC/recall while FURK
could worsen; Credential improved FURK while fixed-FPR Unknown recall could
decline. “Full” was bounded sample-local Temporal+Relation. Single-family
ablation, additional seeds, group/block bootstrap, and formal cost sensitivity
have not run. No later document may silently promote these pilot values to
formal results.

## 3. Evidence and model contracts

### 3.1 Evidence families

- `Basic`: one model-safe current-flow card;
- `Temporal`: fixed, split-local, strictly-past 10/60/300-second aggregates;
- `Relation`: fixed, split-local, strictly-past bounded relation aggregates.

The first formal comparison is exactly `Basic`, `Basic+Temporal`,
`Basic+Relation`, and `Basic+Temporal+Relation`. Application, Payload, and RAG
are optional future families and cannot silently enter these experiments.

Semantic admissibility means legal/test-time/causal network meaning.
Operational utility means empirical predictive improvement. The latter must be
OOF/cross-fitted and must produce family-specific targets:

```text
U_T  = utility of acquiring Temporal from the current state
U_R  = utility of acquiring Relation from the current state
U_TR = utility of acquiring both when the protocol evaluates the joint state
```

Teacher `evidence_sufficient`, `missing_evidence`, or semantic recommendations
are never operational-utility ground truth.

### 3.2 Model B and novelty boundary

Model B candidates use a Qwen traffic representation `h`, a Known Fine Head,
and either a small utility head or an external selector. Unknown is not `K+1`.
Independent novelty candidates read Known logits/representation and the frozen
Evidence state after the recovery gate.

Required value-of-LLM comparisons are:

1. LightGBM on the same legal structured view;
2. one small neural traffic encoder (MLP, FT-Transformer, or small Transformer,
   selected before final runs);
3. frozen Qwen representation plus linear head;
4. Qwen LoRA Model B;
5. optional Model-A warm start, matched against fresh initialization.

If Qwen does not improve classification, utility, novelty, or continual
behavior against strong smaller baselines, the LLM-specific claim is reduced;
the evidence-conditioned method may still stand.

### 3.3 Four-action online policy

The fast online policy has exactly:

```text
STOP_AND_CLASSIFY
ACQUIRE_TEMPORAL
ACQUIRE_RELATION
ENTER_NOVELTY_DETECTION
```

`ENTER_NOVELTY_DETECTION` is a transition, not a prediction of Unknown. Runtime
owns availability, budget, no-repeat, causal Evidence execution, and trace
validation. The Agent orchestrates decisions; it does not replace the Known
classifier or novelty detector.

## 4. Partition and isolation matrix

| Master partition | Allowed uses | Forbidden uses |
| --- | --- | --- |
| TRAIN | classifier fitting; duplicate-aware views; TRAIN-only OOF utility targets; RL development episodes; continual development streams; replay | final model selection or paper final claims |
| VALIDATION | preprocessing/calibration fit only where preregistered; novelty candidate/threshold development using the frozen Known and held-out-development roles; utility validation; RL validation; Teacher-baseline evaluation; continual development validation | gradient updates for the evaluated formal model; any use of FINAL_TEST labels |
| FINAL_TEST | sealed static open-world evaluation; sealed continual stream | model/selector/policy fit; architecture choice; threshold tuning; prompt selection |

If static open-world and continual final evaluation require statistically
independent FINAL_TEST subsets, materialize deterministic, private-group-aware,
mutually exclusive subviews before either result is opened. The ratio and seed
are not yet frozen; they require a small tracked manifest and Decision before
final experiments.

Whole-class rotations are frozen as:

```text
R1=Credential
R2=Recon_Scanning
R3=Web_Injection
```

In a rotation the held-out class is absent from Known classifier training.
Frozen TRAIN/VALIDATION development roles may provide labeled held-out examples
for novelty candidate and threshold selection; FINAL_TEST never does. Held-out
dataset GT is visible only to offline development/evaluation and, later, to the
simulated verified oracle after an explicit label-query event. It never enters
runtime policy state.

## 5. Experiment 1 — Closed-set Model B and representation value

### Question

Does Qwen adaptation add useful Known-class representation beyond structured
and small-neural baselines under the same legal Basic view?

### Compared systems

- `M1`: LightGBM;
- `M2`: one small neural traffic encoder;
- `M3`: frozen Qwen representation + linear Fine Head;
- `M4`: fresh Qwen LoRA Model B;
- `M5`: optional Model-A warm start with an otherwise matched M4 budget.

All use the same class order, duplicate-aware TRAIN view, legal preprocessing,
and master VALIDATION/FINAL derived views. Warm-start comparisons match samples,
steps, optimizer budget, heads, and evaluation.

### Metrics and gate

Report Macro-F1, per-class F1, balanced accuracy, confusion matrix, NLL, ECE,
latency, throughput, and peak VRAM. Use at least three formal seeds. If M4/M5
does not offer a defensible advantage on later utility/novelty/continual tasks,
do not sell closed-set accuracy as an LLM contribution.

## 6. Experiment 2 — Typed Evidence utility and acquisition

### Evidence states

```text
BASIC
BASIC_PLUS_TEMPORAL
BASIC_PLUS_RELATION
BASIC_PLUS_TEMPORAL_PLUS_RELATION
```

Generate OOF/cross-fitted `U_T`, `U_R`, and `U_TR` from paired predictive
outcomes. No model may label a sample's utility after training on that sample.
The exact loss target and cost coefficient `lambda` remain preregistered tuning
choices; correctness recovery and delta-NLL must both be retained for analysis.

### Compared acquisition policies

- `E0`: Basic only;
- `E1`: Always acquire all available core Evidence;
- `E2`: random acquisition matched on rate and cost;
- `E3`: confidence/margin heuristic;
- `E4`: supervised empirical utility selector;
- `E5`: analysis-only oracle using hidden outcomes, never deployable.

Teacher and RL policies enter only in Experiment 5 after their own gates.

### Metrics and causal comparisons

Report Macro/per-class F1, recovery rate, acquisition rate, acquisition cost,
steps, utility AUROC/AUPR, calibration, and performance-cost frontier. Preserve
three comparisons: Basic vs Full (information value), Full vs adaptive
(selection/cost value), and random cost-matched vs utility (policy value).

## 7. Experiment 3 — Evidence-conditioned open world

This is the central experiment. Run R1/R2/R3 separately and aggregate only
after reporting class-conditional results.

### Novelty candidates

- `U0`: maximum softmax probability;
- `U1`: top-1/top-2 margin;
- `U2`: energy;
- `U3`: prototype or Mahalanobis distance;
- optional OpenMax only if simple candidates leave justified headroom.

### System comparisons

- `O1`: Basic → direct novelty;
- `O2`: always acquire Full → novelty;
- `O3`: confidence-gated acquisition → novelty;
- `O4`: supervised empirical-utility acquisition → novelty;
- `O5`: optional frozen Teacher policy baseline after cache generation;
- `O6`: learned fast RL policy after Experiment 5 training.

### Metrics and success gate

Report Unknown AUROC/AUPR, recall at fixed Known FPR, OSCR, Known Macro-F1,
FURK, Evidence Recovery Rate, acquisition rate/cost, steps, and latency. Report
overall and per rotation/class with confidence intervals.

The method gate requires a material FURK reduction without collapsing True
Unknown detection. A higher aggregate AUROC cannot conceal a class rotation
whose Known recovery or Unknown recall degrades materially.

## 8. Experiment 4 — Evidence-gated continual evolution

### Protocol A: quantitative sequential registration

Start with approximately five Known classes and introduce two attack classes
sequentially. Run at least these three orders:

```text
Credential -> Recon_Scanning
Recon_Scanning -> Web_Injection
Web_Injection -> Credential
```

Composition, private-group isolation, verified-label budget, replay budget, and
evaluation checkpoints must be materialized before runs; one favorable order is
not sufficient.

### Protocol B: end-to-end demonstration

Use four initial Known classes, then introduce the three frozen held-out classes
sequentially to produce model versions `v1`, `v2`, and `v3`. This is a systems
demonstration, not a substitute for Protocol A statistics.

### Compared continual systems

- `C0`: frozen model, no adaptation;
- `C1`: naive new-class-only supervised update;
- `C2`: balanced replay;
- `C3`: LwF/distillation baseline;
- `C4`: direct novelty buffer + the same replay adaptation as C5;
- `C5`: Evidence-gated residual buffer + the same replay adaptation as C4;
- `C6`: oracle-clean buffer + the same replay adaptation, analysis ceiling.

C4 and C5 must share adaptation code, capacity, replay, label budget, and update
schedule so that buffer quality is the causal difference.

Report new-class, old-class, and all-class F1; forgetting; backward transfer;
buffer purity/contamination; label queries; verified samples per registration;
time to discovery; adaptation events; and release failures. If clustering is
used, also report ARI/NMI/purity. Success requires a repeatable improvement in
at least buffer purity, label efficiency, or stable new-class learning without
unacceptable old-class regression.

### Experiment 4B: secondary simultaneous-unknown grouping

After sequential results are stable, preregister two-unknown mixtures such as
Credential+Recon and Recon+Web. Compare direct versus Evidence-gated buffers and
simple KMeans/GMM/HDBSCAN only as needed. Report ARI, NMI, purity, query cost,
and downstream registration quality. This does not block the core paper.

## 9. Experiment 5 — Fast Agent policy RL

### Status and purpose

```text
RL_STATUS=PLANNED_LOW_COST_AGENT_POLICY_COMPONENT_PENDING_FORMAL_GATE
LLM_LEVEL_RL=NOT_PLANNED_FOR_CORE
```

RL optimizes the already frozen Evidence/novelty control problem; it does not
learn attack semantics and never updates Qwen directly. Its state contains
`h` or an approved bounded representation, Known probabilities, confidence,
margin, entropy, `U_T`, `U_R`, novelty state, Evidence mask, availability,
history, and budget. It never contains GT, recoverability truth, or held-out
role.

Offline episodes expose cached Basic, Basic+Temporal, Basic+Relation, and Full
states. An action deterministically unlocks the corresponding cached Evidence
and recomputes allowed predictions. GT is available only to the environment's
reward calculation, never to the policy observation.

The reward credits correct Known/Unknown terminal outcomes and penalizes Known
misclassification, false Unknown, Evidence cost, and delay. Exact coefficients
must be preregistered and sensitivity-tested. OOF utility may be a state feature,
reward shaping signal, and supervised baseline; it is not an online oracle.

### Compared policies

- `P0`: confidence/margin heuristic;
- `P1`: supervised empirical-utility policy;
- `P2`: frozen DeepSeek Teacher policy baseline, if generated;
- `P3`: Double DQN; Dueling and prioritized replay are optional ablations;
- `P4`: optional Teacher behavior-cloning initialization followed by P3.

PPO, GRPO, RLAIF, direct Qwen RL, and large reward-model training are out of
scope. RL earns a prominent method role only if it improves the performance-cost
frontier over P0 and preferably P1 across seeds. Otherwise it remains a system
component or negative result, without invalidating Experiments 1–4.

### Slow evolution controller

A later controller may choose `WAIT`, `REQUEST_VERIFIED_LABEL`,
`REGISTER_NEW_CLASS`, or `TRIGGER_ADAPTATION` from buffer and release statistics.
It is secondary, conditional, and not a core-paper blocker. Learning after a
label remains supervised adaptation plus replay; the release gate stays
deterministic and immutable.

## 10. Auxiliary experiments

### A. Missing-Evidence robustness

Remove family availability under controlled, realistic capability conditions;
do not randomly delete arbitrary fields. Compare direct, available-full,
supervised utility, and RL policies. Report FURK, Unknown recall, Macro-F1,
acquisition failure, and cost.

### B. External-domain stress

Use other NF3 sources only after the core protocol is stable. Restrict to shared
classes where necessary, report mapping/support/calibration explicitly, and
treat poor transfer as a limitation. Do not restart dataset search or make
external stress a core dependency.

## 11. Statistical protocol

- Formal model comparisons use at least three independent seeds.
- RL and continual experiments use at least three policy/stream/order seeds;
  use five where cost permits.
- Never bootstrap individual rows as if they were independent.
- Use private activity groups or temporal blocks for bootstrap units.
- Report mean and 95% confidence intervals.
- Use paired resampling for Direct vs Evidence, confidence vs utility, utility
  vs RL, and direct-buffer vs Evidence-gated-buffer comparisons.
- Report both duplicate-group-balanced primary metrics and raw-prevalence
  secondary metrics.
- Any post-hoc analysis is labeled exploratory.

## 12. DeepSeek and semantic artifacts

The already frozen `teacher_cache_v1` sample list contains 2,000 request rows;
the semantic-admissibility request manifest contains 63 cells. Neither has
responses yet.

If separately authorized, responses may serve only as:

```text
TEACHER_SUPERVISOR_BASELINE
OPTIONAL_POLICY_DEMONSTRATION
OPTIONAL_IMITATION_INITIALIZATION
OFFLINE_SEMANTIC_REFERENCE
```

They cannot provide NF3 classification labels, operational utility, True
Unknown, recoverability, continual feedback, or reward ground truth. Historical
Model A Teacher caches are schema/population incompatible and are not reusable.

The current time-sensitive next action remains:

```text
GENERATE_PREPRICE_DEEPSEEK_CACHE_AND_SEMANTIC_REFERENCE
```

This protocol does not authorize or execute that action.

## 13. Materialization registry

Future large artifacts remain Git-external; tracked files contain only small
manifests, hashes, rules, and reports. Before formal runs, materialize and hash:

1. duplicate-aware TRAIN and evaluation views;
2. Basic, Temporal, and Relation cards;
3. OOF fold predictions and `U_T/U_R/U_TR` targets;
4. recoverability/reference-state tables;
5. per-rotation Known/True-Unknown derived views;
6. offline RL episode cache;
7. continual development/final stream manifests;
8. replay and verified-feedback query manifests;
9. optional Teacher responses and semantic reference.

None may alter `SOURCE_ROW_ID_CONTRACT_V1` or the master split.

## 14. Gate and execution order

| Gate | Required evidence | Failure response |
| --- | --- | --- |
| `M` | Qwen/small/frozen/fresh-warm matched value gate | reduce model complexity or LLM claim |
| `E` | single-family and combined OOF utility with robustness | keep only useful families or fall back to Basic |
| `O` | open-world FURK/Unknown tradeoff across rotations | revise selector/novelty, not labels or split |
| `C` | buffer purity/label efficiency/stable continual gain | report static method; do not claim continual evolution |
| `R` | RL frontier better than heuristic/supervised baselines | retain P0/P1; report RL negative result |

Execution order:

```text
B2-A  duplicate-aware/balanced derived views
B2-B  low-cost Model/LLM value gates
B3    single-family and combined OOF utility
B4    evidence-conditioned open-world evaluation
B5    fast RL policy comparison
B6    continual baselines
B7    Evidence-gated continual comparison
B8    optional multi-Unknown grouping
B9    optional slow evolution policy
B10   missing-Evidence and external-domain stress
```

The ordering does not authorize the next stage automatically. Each expensive
stage requires its preceding artifact and Gate review.

## 15. Frozen decisions and unresolved parameters

### Frozen

- Dataset artifact, taxonomy, source-row identity, master split, history scope,
  and three Unknown rotations;
- Known/recoverable/True-Unknown distinction and Unknown-after-Evidence order;
- Basic/Temporal/Relation core families and four online actions;
- OOF/cross-fitted operational-utility origin;
- five main experiments, two auxiliary experiments, baseline families, metrics,
  continual verified-oracle boundary, and statistical units;
- fast policy RL as a planned low-cost gated component; no LLM-level RL;
- Teacher/DeepSeek roles and non-GT limitations.

### Must be preregistered later

- duplicate-view winner; exact Basic serialization; model architecture and
  trainable modules; seeds beyond minimum; optimization budgets;
- utility loss, cost coefficients, selector threshold, and family availability;
- novelty algorithm and thresholds; any FINAL_TEST subview ratio/seed;
- continual stream sizes, query/registration criteria, replay ratio, release
  thresholds; RL reward coefficients and episode budgets.

No unresolved parameter permits tuning on FINAL_TEST.

## 16. Current status

```text
DATASET_V4_CORE_STATUS=FROZEN_PASS
MASTER_SPLIT_STATUS=FROZEN_PASS
HISTORY_PROTOCOL_STATUS=FROZEN_PASS
UNKNOWN_PROTOCOL_STATUS=FROZEN_DESIGN_NOT_RUN
CONTINUAL_PROTOCOL_STATUS=FROZEN_DESIGN_NOT_RUN
EXPERIMENT_PROTOCOL_STATUS=FROZEN_DESIGN_NOT_RUN
EXPERIMENT_1_STATUS=NOT_RUN
EXPERIMENT_2_STATUS=NOT_RUN
EXPERIMENT_3_STATUS=NOT_RUN
EXPERIMENT_4_STATUS=NOT_RUN
EXPERIMENT_5_STATUS=NOT_RUN
AUXILIARY_EXPERIMENTS_STATUS=NOT_RUN
TEACHER_CACHE_STATUS=SAMPLE_MANIFEST_READY_RESPONSES_NOT_GENERATED
SEMANTIC_REFERENCE_STATUS=REQUEST_MANIFEST_READY_RESPONSES_NOT_GENERATED
DEPRECATED_MODEL_A_TEACHER_GT_STATUS=LEGACY_ONLY_NOT_MODEL_B_GROUND_TRUTH
NEXT_ACTION=GENERATE_PREPRICE_DEEPSEEK_CACHE_AND_SEMANTIC_REFERENCE
```
