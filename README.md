# Flow Security Agent

Flow Security Agent is a research framework for **session-level open-world malicious traffic analysis**. The current design uses a post-trained Qwen3.5-9B as the first classifier and a constrained decision Agent to acquire additional evidence, reject unknown traffic and support few-shot class onboarding.

> **New developer or Agent:** start with the [project handoff guide](docs/PROJECT_HANDOFF.md). It summarizes the current research Gate, completed assets, unresolved decisions, allowed next steps and working-tree safeguards.

## Research direction

```text
official PCAP and labels
→ dataset-specific session reconstruction
→ CanonicalSessionRecord and past-only context
→ text-only BF16 LoRA post-trained Qwen3.5-9B first classification and evidence state
→ frozen open-set scoring and calibration
→ constrained Agent evidence expansion and reclassification
→ sample-level 1/5/10-shot class onboarding
```

Edge-IIoTset is frozen as the primary dataset with stated limitations. IoT-23 is an independent scenario-held-out external validation dataset with its own native labels and model adaptation. Both passed the final feasibility Gate with `PASS_WITH_LIMITATIONS`; they share an interface but are not physically merged for training.

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
- reproducible Qwen3.5-9B text-only serve/model-audit/real-smoke tools plus small Evidence Fidelity and model-readiness reports; model weights, environments and runtime logs remain Git-external.

These components are engineering infrastructure, not claimed paper contributions. The Gate models and scores are audit probes, not formal paper results.

## Not implemented yet

The following model and experiment components remain future work:

- formal traditional-model baselines and Qwen3.5-9B SFT/few-shot checkpoints;
- a frozen production Unknown scoring algorithm and calibration threshold;
- Near RLAIF-GRPO Training #2, followed by Independent Unknown and Agent experiments; DPO, full-parameter 9B and formal 27B remain deferred;
- formal experiments and paper metrics.

The remote bootstrap, Production Data Freeze, Edge label-provenance/class-role Gates, paper-grade `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`, PLAN_B candidates, Production Runtime Safe Adapter, Evidence Fidelity Gate and official raw `Qwen/Qwen3.5-9B` local/runtime smoke are complete. These are infrastructure facts, not paper benchmarks; no SFT, RLAIF/GRPO, Unknown or formal Agent experiment has run. DEC-0019 now freezes `ONE_MAINLINE_FIRST`: Edge Near seed `20260809` is the first full route, using its unchanged K/U and 16,979 PLAN_B `K_known ∩ train` candidates. The trained design is frozen Qwen base + LoRA + one Linear Fine Classification Head + LM Evidence State, followed by Independent Unknown and a DeepSeek Flash Supervisor under deterministic Runtime. Application, sanitized payload and Production RAG are currently unavailable but are planned on-demand Near capabilities. Far, Mixed, IoT-23 execution and optional ablations wait until Near completes. See the [Near training protocol](docs/training/near_mainline_training_protocol_v1.md), [server migration guide](docs/SERVER_MIGRATION.md) and [Production freeze report](reports/production_data_freeze_20260809/README.md).

The unique long-term code branch is `main`; the audited baseline for this documentation synchronization is `e28c3f4806aa56dcdeb9e561cf6201e71f98a2a5`, which contains Edge v2, the Production Runtime Adapter, official raw Qwen deployment smoke and the CI portability fix. Protocol synchronization is isolated on `docs/sync-near-mainline-protocol`; training remains separately authorized future work.

## Research Plan and Change Control

The canonical research plan is stored in:

- [Detailed research and implementation specification](docs/research_plan/research_plan_detailed.md) — highest research authority;
- [Near-first training and Open-world protocol](docs/training/near_mainline_training_protocol_v1.md) — training/Open-world execution authority;
- [Agent / Runtime architecture](docs/design/agent_architecture_provisional.md) — Runtime/Supervisor/RAG/Memory design authority within the first two;
- [Timeline and stage-control view](docs/research_plan/research_plan_and_timeline.md);
- [Brief research overview](docs/research_plan/research_plan_brief.md).

Developers and agents must read the canonical specification before research changes, then the Near training protocol before model/training/Unknown/novel-class work, and the Agent architecture before Runtime/Supervisor/RAG/Memory work. PROJECT_HANDOFF records current state but cannot override these authorities.

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
