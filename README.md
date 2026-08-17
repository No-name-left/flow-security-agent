# Flow Security Agent

Flow Security Agent is a research framework for **evidence-conditioned open-world malicious traffic recognition**. The current Model B design uses a traffic representation and Known classifier, an empirically grounded selector for bounded typed Evidence, an independent novelty detector, and verified-feedback continual evolution.

> **New developer or Agent:** start with the [project handoff guide](docs/PROJECT_HANDOFF.md). It summarizes the current research Gate, completed assets, unresolved decisions, allowed next steps and working-tree safeguards.

## For AI coding/research agents

Current project state and operating constraints:

- `docs/AGENT_CONTEXT.md` — the compact, agent-neutral current-state entry; read it before substantive project work.
- `docs/PROJECT_HANDOFF.md` — detailed history, read on demand (see AGENT_CONTEXT for the read policy).

Agents should read `docs/AGENT_CONTEXT.md` before substantive project work.

## Research direction

```text
official NF3-ToN-IoT flow row and dataset GT
→ model-safe Basic Evidence and Known prediction
→ OOF/cross-fitted utility-driven Temporal/Relation acquisition
→ Known re-evaluation
→ independent novelty detection after the Evidence gate
→ verified-feedback continual adaptation with replay and release gates
```

The official NF3-ToN-IoT final processed artifact is the Dataset-v4 core. Edge-IIoTset Model A is a completed legacy controlled-domain baseline and optional replay source. Other NF3 sources are secondary external-domain stress/replication candidates, not required merged training inputs.

## Implemented foundation

This repository currently provides:

- a reusable OpenAI-compatible LLM runtime with timeout, retry and bounded concurrency;
- Pydantic-based structured-output extraction and validation;
- input, prompt, model, generation and schema fingerprints;
- per-record validated cache and verifiable resume;
- independent failure, usage and latency traces;
- Markdown/YAML-front-matter RAG document ingestion with source metadata;
- a Flow-oriented Python package and baseline tests;
- a reproducible dual-dataset feasibility Gate with prototype Edge/IoT-23 adapters, manifests, leakage checks and synthetic schema fixtures;
- production `EdgeAdapter`/`IoT23Adapter`, `CanonicalSessionRecord` v1, checkpoint/resume, partitioned Parquet assets, paper-grade chronological/scenario-held splits, frozen K/U, diversity-aware SFT candidates, support/query manifests, and deterministic/leakage audits.
- a deterministic Agent Runtime foundation with model-safe views, capability/budget enforcement, memory permissions, one-action-per-round validation and structured traces;
- provider-neutral Traffic Expert/Supervisor transport contracts, strict parsers, versioned prompt profiles, a Fake Provider, and an explicitly injected OpenAI-compatible chat transport;
- an exact allow-list `production_runtime_adapter_v1` that reads materialized Production v2 evidence, emits typed Runtime inputs/tools, enforces phase/U_final permissions and keeps backend provenance out of model prompts;
- reproducible Qwen3.5-9B text-only serve/model-audit/real-smoke tools plus small Evidence Fidelity and model-readiness reports; model weights, environments and runtime logs remain Git-external;
- a Transformers/PEFT training harness with a dynamic Linear Fine Head, masked multi-task loss, real Qwen LoRA inventory, frozen pooling/serialization/Prompt/schema v1, and a real two-step 9B dry-run;
- historical Git-external Near PLAN_B Application/Payload sidecars, Teacher V3 corpus and RL pool; DEC-0021 supersedes these as formal training inputs while retaining them for audit.
- accepted six-class Observable Dataset v3, packet-aligned Basic/Evidence-v2, multi-gap Teacher-v2 and a session-weighted formal corpus v3; generated Parquet/JSONL/cache remain Git-external.
- completed Model A Formal Near SFT/evaluation, retained as a controlled baseline; its Known classifier passed while its LM Evidence-State branch failed for the target purpose;
- a frozen Dataset-v4 B1 schema plus the formal seven-class grouped/temporal split, whole-class Unknown rotations, strict-past history contract, 2,000-row Teacher-cache sample manifest and 63-row semantic-review request manifest. No response/API generation is included.

These components are engineering infrastructure, not claimed paper contributions. The Gate models and scores are audit probes, not formal paper results.

## Not implemented yet

The following current components remain future work:

- optional generation/review of the frozen Teacher-cache and semantic-reference requests, only after explicit researcher authorization;
- Model B low-cost fresh-vs-warm and Qwen-vs-small architecture Gates;
- formal Basic/Temporal/Relation single-family and combined utility experiments with second-seed/bootstrap checks;
- independent novelty candidates, evidence-conditioned open-world evaluation, and verified-feedback continual adaptation;
- a gated, low-cost fast Agent-policy comparison (heuristic/supervised utility vs Double DQN); it has not started and may remain a negative result. LLM RLAIF/PPO/GRPO is not part of the core plan.

The remote bootstrap, Production Data Freeze, Edge split/Runtime assets, Dataset-v3/Evidence-v2, and Model A checkpoint remain reusable historical foundations. Model A Teacher V3/v2 annotations and Evidence-State fields are provenance/reference only: they are not Model B labels, operational utility, or Unknown truth. DeepSeek is limited to offline semantic review and optional policy-demonstration/explanation/Supervisor baselines.

The unique long-term code branch is `main`. Model A training/evaluation and Dataset-v4 B1 formalization are complete. Model A's formal config is fail-closed against accidental relaunch. Model B training, continual learning, RL, and Teacher response generation have not started.

## Research Plan and Change Control

The canonical research plan is stored in:

- [Detailed research and implementation specification](docs/research_plan/research_plan_detailed.md) — highest research authority;
- [Formal Experiment Protocol v1](docs/research_plan/experiment_protocol_v1.md) — frozen experiment matrix, derived-view isolation, baselines, metrics and statistical rules;
- [Model B Evidence/open-world design](docs/research_plan/model_b_evidence_openworld_design.md) and [continual Agent design](docs/research_plan/open_world_continual_agent_design.md) — current Model B method/control boundary;
- [Dataset-v4 B1 runtime contract](docs/research_plan/dataset_v4_b1_runtime_contract.md) — current observation/Evidence/state/action engineering boundary;
- [Dataset-v4 split protocol](docs/research_plan/dataset_v4_split_protocol.md) — frozen taxonomy, identity, split, rotations, history scope and Teacher sampling population;
- [Near-first training protocol](docs/training/near_mainline_training_protocol_v1.md) and [provisional Agent architecture](docs/design/agent_architecture_provisional.md) — Model A lineage and reusable implementation constraints only where DEC-0025/0026/0027 do not supersede them;
- [Timeline and stage-control view](docs/research_plan/research_plan_and_timeline.md);
- [Brief research overview](docs/research_plan/research_plan_brief.md).

Developers and agents must read the canonical specification, Experiment Protocol and current Model B/Dataset-v4 contracts before research or runtime changes. Read the Near protocol and provisional Agent document when Model A lineage or reusable implementation details matter; neither can override DEC-0025/0026/0027. PROJECT_HANDOFF records current state but cannot override these authorities.

If a code change intentionally deviates from the plan and changes research meaning, comparability or conclusions, the same PR or commit must update the detailed specification and record the previous decision, new decision, reason, affected data/stages/metrics and a `Confirmed`, `Provisional` or `Experimental` status. Update the timeline or brief when their scope is affected.

Ordinary engineering changes normally do not require a plan update when semantics and experiment protocols are unchanged, including refactoring, logging improvements, variable renaming, unit-test fixes, path compatibility and performance optimization with unchanged inputs and outputs.

Agents must not tune on frozen test data or independently change frozen dataset roles, data permissions or final evaluation protocols. Do not retroactively rewrite research goals to match an implementation or leave a material code/plan divergence undocumented.

## Development

Python 3.11 or newer is recommended.

```bash
python -m pip install -e ".[test,data]"
python -m pytest
```

Build RAG chunks from a directory of Markdown knowledge documents:

```bash
python scripts/build_rag_chunks.py \
  --knowledge-dir docs/knowledge \
  --output artifacts/rag/chunks.jsonl
```

Runtime examples are in `configs/runtime.example.yaml`. API keys must be supplied through environment variables and must never be committed.

## Repository layout

```text
src/flowsec/llm/     reusable model runtime, cache, validation and traces
src/flowsec/rag/     knowledge-document ingestion
src/flowsec/production/ production adapters, schemas, manifests and audits
src/flowsec/runtime/ deterministic Agent state, policy, budget, memory and tool contracts
src/flowsec/integrations/llm/ provider-neutral Traffic Expert/Supervisor backend boundary
configs/             non-secret runtime examples
scripts/             small command-line entry points
tools/               auditable dataset and experiment utilities
reports/             feasibility evidence, manifests and reproducible audit scripts
tests/               infrastructure tests and synthetic fixtures
docs/                engineering contracts and migration notes
docs/research_plan/  canonical research specification and derived views
```

Dataset files, model checkpoints and generated artifacts are intentionally outside version control.
