# Agent / Runtime 暂定架构与实施约束

> Status: **DEC-0024 IMPLEMENTATION BOUNDARY / PROVISIONAL MODEL B DESIGN**
>
> Updated: 2026-08-15
>
> Authority: the [canonical research plan](../research_plan/research_plan_detailed.md) is highest; the [open-world continual design](../research_plan/open_world_continual_agent_design.md) defines current Model B architecture. The Near protocol remains the historical Model A execution contract. This document maps the new architecture onto Runtime boundaries; [PROJECT_HANDOFF](../PROJECT_HANDOFF.md) records implementation state only.

## 1. Status labels

- **[HARD CONSTRAINT]**: frozen architecture, safety or information-isolation boundary; changes require a new canonical Decision.
- **[CURRENT DEFAULT]**: first implementation choice, selectable only through the legal validation procedure.
- **[VALIDATION TUNABLE]**: small, reproducible train/validation-safe choice; never tune on formal test or `U_final`.
- **[DEFERRED]**: outside the first Near mainline.
- **[OPTIONAL]**: may be omitted without blocking the current gated phase.
- **[IMPLEMENTED] / [UNAVAILABLE]**: current engineering fact, not a permanent research decision.

## 2. DEC-0024 end-to-end architecture

**[HARD CONSTRAINT]** Perception, Control and Evolution have distinct responsibilities:

```text
Traffic Stream → Canonical Evidence
→ Qwen3.5-9B shared representation h
→ Family Head + Fine Head + post-hoc Unknown scores
→ Known classify | Unknown reject | Unknown Buffer
→ optional Evidence/Knowledge [only after Gates]
→ verified analyst/oracle feedback
→ class confirmation + replay adaptation
→ regression-gated Model B_t → Model B_{t+1}
→ Structured Result + Trace + Version Registry
```

No traditional classifier routes samples to Qwen. No policy, provider, RAG or Runtime component may manufacture observation or override verified GT. Runtime remains the sole action, information, hidden-oracle, model-release and rollback authority.

Model A's `Fine Head + generative Evidence State + DeepSeek Supervisor` path is retained as a historical baseline, not the current mandatory architecture. Model A Evidence State failed on Basic-insufficient and missing-gap detection. Teacher sufficiency is not operational utility. DeepSeek is now offline Teacher/demonstration/reviewer plus an optional Supervisor baseline.

## 3. Qwen representation boundary

### 3.1 Shared backbone and Fine Head

**[HARD CONSTRAINT]** Model B0 uses frozen Qwen base + trainable LoRA + small trainable Family and Fine Classification Heads + retained frozen original LM Head. Both heads consume shared `h_session`. `EXACT` mappings may supervise both heads; `FAMILY_ONLY` masks Fine loss. There is no generative competing fine label.

Model A used `ATTENTION_MASKED_MEAN_V1`; Model B0 pooling must be registered in its own matched pilot rather than assumed from Model A. The implemented training-side harness and audited Qwen3.5 LoRA inventory are reusable. The vLLM raw service does not implement task heads.

### 3.2 LM Head status

The LM Head is retained for explanation and optional structured descriptive output. Model A's multi-gap schema remains a reusable serialization contract, but its runtime sufficiency/gap capability is `FAIL`. It has no stop/acquire authority.

Historical Model A fields included:

- optional brief behavior summary;
- supporting evidence references;
- unique `missing_evidence[]` from `PACKET_PAYLOAD`, `APPLICATION`, `TEMPORAL`, `RELATION`, `KNOWLEDGE`;
- evidence sufficiency;
- `primary_gap`;
- `gap_type` in `OBSERVATIONAL`, `KNOWLEDGE`, `MIXED`, `NONE`;
- `recoverability` in `ALREADY_SUFFICIENT`, `RECOVERABLE_WITH_AVAILABLE_TOOLS`, `NOT_RECOVERABLE_FROM_AVAILABLE_NETWORK_EVIDENCE`;
- backoff/abstention-related state.

It does not generate an independent competing fine label or a free-form tool name. A future Evidence Decision Head is built only after out-of-fold Evidence Utility passes; it is a small discriminative head before any new LM supervision. Long Chain-of-Thought is not a model or system interface.

### 3.3 Model A Evidence-v2 historical contract

Model A learned one Basic-v2 primary per eligible TRAIN session and bounded auxiliary states. Its data legality, packet alignment, strict-past and Observation/Knowledge rules remain reusable. Its Teacher semantic targets do not become Model B operational utility labels.

`CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1` remains a valid Model A supervision rule, but the current Evidence LM output failed operational evaluation. Old Training #2 Evidence-only RLAIF is downgraded. Model B first validates source compatibility, Evidence utility, static heads/Unknown and a non-RL continual loop.

## 4. Independent Unknown boundary

**[HARD CONSTRAINT]** Unknown is not a K+1 training class and is independent from LLM self-reported confidence. Dataset-v4 freezes `K0/U_dev/U_final/U_inc` by canonical semantic class before training. The first detector compares MSP, Energy and normalized-cosine Prototype Distance over Fine logits and/or `h_session`; U_dev selects thresholds and U_final remains sealed.

Scores may be recomputed after a legal Evidence update only if Evidence Utility passed and the route was frozen before formal evaluation. Unknown and Abstain differ:

- **Unknown**: evidence supports that the session is outside K_known.
- **Abstain**: evidence/capability/budget is insufficient for a reliable decision.

A small learned Unknown head and score fusion are **[DEFERRED BACKUP]** until simple candidates demonstrate a limitation.

## 5. DeepSeek logical roles after DEC-0024

DeepSeek is an external offline assistance provider, not the permanent control core. The concrete endpoint/model ID belongs in run config and manifest, not in the architecture.

### 5.1 Teacher

Teacher assists TRAIN/development Evidence-State target construction. It may receive verified GT as immutable context but cannot decide or change the label, create observations or access `U_final`.

### 5.2 Policy demonstration / optional Judge

DeepSeek may provide bounded policy demonstrations or optional semantic review after a valid environment/reward exists. It is not a source of self-confirming GT and no bulk RLAIF is currently authorized.

### 5.3 Optional Supervisor baseline

The existing Supervisor can be evaluated as a policy baseline. It is not required by the final architecture and cannot be called the system's own continual policy because its external parameters are not adapted by this project.

It cannot replace the fine label, see hidden GT, release a model, register a class or bypass Runtime.

### 5.4 Role isolation

**[HARD CONSTRAINT]** Teacher, demonstration/Judge and optional Supervisor baseline retain independent prompts, schemas, permissions, caches and logs. Codex implements orchestration and audits but is not a formal label authority.

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

Each round executes at most one Runtime-validated action. Initial Model B action families are:

- `CLASSIFY_KNOWN`;
- `REJECT_AS_UNKNOWN`;
- `DEFER_TO_UNKNOWN_BUFFER`;
- `QUERY_KNOWLEDGE`;
- `REQUEST_ANALYST_FEEDBACK`.

Only after `EVIDENCE_UTILITY_GATE=PASS` may the policy add `ACQUIRE_PACKET_PAYLOAD`, `ACQUIRE_APPLICATION`, `ACQUIRE_TEMPORAL` and `ACQUIRE_RELATION`. `PROPOSE_NEW_CLASS` and `TRIGGER_ADAPTATION` remain future gated actions. Runtime, not the Agent, performs class registration, parameter update and release.

Historical Model A action names remain supported for audit/runtime compatibility but are not the Model B policy contract. Arbitrary raw payload access remains prohibited.

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
+ model-safe descriptive state and/or validated policy features
+ frozen Unknown state/score
+ small retrieved validated Experience set
+ budget/history
```

Before formal test/U_final, freeze prompt hashes, schemas, provider/model identity, temperature/reasoning config, API version and budget. A Supervisor may propose an improvement but cannot modify its own system prompt online.

## 11. Agent baselines and fairness

If the Evidence Utility Gate passes, the Evidence-policy comparison includes:

- Basic: Basic-v2 only;
- Fixed Full: all legal currently available Evidence without dynamic selection;
- RulePolicy: deterministic evidence choice;
- DeepSeek Supervisor baseline: optional external dynamic evidence choice.

All share the same Traffic Expert, tools, information domain and maximum budget. Report fine/open-set metrics plus tool calls, Qwen/Supervisor/RAG tokens, latency, API cost, recovery and budget compliance. Fixed Full is an evidence upper-bound/control, not an Agent.

The primary policy baseline is a strong Heuristic. A small learnable policy is attempted only after the non-RL continual environment works. If it does not improve long-horizon outcomes over Heuristic, policy RL stops and the negative result is reported.

## 12. Evolution stores

The Evolution Plane separates Unknown Buffer, Experience Buffer, Verified Feedback Store, Replay Buffer, Class Registry and Model Version Registry. Experience records only externally verified `State → Action → Outcome → Verified Feedback`; self-predictions never self-confirm.

| Phase | Permission |
| --- | --- |
| TRAIN | verified read/write |
| Validation | read-only; may select retrieval settings |
| U_dev | read-only by default |
| Test/U_final | frozen read-only |

Stores exclude raw identity/payload shortcuts from model-visible retrieval. Formal test/U_final are frozen read-only and never trigger adaptation.

## 13. Verified new-class registration

Few-shot Class Memory is no longer a core route. Unknown clustering is only a proposal mechanism. Semantic class registration requires multiple consistent labels from the Verified Feedback Store and a reviewed Class Registry update.

```text
Unknown Buffer → representative REQUEST_ANALYST_FEEDBACK
→ multiple consistent verified labels
→ reviewed REGISTER_NEW_CLASS
→ episodic new-class batch + balanced replay
→ regression-gated Model B_t → Model B_{t+1}
```

Updates may compare head-only with LoRA+heads; base Qwen remains frozen. A failed Release Gate rolls back. One-shot automatic class creation is prohibited.

## 14. RL staging boundary

`RL-0` is a strong deterministic Heuristic. `RL-1` freezes Qwen and trains only a small policy over Known/Unknown scores, Evidence/capability state, buffer/feedback state, budget, history and model version. Choose bandit versus sequential RL only after the environment shows whether actions affect future state.

`RL-2` Qwen policy LoRA/PPO/GRPO is high-cost and unauthorized until RL-1 reproducibly beats Heuristic, delayed reward is trustworthy, enough trajectories/GPU exist and the advisor confirms RL should update Qwen. Reward uses verified eventual outcomes, never confidence as a self-reward.

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

Reusable implementation: deterministic Runtime, Production Safe Adapter v1, provider-neutral boundaries, local Qwen, training-side hidden-state/Fine-Head harness, Dataset-v3/Evidence-v2 provenance, role-isolated DeepSeek paths and Model A checkpoint/evaluation. Model A Formal SFT and evaluation are complete; its known classification passes and generative Evidence State fails.

Not implemented/run: Dataset-v4 source preflight/build, Evidence Utility Gate, Family Head/Model B0, fresh-vs-warm-start ablation, Dataset-v4 Unknown, continual stream, verified-feedback adaptation, RL-0/1/2 or sealed final open-world evaluation.

**[DOWNGRADED / CONDITIONAL]** old Evidence-only RLAIF, permanent DeepSeek Supervisor, few-shot onboarding and current generative Evidence-State control. Full Teacher labeling, Model B0 SFT, complex continual learning and LLM RL all require cheap Gates.

**[PROVISIONAL]** final Dataset-v4 composition/taxonomy, warm start, Evidence actions/head, Unknown detector/fusion, clustering, replay tolerance, RL algorithm/rewards and whether RL ever updates Qwen.


## Optional DeepSeek baseline task-state boundary

Any DeepSeek baseline remains least-privilege at every API call. Runtime owns
the complete episode and sends only a typed, role-specific allowlist projection.
This section constrains an optional provider baseline; it does not make DeepSeek
the permanent controller.

Three code paths are isolated:

- Teacher: current legal TRAIN Evidence, immutable verified TRAIN class,
  capability names and rubric. No K/U role, split, sample/capture identity,
  backend path, raw PCAP, test/U_final, or future Evidence content.
- Demonstration/Judge: current legal state, rollout, deterministic check summary
  and semantic rubric. No self-confirming reward or hidden runtime GT.
- Optional Supervisor baseline: Qwen fine/top-k and descriptive state, Unknown state, acquired
  Evidence, available capabilities, prior actions, remaining budget and
  validated memory. No GT, raw backend identity, future evidence, shell, Git or
  direct Evidence Store access.

The optional Supervisor baseline may choose only one frozen action inside its
evaluation action space. Runtime validates and executes it. Payload/RAG remains
untrusted data and cannot override prompts, hidden-oracle permissions, class
registration or model release.

Neither role is a second Traffic Expert, verified-label source, autonomous
machine/repository agent or required component of Model B continual evolution.
