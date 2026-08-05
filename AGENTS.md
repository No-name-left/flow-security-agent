# Flow Security Agent Instructions

These instructions apply to the entire repository.

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
