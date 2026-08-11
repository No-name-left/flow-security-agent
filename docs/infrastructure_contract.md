# Model-call infrastructure contract

This document defines the minimum engineering contract for Traffic Expert, DeepSeek Flash Teacher/Judge/Supervisor, RAG and other formal model calls. The three DeepSeek roles must use distinct prompt/schema/permission/log identities even when they share one configurable provider.

## Required identity

Every request must be identified by:

- a stable record ID;
- a canonical input fingerprint;
- the exact prompt fingerprint;
- the model identity;
- generation-parameter identity;
- a non-secret runtime/configuration fingerprint;
- structured-output schema version.

A cache entry is reusable only when all identities match. Matching the record ID alone is insufficient.

## Required result handling

Only output that has passed the declared Pydantic schema may enter the validated cache. Each result must retain:

- cache-hit status and attempt count;
- response ID when available;
- prompt, completion and total token usage when provided;
- measured latency;
- the request identity used for validation.

Raw mixed-text model output is not a cache contract and should not be treated as a successful result.

## Failure and resume behavior

A failed record must not discard successful records from the same run. Failures are written separately with a bounded error message and attempt count. Resume checks the full request identity and the cached structured output before skipping a call.

Per-record cache writes use a temporary file followed by an atomic replace. Aggregate traces are deterministic summaries and can be rebuilt from a completed run.

## Scope

This contract is reusable experiment infrastructure. It does not define the Fine Head, Traffic Expert schema, Teacher/Judge/Supervisor rubrics, Unknown algorithm, RAG policy or Agent strategy; those follow the canonical plan, Near training protocol and Agent architecture.
