# Runtime Foundation v1

This package is the provider-neutral software control skeleton for the provisional
Traffic Expert → independent Unknown Scorer → constrained Supervisor workflow.
The deterministic runtime validates one proposed evidence action per round,
enforces capability and budget limits, executes whitelisted tools, re-evaluates
the Traffic Expert and Unknown state after new evidence, and emits an auditable,
model-safe trace.

The package currently contains typed contracts, protocols, deterministic mocks,
phase-aware in-memory experience storage, isolated class-memory contracts,
experiment-variant configuration and a synthetic result collector. Production
connects through `production_runtime_adapter_v1`, which supplies allow-listed
Initial Evidence and bound packet/temporal/relation/application tools. It
intentionally does **not** implement a real Qwen backend, real LLM Supervisor
backend, final prompt or response schema, final Unknown algorithm, application or
payload extraction, production Knowledge RAG, final experience retrieval, or
model training.

## Integration boundary

- Traffic Expert, Supervisor and Evidence Tool backends must provide a local,
  side-effect-free `estimate()` before each call. The runtime reserves that
  declared upper bound before execution; a structured result may reconcile the
  reservation downward, while a failed call without structured usage retains the
  conservative reservation.
- Production adapters must create only allow-listed `EvidenceItem` projections.
  The runtime rejects explicit backend identities and sends the Supervisor a
  frozen `SupervisorView` without sample identity or raw verification feedback.
- Evidence-action parameter sets, experiment budgets, maximum rounds and memory
  retrieval limits must be supplied by the experiment configuration. Values used
  in tests are synthetic fixtures and are not paper or deployment defaults.
- Retrieved text remains `UNTRUSTED_EVIDENCE`; a real prompt adapter must quote
  and delimit it as data rather than execute it as an instruction.
