# DeepSeek API operations

DeepSeek is an external reasoning provider. It receives only the typed,
role-specific context constructed by Runtime or the training driver. It never
receives arbitrary repository/server access. Secrets stay outside Git.

## Runtime configuration

The only required secret is DEEPSEEK_API_KEY. Optional DEEPSEEK_BASE_URL and
DEEPSEEK_MODEL override defaults. The operator-managed environment file stays
outside the repository. Source it only in the same shell that starts the
command. Never print, copy, persist, or add that file to Git.

DeepSeek V4 defaults to thinking mode, so the project provider explicitly sends
non-thinking mode for short deterministic JSON Teacher/Judge/Supervisor calls.
The model ID remains configurable.

## Health check

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

## Teacher operations

~~~bash
python tools/prepare_near_pretraining.py teacher-pilot --teacher-concurrency 4
python tools/prepare_near_pretraining.py teacher-bulk --teacher-concurrency 16
python tools/prepare_near_pretraining.py finalize-sft
~~~

Pilot must cover all known classes, evidence stages, and sufficient/insufficient
states and finish with zero quarantine. Bulk records/cache are Git-external,
deterministically keyed by state digest + prompt digest + model, and resumable.
Bulk reuses valid pilot cache entries.

Teacher requests are built only by build_teacher_request. Future RLAIF Judge
requests use build_judge_request; formal Agent Supervisor requests use
build_supervisor_request. Do not replace these with a generic all-context
prompt.

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

Teacher and Judge are training-driver controlled. Supervisor may choose only a
frozen action; Runtime validates and executes it. No DeepSeek role may execute
shell/Git/tools or read backend stores directly.
