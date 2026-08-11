# Flow Security Agent Instructions

These instructions apply to the entire repository.

## Current frozen project state

- Authority order is: `docs/research_plan/research_plan_detailed.md` (highest research meaning) → `docs/training/near_mainline_training_protocol_v1.md` (training/Open-world execution) → `docs/design/agent_architecture_provisional.md` (Agent/Runtime/Supervisor/RAG/Memory design) → `docs/PROJECT_HANDOFF.md` (current implementation state only). Server/data recovery instructions are in `docs/SERVER_MIGRATION.md`.
- The mainline is session evidence → Qwen3.5-9B shared representation → one Linear Fine Classification Head plus LM Evidence State → deterministic fine-to-coarse mapping → Independent Unknown → DeepSeek Flash Supervisor under deterministic Runtime → on-demand Evidence → optional Class Memory. Do not restore a tree-first, Qwen-as-Reviewer, competing generative-fine, Unknown-as-K+1, Supervisor-as-classifier, always-on RAG or unlimited raw-Payload architecture.
- Agent evidence acquisition must be driven by the declared missing-evidence type under a shared state, capability and budget contract. Do not treat a fixed full-tool chain as an adaptive Agent, do not use RAG to invent missing observations, and perform component-level error attribution before deciding which component to update.
- Edge-IIoTset is the limited primary dataset; IoT-23 is the limited independent-scenario external validation dataset. Do not reopen dataset search, replace these roles or physically merge their fine-label training without an authorized new Decision.
- Near Training Protocol v1 is frozen at the architecture/permission level: Training #1 is classification-first Multi-task BF16 LoRA SFT for LoRA + Fine Head; Training #2 is RLAIF-GRPO for rollout-varying Evidence behavior plus separate classification CE preservation. Fine correctness is not a group-relative GRPO reward. QLoRA is only a post-Near fallback/ablation. `U_dev` is not main-classifier supervision; `U_final` cannot select or tune Qwen, Prompt/serialization, Teacher/Judge, Unknown, sanitizer, RAG, Supervisor or Memory.
- Production `CanonicalSessionRecord`, EdgeAdapter and IoT23Adapter are implemented. The identity-based-dedup full rebuild, Edge label-provenance guard, class-role support Gate and postfix pre-commit audit have passed with documented limitations; `PRODUCTION_DATA_READY=true`. These assets are not paper results, and no model training has started.
- The paper-grade Edge split is `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`, preserving all 7,619,032 identities with `PAPER_EVALUATION_READINESS_GATE=PASS_WITH_LIMITATIONS`. `ONE_MAINLINE_FIRST` freezes Edge Near seed `20260809` as the first complete route, using its existing K/U and 16,979 PLAN_B `K_known ∩ train` candidates. Far, Mixed, IoT-23 and optional ablations wait until `NEAR_MAINLINE_COMPLETE=true`. Raw Qwen ran only controlled deployment smoke; SFT/RL/Unknown/formal benchmarks did not run.
- The remote bootstrap, official recovery, Production Data Freeze, Edge v2 split, `production_runtime_adapter_v1`, Evidence Fidelity and official raw Qwen deployment smoke are complete. The audited `main` baseline is `e28c3f4806aa56dcdeb9e561cf6201e71f98a2a5`; documentation synchronization occurs on `docs/sync-near-mainline-protocol`. Application, sanitized payload and production Knowledge RAG remain UNAVAILABLE engineering capabilities but are required on-demand final Near capabilities. Keep data/artifact/model roots outside Git and configurable through existing environment/configuration.
- Raw traffic, dataset archives, large generated tables, model weights, checkpoints, credentials and environment secrets must not enter Git.
- A material research change must update the canonical plan and Decision Log, then synchronize the handoff. Do not commit or push unless the user explicitly authorizes it.

## Required project context

Before changing the project, inspect `git status --short` and preserve all user changes. Then read according to task meaning:

1. Read `README.md` for repository orientation.
2. Read `docs/research_plan/research_plan_detailed.md` before any work that can affect research meaning, model/training, data roles, labels, splits, evaluation or paper conclusions.
3. Read `docs/training/near_mainline_training_protocol_v1.md` before any training, checkpoint, pooling, LoRA, SFT, RLAIF/GRPO, Unknown, U_dev/U_final or novel-class work.
4. Read `docs/design/agent_architecture_provisional.md` before any Runtime, Supervisor, Evidence Tool, Application/Payload, RAG or Memory work. It cannot override the canonical plan or training protocol.
5. Read `docs/PROJECT_HANDOFF.md` after the authorities above to learn actual implementation state, current branch/stop point and the next allowed phase. Handoff never overrides research or execution authorities.
6. Read the specific audit/manifest named by the handoff for the component being changed.

For Chinese Markdown on Windows PowerShell, use `Get-Content -Encoding UTF8`.

## Keep the handoff document synchronized

Update `docs/PROJECT_HANDOFF.md` in the same task whenever the work materially changes any of the following:

- implemented or removed capabilities;
- dataset availability, dataset roles, research Gates or permission boundaries;
- frozen or provisional research decisions;
- completed audits, experiments or training stages;
- test, CI, runtime, model-serving or environment status relevant to handoff;
- active blockers, unresolved decisions or safety restrictions;
- the recommended next action or milestone;
- important entry points, commands, artifacts, reports or file locations;
- what future developers or Agents are allowed or not allowed to do.

When updating the handoff document:

- distinguish clearly among completed facts, provisional proposals and unresolved decisions;
- never present audit probes as formal paper results;
- never present an unapproved candidate protocol as a frozen decision;
- preserve the source-of-truth hierarchy documented in the handoff guide;
- update the verification date when the project-state snapshot is revalidated;
- keep the guide concise and action-oriented rather than duplicating the detailed research plan;
- verify that paths, commands, test counts and current Gates are still accurate;
- keep the `README.md` handoff link valid.

A handoff update is normally unnecessary for formatting-only edits, comments, spelling fixes or internal refactors that do not change behavior, interfaces, project status, operational guidance or research meaning.

## Scope conflicts

Explicit user instructions and file-scope restrictions take precedence. If a task changes project state but the user permits modification of only specified files and excludes `docs/PROJECT_HANDOFF.md`, do not modify the handoff document. Instead, state clearly in the final response that it may now require synchronization and identify the affected section.

Do not expand a narrowly scoped task merely to rewrite the handoff document. Synchronize only the sections affected by verified changes.

## Research and data safeguards

- Do not change dataset roles, Known/Unknown sets, label mappings, split rules, training permissions or evaluation protocols without updating the canonical detailed plan and its Decision Log when the task authorizes those files.
- Do not use frozen test or external-test labels to tune models, thresholds, prompts, RAG content or training data.
- Do not describe week/file proxy groups as official mission or activity identifiers.
- Raw PCAP remains backend source-of-truth only. Model-visible Application/Payload must follow the frozen on-demand, bounded, sanitized, model-safe contracts; never expose raw identity, unlimited payload, host logs or legacy shortcut labels.
- Do not start Raw benchmarks, SFT, RLAIF/GRPO, Unknown, U_final or Agent experiments without an explicitly authorized task and the preceding Near protocol Gate.
- Do not reset, discard, overwrite or commit unrelated pre-existing working-tree changes.

## Completion check

Before finalizing a material project update:

1. Compare the resulting implementation and artifacts with the canonical plan and, when relevant, the Near training protocol and Agent architecture.
2. Decide whether the handoff synchronization rule was triggered.
3. Update only the affected handoff sections when permitted.
4. Run verification proportional to the change.
5. Report which project-state facts changed, whether `docs/PROJECT_HANDOFF.md` was updated, and any remaining divergence or blocker.
