# Near-First Training and Open-World Protocol v1

> Status: **FROZEN / Training and Open-World Execution Authority**
>
> Protocol date: 2026-08-11
>
> Scope: first complete Edge-IIoTset Near mainline, from training readiness through SFT, RLAIF-GRPO, Independent Unknown, Agent evaluation, Experience Memory and novel-class onboarding.
>
> State: `TRAINING_PROTOCOL_FROZEN=true`; `SFT_RUN=false`; `RL_RUN=false`; `UNKNOWN_ALGORITHM_FROZEN=false`.
>
> Authority: the [canonical research plan](../research_plan/research_plan_detailed.md) is the highest research authority. This protocol is the execution authority for training and open-world work. The [Agent architecture](../design/agent_architecture_provisional.md) governs Runtime/Supervisor/RAG/Memory implementation, and [PROJECT_HANDOFF](../PROJECT_HANDOFF.md) records current implementation state only.

## 1. Status vocabulary

- **FROZEN**: the architecture, permission boundary or execution order cannot change without a new canonical Decision.
- **CURRENT DEFAULT**: the first implementation choice; it may change only through the validation-safe procedure defined here.
- **VALIDATION TUNABLE**: a bounded, preregistered choice using legal train/validation data, never formal test or `U_final`.
- **DEFERRED**: outside the first Near end-to-end completion condition.
- **OPTIONAL**: may be skipped without blocking the first Near mainline.

Freezing this protocol does not claim that training has run, that numerical hyperparameters have been selected, or that planned Application/Payload/RAG capabilities are implemented.

## 2. ONE_MAINLINE_FIRST

**[FROZEN]** The first complete research route is Edge-IIoTset **Near**. Do not develop Near, Far, Mixed, IoT-23, several RL methods, several Unknown methods and several tokenizer methods as simultaneous first-class tracks.

Near must first produce:

1. real training checkpoints;
2. closed-set and open-world results;
3. complete Basic/Fixed Full/RulePolicy/DeepSeek Flash Supervisor results;
4. 1/5/10-shot Class Memory adaptation results.

Only after `NEAR_MAINLINE_COMPLETE=true` may the project resume Pure Generative SFT ablation, DPO, Far, Mixed, IoT-23, tokenizer ablation, QLoRA, thinking-on, low-resource stress, learnable Agent policy RL or continual LoRA. Far and Mixed retain their frozen K/U roles, but require their own legal corpora and checkpoints; a Near checkpoint is not their formal known-class model.

## 3. Frozen Near data protocol

| Item | Frozen value |
| --- | --- |
| Dataset | Edge-IIoTset, with documented single-capture/run limitations |
| Preset | Near |
| Seed | `20260809` |
| Physical split | `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2` |
| SFT selection | `CLASS_BALANCED_DIVERSITY_AWARE_SFT_SELECTION_V1`, `PLAN_B` |
| Candidate count | 16,979 unique sessions |
| Candidate universe | `K_known ∩ physical train` only |

`K_known`:

- Backdoor
- DDoS_HTTP
- DDoS_TCP
- MITM
- Normal
- Password
- Port_Scanning
- Ransomware
- SQL_injection
- Uploading
- Vulnerability_scanner

`U_dev`: DDoS_ICMP, OS_Fingerprinting.

`U_final`: DDoS_UDP, XSS.

Validation, test, `U_dev` as a Known supervision label and `U_final` are forbidden from the SFT candidate universe. Do not rerun PLAN_A/B/C selection, change K/U, change the split or choose a different seed because of model outcomes.

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

Before formal SFT corpus generation, freeze and fingerprint:

- Traffic Expert Prompt v1;
- Fine class map and deterministic fine-to-coarse map;
- Evidence State response schema v1;
- serialization v1;
- classification marker/pooling contract;
- model-safe Observation/Knowledge distinction;
- Evidence stage schema and missing-capability behavior.

Prompting remains concise, non-thinking and direct-response. Do not request long Chain-of-Thought, include dataset/capture hints, or embed encyclopedia material in the system prompt.

## 6. Evidence stages and corpus permissions

A legal session can create bounded stage variants:

| Stage | Evidence |
| --- | --- |
| 0 | Initial Evidence: packets 1–8 plus whole-session safe summary |
| 1 | + packets 9–16 |
| 2 | + strictly past-only Temporal Context |
| 3 | + anonymous Graph/Relation Context |
| 4 | + structured Application Evidence |
| 5 | + bounded Sanitized Payload |
| 6 | + Knowledge RAG Evidence |

Only genuinely AVAILABLE, materialized and model-safe Evidence may appear. The current implementation supports stages 0–3; Application Evidence, Sanitized Payload and Production Knowledge RAG are currently UNAVAILABLE. Those are engineering states, not permanent research prohibitions.

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

Teacher may receive verified GT as immutable task context, but may only organize and assess existing observations; it cannot modify GT or invent observations. Teacher prompt, schema, permissions and logs are independent from Judge and Supervisor.

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
| B | Training-side Transformers/PEFT harness; LoRA inventory checks; pooling; serialization v1; Prompt/schema v1; Application/Payload contracts; RAG Evidence Contract | readiness artifacts frozen, no U_final access |
| C | Raw Near Qwen and strong traditional baselines | reproducible baseline manifests |
| D | Build bounded, diversity-aware multi-stage Near SFT corpus | only legal K_known TRAIN stages, digests frozen |
| E | DeepSeek Flash Teacher annotation, automatic consistency filtering and bounded human audit | accepted/rejected audit trail frozen |
| F | Training #1 classification-first multi-task LoRA SFT | Checkpoint A + manifest |
| G | SFT validation/evaluation | no formal test-driven tuning |
| H | Build fixed reproducible RL Prompt Pool from legal K_known TRAIN states | prompt-pool digest frozen |
| I | Training #2 RLAIF-GRPO + classification CE preservation | Checkpoint B + rollout/Judge manifests |
| J | RL validation/evaluation | final primary candidate selected without U_final |
| K | Freeze final primary Qwen checkpoint | Checkpoint B immutable |
| L | Independent Unknown development using K validation + U_dev | candidate comparison complete |
| M | Freeze Unknown | algorithm and threshold immutable |
| N | First U_final open-set evaluation | one-way sealed evaluation; no feedback to development |
| O | Complete/finalize Application, Payload and RAG if not already production-ready | required tool contracts/assets frozen |
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

Completed infrastructure facts include Production Data Freeze, Edge v2 split, Near PLAN_B candidates, Production Runtime Safe Adapter v1, Evidence Fidelity Gate and official raw Qwen local/runtime smoke. Current capabilities are Initial, packets 9–16, Temporal and limited anonymous Relation; Application, Sanitized Payload and Production RAG remain unavailable.

No SFT, LoRA training, Fine Head training, RLAIF/GRPO, Unknown development, DeepSeek Teacher/Judge/Supervisor formal run or benchmark has started.

**NEXT IMPLEMENTATION PHASE: Phase B — Training Protocol Readiness.** Implement the training-side model harness and freeze pooling, LoRA target inventory checks, serialization v1, Prompt/schema v1, Application/Payload contracts and RAG Evidence Contract. This document does not authorize executing Phase C or later.

## 19. End-to-end flow

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
