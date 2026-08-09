# Flow Security Agent Instructions

These instructions apply to the entire repository.

## Current frozen project state

- The canonical research specification is `docs/research_plan/research_plan_detailed.md`; operational status is in `docs/PROJECT_HANDOFF.md`, and server/data recovery instructions are in `docs/SERVER_MIGRATION.md`.
- The mainline is session evidence → text-only Qwen3.5-9B first classification → frozen Unknown scoring/calibration → constrained Agent evidence expansion. Do not restore a tree-first or Qwen-as-Reviewer architecture.
- Edge-IIoTset is the limited primary dataset; IoT-23 is the limited independent-scenario external validation dataset. Do not reopen dataset search, replace these roles or physically merge their fine-label training without an authorized new Decision.
- Default formal training is BF16 LoRA SFT with visual modules frozen and non-thinking output. QLoRA is only a resource/compatibility fallback. `U_dev` is not main-classifier SFT supervision; `U_final` must never be used for SFT/DPO, Prompt/RAG examples, Unknown algorithm or threshold selection, Agent training, or error-driven tuning.
- Production `CanonicalSessionRecord`, EdgeAdapter and IoT23Adapter are not implemented. The Gate implementations in `reports/data_feasibility_gate_20260806/run_final_gate.py` are prototypes and audit evidence, not the production pipeline or paper results.
- The remote server is rented and reachable; the current stage is `SERVER INITIALIZATION`. Keep data/artifact/model roots outside the Git checkout and configurable through environment/configuration rather than hard-coded local Windows or server paths.
- Raw traffic, dataset archives, large generated tables, model weights, checkpoints, credentials and environment secrets must not enter Git.
- A material research change must update the canonical plan and Decision Log, then synchronize the handoff. Do not commit or push unless the user explicitly authorizes it.

## Required project context

Before changing the project:

1. Read `README.md`.
2. Read `docs/PROJECT_HANDOFF.md`.
   - On Windows PowerShell, use `Get-Content -Encoding UTF8` when reading Chinese Markdown files; the legacy Windows PowerShell default encoding may display valid UTF-8 text as mojibake.
3. For work that can affect research meaning, data roles, labels, splits, model stages, evaluation protocols or paper conclusions, read `docs/research_plan/research_plan_detailed.md` in full. It is the canonical research specification.
4. Inspect `git status --short` and preserve all pre-existing user changes.

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
- Do not reintroduce PCAP, Payload, host logs or legacy competition labels into the formal Flow-only mainline unless the research plan is explicitly changed and approved.
- Do not start formal long-running Qwen training while the current data Gate prohibits it.
- Do not reset, discard, overwrite or commit unrelated pre-existing working-tree changes.

## Completion check

Before finalizing a material project update:

1. Compare the resulting implementation and artifacts with the canonical plan.
2. Decide whether the handoff synchronization rule was triggered.
3. Update only the affected handoff sections when permitted.
4. Run verification proportional to the change.
5. Report which project-state facts changed, whether `docs/PROJECT_HANDOFF.md` was updated, and any remaining divergence or blocker.
