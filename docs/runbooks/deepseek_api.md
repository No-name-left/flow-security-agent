# DeepSeek API operations

> **LEGACY_MODEL_A_OPERATIONS / DEPRECATED / DO_NOT_EXECUTE_FOR_MODEL_B**
>
> The commands below preserve completed Model A recovery provenance. They are
> not current Model B instructions. Model B does not require DeepSeek for NF3
> labels, operational Evidence utility, True Unknown, novelty detection, or
> continual verified labels. Do not rerun Model A Teacher bulk, generate RLAIF
> rewards, or start a mandatory online Supervisor from this runbook.

DeepSeek is an external reasoning provider. It receives only the typed,
role-specific context constructed by Runtime or the training driver. It never
receives arbitrary repository/server access. Secrets stay outside Git.

Under DEC-0025/0027, future DeepSeek use is limited to offline semantic review and
explicitly optional policy-demonstration, explanation, or Supervisor-baseline
work. The final nonleaking `teacher_cache_v1` sample manifest is frozen under
DEC-0026, but it is not executable until a researcher separately authorizes generation. Its
output can never be classification GT, operational utility GT, Unknown GT, or
continual-learning GT.

## Runtime configuration

The only required secret is DEEPSEEK_API_KEY. Optional DEEPSEEK_BASE_URL and
DEEPSEEK_MODEL override defaults. The operator-managed environment file stays
outside the repository. Source it only in the same shell that starts the
command. Never print, copy, persist, or add that file to Git.

DeepSeek V4 defaults to thinking mode, so the project provider explicitly sends
non-thinking mode for short deterministic JSON Teacher/Judge/Supervisor calls.
The model ID remains configurable.

## Legacy Model A health check — do not execute for Model B

Use the project entrypoint, not an ad-hoc production client:

~~~bash
export ARTIFACT_ROOT=/data/processed
python tools/prepare_near_pretraining.py provider-status
~~~

The operator may source the external secret immediately before that command.
The health check performs model discovery, one text completion, and one JSON
completion through the project OpenAI-compatible transport. Its manifest
records request IDs, token usage, latency, model ID, and redaction status, never
the key. A direct models/ChatCompletion request may diagnose provider/network
configuration but does not replace the project health check.

## Legacy Model A Teacher operations — completed; do not rerun

~~~bash
python tools/prepare_near_pretraining.py teacher-pilot --teacher-concurrency 4
python tools/prepare_near_pretraining.py teacher-bulk --teacher-concurrency 16
python tools/prepare_near_pretraining.py finalize-sft
~~~

These commands are retained only for disaster recovery of historical Model A
artifacts. Pilot was required to cover all known classes, evidence stages, and sufficient/insufficient
states and finish with zero quarantine. Bulk records/cache are Git-external,
deterministically keyed by state digest + prompt digest + model, and resumable.
Bulk reuses valid pilot cache entries.

Historical Teacher requests were built only by `build_teacher_request`.
Historical `build_judge_request` and `build_supervisor_request` capabilities do
not authorize Model B RLAIF or a mandatory Supervisor. Any separately
authorized Model B cache must use the materialized B1 request manifest and
exact four-action contract; do not adapt the old Evidence-State schema by
changing only a prompt.

## Failure diagnosis

- NO_API_KEY: configure the external environment in the current process.
- model unavailable: verify the configured model against /models.
- empty final content: verify explicit non-thinking mode and adequate output
  tokens; V4 thinking output can otherwise consume the bound.
- schema/grounding rejection: inspect the safe failure type and one legal TRAIN
  response, then make at most a bounded prompt/validator correction.
- timeout/rate-limit: keep bounded concurrency and retry; resume from validated
  cache.
- stale cache: prompt/model/source digest mismatch intentionally causes a fresh
  call.
- secret-redaction failure: stop immediately; never publish logs or reports.

Any explicitly authorized future Teacher/baseline remains driver controlled,
and Runtime validates every action. No DeepSeek role may execute shell/Git/tools
or read backend stores directly. Existing `evidence_sufficient`,
`missing_evidence`, and `primary_gap` caches are `LEGACY_REFERENCE` only.
