# Near-First Training and Open-World Protocol v1

> Status: **FROZEN MODEL A HISTORICAL EXECUTION CONTRACT / DEC-0025 OVERRIDDEN FOR MODEL B**
>
> Protocol date: 2026-08-11; implementation status revalidated 2026-08-15
>
> Scope: the completed Edge-IIoTset Model A data/SFT contract and its historical follow-on design. Model B/open-world execution follows DEC-0025 and requires a future versioned protocol after Dataset-v4 formalization and low-cost Gates.
>
> State: `MODEL_A_SFT_RUN=true`; `MODEL_A_EVALUATION_COMPLETE=true`; `MODEL_A_EVIDENCE_STATE=FAIL`; `RL_RUN=false`; `DATASET_V4_BUILD_STARTED=false`; `MODEL_B0_TRAINING_STARTED=false`.
>
> Authority: the [canonical research plan](../research_plan/research_plan_detailed.md) is highest. The [Model B design](../research_plan/model_b_evidence_openworld_design.md) and [open-world continual design](../research_plan/open_world_continual_agent_design.md) supersede this file for Model B phase order, DeepSeek role, Evidence utility, novelty, continual evolution and RL. This file remains authoritative only for Model A lineage/provenance.

> **DEC-0021 EXECUTION OVERRIDE:** the old 11-class PLAN_B population, Teacher V3 targets, `NEAR_SFT_CORPUS_V2`, validation artifact and `NEAR_SFT_CONFIG_V1` authorization are superseded historical inputs. No formal SFT may start until Task Definition v2, Observable Dataset v3, Evidence-v2, Teacher-v2 and corpus v3 pass a new acceptance. Architecture, Near-first order, DEC-0020 classification/sufficiency decoupling and U_final isolation remain frozen.

> **DEC-0024 MODEL B OVERRIDE:** Model A Formal SFT/evaluation are complete. Its Known classification passes, but generative Evidence State fails (`Basic-insufficient sufficiency F1=0`, `gap micro-F1=0`). Sections that make Active Evidence, DeepSeek online Supervisor, Evidence-only RLAIF, few-shot onboarding or Model A warm-start mandatory are historical and do not authorize those stages. The current order is source preflight → OOF Evidence Utility Gate → Dataset-v4 → static Model B0/Unknown/LLM-value ablations → non-RL verified-feedback continual baseline → RL-1 only if justified. RL-2 requires a prior Gate and advisor confirmation.

> **DEC-0025 HISTORICAL MODEL B OVERRIDE:** official NF3-ToN final processed data is the Dataset-v4 core priority. Model B distinguishes Basic-sufficient Known, recoverable Known and whole-class held-out True Unknown; novelty runs only after the Evidence gate. Operational utility comes from OOF/cross-fitted decision improvement, never Teacher-v2 semantic state. DEC-0025's then-current order ended in optional small RL; the immediately following DEC-0027 override replaces that phase order. All conflicting sections below are historical and do not authorize execution.

> **DEC-0027 FORMAL EXPERIMENT OVERRIDE:** [Experiment Protocol v1](../research_plan/experiment_protocol_v1.md) supersedes the preceding historical Model B phase sentence. It freezes five formal experiments, duplicate-aware derived views, group-aware statistics, matched continual comparisons, and fast four-action policy RL as `PLANNED_LOW_COST_AGENT_POLICY_COMPONENT_PENDING_FORMAL_GATE`. LLM-level PPO/GRPO/RLAIF remains outside the core. This historical Model A protocol does not authorize any Model B run.

## 1. Status vocabulary

- **FROZEN**: the architecture, permission boundary or execution order cannot change without a new canonical Decision.
- **CURRENT DEFAULT**: the first implementation choice; it may change only through the validation-safe procedure defined here.
- **VALIDATION TUNABLE**: a bounded, preregistered choice using legal train/validation data, never formal test or `U_final`.
- **DEFERRED**: outside the first Near end-to-end completion condition.
- **OPTIONAL**: may be skipped without blocking the first Near mainline.

Freezing this protocol by itself does not claim that training has run or that planned capabilities are implemented. Verified implementation selections and remaining blockers are recorded in Section 18 and PROJECT_HANDOFF; formal SFT/RL status remains independently gated.

## 2. ONE_MAINLINE_FIRST

**[FROZEN]** The first complete research route is Edge-IIoTset **Near**. Do not develop Near, Far, Mixed, IoT-23, several RL methods, several Unknown methods and several tokenizer methods as simultaneous first-class tracks.

Near must first produce:

1. real training checkpoints;
2. closed-set and open-world results;
3. complete Basic/Fixed Full/RulePolicy/DeepSeek Flash Supervisor results;
4. 1/5/10-shot Class Memory adaptation results.

Only after `NEAR_MAINLINE_COMPLETE=true` may the project resume Pure Generative SFT ablation, DPO, Far, Mixed, IoT-23, tokenizer ablation, QLoRA, thinking-on, low-resource stress, learnable Agent policy RL or continual LoRA. Far and Mixed retain their frozen K/U roles, but require their own legal corpora and checkpoints; a Near checkpoint is not their formal known-class model.

## 3. Frozen Near Task Definition v2 data protocol

| Item | Frozen value |
| --- | --- |
| Dataset | Edge-IIoTset, with documented single-capture/run limitations |
| Preset | Near |
| Seed | `20260809` |
| Physical split | `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2` |
| Dataset population | Observable Dataset v3, same eligibility contract across train/validation/test |
| Split default | preserve `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`, then filter each split |
| SFT universe | eligible TRAIN sessions from `FINAL_MAIN_CLASSES` only |

`MAX_MAIN_CLASSES=8`; candidates:

- DDoS_HTTP
- DDoS_TCP
- MITM
- Normal
- Password
- Port_Scanning
- SQL_injection
- Vulnerability_scanner

Final main classes may be reduced to seven or six only by pre-model eligibility, split support and evidence-diversity gates. Backdoor is a Long-Horizon Temporal Case Study. Uploading and Ransomware are Observability-Limited/Abstain auxiliary classes. All three have `classification_ce_eligible=false` outside a future explicitly scoped case-study task.

`U_dev`: DDoS_ICMP, OS_Fingerprinting.

`U_final`: DDoS_UDP, XSS.

Validation, test, `U_dev` and `U_final` are forbidden from Teacher-v2 and the SFT corpus. Preserve the old split then filter by default; only an unusable per-class split support result may trigger a deterministic grouped/chronological v3 assignment before model runs. Random row splitting and model-driven data selection are prohibited.

## 4. Formal model and role separation

### 4.1 Qwen Traffic Expert

**[FROZEN]** The primary model is official `Qwen/Qwen3.5-9B` revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`, used text-only in non-thinking/direct-response mode. It is the first classifier, not a traditional-classifier reviewer.

The formal trained model is:

```text
frozen Qwen language base
+ trainable LoRA adapters
+ trainable Fine Classification Head
+ retained original LM Head
```

The language base, vision encoder and multimodal alignment components stay frozen. Embeddings and the original LM Head are frozen by default. The trainable components are LoRA adapters and one Fine Classification Head.

### 4.2 Fine Classification Head

**[FROZEN]** Known fine classification is produced by a task-output head over the session representation:

```text
h_session → Linear(hidden_size, |K_known|) → fine logits
```

The first version is a simple Linear head, not a deep MLP and not an attention head. The Fine Head is the single formal fine-class decision source for the trained multi-task model.

No separate Coarse Head is added. Coarse output is derived by the frozen deterministic fine-to-coarse mapping, preventing mutually inconsistent fine and coarse heads.

### 4.3 Original LM Head

The original LM Head remains available for concise Evidence State generation:

- optional brief behavior summary;
- supporting evidence;
- missing evidence;
- evidence sufficiency;
- gap type;
- backoff-related Evidence State.

It must not freely generate an independent competing `fine_class`. Runtime combines Fine Head results and LM-generated Evidence State into one Traffic Expert Result.

Raw Qwen has no Fine Head. Its baseline may use a classification-capable generative prompt; its interface is therefore not identical to the trained custom-head model, and no extra head is trained merely to make the raw baseline look identical.

### 4.4 Session representation and pooling

Pooling is **[VALIDATION TUNABLE]** among:

1. last meaningful input token;
2. a dedicated classification marker (**CURRENT DEFAULT**);
3. a minimal mean/other simple pooling method.

Select `CLASSIFICATION_POOLING_V1` through small train/validation-safe stability, representation consistency and classification validation checks. Do not use formal test or `U_final`.

### 4.5 Qwen3.5 LoRA target inventory

The model is not assumed to be a standard all-attention Transformer. The audited language path contains 24 Gated DeltaNet layers, 8 full gated-attention layers and FFN projections. LoRA target selection must use the real `named_modules()` inventory in `reports/model_readiness/qwen35_9b_model_inspection.json`; do not hard-code only `q_proj/k_proj/v_proj/o_proj` and claim the language backbone is covered.

The exact target set, rank, alpha and dropout are **[VALIDATION TUNABLE]**. Any selected set must record matched module names/counts, trainable parameter count and a fail-fast assertion that the intended families are actually attached.

## 5. Serialization, Prompt and schema freeze

The official Qwen3.5 tokenizer is **[FROZEN DEFAULT]**. Training a traffic-specific tokenizer is **[DEFERRED ABLATION]**.

Before corpus materialization, compare only:

- current model-safe serialization;
- compact model-safe serialization.

Compact serialization may remove redundant keys, repeated punctuation and uninformative wording. It must not remove legal Evidence, change values/units/order or alter semantics. The selected form becomes `SERIALIZATION_V1`.

Before formal SFT corpus v3 generation, freeze and fingerprint:

- Basic-v2 Traffic Expert Prompt;
- Fine class map and deterministic fine-to-coarse map;
- Evidence State response schema v2 with multi-gap, primary gap and recoverability;
- serialization v1;
- classification marker/pooling contract;
- model-safe Observation/Knowledge distinction;
- Evidence stage schema and missing-capability behavior.

Prompting remains concise, non-thinking and direct-response. Do not request long Chain-of-Thought, include dataset/capture hints, or embed encyclopedia material in the system prompt.

## 6. Evidence-v2 states and corpus permissions

A legal Dataset v3 TRAIN session creates exactly one Basic-v2 primary and at most one or two meaningful cumulative auxiliary states. Basic-v2 is cheap-but-useful: session summary, first-eight packet metadata, packet-index-aligned bounded sanitized payload and cheap deterministic Application metadata. Auxiliary states follow real unresolved gaps; they are not random masks and do not enumerate all family combinations.

Evidence families are fixed:

| Domain | Families |
| --- | --- |
| Observation | `PACKET_PAYLOAD`, `APPLICATION`, `TEMPORAL`, `RELATION` |
| Knowledge | `KNOWLEDGE` |

Temporal-v2 supports fixed 10/60/180/300 second strictly-past windows. Relation-v2 may include time-linked ARP/link-layer and other lawful relations without changing the target session definition. Payload rows must carry explicit session ID, packet index, direction, relative time, protocol, presence/length, sanitized text and sanitizer version.

The old stage table remains historical only:

| Stage | Evidence |
| --- | --- |
| 0 | Basic-v2: summary + packets 1–8 metadata + packet-aligned sanitized payload + cheap Application |
| 1 | + packets 9–16 |
| 2 | + strictly past-only Temporal Context |
| 3 | + anonymous Graph/Relation Context |
| 4 | + structured Application Evidence |
| 5 | + bounded Sanitized Payload |
| 6 | + Knowledge RAG Evidence |

Only genuinely AVAILABLE, materialized and model-safe Evidence may appear. Old PLAN_B Application/Payload sidecars lack the v2 population and packet-alignment contract and cannot be reused as formal v2 evidence. Knowledge assets may be reused only after new source/query/schema fingerprints and leakage gates pass.

**[FROZEN]** Final Near Agent/SFT must support Application Evidence wherever the source PCAP provides reliably extractable fields. Payload is never default input but must be available on demand when a real content gap exists. Corpus construction uses bounded stage multiplicity and diversity-aware sampling so one session cannot dominate through many near-identical stage variants.

If stages 4–6 are intended to train the final Traffic Expert, their parser/sanitizer/retrieval format and legal assets must be frozen before those examples are generated. An interim stage-0–3 engineering checkpoint cannot be mislabeled as the final Near checkpoint.

## 7. Application and Sanitized Payload protocol

Application Evidence prefers structured observations such as real HTTP method, URI shape, status, content type, parameter structure/count, request/response size, DNS query type/response code and TLS handshake metadata. It must never invent a field that the PCAP does not expose.

Sanitized Payload is **on-demand only** and must be:

- bounded by bytes/characters/tokens;
- protocol-aware;
- truncated by a frozen policy;
- redacted and normalized by a frozen policy;
- marked untrusted;
- accompanied by backend-only provenance.

The sanitizer removes raw IP, capture/dataset identity, GT, backend IDs, absolute time and equivalent shortcuts while preserving, where safely possible, SQL/XSS syntax, command semantics, HTTP parameter semantics, protocol semantics and attack-relevant content structure. Unlimited raw payload is prohibited.

Because Edge labels are capture-coupled, `PAYLOAD_SHORTCUT_RISK` audit is mandatory. Sanitizer design uses TRAIN and legal validation development only. It cannot be changed after viewing `U_final`.

## 8. Knowledge RAG protocol

RAG is an on-demand Knowledge Evidence Tool, not an every-sample default:

```text
Observation → Qwen Evidence State → Supervisor identifies knowledge gap
→ REQUEST_KNOWLEDGE → Runtime constructs a safe query
→ hybrid retrieval → Knowledge Evidence → Qwen re-evaluation
```

Observation Evidence and Knowledge Evidence must be separately typed. Knowledge may explain a pattern but cannot claim that the current session observed it.

The v1 KB may contain protocol/RFC-derived knowledge, generic attack behavior, public CVE/security knowledge and generic threat intelligence. It must not contain Edge capture facts, run identifiers, fixed IP-to-label mappings, U_final shortcuts or dataset-specific payload fingerprints.

The first retriever is **[CURRENT DEFAULT]** hybrid BM25 + dense retrieval, merged, deduplicated and top-k limited. Top-k is **[VALIDATION TUNABLE]**. GraphRAG, complex reranking, multi-agent rewriting and multi-hop retrieval are deferred unless legal validation demonstrates a need.

Supervisor identifies the missing knowledge target; deterministic Runtime constructs the actual query and strips backend identity, raw IP, dataset identity and GT. KB corpus, index, retriever, serialization and query policy must be frozen before formal Agent evaluation. If SFT contains RAG stages, the minimum KB/retrieval format must be frozen before those examples are generated.

## 9. Training #1 — classification-first multi-task LoRA SFT

**[FROZEN]** Training #1 is the primary training stage:

```text
L_SFT = lambda_cls * L_classification + lambda_ev * L_evidence_generation
```

Classification is the primary objective. Official/verified GT directly supervises Fine Head Cross Entropy and backpropagates through the Fine Head and LoRA. A Teacher must never decide or replace the official attack label.

Evidence generation is auxiliary supervision for grounding, supporting/missing evidence, sufficiency, gap type and appropriate backoff. Dataset GT does not natively provide these targets, so they are built from:

```text
deterministic evidence rules
+ controlled masking/evidence stages
+ DeepSeek Flash Teacher assistance
+ automatic consistency checks
+ bounded human audit
```

Teacher-v2 runs only after deterministic eligibility filtering. It may receive verified GT as immutable task context, but may only organize and assess existing observations; it cannot modify GT, clean the dataset or invent observations. It labels`evidence_sufficient`, grounded support, unique `missing_evidence[]`, `primary_gap`, `gap_type` and `recoverability`. Run a deterministic 20–50-state smoke before resumable bulk; old Teacher V3 cache/results cannot seed v2.

`Evidence State v2` consistency is mandatory: sufficient implies no missing family, null primary gap, `gap_type=NONE` and `recoverability=ALREADY_SUFFICIENT`; insufficient primary gap must belong to the unique missing family set, and domain/recoverability must agree with available capabilities.

LoRA rank/alpha/dropout, learning rate, batch size, gradient accumulation, epochs, warmup, `lambda_cls` and `lambda_ev` are **[VALIDATION TUNABLE]** through a small preregistered search. Primary selection uses validation fine Macro-F1, with per-class F1, loss, Evidence-State quality and training stability as secondary diagnostics. Do not run a large grid search.

## 10. Baselines before formal SFT

Before Training #1, run and archive the Near Raw Qwen baseline and strong legal structured-feature baselines: LightGBM, XGBoost, Random Forest and any retained minimal method from the canonical plan. They use only model-safe features and never become a router for Qwen.

If trained Qwen fine Macro-F1 is more than approximately five percentage points below the strongest traditional baseline, trigger data/representation/training diagnosis. This is a diagnostic red line, not an automatic architecture reversal or a paper non-inferiority claim.

## 11. Training #2 — RLAIF-GRPO with classification preservation

Training #2 starts from a cloned/reference Near SFT checkpoint. It is a joint post-training stage with distinct signals:

```text
L_RL_TOTAL = L_GRPO + lambda_cls_rl * L_classification
```

Fine Head CE continues to update the Fine Head and LoRA, preserving Known classification and reducing RL drift. GRPO optimizes rollout-varying Evidence behavior:

- grounding;
- evidence sufficiency correctness;
- missing-evidence and gap-type quality;
- appropriate backoff/abstention within legal training scope;
- hallucination avoidance;
- schema validity, brevity and compliance.

**[FROZEN CORRECTION]** Fine Head correctness is constant across LM rollouts for the same input and therefore cannot be the main group-relative GRPO reward. Classification correctness belongs to the separate CE preservation term, not a claimed per-rollout relative advantage.

Use deterministic checks for schema, Evidence reference validity and format wherever possible. DeepSeek Flash Judge provides structured AI feedback only for semantic properties that require it. The Judge normally does not need the GT fine label; classification supervision is handled by CE.

GRPO uses a fixed, reproducible RL Prompt Pool built only from legal Near `K_known ∩ TRAIN` Evidence states. At each training step, the current Qwen policy generates multiple live rollouts; deterministic reward plus DeepSeek Flash Judge reward produces the group-relative objective. DeepSeek does not pre-generate a complete fixed RL dataset. Rollouts and Judge results are cached/logged for audit, but policy updates require new rollouts.

GRPO group size, prompt-pool sample size, learning rate, KL control if used, `lambda_cls_rl`, Judge batch size and reward weights are **[VALIDATION TUNABLE]**. DPO remains **[DEFERRED]** as a later offline preference ablation.

## 12. DeepSeek Flash roles and orchestration

The current configurable external high-capability default is **DeepSeek Flash**. Do not hard-code a provider model ID into the research architecture; record the exact endpoint/model in each run manifest.

Even if one provider serves all three, these are separate logical roles:

| Role | Scope | GT access | Required separation |
| --- | --- | --- | --- |
| Teacher | train/development Evidence-State corpus construction | verified GT may be immutable context | own prompt/schema/permissions/logs |
| Judge | online/asynchronous RLAIF rollout scoring | normally no fine GT | own prompt/schema/permissions/logs |
| Supervisor | formal inference action selection | never | own prompt/schema/permissions/logs |

Codex is not the formal Teacher/Judge model. Codex implements provider abstraction, orchestration, prompts, RAG, retries, rate limits, batching, cache, request IDs, response validation, experiment execution and audit.

Each DeepSeek call records role, request ID, prompt/schema version, provider/model identity, temperature/reasoning configuration, token usage, cost, latency, validation status and failure handling. No role may silently share a vague common prompt.

## 13. Independent Unknown protocol

Unknown is not a K+1 class. `U_dev` is not mapped to an Unknown supervision label in SFT, and `U_final` never trains Qwen.

After Training #2 validation, freeze the primary Qwen checkpoint. Develop Independent Unknown using only Known validation and Near `U_dev`:

- margin;
- entropy;
- energy;
- prototype distance from Fine Head logits and/or `h_session`.

Prefer methods that do not require a new neural network. A small learned Unknown head is **[DEFERRED BACKUP]** only if the simple candidates are demonstrably inadequate. Fit prototypes and calibrate thresholds without retraining Qwen.

Freeze score family, representation, normalization, threshold, calibration data digest and implementation version before any Near `U_final` evaluation.

## 14. U_final seal and formal evaluation isolation

Near `U_final` is DDoS_UDP and XSS. It remains strictly sealed from:

- Prompt and serialization selection;
- pooling and LoRA target selection;
- SFT/RL and all hyperparameters;
- Teacher/Judge rubrics;
- Unknown score/threshold selection;
- payload sanitizer;
- KB/RAG/top-k/query policy;
- Supervisor prompt/budget/policy;
- Memory retrieval settings.

The first U_final opening occurs only after the evaluated system components are frozen. If Application/Payload/RAG/Supervisor implementation that can influence the final route is not ready, complete and freeze that development before U_final; phase labels never authorize retroactive tuning. After opening, results cannot change any development parameter.

Formal evaluation processes sessions in capture/scenario chronological order whenever Temporal, Graph or Memory is involved. Never random-shuffle in a way that exposes future context. One reconstructed session produces one primary result.

## 15. Supervisor, Experience Memory and novel-class adaptation

The DeepSeek Flash Supervisor is not a classifier and cannot override the Fine Head. It sees model-safe Evidence, Fine Head result/top candidates allowed by the interface, Evidence State, frozen Unknown state/score, capabilities, budget, previous actions and validated Experience Memory. It outputs a structured action, target and short reason, never a long CoT.

One round permits at most one Evidence action. Exact duplicate requests are rejected; a tool may be called again only with a distinct validated signature. Agent max extra rounds begins from a current default of 3 and is **[VALIDATION TUNABLE]**.

Formal Near Agent comparisons are Basic, Fixed Full, RulePolicy and DeepSeek Flash Supervisor with shared Qwen, legal information domain and maximum budget. Report tool calls, Qwen/Supervisor/RAG tokens, latency and API cost.

Run the first Agent comparison without Experience Memory. Then add Experience Memory as a separate experiment. Only externally verified TRAIN experience may be written; validation, test and U_final are read-only. Supervisor self-predictions never self-confirm.

Unknown rejection and novel-class recognition are separate. The v1 onboarding route is:

```text
Unknown → REQUEST_LABEL → human/oracle 1/5/10-shot support
→ REGISTER_NEW_CLASS → Class Memory/prototype → later query recognition
```

Class Memory stores safe labeled support representation, prototype, description and support metadata, not raw identity or dataset shortcuts. The first mainline does not retrain LoRA after few-shot registration. `CONTINUAL_LORA=DEFERRED`.

## 16. Ordered execution plan and gates

| Phase | Required work | Exit condition |
| --- | --- | --- |
| A | Production, split, Adapter, fidelity and raw Qwen deployment | **COMPLETE** with recorded limitations |
| B | Training-side Transformers/PEFT harness; LoRA inventory checks; pooling; serialization v1; Prompt/schema v1; Application/Payload contracts; RAG Evidence Contract | **COMPLETE** for non-API readiness; no U_final access |
| C | Raw Near Qwen and strong traditional baselines | reproducible baseline manifests |
| C0 | Evidence-v2, all-split eligibility and Observable Dataset v3 | **COMPLETE / PASS** |
| D | Build one Basic-v2 primary plus at most two meaningful auxiliary states per eligible TRAIN session | **COMPLETE / PASS** |
| E | Teacher-v2 40-state smoke, resumable 20,807-state bulk, consistency filtering and bounded audit | **COMPLETE / PASS** |
| E2 | Corpus v3, active class-map/session-weight/preflight/blind-sanity acceptance | **COMPLETE / PASS**；11,958 sessions / 14,350 records |
| F | Training #1 classification-first multi-task LoRA SFT | Checkpoint A + manifest |
| G | SFT validation/evaluation | no formal test-driven tuning |
| H | Build fixed reproducible RL Prompt Pool from legal v3 K_known TRAIN states | NOT STARTED; historical 6,000-prompt pool is superseded |
| I | Training #2 RLAIF-GRPO + classification CE preservation | Checkpoint B + rollout/Judge manifests |
| J | RL validation/evaluation | final primary candidate selected without U_final |
| K | Freeze final primary Qwen checkpoint | Checkpoint B immutable |
| L | Independent Unknown development using K validation + U_dev | candidate comparison complete |
| M | Freeze Unknown | algorithm and threshold immutable |
| N | First U_final open-set evaluation | one-way sealed evaluation; no feedback to development |
| O | Complete/finalize Application, Payload and RAG if not already production-ready | pretraining sidecar/KB/index ready; formal Runtime tool wiring remains pending |
| P | Agent: Basic, Fixed Full, RulePolicy, DeepSeek Flash Supervisor | budget-matched results |
| Q | Experience Memory experiment | read/write protocol audited |
| R | 1/5/10-shot Class Memory onboarding | novel-class and old-class results |
| S | `NEAR_MAINLINE_COMPLETE=true` | first end-to-end paper route complete |

Dependency override: Phase N may execute only when every component whose settings could affect the evaluated U_final route is already frozen. If Phase O/P development is incomplete, perform its implementation and validation-safe freeze before N; formal Agent evaluation can remain after N. No result from N may guide O/P.

Only after Phase S resume the deferred tracks listed in Section 2.

## 17. Checkpoint lineage and reproducibility

```text
Base: official Qwen/Qwen3.5-9B @ c202236235762e1c871ad0ccb60c8ee5ba337b9a
  ↓ Training #1
Checkpoint A: Near Multi-task SFT LoRA + Fine Head
  ↓ clone/reference A, then Training #2
Checkpoint B: Near SFT + RLAIF-GRPO LoRA + Fine Head
  ↓ freeze
Independent Unknown calibration → Agent integration
```

Base weights remain immutable. LoRA adapters and Fine Head weights are saved separately. Training #2 must never overwrite Checkpoint A; it creates Checkpoint B from a clone/reference.

Every checkpoint records:

- parent/base revision and checkpoint lineage;
- code commit and environment/software versions;
- data/split/candidate/corpus digest;
- Prompt, response schema and serialization versions;
- class map and Near seed;
- pooling and LoRA target inventory;
- trainable parameter count and all hyperparameters;
- Teacher/Judge versions where applicable;
- random seeds, optimizer/scheduler state and resume status;
- validation results and selection rationale.

Model weights, optimizer state, caches, rollouts and large logs stay Git-external. Git tracks small manifests and audit summaries only.

## 18. Current stop point and next implementation phase

Reusable facts include Production Data Freeze, Edge v2 split, Runtime Adapter/Fidelity, official raw Qwen smoke and the Phase B harness. The harness exposes hidden states, dynamic Linear Fine Head logits, LM logits and combined masked loss; real Qwen inventory covers 248 Gated Attention/DeltaNet/FFN targets and pooling remains `ATTENTION_MASKED_MEAN_V1`. Old Prompt/schema, PLAN_B sidecars, Teacher V3, 22,957 snapshots/corpus, validation asset and RL pool are superseded historical inputs under DEC-0021; they are not v3-ready.

A real Qwen3.5-9B dry-run and save/load/resume smoke passed reusable harness gates. DeepSeek provider/role isolation is reusable. Teacher-v2为20,807/20,807 valid、quarantine 0；formal trajectory剔除161个terminal-inconsistent sessions并在首次sufficient停止，raw Teacher cache不改写。corpus v3为11,958 sessions / 14,350 records，Known validation为3,231条EXACT_EVAL_CLEAN。Formal Model A SFT与evaluation已完成；RLAIF/GRPO、Dataset-v4 Unknown、continual stream与Agent benchmark未运行。

**CURRENT STOP POINT: MODEL_A_FROZEN / DEC-0025 DATASET-V4 FORMALIZATION NEXT.** Model A Formal Macro-F1=`0.9984831207613943`; Frozen-Qwen limited probe Macro-F1=`0.9815630112607532`; Model A Evidence State=`FAIL`. NF3-ToN artifact reconciliation and bounded utility/open-world feasibility are complete with limitations. No further Model A optimizer run, Evidence-only RLAIF, Model B training, continual, RL or U_final access is authorized here. The next separately authorized work is Dataset-v4 formalization and Model B low-cost design Gates.

## 19. Historical Model A end-to-end flow

> The following diagrams document the Model A/DEC-0019 design. They are superseded for the current Model B mainline by DEC-0025.

Inference:

```text
Production Session
→ Production Runtime Safe Adapter
→ legal Evidence Stage
→ Qwen Traffic Expert shared backbone
→ Fine Classification Head + LM Evidence State
→ Independent Unknown
→ DeepSeek Flash Supervisor
→ one deterministic Runtime Evidence action
→ Qwen re-evaluation
→ final Known Fine / Coarse Backoff / Unknown / Abstain
→ optional human label
→ Class Memory registration
```

Training:

```text
Raw Qwen baseline
→ classification-first Multi-task SFT
→ Near Checkpoint A
→ RLAIF-GRPO + Classification CE preservation
→ Near Checkpoint B
→ freeze Qwen
→ Independent Unknown calibration
→ Agent integration
```


## 20. Final pre-training acceptance implementation note

The active formal config is NEAR_SFT_CONFIG_V2: BF16, PEFT LoRA rank 8 / alpha
16 / dropout 0.05 over the audited attention, DeltaNet and FFN projections,
ATTENTION_MASKED_MEAN_V1, classification weight 1.0, Evidence LM weight 0.35,
AdamW 2e-4 with cosine schedule and 3% warmup, two epochs, micro-batch 1,
gradient accumulation 16, max sequence 8192, deterministic per-epoch shuffle,
seed 20260813, step/epoch checkpoints and two-checkpoint retention. The historical
NEAR_SFT_CONFIG_V1/3072-token/11-class corpus remains fail closed.

`CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1` separates two scientific variables.
`classification_ce_eligible` asks whether a record is a legal supervised
classification primary and is determined only by TRAIN/K-known scope, immutable
official GT, provenance/leakage/U_final checks and the deterministic state
protocol. `evidence_sufficient` asks whether current model-safe Evidence is
operationally sufficient to stop additional acquisition; it is an
Evidence-State target and never gates CE.

Every Observable-v3 formal SFT session has at most one Basic-v2 primary state with CE enabled, even
when its Teacher target is insufficient. Controlled lower-evidence auxiliaries
always mask CE but retain Evidence LM supervision. Evidence-State LM loss uses
inverse-states-per-session weights so multi-state sessions do not multiply their
weight. GT remains backend-only and cannot appear in serialized input, Prompt,
RAG query, Payload or model-visible metadata; CE on a legal primary is therefore
supervision, not label leakage. This also prevents a deliberately masked
auxiliary from forcing the Fine Head to guess the immutable target.

Checkpoint selection uses Known validation Macro-F1 as the primary metric,
subject to an explicit Evidence-State schema/hallucination/sufficiency safety
gate. Validation may support bounded preregistered adjustment; test is reserved
for formal results and U_final remains forbidden. The formal launcher is
script/config-driven, refuses overwrite, records config/Git/model/data digests,
saves LoRA + Fine Head + optimizer + scheduler + RNG, and supports strict
resume. Formal execution still requires a separate explicit execute flag and
must never be started as part of a readiness audit.
