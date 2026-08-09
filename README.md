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
- a reproducible dual-dataset feasibility Gate with prototype Edge/IoT-23 adapters, manifests, leakage checks and synthetic schema fixtures.

These components are engineering infrastructure, not claimed paper contributions. The Gate models and scores are audit probes, not formal paper results.

## Not implemented yet

The following research components remain future work:

- production-grade EdgeAdapter, IoT23Adapter and full-data leakage-aware manifests;
- frozen full-data split, Known/Unknown and support/query protocols;
- formal traditional-model baselines and Qwen3.5-9B SFT/few-shot checkpoints;
- a frozen production Unknown scoring algorithm and calibration threshold;
- conditional LoRA DPO experiments; PPO/GRPO and full-parameter 9B or formal 27B training are outside the current mainline;
- formal experiments and paper metrics.

The local closeout and reproducible GitHub stopping point are complete. A remote server has been rented and is reachable through VS Code SSH; the project is now entering server initialization, before official data download or production processing. Formal training defaults to text-only BF16 LoRA with visual modules frozen and non-thinking structured output; QLoRA is only a resource/compatibility fallback. See [server migration and data recovery](docs/SERVER_MIGRATION.md). The repository retains code, reports, manifests, download instructions and small synthetic fixtures, not raw traffic or model artifacts.

## Research Plan and Change Control

The canonical research plan is stored in:

- [Detailed research and implementation specification](docs/research_plan/research_plan_detailed.md) — the single authoritative source;
- [Timeline and stage-control view](docs/research_plan/research_plan_and_timeline.md);
- [Brief research overview](docs/research_plan/research_plan_brief.md).

Developers and agents must read the detailed specification before changing dataset roles, data splits, label definitions, sample or episode construction, model structure, trainable parameters, training stages, losses, SFT/DPO/RLAIF, Known/Unknown/few-shot protocols, calibration, external tests, or anything that may change the paper's conclusions.

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
configs/             non-secret runtime examples
scripts/             small command-line entry points
tools/               auditable dataset and experiment utilities
reports/             feasibility evidence, manifests and reproducible audit scripts
tests/               infrastructure tests and synthetic fixtures
docs/                engineering contracts and migration notes
docs/research_plan/  canonical research specification and derived views
```

Dataset files, model checkpoints and generated artifacts are intentionally outside version control.
