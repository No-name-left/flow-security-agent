# Runtime Foundation v1

This package is the provider-neutral software control skeleton for the provisional
Traffic Expert → independent Unknown Scorer → constrained Supervisor workflow.
The deterministic runtime validates one proposed evidence action per round,
enforces capability and budget limits, executes whitelisted tools, re-evaluates
the Traffic Expert and Unknown state after new evidence, and emits an auditable,
model-safe trace.

The package currently contains typed contracts, protocols, deterministic mocks,
synthetic evidence tools, phase-aware in-memory experience storage, isolated
class-memory contracts, experiment-variant configuration and a synthetic result
collector. It intentionally does **not** implement a real Qwen backend, real LLM
Supervisor backend, final prompt or response schema, final Unknown algorithm,
production evidence tools, final experience-retrieval algorithm, model training,
or a Production dataset adapter. Those systems must connect through the existing
protocol and evidence boundaries after their separate research and data Gates.
