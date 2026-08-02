# Flow Security Agent

Flow Security Agent is a research framework for **Flow-based malicious traffic analysis**. The current research studies open-set recognition, evidence-grounded ATT&CK candidate attribution and few-shot onboarding of Flow-observable attack techniques.

## Research direction

```text
Flow / NetFlow
→ audited raw record / label unit / model sample
→ anchor behavior + past-only behavior-coherent Flow context
→ Qwen3.5-9B supervised and structural adaptation
→ Known / Unknown
→ evidence-grounded Top-k ATT&CK candidates
→ data-dependent few-shot onboarding
```

The multi-Flow episode is a hypothesis to be audited and compared with anchor-only, single-Flow and fixed-window baselines. It is not assumed to be a native or automatically correct label unit.

## Implemented foundation

This initial repository provides:

- a reusable OpenAI-compatible LLM runtime with timeout, retry and bounded concurrency;
- Pydantic-based structured-output extraction and validation;
- input, prompt, model, generation and schema fingerprints;
- per-record validated cache and verifiable resume;
- independent failure, usage and latency traces;
- Markdown/YAML-front-matter RAG document ingestion with source metadata;
- a Flow-oriented Python package and baseline tests.

These components are engineering infrastructure, not claimed paper contributions.

## Not implemented yet

The following research components remain future work:

- public Flow dataset adapters and leakage-aware splits;
- label-unit audit and anchor-plus-past-context sample construction;
- LightGBM training, calibration and group-aware out-of-fold predictions;
- Qwen3.5-9B Stage A/SFT/few-shot training and independent checkpoints;
- DPO and gated RLAIF experiments;
- formal experiments and paper metrics.

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
python -m pip install -e ".[test]"
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
tests/               infrastructure tests without dataset dependencies
docs/                engineering contracts and migration notes
docs/research_plan/  canonical research specification and derived views
```

Dataset files, model checkpoints and generated artifacts are intentionally outside version control.
