# Main Baseline Integrity Audit + Server State Synchronization

Audit date: 2026-08-11

`MAIN_BASELINE_INTEGRITY=PASS_WITH_SYNC_FIXES`

## Git history and baseline

- The audit started on branch `main` with a clean working tree.
- Local HEAD and `origin/main` both resolved to `3ab33e36c8508bcd31afac2e12c094ae1fe0a964`.
- Annotated tag `baseline-pre-model-20260811` dereferences to that same commit.
- Production `44ec95c1b283d1aa8d8cc75ecd1eba4a30601aa0`, Docs/Architecture `08b33b9f2c317e7986464294ac6e25899f944b88`, Runtime `6d702ebd20784517328e5a7807e59d1190744ddb`, backend preparation `930d31ca154f7f5e4dc35dd5c07933ea4e1cabe3`, integration `c84d8115fbafb9ce40121eaa81076b0e6ff614d3`, and final integrated state `3ab33e36c8508bcd31afac2e12c094ae1fe0a964` are all ancestors of the audited baseline.
- Local `server/production-data-freeze` and `integration/production-agent-20260811` are already contained by `main`: `SAFE_TO_DELETE_LATER`, but retained by this audit. Both existing Git bundles are `KEEP`.

## Documents, code modules, and architecture

- All required research, handoff, server migration, provisional architecture, Runtime, LLM integration, Runtime audit, Production, test, tool, config, schema, manifest, readiness, and audit files exist, are readable, and are non-empty.
- The architecture grill passed all requested checks: Qwen Traffic Expert first classification; traditional models as baselines/diagnostics; independent Unknown; High-Capability Supervisor unable to create a fine label; deterministic Runtime execution with one legal evidence action per round; observational versus knowledge gaps; no RAG-fabricated observations; payload/RAG treated as untrusted evidence; separate Experience/Class Memory; frozen evaluation memory; optional Growth; 1/5/10-shot lifecycle; packets 1–8 initial and 9–16 expandable; BF16 LoRA default, QLoRA fallback, optional DPO; model ID, prompt, and Unknown algorithm still deferred.
- Production retains identity-only canonical dedup, evaluation-only exact/near sensitivity, provenance/purity guards, verified capture fallback, logical K/U and U_final isolation, separate BASE/few-shot readiness, the class-role support correction, evidence diversity before limiting, stale-run identity checks, Edge Near/Far/Mixed, IoT coarse roles, support/query generation, and readiness logic.
- Stale operational text was found in current-state documentation and synchronized without changing research semantics, data roles, K/U, sessionization, model roles, Unknown definition, Agent responsibilities, or experiment protocols.

## Server data and Production assets

| Root | Present | Approximate size | Current role |
| --- | --- | ---: | --- |
| `/root/autodl-tmp/workspace` | yes | 8.4M | Git workspace |
| `/root/autodl-tmp/datasets` | yes | 13G | official raw/extracted datasets |
| `/root/autodl-tmp/processed` | yes | 47G | Production assets and checkpoints |
| `/root/autodl-tmp/models` | yes | 0 | empty; no model downloaded |
| `/root/autodl-tmp/checkpoints` | yes | 0 | empty top-level model checkpoint root |
| `/root/autodl-tmp/experiments` | yes | 3.9M | Production reports/manifests |
| `/root/autodl-tmp/cache` | yes | 119M | external cache |
| `/root/autodl-tmp/conda` | yes | 1.2G | isolated environments |
| `/root/autodl-tmp/tmp` | yes | 120K | temporary workspace |

- Edge official archive is present at 1,746,605,436 bytes with MD5 `d0f9be0185845a1ef4ed31cc6db4a9b2`. The extract inventory matches its manifest: 52 members, including 24 PCAP and 26 CSV files.
- The IoT-23 source manifest has 19 entries with no missing or size-mismatched item. The selected dataset contains eight PCAPs, eight companion `conn.log.labeled` files, README material, and all eight formal scenarios; no unexpected formal asset was found.
- Current Production manifests report 7,818,954 backend records and 7,569,346 canonical sessions, exactly matching the historical expected counts.
- Current status remains `PRODUCTION_DATA_READY=true`, `CLASS_ROLE_SUPPORT_GATE=PASS`, `CAPTURE_PROVENANCE_GATE=PASS`, `LABEL_PROVENANCE_AUDIT_POSTFIX=PASS_WITH_LIMITATIONS`, `POSTFIX_PRECOMMIT_AUDIT=PASS_WITH_LIMITATIONS`, and `U_FINAL_ISOLATION_PASS=true`.
- Edge provenance remains 24/24 captures passed. All 7,619,032 Edge backend sessions use verified capture fallback; conflicts and unmatched/quarantine counts are zero.
- Production `_state/checkpoints` contains 32 completed checkpoints: 24 Edge and 8 IoT. The reuse audit reports `CHECKPOINT_REUSABLE=true`, source/config/mode/count/provenance checks true, SQLite `database_integrity=ok`, and no TShark rerun required for completed captures. The catalog remains Git-external and was not subjected to an unnecessary full rescan.

## Environment and external-asset safety

- `/root/autodl-tmp/conda/flow-data` is present with Python 3.11.15, Pydantic 2.13.4, pytest 9.1.1, PyYAML 6.0.3, and PyArrow 25.0.0. No package was installed or updated.
- TShark is `/usr/bin/tshark`, Wireshark 3.6.2. Zeek is not installed and was not required for this audit.
- `/root/autodl-tmp/models` and the top-level `/root/autodl-tmp/checkpoints` are empty. No Qwen, DeepSeek, formal model training, or SFT has run.
- No tracked PCAP/PCAPNG, raw archive, Parquet, SQLite/database, model weight, checkpoint, large JSONL, credential, or tracked file at least 5 MB was found. Production data and complete artifacts remain outside Git.
- The safe HTTPS command `git push --dry-run origin HEAD:refs/heads/server-push-auth-test` currently fails because Git cannot read a GitHub username in this server shell. `SERVER_GITHUB_PUSH_DRY_RUN=FAIL`. No PAT, SSH key, `gh`, push, or remote branch mutation was performed.

## Verification

- Import smoke: `flowsec.production`, `flowsec.runtime`, and `flowsec.integrations.llm` all import successfully.
- Full test suite: `234 passed` on Python 3.11.15.
- `git diff --check`: PASS.
- Conflict-marker scan: PASS.

## Remaining limitations and next task

- The documented Edge single-capture/shortcut risks and IoT-23 small-support/matching limitations remain unchanged.
- Real provider/model identifiers, final prompts, the Unknown algorithm, Qwen weights, training, and formal experiments remain deferred.
- GitHub push authentication is unavailable in the current server shell; this does not invalidate the local baseline.
- Authoritative structure: `main` is the unique long-term code line; `research_plan_detailed.md` is the canonical research specification; `agent_architecture_provisional.md` is the provisional implementation design; `PROJECT_HANDOFF.md` is current status/next-step guidance; `AGENTS.md` is the Codex entry contract; `SERVER_MIGRATION.md` is the server/data recovery guide.
- The single recommended next development task is **Production → Runtime Safe Adapter**, but it was not implemented in this audit.
