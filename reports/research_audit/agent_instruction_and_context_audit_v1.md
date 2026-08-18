# Agent Instruction and Context Audit — V1

Date: 2026-08-18
Scope: read-only architecture/documentation audit. No experiments run, no
research conclusions changed, no existing documents rewritten or
synchronized. This report is the only file created.

Audited HEAD: `22c92c7` (`research: preregister recovery signal characterization v2`),
branch `main`, 5 commits ahead of `origin/main` (push blocked: no GitHub creds).

Working tree at audit time:

- modified: `docs/AGENT_CONTEXT.md`, `docs/PROJECT_HANDOFF.md`,
  `tools/run_recovery_signal_characterization_v2.py` (4-line runtime bugfix:
  boolean-mask re-indexing before `recovered_split`; scientific semantics
  unchanged, permitted by the V2 protocol's execution-lock bugfix rule);
- untracked: `reports/research_audit/recovery_signal_characterization_gate_v2.json`,
  `reports/research_audit/recovery_signal_characterization_gate_v2.md`
  (V2 results intentionally left uncommitted for researcher review).

---

## 1. Classification of agent-facing files

### A. AUTO / INHERITED

| File | Evidence |
|---|---|
| `AGENTS.md` (repo root, 10.4 KB) | Present at repository root with the standard agent-instructions filename; both Claude Code and Codex auto-load a root `AGENTS.md` by harness default. In-repo corroboration: `reports/integration/main_baseline_integrity_20260811.md` names it "the Codex entry contract". No repo-level `.claude/` directory exists, so no project settings/hooks/commands are loaded. No `CLAUDE.md` exists at repo root or in any parent. |
| Parent directories | `/root`, `/root/autodl-tmp`, `/root/autodl-tmp/workspace` contain **no** `AGENTS.md`/`CLAUDE.md` — verified directly; nothing inherited. |
| `/root/.claude/settings.json` (user-level harness config) | Loaded automatically by the Claude Code harness. Contains only API/model/env configuration (`apiKeyHelper`, DeepSeek base URL, model aliases, effort level) and **no project instructions or memory content**. |
| Persistent agent memory `/root/.claude/projects/-root-autodl-tmp/memory/` | Directory exists but is **empty** (no `MEMORY.md`, no memory files). The "conversational / persistent Agent memory" level in the AGENT_CONTEXT priority list currently has no stored content, so it cannot override anything today. |
| `/root/.codex/config.deepseek.toml` (user-level Codex config) | Marks `/root/autodl-tmp` as trusted; no instruction content. Relevant only because the same `AGENTS.md` also serves Codex sessions. |

Conclusion: **`AGENTS.md` is the only automatically loaded instruction file.** Its loading is the harness default triggered by the root filename — provable from the file's existence and location; there is no local config that customizes or disables it.

### B. PROMPT-REFERENCED

Files that enter a task only because the auto-loaded file or the task prompt tells the agent to read them:

- `docs/AGENT_CONTEXT.md` (20.9 KB) — mandated as "read first" by `AGENTS.md` item 0 and by `README.md`; every recent task prompt also names it. Semi-automatic in practice, but harness-wise it is prompt-referenced.
- `docs/PROJECT_HANDOFF.md` (28.2 KB) — `AGENTS.md` item 5, `README.md`.
- `README.md` (10.0 KB) — `AGENTS.md` item 1 (orientation).
- `docs/research_plan/research_plan_detailed.md` (100.4 KB) — `AGENTS.md` item 2, for any research-meaning work.
- `docs/training/near_mainline_training_protocol_v1.md` — `AGENTS.md` item 3 (Model A lineage tasks).
- `docs/design/agent_architecture_provisional.md` — `AGENTS.md` item 4 (Runtime/Supervisor/Evidence/RAG/Memory tasks).
- `docs/research_plan/recovery_signal_characterization_v2_protocol.md` (21.0 KB, frozen) + `reports/research_audit/recovery_signal_characterization_v2_preregistration.json` (12.0 KB, committed in `22c92c7`) — read only by V2 gate execution/audit tasks.
- Gate report pairs in `reports/research_audit/*.{json,md}` — read on demand per the AGENT_CONTEXT "Read on demand" index.

### C. HUMAN-REFERENCE

Useful documentation that does not need to enter every agent task:

- `README.md` (orientation half), `docs/SERVER_MIGRATION.md` (legacy Model A recovery, explicitly "not a Model B runbook"), `docs/legacy_migration_summary.md`, `docs/phase0_data_audit.md`, `docs/infrastructure_contract.md`, `docs/runbooks/deepseek_api.md`.
- Derived plan views: `docs/research_plan/research_plan_brief.md`, `research_plan_and_timeline.md`, `task_definition_v2.md` (Model A provenance only).
- Historical audit bundles under `reports/` (`dataset_audit/`, `data_feasibility_gate_20260806/`, `production_data_freeze_20260809/`, `training_readiness/`, `model_readiness/`, `runtime_audit/`, `edge_split_revision_v2/`, `plan_consistency/`, `architecture_audit/`, `local_data_cleanup_20260806/`, `integration/`).
- `configs/` manifests and `schemas/` — engineering contracts read by code/tests, not by agent instructions.

### D. MACHINE-AUTHORITY

Formal artifacts whose content should override narrative summaries when scientific status matters:

- Formal result JSONs in `reports/research_audit/` (e.g. `core_hypothesis_gate_v1.json`, `open_world_recoverability_gate_v1.json`, `recovery_signal_characterization_gate_v2.json`).
- `reports/research_audit/recovery_signal_characterization_v2_preregistration.json` (frozen hypotheses/criteria before evaluation).
- Frozen protocol documents with hash pinning: `docs/research_plan/recovery_signal_characterization_v2_protocol.md` (sha256 `b1d01629…5b7b`, recorded in the preregistration and in the report header).
- Canonical artifact manifests/hashes in `configs/dataset_v4/` and the frozen hashes recorded in PROJECT_HANDOFF §4/§10.
- `docs/research_plan/experiment_protocol_v1.md` (frozen experiment matrix/statistics; `EXPERIMENT_PROTOCOL_STATUS=FROZEN_DESIGN_NOT_RUN`).
- The gate tool + its tests: `tools/run_recovery_signal_characterization_v2.py` and `tests/tools/test_recovery_signal_characterization_v2.py` — the test `test_linear_vs_rf_configs_match_preregistration` programmatically asserts tool constants equal the frozen preregistration JSON (an actual machine check, the strongest mechanism in the repo).
- CI (`.github/workflows/ci.yml`) runs `pytest` on push/PR — it validates code/artifact consistency but reads none of the instruction documents.

---

## 2. Instruction/context dependency map

### Core instruction files

| Path | Purpose | Loading mechanism | Authority | References | Updated after tasks? | Duplicated content | Stale content | Conflicts / precedence notes | Size |
|---|---|---|---|---|---|---|---|---|---|
| `AGENTS.md` | Vendor-bootstrap: frozen state summary, authority chain, required-context cascade, handoff-sync duty, safeguards, DeepSeek policy, git landing policy | A: auto-loaded (root AGENTS.md) | Lowest of the written sources (ranked #7 by AGENT_CONTEXT; it itself defers to AGENT_CONTEXT for project state) | AGENT_CONTEXT, README, detailed plan, Near protocol, architecture, HANDOFF, SERVER_MIGRATION (legacy) | Rarely (last touched `0cb49e3` to add AGENT_CONTEXT pointer) | Restates the authority chain (also in README, HANDOFF §1, architecture doc, training protocol) and frozen-state bullets (also in AGENT_CONTEXT/HANDOFF) | Frozen-state bullets lag behind the V2 gate outcome (still describe "Gate 1 done" era; do not mention V1 FAIL / V2 CASE D) | Mandates reading the 100 KB detailed plan for research-meaning work while AGENT_CONTEXT mandates minimal on-demand reading (see §5) | 10.4 KB — fine |
| `docs/AGENT_CONTEXT.md` | Compact agent-neutral current state: SOURCE_OF_TRUTH_PRIORITY, state register, authorization/forbidden list, read-on-demand index, state-maintenance rules, git checkpoint | B: AGENTS.md item 0 + prompt | #5 in its own priority list (above HANDOFF/AGENTS.md/memory; below frozen protocol, JSON, MD, manifest) | HANDOFF, gate report pairs, preregistration, V2 protocol, literature reports, Git-external artifact dirs | **Yes, after every material task** (V2 update currently uncommitted) | Duplicates gate numbers 2× internally (state block + "Latest formal result" narrative) and again in HANDOFF; teacher-cache status also in HANDOFF/README/reports | **Git/repository state block is stale**: `GIT_CHECKPOINT=4fc7591` while HEAD is `22c92c7`; `GATE_1B_COMMIT_CREATED=false`, `FAILURE_ATTRIBUTION_COMMIT_CREATED=false`, `NOVELTY_AUDIT_COMMIT_CREATED=false` are all false — those artifacts were committed in `917303a`/`7604736`; "(untracked: …)" list names files that are now tracked; read-on-demand section still labels gates v1b/open-world/attribution "untracked (do not commit)" although they are tracked — only the V2 result pair is actually untracked | Forbids `ANY_MODEL_B_OR_RL_WORK` and `ANY_NOVELTY_SCORING_CHANGE_WITHOUT_NEW_AUTHORIZED_PROTOCOL`; `NEXT_ACTION_AUTHORIZED=false` — conflicts with the stale HANDOFF §10 `NEXT_ACTION` (see §5) | 20.9 KB — acceptable |
| `docs/PROJECT_HANDOFF.md` | Detailed history, current stop point, DO-NOT-REOPEN list, env/entry points (Chinese) | B: AGENTS.md item 5 + README + AGENT_CONTEXT read-on-demand | #6; explicitly "cannot override research or execution authorities" | detailed plan + DECs, experiment protocol, Model B/continual designs, dataset-v4 contracts, Near protocol, architecture doc, gate reports, Git-external paths | **Yes, in practice after every gate** (per AGENTS.md sync rule + AGENT_CONTEXT maintenance rule #3, which says "only if high-level project interpretation changed") | Full per-gate numeric sections (Gate 1, 1B, V1, attribution, V2) duplicating the formal reports and AGENT_CONTEXT; authority chain restated (§1) | §10 `NEXT_ACTION=PREPARE_DUPLICATE_AWARE_DATA_VIEWS_AND_START_MODEL_B_LOW_COST_GATES` predates V2 and contradicts the V2 paragraph in the same file (CASE D → `RESEARCHER_REASSESS_COST_BENEFIT_BEFORE_MODEL_B`, "任何Model B、novelty interface、purification工作均须researcher决策") and contradicts AGENT_CONTEXT's forbidden list. It does warn agents to run `git status` instead of trusting hashes | Internal: §10 next-action vs later V2 paragraph; external: vs AGENT_CONTEXT authorization | 28.2 KB — acceptable alone, heavy inside the full cascade |
| `README.md` | Orientation + research direction + implemented foundation + plan index | B: AGENTS.md item 1; also human entry point | Orientation only | AGENT_CONTEXT, HANDOFF, all plan docs | Only at milestones (Model A completion, Teacher cache freeze) | Restates authority chain and frozen-state summary | Reasonably current | Its "Agents should read AGENT_CONTEXT first" agrees with AGENTS.md | 10.0 KB — fine |

### Research plan and protocol documents

| Path | Purpose | Loading mechanism | Authority | Updated after tasks? | Size |
|---|---|---|---|---|---|
| `docs/research_plan/research_plan_detailed.md` | Canonical research specification; DEC-0025/0026/0027 frozen current plan at top; Decision Log at bottom (41 DEC mentions) | B: AGENTS.md item 2 | **Highest research meaning** (per AGENTS.md and HANDOFF §1) | Only on material plan deviations (Decision Log entries) | **100.4 KB — too large for default context alongside anything else** |
| `docs/research_plan/experiment_protocol_v1.md` | Frozen formal experiment matrix, isolation, baselines, metrics, statistics | B: AGENTS.md item 2 context / README | #2 research authority (frozen design, not run) | Frozen (not updated) | 24.5 KB |
| `docs/research_plan/model_b_evidence_openworld_design.md` | Model B representation/utility/novelty boundary | B: AGENTS.md chain | #3 (current Model B design) | Frozen until DEC change | 9.6 KB |
| `docs/research_plan/open_world_continual_agent_design.md` | Controller/Runtime/continual boundary | B: AGENTS.md chain | #4 | Frozen until DEC change | 9.3 KB |
| `docs/research_plan/multi_dataset_v4_design.md` | Dataset-v4 data contract | B: AGENTS.md chain | #5 | Frozen | 8.1 KB |
| `docs/research_plan/dataset_v4_b1_runtime_contract.md` | B1 observation/Evidence/runtime/action/Teacher-cache engineering contract | B: AGENTS.md chain | #6 | Frozen | 14.8 KB |
| `docs/research_plan/dataset_v4_split_protocol.md` | Frozen taxonomy/identity/split/rotations/history/sampling population | B: AGENTS.md chain | #7 | Frozen | 7.7 KB |
| `docs/research_plan/recovery_signal_characterization_v2_protocol.md` | Frozen preregistered V2 gate protocol (hash-pinned) | B: V2 tasks only | #1 for its scoped task (researcher-authorized frozen protocol) | Frozen; never rewritten (hash breaks) | 21.0 KB |
| `docs/research_plan/literature_novelty_reassessment_v1.md` | Non-frozen novelty addendum; next-gate design requirements | B: referenced by AGENT_CONTEXT/HANDOFF | Below frozen contracts; cannot alter DEC-0025/0027 | Editable (non-frozen) | 8.4 KB |
| `docs/training/near_mainline_training_protocol_v1.md` | Model A historical execution contract | B: AGENTS.md item 3 | Model A lineage only; "DEC-0025 OVERRIDDEN FOR MODEL B" | Frozen historical | ~10 KB |
| `docs/design/agent_architecture_provisional.md` | Runtime implementation boundary | B: AGENTS.md item 4 | Below canonical plan/experiment protocol | Provisional | ~10 KB |
| `docs/research_plan/research_plan_brief.md` / `research_plan_and_timeline.md` | Derived views (advisor brief / timeline) | C: read when those scopes change | Derived, not authoritative | Only when their scope is affected | 4.6 KB / 8.7 KB |
| `docs/research_plan/task_definition_v2.md` | Model A Dataset-v3/Evidence-v2/Teacher-v2 provenance | C | Model A provenance only | Frozen historical | 15.6 KB |

### Machine-authority artifacts

| Path | Purpose | Authority | Notes |
|---|---|---|---|
| `reports/research_audit/*_gate_*.json` + matching `.md` | Formal gate results (tool-generated JSON = primary; MD = explanatory context) | JSON above MD (AGENT_CONTEXT priority #2 vs #3) | MDs are hand-written narratives; the open-world gate MD says the JSON was "copied" from the tool output |
| `reports/research_audit/recovery_signal_characterization_v2_preregistration.json` | Frozen hypotheses/criteria/split/calibration before evaluation | #1-equivalent for the V2 task (hash-linked to protocol) | Committed before evaluation (`22c92c7`) |
| `configs/dataset_v4/*.json` | Frozen manifests + hashes | #4 (manifest/hash) | Read by tools/tests |
| `tools/run_recovery_signal_characterization_v2.py` + `tests/tools/test_recovery_signal_characterization_v2.py` | Executable encoding of the frozen protocol; test asserts tool constants == preregistration JSON | Machine check (strongest) | Tool docstring references the protocol path only; sha256 passed as CLI arg, not read from the doc |

### What references what (directed edges)

```
AGENTS.md ──mandates──> AGENT_CONTEXT ──points──> HANDOFF, gate JSON/MD,
                       README            preregistration, V2 protocol, literature reports
AGENTS.md ──mandates──> README ──points──> AGENT_CONTEXT, HANDOFF, all plan docs
AGENTS.md ──mandates──> research_plan_detailed (canonical, includes DEC log)
AGENTS.md ──mandates──> near_mainline_training_protocol ──defers──> detailed plan, Model B design
AGENTS.md ──mandates──> agent_architecture_provisional ──defers──> detailed plan, experiment protocol
AGENTS.md ──mandates──> PROJECT_HANDOFF ──points──> detailed plan, protocol v1, designs, gate reports
preregistration.json ──hash-pins──> recovery_signal_characterization_v2_protocol.md
test_recovery_signal_characterization_v2.py ──asserts──> preregistration.json
run_recovery_signal_characterization_v2.py ──writes──> gate_v2.json + gate_v2.md (nothing else)
```

**No script, tool, or test reads or writes `AGENTS.md`, `AGENT_CONTEXT.md`,
`PROJECT_HANDOFF.md`, or any research plan document.** All synchronization of
those files is manual agent work, driven by prose rules in AGENTS.md
("Keep the handoff document synchronized") and AGENT_CONTEXT ("State
maintenance"). The only machine-enforced consistency is tool-constants
vs preregistration (one test), and manifest/schema tests in `tests/`.

---

## 3. Synchronization burden audit

The same research state is currently hand-copied into these places for each
gate result (V2 as the running example):

| Copy | Authoritative? | Useful summary? | Redundant? | Updated every task? |
|---|---|---|---|---|
| `recovery_signal_characterization_gate_v2.json` (tool output) | **Yes** — primary numbers | — | No | Written once by tool |
| `recovery_signal_characterization_gate_v2.md` (report narrative) | Secondary (explanatory) | Yes | Partially — restates JSON numbers | Once |
| `docs/AGENT_CONTEXT.md` state block (`V2_*` keys) | No | **Yes** — compact status register | Partially | Yes (required by maintenance rule #2) |
| `docs/AGENT_CONTEXT.md` "Latest formal result" narrative + per-gate narratives | No | Weakly — it duplicates the state block *inside the same file* | **Yes — internal duplication** | Yes |
| `docs/PROJECT_HANDOFF.md` per-gate paragraph (full numbers) | No | Weakly — high-level interpretation only would suffice | **Yes — full numbers already in JSON/MD** | Yes (violates its own "only if high-level project interpretation changed" rule, which would normally be satisfied by the V1→V2 interpretation change; the full metric restatement is the redundant part) |
| `README.md` implemented-foundation bullets | No | Yes at milestone granularity | No (coarse) | No (milestones only) — good |
| `AGENTS.md` frozen-state bullets | No | Yes at milestone granularity | No | No (rarely) — good, but now lagging V2 |

Same pattern for: Teacher-cache status (AGENT_CONTEXT + HANDOFF §5/§10 + README +
`teacher_cache_v1_readiness` + `teacher_cache_v1_generation_report` = 5 copies),
Gate 1 / 1B / V1 / attribution numbers (4–5 copies each), and the authority
chain itself (restated in AGENTS.md, README, HANDOFF §1, architecture doc,
training protocol, SERVER_MIGRATION = 6 copies).

Verdict per copy:

- **Authoritative:** formal JSON (tool output), preregistration, frozen
  protocol, manifests/hashes.
- **Useful summaries:** AGENT_CONTEXT state register (keys only), HANDOFF
  high-level interpretation, README milestone bullets.
- **Redundant:** full per-gate metric narratives in HANDOFF; the duplicate
  narrative layer inside AGENT_CONTEXT; authority-chain restatements in every
  document.
- **Unnecessarily updated on every task:** HANDOFF full-number sections, and
  the second narrative layer of AGENT_CONTEXT. Both are prescribed by prose
  rules today, and both could be trimmed without losing any authority because
  the JSON/MD pair already carries the numbers.

Also note the *uncommitted sync backlog*: the V2 updates to AGENT_CONTEXT and
PROJECT_HANDOFF sit in the working tree with the untracked V2 report pair,
intentionally, per the V2 git policy ("DO NOT COMMIT result reports/context
changes; DO NOT PUSH; leave for researcher review"). This is policy, not
drift — but it means the committed context docs are one gate behind the
working tree until the researcher reviews.

---

## 4. Current authority / precedence rules (as found, not invented)

The repository **does** have an explicit precedence rule. Two parallel
formulations coexist:

`docs/AGENT_CONTEXT.md` — `SOURCE_OF_TRUTH_PRIORITY=` (operational truth):

```text
1. researcher-authorized frozen protocol / contract
2. formal report JSON
3. formal report MD
4. canonical artifact manifest / hash
5. this file (AGENT_CONTEXT)
6. PROJECT_HANDOFF
7. vendor bootstrap (AGENTS.md)
8. conversational / persistent Agent memory
```

plus: same-level conflicts → output `PROJECT_STATE_CONFLICT=NEEDS_REVIEW` and STOP.

`AGENTS.md` / `PROJECT_HANDOFF.md` §1 — research-meaning chain:

```text
research_plan_detailed.md + DEC-0025/0026/0027
  > experiment_protocol_v1.md
  > Model B / Dataset-v4 design documents
  > dataset_v4_b1_runtime_contract.md + dataset_v4_split_protocol.md
  > PROJECT_HANDOFF.md
(Near training protocol, provisional architecture: Model A lineage only,
 cannot override DEC-0025/0026/0027; SERVER_MIGRATION: legacy.)
```

The two chains are mostly compatible (plan > protocol-design > contracts >
handoff), and the self-referential ranking works because AGENTS.md explicitly
defers ("Do not treat this file (AGENTS.md) as project state"). The current
effective rule is therefore:

> frozen researcher-authorized protocol (hash-pinned, task-scoped) >
> canonical plan / DEC log (research meaning, repo-wide) >
> formal result JSON > result MD > manifests/hashes >
> AGENT_CONTEXT > PROJECT_HANDOFF > AGENTS.md > memory

One gap: **no rule exists for a conflict between a task-scoped frozen protocol
and the canonical plan itself.** AGENT_CONTEXT's #1 would win under its list;
AGENTS.md's chain would win under its list. In practice the V2 protocol was
derived from the plan, so no live conflict has occurred — the ambiguity is
latent, and matters for the next protocol (see §6).

---

## 5. Conflicts, ambiguities, and stale content

1. **Read-policy conflict (live).** AGENTS.md item 2: "Read
   `research_plan_detailed.md` before any work that can affect research
   meaning…". AGENT_CONTEXT "Read on demand": "read only the protocol
   explicitly required by the current task. Do not preload unrelated reports
   or plans." For a gate-execution task both apply, and they prescribe
   opposite behavior regarding the 100 KB canonical plan. V2 practice followed
   AGENT_CONTEXT (protocol + preregistration only). The contradiction is
   resolved ad hoc per task; it should be resolved once, in text.

2. **Stale git-state block in AGENT_CONTEXT (live, factual error).**
   `GIT_CHECKPOINT=4fc7591` vs actual HEAD `22c92c7`;
   `GATE_1B_COMMIT_CREATED=false` / `FAILURE_ATTRIBUTION_COMMIT_CREATED=false` /
   `NOVELTY_AUDIT_COMMIT_CREATED=false` — all three were committed
   (`917303a`, `7604736`); the "(untracked: …)" parenthetical and the
   read-on-demand "untracked (do not commit)" labels name files that are now
   tracked. Only the V2 result pair is actually untracked. An agent that
   trusts this block misjudges what a commit would touch.

3. **HANDOFF §10 `NEXT_ACTION` contradicts the rest of the repo (live).**
   `NEXT_ACTION=PREPARE_DUPLICATE_AWARE_DATA_VIEWS_AND_START_MODEL_B_LOW_COST_GATES`
   (pre-V2) vs the V2 paragraph in the same file and AGENT_CONTEXT's
   `NEXT_PROPOSED_ACTION=RESEARCHER_REASSESS_COST_BENEFIT_BEFORE_MODEL_B`,
   `CURRENT_FORBIDDEN_NEXT_STEPS=ANY_MODEL_B_OR_RL_WORK …`,
   `NEXT_ACTION_AUTHORIZED=false`. An agent reading only HANDOFF §10 sees
   "start Model B" as the next action; an agent reading AGENT_CONTEXT sees
   Model B as forbidden. **This is the most dangerous inconsistency found.**

4. **AGENTS.md frozen-state bullets lag one gate behind** (no V1 FAIL /
   V2 CASE D). Low risk only because AGENTS.md itself defers to AGENT_CONTEXT
   — but a session that stops at the auto-loaded file is misinformed.

5. **Frozen-protocol vs canonical-plan precedence gap** (latent, see §4).

6. **Executed code ≠ committed code for V2.** The V2 tool has an uncommitted
   4-line mask-indexing bugfix; the report was produced by the working-tree
   version, not the preregistered `22c92c7` version. Legal under the
   protocol's bugfix rule (scientific semantics unchanged), but the
   divergence must be documented to the researcher as part of review.

7. **Language split.** AGENTS.md / AGENT_CONTEXT / README are English;
   PROJECT_HANDOFF and most plan documents are Chinese. Not a conflict, but
   it doubles comprehension cost inside the multi-file cascade.

---

## 6. Relevance to the upcoming Strong Neural OSR experiment

No "Strong Neural OSR" document exists in the repository yet — the experiment
is upcoming and currently undefined in-repo. Facts that will constrain it:

- **Authorization is closed right now.** `CURRENT_AUTHORIZED_TASK=NONE_WAITING_RESEARCHER`,
  `NEXT_ACTION_AUTHORIZED=false`, and forbidden steps include
  `ANY_MODEL_B_OR_RL_WORK` and `ANY_NOVELTY_SCORING_CHANGE_WITHOUT_NEW_AUTHORIZED_PROTOCOL`.
  The Strong Neural OSR protocol draft is the researcher's CASE-D reassessment
  response; nothing about it may execute until the researcher authorizes it.

- **Novelty-candidate boundary is frozen.** `research_plan_detailed.md` §0.5
  (DEC-0025): "Novelty detector … 第一轮只比较MSP、margin、energy和prototype
  distance等简单候选，算法和threshold不预先冻结" and `experiment_protocol_v1.md`
  §7: `U0` MSP, `U1` margin, `U2` energy, `U3` prototype/Mahalanobis,
  "optional OpenMax only if simple candidates leave justified headroom".
  A *strong neural* OSR candidate is outside the first-round candidate set.
  This does **not** block it — the protocol expressly leaves the first-round
  algorithm un-frozen and allows escalation on justified headroom — but the
  new protocol must state its relationship to the frozen first-round set
  (e.g. "second-round escalation justified by V1/V2 headroom diagnostics")
  and either cite an existing DEC or add a Decision Log entry if research
  meaning changes.

- **The V2 prohibition is task-scoped, not global — but is easy to misread.**
  The V2 protocol's NOT AUTHORIZED list includes "neural novelty detector"
  and "detector shopping", and the V1 attribution says "未推荐…neural binary
  detector" (no detector recommended). Both statements were scoped to V2/V1.
  A naive agent could read them as a permanent ban on neural novelty
  scoring. The Strong Neural OSR protocol must explicitly acknowledge and
  scope-limit these prior statements to avoid a false "conflict detected"
  STOP.

- **Stale-context hazards apply directly:** the HANDOFF §10 "start Model B"
  next-action (conflict #3) and the stale AGENT_CONTEXT git block (conflict
  #2) are exactly the files a protocol-drafting agent would read. They must
  be repaired (or explicitly bypassed in the prompt) before the protocol is
  drafted, otherwise the draft may inherit a wrong authorization premise.

- **Precedent to reuse:** the V2 pattern (frozen protocol MD + preregistration
  JSON committed *before* evaluation + tool/test asserting constants match the
  preregistration + results left uncommitted for review) is the repo's proven,
  machine-checked protocol format. The Strong Neural OSR protocol should
  follow it.

---

## 7. Recommended MINIMAL future agent bootstrap

### Default / automatic

1. `AGENTS.md` — keep as the only auto-loaded file; keep it *thin and static*:
   durable operating rules, the authority chain, a fixed "read
   `docs/AGENT_CONTEXT.md` first" pointer, git/hygiene policies. Remove
   perishable frozen-state bullets (or replace with a pointer), because this
   file is the one that never gets refreshed per task.
2. `docs/AGENT_CONTEXT.md` — the single default read after AGENTS.md: state
   register, authorization, read-on-demand index, **a refreshed git-checkpoint
   block**, and pointers to the current frozen protocol/preregistration.

That is the whole default bootstrap. Everything else is on demand.

### On demand only (never in the default path)

- `docs/PROJECT_HANDOFF.md` — when implementation state, environment, entry
  points, or DO-NOT-REOPEN history is needed.
- `docs/research_plan/research_plan_detailed.md` — only for tasks that change
  research meaning, data roles, splits, or decisions (then the full DEC log
  matters). Too large (100 KB) for default context.
- `docs/training/near_mainline_training_protocol_v1.md` and
  `docs/design/agent_architecture_provisional.md` — only for Model A lineage /
  Runtime-architecture tasks.
- `README.md` — human orientation; drop from the per-task agent cascade.
- Historical gate reports — via the AGENT_CONTEXT index, only when a task
  touches that gate's numbers.

### Machine-authoritative (never narratively paraphrased for decisions)

- Frozen protocol + preregistration JSON (hash-pinned pair).
- Formal result JSONs (numbers) with MD as explanatory context.
- Manifests/hashes in `configs/dataset_v4/`.
- The gate tool + its preregistration-consistency test.

### Synchronization after each experiment — keep:

- Write formal report JSON + MD (tool output).
- Update AGENT_CONTEXT state register (keys + one-line interpretation +
  authorization/git block). **Remove** the second narrative layer inside
  AGENT_CONTEXT (its own rule says "do not duplicate full metrics into this
  file" — enforce it).
- Update PROJECT_HANDOFF **only at the level of high-level project
  interpretation** (its own rule #3) — not full metric restatements.

### Synchronization after each experiment — stop:

- Full per-gate number sections in PROJECT_HANDOFF.
- Duplicate narratives inside AGENT_CONTEXT.
- README/AGENTS.md updates per gate (milestones only — current behavior, keep).
- Any task-prompt requirement to re-read or re-verify unrelated plans/reports.

### Do AGENT_CONTEXT and PROJECT_HANDOFF both remain?

**Yes, with a clean split.** AGENT_CONTEXT = machine-facing status register
(short, structured keys, authorization, git checkpoint, index). PROJECT_HANDOFF
= human/agent narrative history, DO-NOT-REOPEN register, environment/entry
points, and the high-level interpretation of each gate. The two currently
overlap heavily (gate numbers in both + twice in AGENT_CONTEXT); the split
removes the overlap without deleting either document.

### Where future frozen experiment protocols live

- `docs/research_plan/<experiment>_protocol.md` — the frozen protocol
  (existing V2 precedent), committed **before** evaluation.
- `reports/research_audit/<experiment>_preregistration.json` — the
  hash-pinned machine preregistration (existing V2 precedent).
- `reports/research_audit/<experiment>_gate_vN.{json,md}` — results, left
  uncommitted for researcher review per the V2 git policy.
- `tools/run_<experiment>.py` + `tests/tools/test_<experiment>.py` with a
  preregistration-consistency test (the repo's only machine enforcement —
  extend it to every protocol).

---

## 8. Specific answers

**What does an agent currently appear to read by default?**
Only `AGENTS.md`, auto-loaded by the harness. That file then instructs a
seven-file cascade (AGENT_CONTEXT → README → detailed plan → Near training
protocol → provisional architecture → PROJECT_HANDOFF → named audit), so the
*prescribed* default is effectively ~190 KB of context before a task even
starts. In recent practice, gate tasks were run on the AGENT_CONTEXT +
task-scoped protocol + preregistration subset instead — i.e. the cascade is
already being honored selectively, not literally.

**What do our existing prompts unnecessarily force it to read?**
(1) `README.md` — orientation with no per-task value; (2)
`research_plan_detailed.md` (100 KB) for tasks that execute a frozen protocol
rather than change research meaning; (3) `near_mainline_training_protocol_v1.md`
and `agent_architecture_provisional.md` for tasks that touch neither training
nor Runtime; (4) `PROJECT_HANDOFF.md` for tasks where the AGENT_CONTEXT state
register suffices; (5) AGENT_CONTEXT's own duplicated narrative layers.

**What documents are unnecessarily duplicated?**
Gate result numbers exist in 4 files (JSON, MD, AGENT_CONTEXT, HANDOFF) plus
a second copy inside AGENT_CONTEXT itself; teacher-cache status in 5 places;
the authority chain restated in 6 documents. The AGENT_CONTEXT↔HANDOFF overlap
and the intra-AGENT_CONTEXT duplication are the unnecessary ones — the
JSON/MD pair and the state register are the necessary copies.

**What synchronization work can be removed safely?**
Full-number updates to PROJECT_HANDOFF per gate (replace with high-level
interpretation); the second narrative layer in AGENT_CONTEXT (replace with
pointers + state keys); any per-gate README/AGENTS.md churn (already rare).
None of these copies is authoritative, so deleting them removes no source of
truth. The git-checkpoint block in AGENT_CONTEXT should instead be refreshed
every task (it currently drifts).

**Are there any instruction conflicts that could affect the upcoming Strong
Neural OSR experiment?**
Yes — four, listed in §6: (a) authorization is closed (Model B / novelty-scoring
work forbidden without a new authorized protocol, and HANDOFF §10 still says
"start Model B low-cost gates"); (b) the frozen first-round novelty-candidate
set (MSP/margin/energy/prototype, OpenMax only on headroom) does not include a
strong neural candidate — the new protocol must justify escalation and,
if research meaning changes, add a DEC entry; (c) the V2 "neural novelty
detector NOT AUTHORIZED" text is task-scoped but reads globally; (d) stale
git-state facts in AGENT_CONTEXT could make the drafting agent misjudge what
is committed. None of these blocks the experiment; all of them can mis-shape
its protocol if unaddressed.

**What should the shortest safe bootstrap for that experiment be?**

```text
1. AGENTS.md                     (auto-loaded; durable rules)
2. docs/AGENT_CONTEXT.md         (state register + authorization + index)
3. new: docs/research_plan/<strong_neural_osr>_protocol.md  (researcher-frozen)
4. new: reports/research_audit/<strong_neural_osr>_preregistration.json
   (hash-pinned, committed before evaluation)
5. new: tools/run_<strong_neural_osr>.py + tests/… (preregistration-consistency
   test, V2 pattern)
On demand only: experiment_protocol_v1.md (statistics/isolation), the frozen
first-round novelty-candidate sections of research_plan_detailed.md §0.5 /
experiment_protocol_v1.md §7, the relevant gate JSONs, literature addendum.
```

The researcher must authorize the protocol (currently
`NEXT_ACTION_AUTHORIZED=false`); the draft itself should be preceded by a
researcher decision on the §5 conflicts, especially the HANDOFF §10 next-action
line and the read-policy contradiction.

---

## 9. Evidence appendix

- No repo-level `.claude/`, no `CLAUDE.md` anywhere (repo or parents), no
  parent `AGENTS.md`; `/root/.claude/settings.json` is config-only; persistent
  memory directory is empty — all verified by direct filesystem inspection.
- `git status` / `git log` / `git diff` / `git ls-files` / `git show --stat`
  used for commit provenance of every `reports/research_audit/` file
  (commits `0cb49e3`, `917303a`, `4fc7591`, `7604736`, `22c92c7`).
- Machine coupling checked by grepping all code/tests for reads/writes of
  instruction documents: none exist except the V2 tool's protocol-path
  docstring comment, the preregistration-consistency test, and the tool's own
  report outputs.
- Sizes from `wc -c`; the 100 KB figure for `research_plan_detailed.md`
  (~25k+ tokens) is the only document that is too large for default context.

This audit is complete. No repository file other than this report was
created or modified. Nothing committed or pushed.
