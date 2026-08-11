# Legacy migration summary

> **Historical / superseded snapshot.** This file records an earlier migration or audit state and does not define the current research mainline. Current authority is `docs/research_plan/research_plan_detailed.md`, DEC-0019, and `docs/training/near_mainline_training_protocol_v1.md`.

## Result

The existing Git history was retained and tagged as `legacy-pcap-competition-final`. The active working tree was rebuilt as the Flow-first `flow_security_agent` project.

## Refactored migration

- OpenAI-compatible calls were extracted into a small transport and runner.
- Timeout, retry, bounded concurrency, per-record cache, SHA-256 fingerprints, usage, latency, failure isolation and resume were reimplemented behind generic interfaces.
- Mixed-text JSON extraction was retained as a concept and placed before Pydantic validation.
- Markdown/YAML-front-matter chunk building was migrated with explicit source trace and content fingerprints.
- Runtime configuration retained environment-injected credentials and separate local/remote endpoint profiles.

No legacy orchestration file was copied wholesale.

## Removed from the active tree

The old packet parsing toolchain, session/group construction, competition labels and rules, aggregate submission path, official exporters, accelerator-specific deployment files, historical outputs, archived scripts and old candidate datasets were removed. They remain available from the legacy Git tag.

## Design-only inheritance

Prompt budgeting, deterministic boundary-oriented retrieval, observable-evidence limits and experiment manifests remain useful ideas. Their old implementations were too coupled to the competition system and were not migrated.

## Current structure

```text
src/flowsec/llm/   model calls, validation, cache and trace
src/flowsec/rag/   document ingestion
configs/           non-secret runtime examples
scripts/           command-line utilities
tests/             infrastructure regression tests
docs/              contracts and migration notes
```

## Repository rename

GitHub repo rename pending. Repository metadata confirms that the connected account has admin permission, but the available GitHub connector does not expose repository rename and GitHub CLI is unavailable. Rename `No-name-left/Qwen-for-pcap` to `flow-security-agent` under **Settings → General → Repository name**, then run:

```bash
git remote set-url origin https://github.com/No-name-left/flow-security-agent.git
git remote -v
```

## Test status

The new infrastructure test suite passes locally: **9 passed**. It covers cache-compatible resume, invalidation after input/Prompt/model/runtime changes, independent failures, usage and latency traces, concurrency/sharding, mixed-text JSON validation, secret-safe runtime resolution and RAG source metadata.

## Next step

Start with public Flow dataset audit and a frozen canonical Flow schema. After the split and leakage policy are fixed, implement the 60-second causal context and LightGBM group-aware out-of-fold baseline before constructing Reviewer training data.
