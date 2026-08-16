# DeepSeek / Teacher API Dependency Audit

> Audit date: 2026-08-15
>
> Repository: `flow-security-agent`
>
> Audited HEAD: `b0b4ed40b3bd11d88555a192d57ed09e52007cdb`
>
> Scope: static repository and cost-exposure analysis only. No API, model, training, data-generation, or canonical-plan mutation was performed.
>
> Historical readiness snapshot: DEC-0026 subsequently froze the split,
> taxonomy, rotations and nonleaking request manifests on 2026-08-16. Its cost
> analysis and role prohibitions remain authoritative; statements that B1 must
> first be frozen are superseded by
> [dataset_v4_final_split_report.md](../dataset_v4/dataset_v4_final_split_report.md).

## 1. Executive conclusion

```text
DEEPSEEK_DEPENDENCY_AUDIT_STATUS=PASS_WITH_DOCUMENTATION_CONFLICTS
REQUIRED_HIGH_TOKEN_TEACHER_WORK=false
LIKELY_OPTIONAL_HIGH_TOKEN_WORK=BOUNDED_TEACHER_CACHE_V1_ONLY
LEGACY_TEACHER_WORK_FOUND=true
CANONICAL_PLAN_CONFLICTS=0
NONCANONICAL_OPERATIONAL_CONFLICTS=6
```

DEC-0025 does not require DeepSeek for NF3 labels, Model B classification, operational Evidence utility, True Unknown construction, the primary controller, novelty scoring, or continual-learning oracle feedback. Every core path can run with zero DeepSeek calls.

The only realistic future price exposure is optional: a bounded, reusable Supervisor/policy-demonstration cache and a much smaller semantic-admissibility reference. A full online DeepSeek Supervisor evaluation remains possible but is not required and should not be pre-generated before Dataset-v4 split/taxonomy, the development Unknown rotations, and the model-safe input contract are frozen.

Historical Model A Teacher work is substantial but sunk and cache-backed. It must not be regenerated. The tracked code retains explicit live Teacher and provider entrypoints, but none is invoked implicitly.

## 2. Scope and method

The keyword scan covered `README.md`, `AGENTS.md`, canonical research plans, architecture/training/operations documents, `PROJECT_HANDOFF`, `configs/`, `tools/`, `scripts/`, `src/`, tests, and tracked reports. The broad scan matched 277 files. These matches were then reduced to real research tasks using the authority chain in `research_plan_detailed.md` and DEC-0025 rather than classifying by keyword alone.

The audit distinguishes:

- **plan requirement** from reusable code capability;
- **current Model B semantics** from Model A historical reproducibility;
- **logical records** from network attempts;
- **semantic admissibility** from empirical operational utility;
- **held-out dataset GT used as an offline oracle** from model-visible GT or Teacher labels.

No endpoint was contacted and no environment secret was read.

## 3. Current authoritative contract

The current canonical plan establishes the following:

- True Unknown is a whole semantic class held out from classifier training and final threshold tuning (`research_plan_detailed.md:33`; `model_b_evidence_openworld_design.md:37,110`).
- Semantic admissibility may use deterministic protocol review, a human expert, or optional offline DeepSeek review (`research_plan_detailed.md:63`).
- Operational utility is OOF/cross-fitted predictive improvement, not a semantic label (`research_plan_detailed.md:64`; `research_plan_and_timeline.md:65,119`).
- DeepSeek is limited to offline semantic review, optional policy demonstrations, optional explanations, and an optional Supervisor baseline; it is not Model B utility GT (`research_plan_detailed.md:89`; `open_world_continual_agent_design.md:130`).
- The first controller is deterministic/supervised utility-driven and does not require RL (`research_plan_detailed.md:89`; `agent_architecture_provisional.md:131`).
- RLAIF/PPO/GRPO are not core requirements and LLM-level RL is unauthorized (`research_plan_detailed.md:93`; `research_plan_and_timeline.md:109`).
- Held-out official labels are offline evaluation truth and become continual feedback only after the explicit label-request/oracle boundary (`open_world_continual_agent_design.md:114`).

## 4. Real plan-item classification and token exposure

Token estimates are deliberately ranges, not price estimates. Input/output exposure includes prompt/schema overhead but excludes provider-side hidden reasoning. “Calls” means logical API requests; bounded repair/retry allowance is stated separately.

| ID | Real plan item | Classification | DeepSeek need | Estimated calls | Estimated input tokens | Estimated output tokens | Decision |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| A1 | NF3 fine/broad classification labels and class map | `ACTIVE_REQUIRED` | none; official dataset GT | 0 | 0 | 0 | Teacher must not create or change labels |
| A2 | Model B Known classifier, small/structured baselines, novelty candidates | `ACTIVE_REQUIRED` | none | 0 | 0 | 0 | Qwen/local models only |
| A3 | Operational utility targets from Basic vs Basic+Evidence | `ACTIVE_REQUIRED` | none; OOF/cross-fitted empirical outcomes | 0 | 0 | 0 | No semantic label may replace this target |
| A4 | True Unknown rotations | `ACTIVE_REQUIRED` | none; whole-class held-out dataset GT | 0 | 0 | 0 | Never Teacher-labeled |
| A5 | Primary deterministic/supervised utility controller | `ACTIVE_REQUIRED` | none | 0 | 0 | 0 | DeepSeek not needed for the proposed method |
| A6 | Continual benchmark feedback and new-class registration | `ACTIVE_REQUIRED` | none; held-out dataset GT may simulate verified oracle after `REQUEST_LABEL` | 0 | 0 | 0 | No self-label or DeepSeek label |
| A7 | Semantic-admissibility contract | `ACTIVE_REQUIRED` | zero API by default; deterministic/human review is sufficient | 0 | 0 | 0 | Optional small reference described below |
| O1 | `teacher_cache_v1`: bounded Supervisor/demo/imitation artifact | `ACTIVE_OPTIONAL_LIKELY` | optional DeepSeek | 2,000 base; cap 2,200 with schema repairs | 2.2–5.5M | 0.22–0.55M | Conditional on B1/input-contract freeze |
| O2 | `semantic_admissibility_reference_v1` | `ACTIVE_OPTIONAL_LIKELY` | optional DeepSeek plus human review | 63 base; cap 80 | 0.04–0.10M | 0.008–0.025M | Small and reusable; not per-sample GT |
| O3 | Full online DeepSeek Supervisor paper baseline | `ACTIVE_OPTIONAL_UNLIKELY` | optional DeepSeek | 3,000–20,000 for 3k–10k episodes and 1–2 decisions | 3–60M | 0.24–5M | Do not pre-generate before final protocol; may be omitted |
| O4 | Selected qualitative explanation generation | `ACTIVE_OPTIONAL_UNLIKELY` | optional DeepSeek or local model | 50–200 | 0.05–0.60M | 0.008–0.08M | Generate only selected final examples, not a corpus |
| O5 | Knowledge/RAG extension | `ACTIVE_OPTIONAL_UNLIKELY` | zero DeepSeek by default | 0 | 0 | 0 | Retrieval is not synthetic RAG generation |
| O6 | Small RL policy comparison | `ACTIVE_OPTIONAL_UNLIKELY` | zero DeepSeek under the current plan | 0 | 0 | 0 | RL does not imply RLAIF |
| L1 | Model A Teacher V3 bulk, 22,957 records | `LEGACY_DEPRECATED` | historical DeepSeek | tens-of-thousands+ attempts | **28.419M actual retained** | **4.082M actual retained** | Completed; cache must be reused, never regenerated |
| L2 | Model A Teacher-v2 bulk, 20,807 records | `LEGACY_DEPRECATED` | historical DeepSeek | at least 20,807 logical records; repairs occurred | actual unknown; 25.8–33.6M estimated | actual unknown; 3.7–4.8M estimated | Completed; provider cost/token totals were not fully retained |
| L3 | Model A Evidence-only RLAIF/GRPO Judge over 6,000-prompt pool | `LEGACY_DEPRECATED` | would require DeepSeek if revived | tens-of-thousands+ per run | roughly 20–200M | roughly 2–30M | Not run; explicitly superseded/unauthorized |
| L4 | Model A mandatory online DeepSeek Supervisor benchmark | `LEGACY_DEPRECATED` | historical plan | thousands | roughly 3–30M | roughly 0.3–3M | Not run; Model B baseline is optional only |
| L5 | Blind sufficiency/classification audit and pair extension | `LEGACY_DEPRECATED` | historical DeepSeek | **529 actual** | **520,887 actual** | **40,089 actual** | Complete; never rerun |
| L6 | DPO/RLHF/PPO/preference generation, synthetic training data, Teacher unknown/new-class labeling | `LEGACY_DEPRECATED` | not authorized | 0 future | 0 future | 0 future | No current task authorizes these |

The L2 estimate uses the tracked Model A V3 mean retained exposure of approximately 1,238 input and 178 output tokens per valid record. Applying the reported 30.4369% V2 repair rate yields an order-of-magnitude upper estimate; it is not reconstructed billing.

## 5. Seven-principle consistency audit

| Principle | Canonical status | Evidence | Repository-wide caveat |
| --- | --- | --- | --- |
| NF3 classification labels come from dataset GT, not Teacher | `PASS` | official artifact/label contract in Dataset-v4 design; no provider may override verified GT in Agent architecture | not restated verbatim in every short derived document |
| Operational Utility is OOF/cross-fitted improvement | `PASS_EXPLICIT` | detailed plan, Model B design, timeline, Dataset-v4 design, Agent design, handoff | stale Model A docs still discuss Teacher sufficiency |
| Teacher `evidence_sufficient/missing_evidence` is not Model B GT | `PASS_EXPLICIT` | detailed plan and Model B/Agent/handoff scope notes | old prompt/config/code remains for Model A reproducibility |
| True Unknown is whole-class held-out GT | `PASS_EXPLICIT` | detailed, Model B, open-world, timeline, Dataset-v4, brief, handoff | old K/U documents describe different Model A roles but are historical |
| Continual benchmark may use held-out dataset GT as verified oracle | `PASS_EXPLICIT_AT_RUNTIME_BOUNDARY` | held-out official label is offline-only and revealed only after `REQUEST_LABEL` | not summarized in every short plan |
| RL is optional and does not require RLAIF | `PASS_EXPLICIT` | detailed, timeline, Model B, open-world, Agent design, handoff | README/AGENTS still state Model A RLAIF as a main stage |
| DeepSeek role is limited to offline review and optional baselines/explanation | `PASS_EXPLICIT` | detailed, Model B, open-world, Agent design, brief, handoff | operational runbook and migration docs are stale |

Within the DEC-0025 canonical set, no semantic contradiction was found. Repository-wide wording is not yet clean: the principles are not repeated with equal explicitness in every brief document, and several operational surfaces still describe superseded Model A execution as current.

## 6. Stale or conflicting operational surfaces

These are not allowed to override DEC-0025, but they materially increase accidental API-call risk:

1. `AGENTS.md:8-14,84-107` still states an LM Evidence-State → mandatory DeepSeek Supervisor → RLAIF mainline, old Edge/IoT roles, and “no model training started.”
2. `README.md:19,52,55,57` still treats Edge/IoT as current sources, Near RLAIF-GRPO as next work, and Formal SFT as not started.
3. `docs/SERVER_MIGRATION.md:3,93,123` still says the only blocker is a missing DeepSeek key and instructs Teacher pilot/bulk resumption, although those tasks completed and were superseded.
4. `docs/runbooks/deepseek_api.md:34-49` presents old Teacher bulk, future RLAIF Judge, and formal Supervisor calls without a DEC-0025 scope warning.
5. `src/flowsec/training/README.md:4-11,45-48` describes the old 16,979-record preparation flow and live Teacher phases as current.
6. `configs/training/near_sft_config_v2.yaml` remains `FROZEN_READY` and `formal_run_authorized: true` for completed Model A. It does not itself call DeepSeek, but can be mistaken for current Model B authorization.

`configs/runtime.example.yaml` contains a dormant `deepseek_remote` profile with an invalid placeholder URL/model. `near_prompt_contracts_v1.json` retains Teacher/Judge/Supervisor schemas. These are reusable capabilities, not automatic calls or current plan requirements.

The live API entrypoints are explicit only: `tools/prepare_near_pretraining.py teacher-pilot|teacher-bulk`, `tools/run_teacher_v2.py connectivity|pilot|bulk`, and the completed blind-audit provider modes. All require explicit invocation and runtime credentials; no scheduled or import-time network call was found.

## 7. `teacher_cache_v1` design — do not execute in this audit

### 7.1 Recommendation and timing

```text
TEACHER_CACHE_V1_RECOMMENDED=CONDITIONAL_YES
TEACHER_CACHE_V1_TARGET_N=2000
EXECUTION_PREREQUISITE=DATASET_V4_B1_SPLIT_TAXONOMY_DEV_ROTATIONS_AND_INPUT_CONTRACT_FROZEN
```

The cache is worth considering because the optional Supervisor/policy-demonstration baseline appears in several current documents and one bounded artifact can support three optional uses. It should **not** be rushed before B1: otherwise class rotations, split legality, confidence provenance, or serialization changes could invalidate the paid output.

If B1 cannot be frozen before the price change, scientific validity takes priority and the cache should not be generated merely to obtain the old price.

### 7.2 Deterministic population

Target `N=2,000`, selected only from legal train/development assets after B1:

| Stratum | Target | Notes |
| --- | ---: | --- |
| `BASIC_SUFFICIENT_KNOWN` | 750 | class-balanced where support permits |
| `RECOVERABLE_KNOWN` | 850 | selection flag remains backend-only |
| `TRUE_UNKNOWN` development rotations | 400 | U-dev/rotation-development only; never sealed final Unknown |

Within each state, balance the seven candidate core classes/rotation roles and OOF Basic confidence bins `<0.40`, `0.40–0.70`, `>0.70`. Record quota shortfalls rather than duplicating rows. Use deterministic sample IDs/digests and a fixed selection seed. A final held-out Unknown, formal test, or any sample later used as a sealed result must not become imitation-training data.

### 7.3 Model-safe runtime input

Allowed:

- current Basic Evidence only;
- OOF Basic predicted class distribution/top candidates and confidence provenance;
- available Evidence family names, bounded costs, budget, and prior action history;
- anonymous Evidence IDs needed for grounding.

Forbidden:

- GT/fine label or class index;
- `BASIC_SUFFICIENT_KNOWN`, `RECOVERABLE_KNOWN`, `TRUE_UNKNOWN`, recoverable flag, or correctness outcome;
- Full Evidence not yet acquired;
- future context or future tool result;
- raw/absolute dataset, file, capture, path, host, address, timestamp, split, or rotation identity;
- final Unknown membership or verified-feedback result.

The backend-only stratification fields must be stored separately from the request digest and must fail a prompt-leakage audit.

### 7.4 Candidate output contract

```json
{
  "predicted_class": "<known class or null>",
  "recommended_action": "STOP | GET_TEMPORAL | GET_RELATION | ENTER_NOVELTY",
  "semantic_gap": "<short normalized semantic description>",
  "confidence": 0.0,
  "short_reason": "<grounded concise reason>"
}
```

`predicted_class` must never invent or name a new class. `short_reason` should be bounded and cite only visible Evidence IDs. One schema repair is allowed; semantic disagreement is retained for evaluation rather than rewritten.

### 7.5 Authorized uses and prohibitions

Authorized only as:

```text
TEACHER_SUPERVISOR_BASELINE
OPTIONAL_POLICY_DEMONSTRATION
OPTIONAL_IMITATION_INITIALIZATION
```

Never as:

```text
OPERATIONAL_UTILITY_GROUND_TRUTH
NF3_CLASSIFICATION_GROUND_TRUTH
TRUE_UNKNOWN_GROUND_TRUTH
CONTINUAL_VERIFIED_LABEL
FINAL_THRESHOLD_TUNING_DATA
```

Each cache record must bind source digest, input digest, prompt/schema version, provider/model ID, generation settings, request ID, token usage, validation status, and role. Store caches outside Git; track only a small manifest/report.

## 8. `semantic_admissibility_reference_v1` design — do not execute

```text
SEMANTIC_REFERENCE_RECOMMENDED=true
BASE_CELLS=7_core_classes × 3_families × 3_patterns = 63
MAX_CALLS_WITH_ADJUDICATION=80
```

Families are `BASIC`, `TEMPORAL`, and `RELATION`. Each family uses three normalized common-pattern archetypes: clearly relevant behavior, common ambiguous/confounded behavior, and missing/weak behavior. The reference reviews class/evidence-level semantics, not individual rows.

Input may name the canonical class and normalized evidence pattern because this is an offline semantic reference, but it must not contain dataset/sample identity, GT row, empirical model outcome, or utility target. Candidate output:

```json
{
  "class": "<canonical class>",
  "evidence_family": "BASIC | TEMPORAL | RELATION",
  "pattern_id": "<versioned pattern>",
  "semantically_admissible": true,
  "relevance": "SUPPORTIVE | NEUTRAL | CONTRADICTORY | CONTEXT_DEPENDENT",
  "causality_constraints": ["..."],
  "common_confounders": ["..."],
  "not_sufficient_when": ["..."],
  "short_rationale": "..."
}
```

All cells require deterministic/expert review before acceptance. This artifact can document admissibility and reviewer consistency; it cannot label samples, define recoverability, supply utility targets, or decide Unknown.

## 9. Pre-price-change recommendation

Recommended, in order:

1. preserve and checksum the existing Model A Teacher V3/V2 and blind-audit caches; this is zero-call work;
2. freeze B1 split/taxonomy/development rotations and the model-safe cache input contract;
3. if step 2 finishes before the price change, generate only `teacher_cache_v1` at `N=2,000` with a 2,200 hard call cap;
4. optionally generate the 63-cell semantic reference, although its low token exposure makes price timing less important.

Do **not** pre-generate full-dataset Teacher `evidence_sufficient/missing_evidence`, operational utility labels, final online Supervisor traces, RLAIF/Judge rewards, unknown/new-class labels, full explanation corpora, synthetic traffic labels, or RAG-generated knowledge. Their protocols are either superseded, unauthorized, not frozen, or scientifically invalid as precomputed truth.

## 10. Acceptance block

```text
DEEPSEEK_DEPENDENCY_AUDIT_STATUS=PASS_WITH_DOCUMENTATION_CONFLICTS
REQUIRED_HIGH_TOKEN_TEACHER_WORK=false
LIKELY_OPTIONAL_HIGH_TOKEN_WORK=TEACHER_CACHE_V1_2000_CALLS_CONDITIONAL
LEGACY_TEACHER_WORK_FOUND=true
CANONICAL_PLAN_CONFLICTS=0

PRE_PRICE_CHANGE_RECOMMENDED_TASKS=VERIFY_EXISTING_CACHES;FREEZE_B1_AND_INPUT_CONTRACT;THEN_OPTIONAL_TEACHER_CACHE_V1_2000;OPTIONAL_SEMANTIC_REFERENCE_63
DO_NOT_PREGENERATE_TASKS=MODEL_B_UTILITY_GT;EVIDENCE_SUFFICIENT_OR_MISSING_EVIDENCE_BULK;FULL_ONLINE_SUPERVISOR_EVAL;RLAIF_OR_JUDGE_REWARDS;UNKNOWN_OR_NEW_CLASS_LABELS;FULL_EXPLANATION_CORPUS;SYNTHETIC_OR_RAG_GENERATED_LABELS

TEACHER_CACHE_V1_RECOMMENDED=CONDITIONAL_YES_AFTER_B1_FREEZE
TEACHER_CACHE_V1_TARGET_N=2000
SEMANTIC_REFERENCE_RECOMMENDED=true

ESTIMATED_TOKEN_EXPOSURE_BY_TASK=REQUIRED_CORE_0;TEACHER_CACHE_V1_INPUT_2.2_TO_5.5M_OUTPUT_0.22_TO_0.55M;SEMANTIC_REFERENCE_INPUT_0.04_TO_0.10M_OUTPUT_0.008_TO_0.025M;FULL_OPTIONAL_SUPERVISOR_INPUT_3_TO_60M_OUTPUT_0.24_TO_5M

RESEARCHER_REVIEW_REQUIRED=true
```
