# Open-World Continually Evolving LLM Traffic Agent

> Status: **CANONICAL ARCHITECTURE SOURCE / PRE-IMPLEMENTATION DESIGN**
>
> Decision: **DEC-0024**
>
> Effective date: 2026-08-15
>
> Scope: Dataset-v4, Model B0, open-world continual evolution, optional Evidence acquisition, verified feedback and staged RL. This document does not authorize data download, model training, Teacher API calls, U_final access or RL.

## 1. Research reframe

The project mainline is now:

```text
Open-World Continually Evolving LLM Traffic Agent
```

The primary question is no longer whether an LLM can classify the six-class Edge closed set, nor whether an external Supervisor can always choose another Evidence tool. The project asks whether a shared LLM traffic representation can support multi-domain Known classification, Unknown rejection, verified new-class discovery, replay-protected parameter adaptation and a cost-aware long-horizon decision policy.

Active Evidence acquisition remains a candidate action family only if a low-cost operational utility pilot passes. Memory growth alone is not model evolution. Continual model evolution means a verified, regression-gated transition `Model B_t -> Model B_{t+1}` that updates trainable model parameters and/or heads.

## 2. Architecture audit that caused DEC-0024

### CURRENT_PLAN_ASSUMPTIONS

- Edge Model A classification and generative Evidence State jointly establish the first Agent foundation.
- Teacher semantic sufficiency can supervise runtime stop/acquire behavior.
- DeepSeek Supervisor is the default online Evidence-action selector.
- Model A LoRA is the default Model B initialization.
- Active Evidence and RLAIF-GRPO are required mainline stages.

### CURRENT_PLAN_CONFLICTS

- Model A closed-set performance is almost saturated even on the Teacher-defined Basic-insufficient subset, so that subset is not operationally difficult for classification.
- The LM Evidence-State output is schema-valid but fails on Basic-insufficient detection and missing-family prediction.
- A frozen-Qwen, limited-data linear probe is already very strong, weakening any claim that Edge closed-set classification demonstrates a uniquely necessary LLM/LoRA contribution.
- A permanent external-API Supervisor cannot itself evolve with the local model and would make the claimed self-evolving system externally dependent.
- The old sequence performs Evidence/RL work before proving that additional Evidence has measurable out-of-fold operational utility.

### MODEL_A_RESULTS_THAT_INVALIDATE_OLD_ASSUMPTIONS

| Result | Frozen value | Consequence |
| --- | ---: | --- |
| Formal Model A Macro-F1 | `0.9984831207613943` | Edge closed-set classification is a controlled baseline, not the main novelty. |
| Formal accuracy / micro-F1 | `0.9984524914887032` | Same conclusion; no cross-domain claim follows. |
| Raw Qwen zero-shot Macro-F1 | `0.5617499100465918` | Prompt-only zero-shot is weak, but is not an adequate sole baseline. |
| Frozen-Qwen linear probe | `0.9815630112607532` on 3,600 balanced TRAIN examples | Pretrained representation is already highly useful and strongly linearly separable for this task. The `0.016920` gap to Formal SFT is not an exact LoRA effect because training volumes differ. |
| Basic-sufficient classification Macro-F1 | `0.9988867951762442` | Basic classification is already near-saturated for most validation records. |
| Basic-insufficient classification Macro-F1 | `0.9973544973544973` | Teacher-defined insufficiency is not equivalent to low operational classification utility. |
| Evidence schema-valid rate | `1.0` | Schema validity alone is not reasoning validity. |
| Evidence sufficiency F1, overall | `0.9101351351351351` | Majority-positive aggregation is misleading. |
| Evidence sufficiency F1, Basic-insufficient | `0.0` | Current Model A Evidence-State is a substantive failure. |
| Gap micro-F1 | `0.0` | Missing-family behavior is not learned. |
| Basic-insufficient predicted sufficient | `532/537` | Current LM Evidence State cannot control runtime acquisition. |

Formal interpretation:

The evaluation artifact's strict convenience flag `BASE_REPRESENTATION_ALREADY_HIGHLY_SEPARABLE=false` used a preregistered `0.99` cutoff. DEC-0024's scientific interpretation is not a rewrite of that flag: Macro-F1 `0.981563` with only 600 records/class is strong evidence of high linear separability, but it did not cross the specific early-stop threshold.

```text
MODEL_A_KNOWN_CLASSIFICATION=PASS
MODEL_A_EVIDENCE_STATE=FAIL
TEACHER_SEMANTIC_SUFFICIENCY_EQUALS_OPERATIONAL_UTILITY=false
CLOSED_SET_CLASSIFICATION_AS_PRIMARY_INNOVATION=NO_GO
```

### COMPONENTS_TO_KEEP

- Dataset-v3 and Evidence-v2 provenance, observation eligibility and leakage contracts;
- deterministic Runtime authority and strict-past enforcement;
- model-visible versus private provenance separation;
- Observation versus Knowledge separation;
- hierarchical Known labels and post-hoc Unknown scoring;
- U_dev/U_final isolation and no final-set tuning;
- verified feedback, replay and regression-gated release;
- Model A checkpoint as an immutable controlled baseline and optional replay source.

### COMPONENTS_TO_DOWNGRADE

- Active Evidence acquisition: `PROVISIONAL`, contingent on Evidence Utility Gate;
- Model A warm start: `PROVISIONAL`, contingent on matched short-run ablation;
- DeepSeek: offline Teacher/demonstration/reviewer and optional baseline mode, not permanent runtime authority;
- RLAIF-GRPO: old Evidence-only mainline is `DOWNGRADED`;
- few-shot: `OUT_OF_SCOPE_FOR_CORE_PLAN`;
- complex clustering, learned Unknown heads and LLM policy RL: deferred until simpler baselines fail or pass their Gates.

### COMPONENTS_TO_REDESIGN

- Dataset-v4 as static splits plus a hidden-oracle continual stream;
- Model B0 as a shared representation with Family and Fine heads;
- Unknown Buffer, Verified Feedback Store, Replay Buffer, Class Registry and Model Version Registry;
- semantic class holdouts across datasets;
- operational Evidence utility via out-of-fold/cross-fitted probes;
- periodic supervised continual adaptation before policy RL;
- RL as an action policy over uncertainty, feedback and adaptation decisions.

## 3. Status registry

### CONFIRMED

- Model A metrics and limitations above;
- Qwen3.5-9B can run locally in the current environment;
- multi-dataset and open-world class-holdout direction;
- verified feedback and no-self-label principles;
- periodic/episodic adaptation with replay as first baseline;
- post-hoc Unknown baselines over representation/logits;
- Runtime as deterministic permission and release authority.

### PROVISIONAL

- final Dataset-v4 source composition and canonical taxonomy;
- existence and magnitude of Evidence operational utility;
- Evidence Decision Head;
- Model A warm start;
- best Unknown score, clustering method and fusion;
- RL algorithm, reward weights and whether RL ever updates Qwen LoRA;
- final replay ratio and release tolerances.

### NO-GO / DEPRECATED

- Model A generative Evidence State as a valid runtime sufficient/insufficient detector;
- Teacher sufficiency as operational Evidence utility ground truth;
- Edge closed-set classification as the main contribution;
- few-shot as a core research line;
- old Evidence-only RLAIF as the mainline;
- permanent DeepSeek API dependence as the system's self-evolving controller;
- model confidence or self-prediction as training ground truth.

## 4. Three-plane system architecture

### Plane A: Traffic Representation / Perception

Model B0 starts from:

```text
Qwen3.5-9B frozen base
+ trainable LoRA
        |
        v
shared hidden representation h
├─ Family Classification Head
├─ Fine Classification Head
├─ Energy / MSP / Prototype Unknown scores from h and logits
├─ optional Evidence Decision Head [only after Utility Gate]
└─ frozen original LM Head
   └─ explanation / structured descriptive state only
```

Qwen is described as a heterogeneous traffic representation learner, not merely a label generator. Candidate model-visible inputs are Basic, Packet/Payload, Application, Temporal, Relation and stage-legal Knowledge. Family and Fine heads are initially small linear heads.

`FAMILY_ONLY` samples train the Family Head but mask Fine loss. `EXACT` samples may train both. `AMBIGUOUS` and `UNSUPPORTED` mappings are excluded from supervised classification by default.

The LM Head has no critical runtime control authority until a capability-specific validation proves it. Model A's current generative Evidence-State output remains a failed baseline.

### Plane B: Agent Control

The bounded action space starts with:

```text
CLASSIFY_KNOWN
REJECT_AS_UNKNOWN
DEFER_TO_UNKNOWN_BUFFER
QUERY_KNOWLEDGE
REQUEST_ANALYST_FEEDBACK
```

Only if the Evidence Utility Gate passes, add:

```text
ACQUIRE_PACKET_PAYLOAD
ACQUIRE_APPLICATION
ACQUIRE_TEMPORAL
ACQUIRE_RELATION
```

Future gated actions are `PROPOSE_NEW_CLASS` and `TRIGGER_ADAPTATION`. An Agent may select one legal action; Runtime performs it.

Runtime exclusively owns Evidence retrieval, capability checks, strict-past validation, duplicate blocking, budgets, future-information isolation, hidden-oracle access, model-version switching, checkpoint release, rollback and trace integrity. No model or external provider can bypass it.

### Plane C: Evolution

```text
Model B0
→ deployment-style stream
→ Known errors / Unknown / drift observations
→ Unknown Buffer + Experience Buffer
→ verified feedback
→ class confirmation and adaptation batch
→ old-class replay
→ update LoRA and/or Family/Fine heads
→ old/new/Unknown/cross-domain regression suite
→ release or rollback
→ Model B1 → Model B2 → ...
```

The evolution plane contains separate, versioned stores:

- `Unknown Buffer`: rejected/deferred observations, embeddings, scores, stage and feedback status;
- `Experience Buffer`: state/action/eventual verified outcome for policy learning;
- `Verified Feedback Store`: labels returned only after a legal feedback event;
- `Replay Buffer`: representative old-class training observations;
- `Class Registry`: canonical semantic classes and activation version;
- `Model Version Registry`: parentage, data/config digests, Gates, release and rollback state.

## 5. DeepSeek role

DeepSeek is repositioned as:

```text
OFFLINE TEACHER
+ POLICY DEMONSTRATION SOURCE
+ SEMANTIC REVIEWER
+ OPTIONAL SUPERVISOR BASELINE
```

It may assist a small Evidence semantic review, hard-example reasoning, early policy demonstrations or review of a new-class proposal. It must not replace the Qwen classifier, receive hidden GT for runtime decisions, label all Evidence states, become the mandatory online controller or directly release a model version.

The existing Supervisor path remains useful as a historical/baseline mode. The final evolving policy should be locally trainable and evaluated against a strong heuristic.

## 6. Dataset-v4 source and compatibility protocol

### Candidate roles

- Primary preflight: CICIDS2017, CSE-CIC-IDS2018 and ToN-IoT;
- Legacy controlled source: Edge-IIoTset-clean;
- Fallback/gap filling: Bot-IoT, UNSW-NB15, CIRA-CIC-DoHBrw-2020 and USTC-TFC2016.

No source is pre-approved for full processing. Initial compatibility work uses a few captures/runs and hundreds of target sessions, including dozens per major source class.

### Source Compatibility Gate

Each source reports `PASS`, `PASS_WITH_LIMITATIONS` or `FAIL` on:

1. raw PCAP/log/official-label availability and asset identity;
2. official GT unit and deterministic mapping to project sessions;
3. packet/flow/session/run/capture granularity;
4. model-visible observational support for source labels;
5. IP, time, capture, dataset, schedule, filename and propagation leakage;
6. multiple run/capture/group units for defensible splits;
7. `EXACT | FAMILY_ONLY | AMBIGUOUS | UNSUPPORTED` taxonomy mapping;
8. legal Payload, Application, Temporal and Relation capability masks;
9. accepted storage, scan and API budget.

Capture-level propagation plus unsupported session evidence is a hard fail. An unavailable optional Evidence family may be an explicit limitation; unknown GT semantics or unrecoverable leakage may not.

## 7. Unified data model

```text
Raw PCAP / Logs / Official GT
→ dataset-specific GT Adapter
→ SourceAttackEvent [private]
→ Common Sessionizer
→ CanonicalSession
→ CanonicalLabel
→ CanonicalEvidenceBundle
→ Static Split + Continual Stream Assignment
```

`SourceAttackEvent` holds dataset/capture, source label, event interval, attacker/victim sets, protocol constraints, source-flow reference and GT provenance. It is private.

`CanonicalSession` freezes bidirectional identity, direction, packet order, start/end, source spans and capability masks. Official flow rows are not automatically project sessions. A source that cannot reconstruct a compatible session may be classification-only auxiliary data, not an Agent/Temporal/Relation/continual-stream source.

Label assignment emits `source_label`, `canonical_family`, optional `canonical_fine`, `mapping_quality` and `assignment_quality`. Only `HIGH_CONFIDENCE` assignment enters main supervision. Direct evidence must be unanimous unless official semantics explicitly justify another aggregation rule.

Private provenance and model-visible Evidence are physically separated. Dataset/capture, absolute time, raw IP, attack schedule, attacker/victim, source label, GT evidence and split group never enter the model-visible envelope.

## 8. Provisional canonical taxonomy

Level 0 is `BENIGN | MALICIOUS`. Provisional Level-1 families are:

- BENIGN;
- AVAILABILITY / DoS-DDoS;
- RECONNAISSANCE / SCANNING;
- CREDENTIAL_ACCESS;
- WEB_APPLICATION_ATTACK;
- MALWARE_BOTNET_C2;
- INFILTRATION_EXFILTRATION;
- EXPLOIT_BACKDOOR, only when GT and observation support it;
- MITM, only when Relation evidence and sample support are defensible.

Level-2 fine labels are frozen only after source preflight. Fine loss is ON only for `EXACT` mappings. Family loss remains available for `FAMILY_ONLY` mappings. Semantic synonyms must share the same K/U role across datasets.

## 9. Model B0 and warm-start Gate

Model B0 is a static foundation, not the final system. It must compare two matched short pilots:

- Run A: base Qwen + fresh LoRA + fresh heads;
- Run B: Model A LoRA initialization + matched fresh/expanded heads.

Both use the same pilot records, steps, learning rate, heads and evaluation. Model A warm-start is selected only if it improves convergence or legal validation without an Evidence/Unknown bias and passes Edge regression. Otherwise Model B0 starts fresh from the base model. Model A remains a baseline and optional replay source either way.

## 10. Evidence Utility Preflight

### Semantic relevance is not operational utility

Experts or a Teacher may judge whether an Evidence family is mechanistically relevant. They cannot declare that it improves an unseen classifier's decision.

For hundreds of preflight sessions, construct Basic and Basic plus one legal family at a time. Extract frozen-Qwen representations once, then use stratified 5-fold out-of-fold probes or equivalent cross-fitting. A sample's utility result must be produced by a probe that never trained on that sample.

For Evidence family `j`:

```text
Delta_j = CE_loss(Basic) - CE_loss(Basic + E_j)
```

Record accuracy, Macro-F1, cross-entropy, correctness flips and confidence change. Cost-adjusted utility may later be `Delta_j - lambda * cost_j`, but `lambda` and hard thresholds are frozen only after the pilot.

`ACTIVE_EVIDENCE_MAINLINE=GO` requires stable, repeatable gain on at least one meaningful difficult class/subset, a bootstrap interval not materially centered across zero, and the same direction under a second seed or reference model. If Basic is already saturated and all extra Evidence families have negligible benefit, Active Evidence becomes explanation-only and no Evidence Decision Head or Evidence RL is built.

If the Gate passes, first fit a small balanced Evidence Decision Head on frozen representations. It predicts `STOP/ACQUIRE` and multi-label candidate families. Failure at this stage diagnoses targets, representation or evidence construction; it does not justify immediate 9B retraining.

## 11. Open-world protocol

Before training, freeze semantic-class partitions:

- `K0`: initial Known classes;
- `U_dev`: whole classes for Unknown method and threshold development;
- `U_final`: different whole classes, sealed until final evaluation;
- `U_inc_1, U_inc_2, ...`: classes revealed progressively in the continual stream.

Holdouts operate on canonical semantic classes across all datasets. A synonym cannot be in K0 through one source and Unknown through another.

Where support permits, separately report unknown subtype (new fine label within a Known family) and unknown family (family absent from K0).

The first detector compares MSP, Energy and normalized cosine Prototype Distance from Known logits/representations. U_dev selects thresholds; U_final never does. Simple fusion is attempted only after complementary errors are demonstrated. Report AUROC, AUPR, FPR@95TPR, Known Macro-F1, Unknown recall/precision, open-set F1 and, if practical, OSCR.

## 12. Continual stream, feedback and class discovery

Dataset-v4 contains both static splits and an ordered deployment-style stream. At `t0`, Model B0 knows K0. Later stages mix Known traffic, domain drift and first appearances of `U_inc_t`. Future GT is hidden.

`REQUEST_ANALYST_FEEDBACK` is the only benchmark event that may reveal the hidden canonical label, simulating analyst, sandbox, threat intelligence or delayed incident response. Confidence is not GT.

Unknown samples enter the Unknown Buffer. Initial discovery uses a simple density clustering baseline such as HDBSCAN/DBSCAN where available; representative queries use medoids or nearest-to-centroid samples. Cluster compactness alone never registers a semantic class. `REGISTER_NEW_CLASS` requires multiple consistent verified labels and a reviewed Class Registry change.

Continual adaptation is episodic, not per-packet or per-session. Each update uses verified new-class examples plus balanced old-class replay, expands the Fine Head from K to K+1 as needed, and tests head-only versus LoRA-plus-head updates. The frozen base remains frozen.

Release Gate evaluates old-Known regression, new-class validation, Unknown validation, cross-domain performance and forgetting. Tolerances are pre-registered after the pilot. Failure rolls back to `B_t`; pass releases `B_{t+1}`.

## 13. RAG and stage-aware knowledge

Knowledge RAG remains separate from Observation Evidence and is most relevant to Unknown investigation, semantic interpretation and analyst support. Each stream stage uses a versioned `RAG_VERSION_t` or equivalent future-knowledge exclusion. Before a class is revealed, the KB cannot expose its future canonical label/signature in a way that invalidates Unknown evaluation.

## 14. RL repositioning

RL learns a decision policy; it does not invent new attack semantics. Verified-label continual adaptation remains supervised/contrastive/LoRA-based.

The state may include Known logits, MSP/Energy/Prototype scores, representation summary, Evidence availability/acquisition history, Unknown-cluster statistics, feedback status, analyst/compute budget, recent error/unknown rate, time since update and current model version. GT is never part of the state.

Reward depends on eventual verified outcomes: correct Known/Unknown decisions, timely new-class discovery and retained performance, minus unnecessary Evidence, query, compute, false-Known, false-registration and forgetting costs. Model confidence is not positive reward by itself.

The staged policy program is:

1. `RL-0 HEURISTIC`: strong deterministic thresholds, buffering, query and adaptation rules;
2. `RL-1 LOW-COST POLICY`: frozen Qwen plus a small policy head/network; choose bandit or sequential RL only after the environment shows whether actions affect future state;
3. `RL-2 LLM POLICY ADAPTATION`: Qwen policy LoRA with PPO/GRPO or another outcome-RL method only if RL-1 passes, delayed reward is trustworthy, trajectories and GPU budget are adequate, and the advisor confirms this interpretation.

RL-1 must outperform the Heuristic reproducibly on long-term classification, Unknown handling, discovery delay, analyst queries, Evidence cost, update count, forgetting and total compute. Otherwise RL remains a negative result and RL-2 is not run.

## 15. Advisor confirmation required

```text
ADVISOR_CONFIRMATION_REQUIRED=true
```

Confirm whether “use RL so the model continually evolves” means:

- A, the executable default: RL controls actions while verified-label supervised continual learning updates attack representations/classes; or
- B, a high-cost requirement: RL itself must update Qwen traffic representation/classification parameters.

The plan adopts A until explicit confirmation. B belongs to RL-2 and is not authorized by this design.

## 16. LLM value ablation

Model B must compare:

1. a strong lightweight structured classifier such as LightGBM on legal deterministic features;
2. frozen-Qwen representations plus linear Family/Fine heads;
3. Qwen + LoRA Model B0;
4. optionally, a compact traffic sequence encoder if implementation cost is reasonable.

The key comparisons are cross-domain transfer, Unknown AUROC/FPR, sealed U_final, continual new-class adaptation, low-label adaptation and representation robustness—not only pooled IID classification. If Qwen does not provide a meaningful advantage there, the paper must narrow claims about LLM necessity.

## 17. Research questions and provisional contributions

### RQ1 — Static foundation

Does an LLM-based shared representation support reliable multi-domain Known family/fine classification, cross-domain generalization and open-set scoring beyond strong lightweight and frozen-representation baselines?

### RQ2 — Open-world continual evolution

Can the system detect Unknown traffic, obtain bounded verified feedback, register a new class, adapt with replay and preserve old-class capability under domain drift?

### RQ3 — Agent policy / RL

Does a learned long-horizon policy outperform a strong heuristic on accuracy, Unknown handling, query/Evidence cost, adaptation timing and forgetting?

Evidence actions enter RQ3 only if the Utility Gate passes.

Provisional contributions are: a rigorous multi-domain open-world traffic benchmark pipeline; a hierarchical LLM shared representation evaluated against strong non-LLM/frozen baselines; a verified-feedback/replay/release continual loop; and, only if RL-1 passes, a cost-aware continual policy. Engineering alone and failed/Gated modules must not be advertised as algorithmic contributions.

## 18. Research guardrails

1. Never infer session GT from a source/capture label without a granularity and mapping Gate.
2. Check sample granularity before full processing.
3. Do not treat Teacher semantic judgment as operational utility.
4. JSON/schema validity is not Evidence reasoning validity.
5. Generate sample utility only with OOF/cross-fitting; the utility model must not train on that sample.
6. Never tune an Unknown threshold on U_final.
7. Prevent future Unknown leakage through another dataset, taxonomy or RAG version.
8. Never use model prediction/confidence as self-training GT.
9. Do not weaken the heuristic or manufacture environment complexity to make RL look useful.
10. Compare LLMs with frozen-Qwen linear and strong lightweight baselines, not only zero-shot prompting.
11. Every high-cost module requires a cheap pilot.
12. A core No-Go removes or downgrades the route; it does not trigger sunk-cost continuation.

## 19. Phase order and cheap Gates

| Phase | Work | Gate / status |
| --- | --- | --- |
| 0 | Freeze Model A success and failure | **COMPLETE** |
| 1 | Source preflight: CICIDS2017, CSE-CIC-IDS2018, ToN-IoT, Edge legacy | Source Compatibility Gate; no full download/scan |
| 2 | Evidence Utility Pilot | OOF frozen-representation probes; Active Evidence Go/No-Go |
| 3 | Dataset-v4 full build | Only accepted sources; static + K0/U_dev/U_final/U_inc stream |
| 4 | Model B0 | fresh-vs-warm-start Gate, Known/Family/Fine, Unknown baselines, LLM value ablation |
| 5 | Open-world continual baseline | Unknown Buffer, verified feedback, clustering, replay adaptation, Release Gate; no RL |
| 6 | RL-1 | Heuristic vs low-cost policy; RL Go/No-Go |
| 7 | Conditional enhancements | Evidence Agent, RAG enhancement or RL-2 only after their Gates |
| 8 | Final evaluation | sealed U_final, ablations, statistics and writing |

High-cost unvalidated items are full external Teacher labeling, full multi-dataset SFT, complex continual methods and Qwen policy RL. None is authorized before its cheap Gate.

## 20. Immediate stop point

```text
MODEL_A_ROLE=LEGACY_CONTROLLED_DOMAIN_AND_BASELINE
MODEL_A_EVIDENCE_STATUS=FAIL
DATASET_V4_STATUS=DESIGNED_PREFLIGHT_NOT_STARTED
CANONICAL_TAXONOMY_STATUS=PROVISIONAL
UNKNOWN_PROTOCOL_STATUS=DESIGNED_NOT_RUN
CONTINUAL_STREAM_STATUS=DESIGNED_NOT_BUILT
EVIDENCE_UTILITY_GATE_STATUS=NOT_RUN
ACTIVE_EVIDENCE_STATUS=PROVISIONAL_PENDING_GATE
DEEPSEEK_ROLE=OFFLINE_TEACHER_DEMONSTRATION_REVIEWER_AND_BASELINE
MODEL_A_WARM_START_STATUS=PROVISIONAL_PENDING_ABLATION
CONTINUAL_ADAPTATION_STATUS=DESIGNED_NOT_RUN
RL_0_HEURISTIC_STATUS=PLANNED_BASELINE
RL_1_LOW_COST_POLICY_STATUS=CONDITIONAL_NOT_RUN
RL_2_LLM_POLICY_STATUS=HIGH_COST_PROVISIONAL_NOT_AUTHORIZED
FEW_SHOT_STATUS=OUT_OF_SCOPE
RLAIF_OLD_STATUS=DOWNGRADED
```

The next separately authorized action is Source Compatibility Preflight plus a bounded Evidence Utility Pilot design. No dataset download, PCAP processing, Teacher batch, Model B training, RL or U_final access is authorized here.
