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
- reproducible Qwen3.5-9B text-only serve/model-audit/real-smoke tools plus small Evidence Fidelity and model-readiness reports; model weights, environments and runtime logs remain Git-external;
- a Transformers/PEFT training harness with a dynamic Linear Fine Head, masked multi-task loss, real Qwen LoRA inventory, frozen pooling/serialization/Prompt/schema v1, and a real two-step 9B dry-run;
- Git-external Near K-known TRAIN Application/Payload sidecars, a 30-source BM25+dense Knowledge RAG index, a 22,957-state pre-Teacher snapshot universe, and a frozen 6,000-prompt RL pool.

These components are engineering infrastructure, not claimed paper contributions. The Gate models and scores are audit probes, not formal paper results.

## Not implemented yet

The following model and experiment components remain future work:

- DeepSeek provider preflight, Teacher pilot/bulk and the final Teacher-grounded SFT corpus; the sole current blocker is a missing runtime `DEEPSEEK_API_KEY`;
- formal traditional-model baselines and Qwen3.5-9B SFT/few-shot checkpoints;
- formal Runtime wiring for the prepared Application/Payload/RAG assets;
- a frozen production Unknown scoring algorithm and calibration threshold;
- Near RLAIF-GRPO Training #2, followed by Independent Unknown and Agent experiments; DPO, full-parameter 9B and formal 27B remain deferred;
- formal experiments and paper metrics.

The remote bootstrap, Production Data Freeze, Edge label-provenance/class-role Gates, paper-grade `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`, PLAN_B candidates, Production Runtime Safe Adapter, Evidence Fidelity Gate and official raw `Qwen/Qwen3.5-9B` local/runtime smoke are complete. Phase B has additionally completed every non-API pre-training preparation and a reversible two-step real-9B dry-run. These are infrastructure facts, not paper benchmarks; no formal SFT, RLAIF/GRPO, Unknown or Agent experiment has run. DEC-0019 freezes `ONE_MAINLINE_FIRST`: Edge Near seed `20260809` is the first full route, using unchanged K/U and 16,979 PLAN_B `K_known ∩ train` candidates. The trained design remains frozen Qwen base + LoRA + one Linear Fine Classification Head + LM Evidence State, followed by Independent Unknown and a DeepSeek Flash Supervisor under deterministic Runtime. Prepared Application/Payload/RAG artifacts are Git-external and not yet formal Runtime tools. Far, Mixed, IoT-23 execution and optional ablations wait until Near completes. See the [Phase B readiness report](reports/training_readiness/near_pretraining_readiness_v1.md), [Near training protocol](docs/training/near_mainline_training_protocol_v1.md), and [server migration guide](docs/SERVER_MIGRATION.md).

The unique long-term code branch is `main`; the audited source baseline is `ff4eca8fc6e00196666a9a3768679e3ddfefea60`. Phase B implementation is isolated on `feat/near-pretraining-readiness-v1`; it must not be interpreted as authorization to start formal training.

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
