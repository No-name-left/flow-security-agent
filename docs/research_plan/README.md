# docs/research_plan — Canonical Navigation Index

> LAST_UPDATED=2026-08-20
> UPDATED_BY_TASK=CREATE_GROUP_MEETING_PROJECT_OVERVIEW_AND_INVESTIGATE_GITHUB_ERROR
>
> This README is the canonical index for the research-plan directory. It
> classifies every document by lifecycle stage so that normal Agent startup
> does NOT require reading every file. Lifecycle classification is carried
> by this page plus each document's STATUS header; file paths are stable
> (no physical relocation — moving files would break links across 15+
> docs and add churn without authority value).

## 0. Authority order (never changed by this index)

1. researcher-authorized frozen protocol / contract
2. formal report JSON
3. formal report MD
4. canonical artifact manifest / hash
5. `docs/AGENT_CONTEXT.md`
6. `docs/PROJECT_HANDOFF.md`
7. vendor bootstrap (`AGENTS.md`)
8. conversational / persistent Agent memory

Within this directory the standing hierarchy is:
`research_plan_detailed.md` (highest research meaning, §0 = current frozen
scheme) → `experiment_protocol_v1.md` (DEC-0027 formal experiment /
statistical rules) → the current active protocol →
`dataset_v4_b1_runtime_contract.md` + `dataset_v4_split_protocol.md`
(engineering / data boundaries). `AGENTS.md` states the same order.

## 1. Current research direction (three mechanisms / timescales)

Project framing preserved: **open-world continually learning /
self-evolving malicious traffic Agent** — Evidence-Conditioned Open-World
Traffic Recognition. The recent review (2026-08-20) distinguishes three
interdependent mechanisms / timescales inside that framing:

```text
A. REPRESENTATION / OBSERVATION ADAPTATION   (Model B V1 territory)
   - runtime typed Evidence (Basic/Temporal/Relation)
   - Recoverable Known vs residual novelty
   - target-specific recovery correspondence
   - generic Evidence-distribution-induced Knownness must NOT be
     confused with recovery

B. POLICY EVOLUTION                          (future, gated)
   - RL policy for Evidence acquisition / stopping / novelty admission
   - possible discovery/verification routing
   - RL is a DECISION component, NOT a generic replacement for the
     supervised/clustering components

C. KNOWLEDGE / CLASS EVOLUTION               (future, gated)
   - residual Unknown buffer -> clustering -> trusted/human verification
   - new-class registration -> supervised adaptation -> old-class replay
   - safety/release gate

LONG_TERM_SELF_EVOLUTION_CANDIDATE (LONG-TERM / CANDIDATE, not demonstrated)
   verified novel-class outcomes may later provide delayed feedback for
   past recovery/acquisition/novelty-admission trajectories:
   pi_0 -> pi_1 -> pi_2 -> ...
   Future evaluation must test whether later evolution rounds improve
   performance on FUTURE unseen classes, not only already registered ones.
```

No novelty is claimed for generic open-set recognition, Unknown
clustering, class-incremental learning, active feature acquisition, RL or
continual learning (see `literature_novelty_reassessment_v1.md`).
No RL / continual / self-evolution experiment is authorized by this
index; those remain LONG-TERM / CANDIDATE.

## 2. Lifecycle classification

| Class | Files |
| --- | --- |
| CURRENT_CORE | `research_plan_detailed.md`, `research_plan_and_timeline.md`, `experiment_protocol_v1.md`, `open_world_continual_agent_design.md` |
| ACTIVE_PROTOCOL | `model_b_recovery_aware_representation_v1_protocol.md` |
| DATA_CONTRACT | `dataset_v4_split_protocol.md`, `dataset_v4_b1_runtime_contract.md` |
| COMPLETED_FROZEN_PROTOCOL | `recoverability_information_sufficiency_gate_v1_protocol.md`, `recovery_signal_characterization_v2_protocol.md`, `strong_hybrid_osr_evidence_gate_v2_protocol.md`, `strong_neural_osr_evidence_gate_v1_protocol.md`, `evidence_processing_method_dependence_diagnostic_v1_protocol.md` |
| LEGACY_SUPERSEDED | `model_b_evidence_openworld_design.md` (DEC-0025 design source; operative design now the Model B V1 protocol), `multi_dataset_v4_design.md` (frozen core dataset; multi-source only secondary candidates, re-opening needs a Decision) |
| REFERENCE | `literature_novelty_reassessment_v1.md` (active novelty addendum), `research_plan_brief.md` (human-oriented brief), `task_definition_v2.md` (original task spec) |
| REPORTING_REFERENCE | `group_meeting_project_overview_2026-08-20.md` (advisor-facing project overview; STATUS=REPORTING_REFERENCE, SCIENTIFIC_AUTHORITY=false — NOT a protocol or authority) |

## 3. Per-file index

| File | Class | Status / note |
| --- | --- | --- |
| [research_plan_detailed.md](research_plan_detailed.md) | CURRENT_CORE | canonical detailed plan; §0 = current frozen scheme (DEC-0025/0026/0027); later sections historical |
| [research_plan_and_timeline.md](research_plan_and_timeline.md) | CURRENT_CORE | canonical execution order, phases B1–B7, hard boundaries, current status |
| [experiment_protocol_v1.md](experiment_protocol_v1.md) | CURRENT_CORE | DEC-0027 frozen formal experiment / isolation / statistical rules (FROZEN DESIGN / NOT RUN) |
| [open_world_continual_agent_design.md](open_world_continual_agent_design.md) | CURRENT_CORE | long-term continual / self-evolving Agent design; Plane A/B/C; RL boundary |
| [model_b_recovery_aware_representation_v1_protocol.md](model_b_recovery_aware_representation_v1_protocol.md) | ACTIVE_PROTOCOL | Model B V1: recovery-aware typed-Evidence representation (STATUS=FROZEN_DESIGN_NOT_RUN as of 2026-08-20; training launched only by a separate task) |
| [dataset_v4_split_protocol.md](dataset_v4_split_protocol.md) | DATA_CONTRACT | DEC-0026 frozen split, taxonomy, rotations, leakage contract |
| [dataset_v4_b1_runtime_contract.md](dataset_v4_b1_runtime_contract.md) | DATA_CONTRACT | DEC-0025 B1 runtime-input boundary, Evidence semantics, Teacher cache |
| [recoverability_information_sufficiency_gate_v1_protocol.md](recoverability_information_sufficiency_gate_v1_protocol.md) | COMPLETED_FROZEN_PROTOCOL | frozen gate; OUTCOME=REPRESENTATION_BOTTLENECK_SUPPORTED; post-run validation PASS (2026-08-20) |
| [recovery_signal_characterization_v2_protocol.md](recovery_signal_characterization_v2_protocol.md) | COMPLETED_FROZEN_PROTOCOL | frozen gate V2; outcome RECOVERY_SIGNAL_INCONCLUSIVE (CASE D) |
| [strong_hybrid_osr_evidence_gate_v2_protocol.md](strong_hybrid_osr_evidence_gate_v2_protocol.md) | COMPLETED_FROZEN_PROTOCOL | frozen gate; decision METHOD_DEPENDENT_REVIEW; validation performed 2026-08-18 |
| [strong_neural_osr_evidence_gate_v1_protocol.md](strong_neural_osr_evidence_gate_v1_protocol.md) | COMPLETED_FROZEN_PROTOCOL | DEC-0028 frozen pre-Model-B baseline gate; post-run validation performed 2026-08-18 |
| [evidence_processing_method_dependence_diagnostic_v1_protocol.md](evidence_processing_method_dependence_diagnostic_v1_protocol.md) | COMPLETED_FROZEN_PROTOCOL | frozen diagnostic; completed 2026-08-18 (READOUT_DOMINANT interpretation) |
| [model_b_evidence_openworld_design.md](model_b_evidence_openworld_design.md) | LEGACY_SUPERSEDED | DEC-0025 Model B design source (lineage only; operative design = Model B V1 protocol) |
| [multi_dataset_v4_design.md](multi_dataset_v4_design.md) | LEGACY_SUPERSEDED | multi-dataset design; core dataset frozen to NF3-ToN-IoT; secondary sources need a Decision |
| [literature_novelty_reassessment_v1.md](literature_novelty_reassessment_v1.md) | REFERENCE | active novelty / claim-safety addendum (non-frozen, supersedes nothing); register in `reports/research_audit/related_work_novelty_reassessment_v1.{md,json}` |
| [research_plan_brief.md](research_plan_brief.md) | REFERENCE | human-oriented brief (points to detailed plan) |
| [group_meeting_project_overview_2026-08-20.md](group_meeting_project_overview_2026-08-20.md) | REPORTING_REFERENCE | advisor/group-meeting overview (Chinese, 2026-08-20); communicates current plan + validated results; no scientific authority, not a protocol |
| [task_definition_v2.md](task_definition_v2.md) | REFERENCE | original task definition v2 (historical) |

## 4. What to read for each task category

Normal startup is `AGENTS.md` → `docs/AGENT_CONTEXT.md` → the specific
frozen protocol/report the task names. From this directory, per category:

| Task category | Normally read (1–3 files) |
| --- | --- |
| Freeze / preregister a formal gate or run a formal gate | `research_plan_detailed.md` §0, `experiment_protocol_v1.md`, the gate's own protocol |
| Model B formal training / evaluation | `model_b_recovery_aware_representation_v1_protocol.md`, `dataset_v4_split_protocol.md`, (serializer `tools/model_b_input_serializer_v1.py`) |
| Data / split / runtime-contract work | `dataset_v4_split_protocol.md`, `dataset_v4_b1_runtime_contract.md` |
| Novelty / claim-safety / literature work | `literature_novelty_reassessment_v1.md` (+ register in `reports/research_audit/`) |
| Long-term continual / RL / self-evolution design | `open_world_continual_agent_design.md`, `research_plan_and_timeline.md` |
| Prior gate outcomes | `docs/AGENT_CONTEXT.md` + the specific formal report under `reports/research_audit/` (never reinterpret frozen results) |
| Model A lineage / training | `docs/training/near_mainline_training_protocol_v1.md` (historical; cannot override DEC-0025/26/27) |

## 5. Maintenance rules

- New protocol documents: add a clear STATUS header (DRAFT /
  FROZEN_BEFORE_EVALUATION / FROZEN / COMPLETED) and register the file in
  the table above on creation and on status change.
- After a formal gate completes, its protocol moves conceptually to
  COMPLETED_FROZEN_PROTOCOL (file stays in place).
- Completed gates' reports live under `reports/research_audit/`; their
  preregistration metadata under the same directory
  (`*_preregistration.json`).
- Never delete frozen protocols or scientifically useful history.
- Do not move files for aesthetics; if a physical restructure ever
  becomes necessary, update every reference (this index, AGENTS.md,
  AGENT_CONTEXT.md, all `docs/research_plan/` links) in the same change.
