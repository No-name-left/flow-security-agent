# Flow Security Agent

Flow Security Agent is a research framework for **Flow-based malicious traffic analysis**. The project studies how a fast tabular classifier and a security-focused language-model reviewer can cooperate under static and agentic orchestration.

## Research direction

```text
Flow / NetFlow
→ causal historical context
→ LightGBM
→ Qwen Security Reviewer
→ Static / Agentic workflow
```

The language model is intended to review selected difficult records rather than replace the tabular classifier for every Flow.

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

- public Flow dataset adapters and leakage-aware data splits;
- 60-second causal context construction;
- LightGBM training, calibration and group-aware out-of-fold predictions;
- Qwen reviewer data construction, QLoRA-SFT and preference optimization;
- DeepSeek orchestration or any agent workflow;
- formal experiments and paper metrics.

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
```

Dataset files, model checkpoints and generated artifacts are intentionally outside version control.
