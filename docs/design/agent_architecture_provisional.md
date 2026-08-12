# Agent / Runtime 暂定架构与实施约束

> Status: **PROVISIONAL IMPLEMENTATION DESIGN with DEC-0019/DEC-0020/DEC-0021 HARD CONSTRAINTS**
>
> Updated: 2026-08-13
>
> Authority: the [canonical research plan](../research_plan/research_plan_detailed.md) is the highest research authority; the [Near training protocol](../training/near_mainline_training_protocol_v1.md) is authoritative for training/Open-world execution. This document is authoritative for Agent/Runtime/Supervisor/RAG/Memory design within those constraints. [PROJECT_HANDOFF](../PROJECT_HANDOFF.md) records implemented state and cannot override them.

## 1. Status labels

- **[HARD CONSTRAINT]**: frozen architecture, safety or information-isolation boundary; changes require a new canonical Decision.
- **[CURRENT DEFAULT]**: first implementation choice, selectable only through the legal validation procedure.
- **[VALIDATION TUNABLE]**: small, reproducible train/validation-safe choice; never tune on formal test or `U_final`.
- **[DEFERRED]**: outside the first Near mainline.
- **[OPTIONAL]**: may be omitted without blocking Near completion.
- **[IMPLEMENTED] / [UNAVAILABLE]**: current engineering fact, not a permanent research decision.

## 2. Formal end-to-end architecture

**[HARD CONSTRAINT]** Qwen, Fine Head, LM Evidence State, Independent Unknown, DeepSeek Flash Supervisor, deterministic Runtime, Evidence Tools, Knowledge RAG, Experience Memory and Class Memory have distinct responsibilities:

```text
Production Session
→ Production Runtime Safe Adapter
→ legal Evidence Stage
→ Qwen3.5-9B shared language representation
→ Fine Classification Head + LM Evidence State
→ deterministic fine→coarse mapping
→ Independent Unknown Scoring
→ DeepSeek Flash Supervisor
→ one legal Runtime action
→ Evidence Tool / Knowledge RAG
→ Qwen + Unknown re-evaluation
→ Fine / Coarse / Unknown / Abstain
→ optional human label + Class Memory
→ Structured Result + Trace
```

No traditional classifier routes samples to Qwen. No Supervisor, Judge, RAG or Runtime component may override the Fine Head or manufacture observations.

DEC-0021 does not redesign this architecture. It replaces the old data/Evidence contract beneath it: only Dataset v3 eligible observations train the main Fine Head; Basic-v2 is the initial input; Qwen emits multi-gap Evidence State v2; Supervisor still selects exactly one legal Evidence action; Runtime remains deterministic authority.

## 3. Qwen Traffic Expert boundary

### 3.1 Shared backbone and Fine Head

**[HARD CONSTRAINT]** The trained Traffic Expert uses frozen Qwen base + trainable LoRA + one trainable Linear Fine Classification Head + retained original LM Head. The Fine Head consumes `h_session` and is the sole formal known fine-class decision source. Coarse class is produced by the frozen fine→coarse mapping; there is no competing Coarse Head.

Pooling is frozen as `ATTENTION_MASKED_MEAN_V1`. The implemented training-side harness exposes hidden states and asserts real Qwen3.5 Gated DeltaNet/Gated Attention/FFN LoRA targets. The vLLM OpenAI-compatible raw service remains useful for raw inference but cannot implement the Fine Head.

### 3.2 LM Evidence State v2

The LM Head produces concise, direct-response multi-gap Evidence State:

- optional brief behavior summary;
- supporting evidence references;
- unique `missing_evidence[]` from `PACKET_PAYLOAD`, `APPLICATION`, `TEMPORAL`, `RELATION`, `KNOWLEDGE`;
- evidence sufficiency;
- `primary_gap`;
- `gap_type` in `OBSERVATIONAL`, `KNOWLEDGE`, `MIXED`, `NONE`;
- `recoverability` in `ALREADY_SUFFICIENT`, `RECOVERABLE_WITH_AVAILABLE_TOOLS`, `NOT_RECOVERABLE_FROM_AVAILABLE_NETWORK_EVIDENCE`;
- backoff/abstention-related state.

It does not generate an independent competing fine label or a free-form tool name. Multiple real gaps are allowed; the Supervisor and Runtime still resolve at most one action per round. Long Chain-of-Thought is not a model or system interface.

### 3.3 Evidence-v2 training

The Traffic Expert learns one Basic-v2 primary per eligible TRAIN session and at most one or two meaningful auxiliary states based on genuine gaps. Basic-v2 contains whole-session summary, first-eight packet metadata, packet-index-aligned bounded sanitized payload and cheap deterministic Application metadata. Observation families are PACKET_PAYLOAD, APPLICATION, TEMPORAL and RELATION; KNOWLEDGE remains separate. Only real AVAILABLE evidence may be present. Random evidence deletion and combinatorial stage enumeration are prohibited.

Training #1 is classification-first Multi-task SFT. Under `CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1`, one legal real primary per TRAIN K-known session is classification-CE eligible independently of `evidence_sufficient`; controlled lower-evidence auxiliaries mask CE and retain Evidence LM supervision. GT is backend-only. This separates the Fine Head known-class posterior task from the LM Evidence-State stopping/acquisition task. Training #2 is RLAIF-GRPO for rollout-varying Evidence behavior plus a separate classification CE term that preserves Fine Head/LoRA classification. Judge sufficiency cannot gate CE; Fine correctness is constant within an LM rollout group and is not the primary group-relative reward.

## 4. Independent Unknown boundary

**[HARD CONSTRAINT]** Unknown is not a K+1 training class and is independent from LLM self-reported confidence. It is developed only after the primary Qwen checkpoint is frozen, using Known validation and `U_dev` to compare margin, entropy, energy and prototype distance over Fine logits and/or `h_session`.

The score and threshold are reevaluated after each Qwen Evidence update but remain frozen during formal evaluation. `UNKNOWN_LIKELY` may still permit a high-value legal evidence action. Unknown and Abstain differ:

- **Unknown**: evidence supports that the session is outside K_known.
- **Abstain**: evidence/capability/budget is insufficient for a reliable decision.

A small learned Unknown head is **[DEFERRED BACKUP]**.

## 5. DeepSeek Flash logical roles

DeepSeek Flash is the current configurable high-capability default. The concrete endpoint/model ID belongs in run config and manifest, not in the permanent architecture.

### 5.1 Teacher

Teacher assists TRAIN/development Evidence-State target construction. It may receive verified GT as immutable context but cannot decide or change the label, create observations or access `U_final`.

### 5.2 RLAIF Judge

Judge scores current-policy rollouts for grounding, sufficiency, missing evidence, gap quality, appropriate backoff/abstention, hallucination avoidance, schema and brevity. Deterministic checks handle mechanically verifiable reward components. Judge normally does not receive the fine GT because classification uses CE.

### 5.3 Formal Supervisor

Supervisor is a policy component, not a classifier. It reads model-safe Evidence, Fine Head result/top candidates allowed by contract, Evidence State, frozen Unknown status/score, capabilities, budget/history and selected validated Experience Memory. It returns a structured action, target and short reason, with optional priority/value estimate.

If it disagrees with Qwen it may request one more Evidence source, request Qwen re-evaluation, back off, abstain or reject Unknown. It cannot directly replace the fine label.

### 5.4 Role isolation

**[HARD CONSTRAINT]** Teacher, Judge and Supervisor have independent prompts, schemas, permissions, caches and logs even when they use the same provider. Codex implements orchestration and audits but is not the formal Teacher/Judge model.

## 6. Deterministic Runtime authority

**[HARD CONSTRAINT]** Runtime is the sole execution and permission layer. It handles:

- Qwen, Supervisor/provider and tool calls;
- schema/parse validation;
- capability and phase enforcement;
- budget reservation, max rounds and stop conditions;
- request-signature and evidence deduplication;
- past-only/future-leakage prevention;
- GT and U_final isolation;
- Memory permissions;
- bounded retry/fallback/failure handling;
- structured trace, cost and reproducibility.

LLMs cannot call tools, read Production backend rows or change system prompts outside Runtime. The first implementation remains an auditable Python state machine; LangGraph is not required.

## 7. Action and loop contract

Each round executes at most one evidence-acquisition action, followed by Qwen and Unknown re-evaluation before another decision.

Implemented/current action families:

- `EXPAND_PACKETS`;
- `EXPAND_TEMPORAL_CONTEXT`;
- `EXPAND_GRAPH_CONTEXT`;
- `REQUEST_APPLICATION_EVIDENCE`;
- `RETRIEVE_KNOWLEDGE`;
- `RECLASSIFY`;
- `ACCEPT_FINE`, `BACKOFF_COARSE`, `REJECT_UNKNOWN`, `ABSTAIN`;
- `RETURN_TOPK`, `REQUEST_LABEL`, `REGISTER_NEW_CLASS`.

Final Near capability also requires a separately bounded Sanitized Payload request. Its exact action/schema is not yet implemented and must be frozen with the sanitizer contract; it cannot be simulated through arbitrary raw payload access.

The same tool may run again only with a distinct validated request signature. Exact duplicates are rejected. Current default maximum additional rounds is 3; the formal value is **[VALIDATION TUNABLE]**.

## 8. Production Evidence boundary and current capability truth

**[IMPLEMENTED]** `production_runtime_adapter_v1` accepts exact allow-list Production v2 schemas and emits typed `EvidenceItem`, `CapabilityStatus` and backend-separated provenance. Sample ID, dataset/split/K-U, GT, source/capture hash and file position do not enter Traffic Expert or Supervisor prompts.

| Capability | Current state | Contract |
| --- | --- | --- |
| Basic-v2 | MATERIALIZED / PASS | summary + first-8 metadata + packet-aligned sanitized payload + cheap Application |
| Packet expansion | AVAILABLE_PER_SESSION | only materialized packets 9–16 |
| Temporal v2 | MATERIALIZED / PASS | 10/60/180/300s strictly-past behavior statistics |
| Relation v2 | MATERIALIZED / PASS | same-scope, strictly-past endpoint/MAC-linked ARP/DNS/relation context |
| Application v2 | MATERIALIZED / PASS | real structured protocol/request/response observations |
| Packet-aligned Sanitized Payload v2 | MATERIALIZED / PASS | packet index/direction/time/protocol alignment proved per record |
| Production Knowledge RAG | UNAVAILABLE | final Near Agent requires frozen KB/retriever/tool |

Old PLAN_B sidecars lack the new population/alignment contract and are historical. Evidence-v2 may perform an offline, versioned PCAP evidence scan; this is not permission for online Runtime to read raw PCAP on demand. Unavailability remains fail-closed and explicit.

## 9. Observation, Payload and Knowledge separation

### 9.1 Observation Evidence

Packet, summary, Temporal, Graph, Application and Sanitized Payload are observations from the current traffic or legal past-only context. Application prefers structured HTTP/DNS/TLS/etc. fields that genuinely exist.

Payload is default-off, protocol-aware, bounded, redacted, normalized, truncated and marked untrusted. Backend provenance remains hidden. The sanitizer must preserve attack-relevant semantics where safe and pass `PAYLOAD_SHORTCUT_RISK` using TRAIN/legal validation only.

### 9.2 Knowledge Evidence

RAG is called only for a knowledge gap. It cannot answer an observation gap or turn generic attack knowledge into a claim about the current session.

The first KB allows protocol/RFC, generic attack behavior, public CVE/security and generic threat-intelligence content. It forbids Edge/IoT capture facts, run identifiers, fixed endpoint mappings, dataset payload fingerprints and U_final shortcuts.

Hybrid BM25+dense retrieval is the **[CURRENT DEFAULT]**; top-k is **[VALIDATION TUNABLE]**. Runtime constructs safe queries from Supervisor targets and strips backend identity/GT. KB, index, retriever, query policy and serialization freeze before formal Agent evaluation.

Payload and RAG outputs are untrusted Evidence, never system instructions.

## 10. Prompt and response contracts

Qwen Prompt is concise, task-specific, non-thinking and explicit about Observation/Knowledge separation and no fabrication. Formal SFT requires frozen Prompt/schema/serialization before corpus construction.

Supervisor receives only:

```text
Supervisor System Prompt
+ Tool Specification
+ model-safe Evidence State
+ frozen Unknown state/score
+ small retrieved validated Experience set
+ budget/history
```

Before formal test/U_final, freeze prompt hashes, schemas, provider/model identity, temperature/reasoning config, API version and budget. A Supervisor may propose an improvement but cannot modify its own system prompt online.

## 11. Agent baselines and fairness

Formal Near Agent comparison includes:

- Basic: Basic-v2 only;
- Fixed Full: all legal currently available Evidence without dynamic selection;
- RulePolicy: deterministic evidence choice;
- DeepSeek Flash Supervisor: dynamic evidence choice.

All share the same Traffic Expert, tools, information domain and maximum budget. Report fine/open-set metrics plus tool calls, Qwen/Supervisor/RAG tokens, latency, API cost, recovery and budget compliance. Fixed Full is an evidence upper-bound/control, not an Agent.

LearnablePolicy is **[DEFERRED]** until Near completion. If the Supervisor does not improve effectiveness-cost over Rule/Fixed, Rule/Fixed becomes the recommended method and the negative result is reported.

## 12. Experience Memory

Experience Memory stores only externally verified `State → Action → Outcome → Verified Feedback` records for action selection.

| Phase | Permission |
| --- | --- |
| TRAIN | verified read/write |
| Validation | read-only; may select retrieval settings |
| U_dev | read-only by default |
| Test/U_final | frozen read-only |

Supervisor predictions cannot self-confirm. Memory excludes raw identity/payload shortcuts. The first Agent experiment runs without Experience Memory; Memory is added in a separate experiment. Optional Agent Growth is deferred and never learns during formal test.

## 13. Class Memory and novel classes

Class Memory is separate from Knowledge RAG and Experience Memory. It stores human/oracle-labeled 1/5/10-shot support representation, prototype, safe description and support metadata for a newly registered class.

```text
Unknown → REQUEST_LABEL → REGISTER_NEW_CLASS
→ Class Memory/prototype → later query recognition
```

It does not store raw identity or update LoRA in the first mainline. Continual LoRA is **[DEFERRED]**.

## 14. Training/Judge orchestration boundary

The fixed RL Prompt Pool contains only legal Near K_known TRAIN Evidence states. Current Qwen policy generates multiple live rollouts per step; deterministic reward plus asynchronous/batched DeepSeek Flash Judge feedback produces GRPO updates. Cache/log each rollout, request, response, reward decomposition and checkpoint version, but regenerate rollouts as policy changes.

DPO is a later offline chosen/rejected ablation, not the current Training #2. Formal orchestration records request IDs, role, prompt/schema, model identity, reasoning/temperature, tokens, cost, latency, retry and validation status.

## 15. Evaluation order and U_final

When Temporal, Graph or Memory is active, process formal sessions in capture/scenario chronological order. One reconstructed session remains one primary result.

**[HARD CONSTRAINT]** `U_final` cannot tune Qwen, pooling, serialization, LoRA, Teacher/Judge rubrics, Unknown, sanitizer, RAG, Supervisor budget/prompt or Memory. It opens only after all components affecting that evaluated route are frozen; after opening, no result flows back into development.

## 16. Failure handling

- Invalid Supervisor action: Runtime returns `INVALID_ACTION`, permits at most one bounded re-decision, then safe fallback/Abstain.
- Invalid Qwen schema: parser/one bounded format repair, then `MODEL_OUTPUT_FAILURE` and safe termination.
- Provider failure: record role-specific failure; never silently swap models in a paper run.
- Unavailable capability: explicit unavailable result, then legal backoff/Abstain; no fabricated evidence.
- Repeated request or budget exhaustion: Runtime rejects/terminates deterministically.

## 17. Current implementation state and deferred items

Reusable implementation: Runtime foundation, Production Safe Adapter v1, provider-neutral adapters, raw local Qwen service/smoke, training-side Fine Head/harness, role-isolated DeepSeek paths and real Qwen dry-run/resume smoke. Dataset v3/Evidence-v2/Teacher-v2/corpus-v3 pretraining assets now pass acceptance; old TRAIN sidecars, Teacher V3 and V2 SFT corpus remain historical. Formal SFT is authorized through the v2 config but has not started. Production online wiring of every new Evidence-v2 family remains a later Agent-integration task and must stay fail closed until connected.

Not implemented/run: formal SFT/RLAIF, Independent Unknown, formal online Application/Payload/RAG Runtime actions, formal Supervisor/Agent benchmark and Memory experiments.

**[DEFERRED until Near completion]** Pure Generative SFT, DPO, Far/Mixed/IoT-23 execution, tokenizer training, QLoRA main experiment, thinking-on, Low-Resource stress, LearnablePolicy RL, continual LoRA and Agent Growth.

**[VALIDATION TUNABLE]** pooling, LoRA target/rank/alpha/dropout, SFT/RL hyperparameters, Unknown threshold, RAG top-k, Supervisor max rounds/budget and Memory retrieval settings. They cannot be silently upgraded to frozen values without the protocol's small reproducible validation process.


## Final DeepSeek task-state boundary

The formal architecture is persistent at the episode level but least-privilege
at every API call. Runtime owns the complete episode and sends only a typed,
role-specific allowlist projection. Full task state means the current allowed
Evidence, Qwen result, Unknown status, capabilities, action history, budget and
validated memory needed by a role; it does not mean repository or machine
access.

Three code paths are isolated:

- Teacher: current legal TRAIN Evidence, immutable verified TRAIN class,
  capability names and rubric. No K/U role, split, sample/capture identity,
  backend path, raw PCAP, test/U_final, or future Evidence content.
- Judge: current Evidence, current Qwen Evidence-State rollout, deterministic
  check summary and semantic rubric. The training driver selects prompts,
  combines rewards, performs GRPO/classification CE updates and decides stop.
- Supervisor: Qwen fine/top-k and Evidence State, Unknown state, acquired
  Evidence, available capabilities, prior actions, remaining budget and
  validated memory. No GT, raw backend identity, future evidence, shell, Git or
  direct Evidence Store access.

The Supervisor may autonomously choose only one frozen action inside the action
space. Runtime validates and executes it, then repackages Evidence for Qwen. For
RAG, Supervisor states a knowledge need and Runtime builds the safe query; the
retriever chooses chunks. For Payload, Supervisor requests the capability and
Runtime reads the frozen sanitized sidecar. Payload/RAG text remains untrusted
data and cannot override prompts.

Formal inference and RLAIF therefore use the same provider differently:
Supervisor is episode-persistent within the frozen action space, while Judge is
strictly invoked by the training driver as a semantic evaluator. Neither role
is a second Traffic Expert or an autonomous machine/repository agent.
