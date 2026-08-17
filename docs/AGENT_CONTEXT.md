# Agent Context

STATE_SCHEMA=AGENT_CONTEXT_V1
LAST_UPDATED=2026-08-17
UPDATED_BY_TASK=CREATE_COMPACT_AGENT_NEUTRAL_CONTEXT_V1

This is the single short entry point every agent reads before substantive project
work. It carries only the current state and operating rules. Historical detail
lives in the sources listed under "Read on demand".

## Authority

Repository artifacts override conversational or persistent Agent memory.

SOURCE_OF_TRUTH_PRIORITY=

1. researcher-authorized frozen protocol / contract
2. formal report JSON
3. formal report MD
4. canonical artifact manifest / hash
5. this file
6. PROJECT_HANDOFF
7. vendor bootstrap (AGENTS.md)
8. conversational / persistent Agent memory

If a higher-priority source conflicts with a lower-priority one, use the
higher-priority one. If same-level authoritative artifacts conflict, output
`PROJECT_STATE_CONFLICT=NEEDS_REVIEW` and STOP.

## Stable operating rules

- Master split is immutable.
- FINAL_TEST is protected unless explicitly authorized.
- Evidence must obey strict past-only runtime availability.
- Teacher is not GT (not classification / utility / Unknown / recoverability /
  continual / RL-reward GT).
- No hidden rescue experiment after a preregistered gate result.
- Do not relabel PASS / YELLOW / FAIL after results.
- Large artifacts stay outside Git.
- Never force push.
- Use PROVISIONAL / NOT_RUN / NEEDS_REVIEW instead of guessing.
- NEXT_PROPOSED_ACTION is not authorization.
- Only CURRENT_AUTHORIZED_TASK or an explicit researcher prompt authorizes
  execution.

## Current research state

```text
PROJECT_STAGE=CORE_HYPOTHESIS_VALIDATION

CORE_DATASET=NF3-ToN-IoT
MASTER_SPLIT_STATUS=FROZEN
FINAL_TEST_STATUS=PROTECTED

TEACHER_CACHE_STATUS=FROZEN_COMPLETE_2000_VALID
SEMANTIC_REFERENCE_STATUS=FROZEN_COMPLETE_63_VALID
TEACHER_CACHE_MODEL=deepseek-v4-flash
CORE_HIGH_TOKEN_DEEPSEEK_DEPENDENCY_COMPLETE=true

TEACHER_ACTION_COVERAGE=STOP_AND_CLASSIFY 741 / ACQUIRE_TEMPORAL 1259
  / ACQUIRE_RELATION 0 / ENTER_NOVELTY_DETECTION 0
(TEACHER_SUPERVISOR_BASELINE=VALID; policy demonstration is
valid-with-action-support-limitation; imitation init is limited, not default)

CORE_HYPOTHESIS_GATE_1=YELLOW        (do not relabel PASS)
GATE_0=PASS
GATE_1_TEMPORAL_STATUS=MODEST_CONSISTENT_POSITIVE
GATE_1_RELATION_STATUS=OVERALL_NEGATIVE_CONDITIONAL_VALUE_UNRESOLVED
GATE_1_FULL_STATUS=NEGATIVE_AT_FROZEN_RF_PROBE
GATE_1_AGGREGATE_BOOTSTRAP_COMPLETENESS=PENDING_OPTIONAL_CHECK

CORE_HYPOTHESIS_GATE_1B=NOT_RUN
MODEL_B_STATUS=NOT_STARTED
RL_STATUS=NOT_STARTED
OPEN_WORLD_CAUSAL_GATE_STATUS=NOT_STARTED
CONTINUAL_STATUS=NOT_STARTED
```

## Current authorization

```text
CURRENT_AUTHORIZED_TASK=AGENT_CONTEXT_SYNCHRONIZATION_ONLY
NEXT_PROPOSED_ACTION=CORE_HYPOTHESIS_GATE_1B_CONDITIONAL_EVIDENCE_UTILITY_SEPARABILITY
NEXT_ACTION_AUTHORIZED=false

CURRENT_FORBIDDEN_NEXT_STEPS=
  CORE_GATE_1B_EXECUTION
  QWEN_MODEL_B
  RL
  OPEN_WORLD_CAUSAL_GATE
  CONTINUAL
```

Gate 1B (proposed, not authorized) asks: before acquiring Evidence, can
runtime-visible Basic state alone predict HELP vs HARM — especially Temporal
conditional utility and Relation unique/conditional utility?

## Latest formal result

```text
LATEST_FORMAL_REPORT_JSON=reports/research_audit/core_hypothesis_gate_v1.json
LATEST_FORMAL_REPORT_MD=reports/research_audit/core_hypothesis_gate_v1.md
```

Gate 1 interpretation (only what is needed here):

- Temporal is modest but consistently positive (3/3 seeds; mean ΔMacro-F1
  ≈ +0.0065, mean recoverable ≈ 0.0276, mean net recovery ≈ +0.0066;
  meaningful attack-class recovery: DoS, Web_Injection).
- Relation is harmful when always-on under the frozen RF probe (mean
  recoverable ≈ 0.0455, but harm > recovery); non-zero recovery means
  conditional value remains unresolved.
- Temporal + Relation combined is negative at the frozen RF probe.
- Gate 1 remains YELLOW because the preregistered strong-existence criteria
  were not all met. The prior 24k pilot's strong recoverability did not
  reproduce at the same strength.
- Model B / RL / continual are not yet authorized.

## Read on demand

For detailed project history:

```text
docs/PROJECT_HANDOFF.md
```

For exact Gate 1 numbers:

```text
reports/research_audit/core_hypothesis_gate_v1.json   (primary)
reports/research_audit/core_hypothesis_gate_v1.md     (explanatory context)
```

For task-specific frozen constraints: read only the protocol explicitly
required by the current task. Do not preload unrelated reports or plans.

## State maintenance

After a MATERIAL project-state change:

1. create/update the task formal report;
2. update this file;
3. update PROJECT_HANDOFF only if high-level project interpretation changed;
4. preserve historical formal reports unchanged;
5. do not duplicate full metrics into this file.

Material changes include: formal Gate completion; PASS/YELLOW/FAIL; model
training start/completion; dataset/split status change; authorized frozen
protocol change; canonical artifact/hash change; component deprecation;
CURRENT_AUTHORIZED_TASK change; NEXT_PROPOSED_ACTION change; blocker status
change.

## Git/repository state

```text
GIT_CHECKPOINT=50fecfbf6bae84fb3d5106a8f83cb14cfe817471
WORKING_TREE_STATE=Gate 1 formal results complete, uncommitted
GATE_1_CHECKPOINT_STATUS=FORMAL_RESULTS_COMPLETE_UNCOMMITTED
```

(untracked: Gate 1 report json/md + runner tool + its test)
