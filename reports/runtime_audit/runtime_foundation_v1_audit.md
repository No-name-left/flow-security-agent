# Runtime Foundation v1 Scientific & Architecture Audit

> Audit date: 2026-08-09
>
> Branch: `feat/model-agent-runtime`
>
> Scope: software contracts, deterministic runtime, mocks and synthetic tests only
> This report is an engineering/scientific-method audit, not a paper result.

## Verdict

`AUDIT_STATUS = PASS_WITH_FIXES`

`REAL_BACKEND_INTEGRATION_READY = true`

No architecture blocker was found after the fixes below. Integration may proceed
through the provider and Production-adapter boundaries, but this does not mean a
real Qwen backend, Unknown algorithm, Supervisor provider, evidence tool, prompt,
dataset adapter or experiment protocol has been validated.

## Audit basis

The implementation was checked against the canonical research plan and
`docs/design/agent_architecture_provisional.md`, with emphasis on component
authority, model-visible data isolation, Unknown independence, memory permissions,
observational/knowledge separation, budget timing, termination, determinism and
experiment-variant fairness. The baseline was 71 repository tests, including 47
Runtime tests.

## Findings and fixes

| ID | Severity | Finding | Fix and verification | Status |
| --- | --- | --- | --- | --- |
| F-01 | High | Supervisor received a copied but overly broad internal `EvidenceState`, including sample identity and full `VerifiedFeedback`; Traffic Expert also accepted internal previous state, and already-instantiated Pydantic objects could bypass construction-time checks. | Added frozen `SupervisorView` and `ValidatedExperienceView`; removed sample identity and raw feedback from Supervisor input; Traffic Expert now receives only detached model-safe evidence; Runtime revalidates every initial/backend/tool boundary. | Fixed |
| F-02 | High | Expert, Supervisor and Tool abstract resource limits could be discovered only after a call returned. | Added side-effect-free preflight `estimate()` contracts. Runtime reserves the declared bound before every call; successful structured calls reconcile downward, while output-less failures keep the conservative reservation. | Fixed |
| F-03 | High | A structurally valid Supervisor could force `ACCEPT_FINE`, `BACKOFF_COARSE` or `REJECT_UNKNOWN` without the corresponding evidence/Unknown conditions. | Runtime now validates terminal semantics. Final labels still come only from Traffic Expert candidates; Supervisor cannot create a label. | Fixed |
| F-04 | High | Temporal requests had no explicit future-context rejection and tool parameters lacked a configurable allow-list boundary. | Temporal acquisition now requires `past_only=true`, future/look-ahead markers are rejected, and optional per-action parameter allow-lists are enforced by request signature. | Fixed |
| F-05 | High | Verified feedback had no explicit positive/negative outcome or constrained source, so a non-abstaining prediction could be stored as a positive experience. | Added `FeedbackSource` and required `outcome_positive`; Runtime uses external verified polarity rather than its own prediction. Supervisor has no feedback/write interface. | Fixed |
| F-06 | Medium | Current expert output replaced the previous supporting/missing evidence without an explicit state-history contract. | Added `traffic_expert_history`. Current missing evidence changes only after the next Traffic Expert result; prior supporting/missing signals remain auditable. | Fixed |
| F-07 | Medium | Different requests returning identical evidence could grow state and trigger pointless reclassification; conflicting reuse of an evidence ID was ambiguous. | Evidence merge now deduplicates semantic repeats, rejects conflicting IDs and emits `NO_STATE_CHANGE` without incrementing the evidence round or rerunning the model. | Fixed |
| F-08 | Medium | Pydantic frozen models still contained mutable dictionaries, allowing a backend to mutate nested input aliases or a consumer to alias the mutable result budget. | Runtime now deep-detaches inputs independently for estimate/evaluate/decide/execute calls, copies and revalidates backend outputs, and returns a detached immutable budget snapshot. | Fixed |
| F-09 | Medium | Numeric max-round and memory retrieval defaults could be mistaken for frozen scientific choices. | All experiment budgets, maximum rounds and memory retrieval limits must now be supplied explicitly; test values are labelled synthetic fixtures. Budget-matched variants derive from a caller-supplied common budget. | Fixed |
| F-10 | Medium | Knowledge results were domain-checked but not required to retain their untrusted-evidence status. | RAG evidence must be knowledge-domain, knowledge-type and `UNTRUSTED_EVIDENCE`; it never marks an observational gap resolved. | Fixed |
| F-11 | Low | Duplicate tool actions or action/capability mismatches could be silently registered. | Constructor now rejects duplicate, terminal or capability-mismatched tool registrations. | Fixed |
| F-12 | Low | Memory read/write backend failures could escape finalization or expose an unvalidated preloaded experience. | Runtime drops invalid retrievals, records memory failures and preserves the classification result; the in-memory store rejects unverified preload/write records. | Fixed |

Counts: **critical 0, high 5, medium 5, low 2**.

## Boundary conclusions

### Component authority

- Traffic Expert alone creates fine/coarse candidates and evidence-understanding
  signals; it has no Tool interface.
- Unknown Scorer remains provider-neutral and is invoked after every Traffic
  Expert evaluation. `UNKNOWN_LIKELY` can still lead to evidence acquisition when
  valuable evidence remains.
- Supervisor receives only a frozen model-visible projection and proposes one
  structured action. It cannot execute tools, mutate the real budget, write memory
  or provide a final class field.
- Runtime owns validation, capability checks, request deduplication, budget,
  maximum rounds, Tool execution, memory permissions and final stopping.

### Model-visible data flow

```text
synthetic/Production backend record
→ explicit model-safe EvidenceItem projection
→ detached Traffic Expert input
→ validated TrafficExpertResult + independent UnknownDecision
→ frozen SupervisorView (no sample ID or raw feedback)
→ validated ToolRequest
→ model-safe/untrusted Tool evidence
→ aggregate-only Trace and Evaluation
```

Contracts reject explicit ground truth/evaluation labels, dataset/capture/scenario
identity, backend identity, raw IP and absolute timestamps in model-visible text or
metadata. This lexical defence supplements rather than replaces a Production
allow-list projection. Evaluation truth remains outside `RuntimeInput`,
`EvidenceState`, `SupervisorView`, Experience retrieval views and model-visible
trace summaries.

### Memory permissions

Only `TRAIN + externally VerifiedFeedback` can write Experience Memory.
`VALIDATION`, `U_DEV`, `TEST` and `U_FINAL` remain read-only through normal,
failure and finalization paths. Positive and negative outcomes come from verified
feedback polarity. Class Memory has a distinct record type, interface, store and
write path.

### Budget and termination

Expert, Supervisor, Tool and RAG attempts are counted separately. A call must fit
its preflight reservation before execution. Invalid Supervisor actions consume a
Supervisor call but not an evidence round; failed calls count as attempts. A
structured result reconciles to reported usage within its estimate, while an
exception without structured usage keeps the reservation. RAG increments both
Tool and RAG counters.

For arbitrary structured Supervisor behaviour, termination is bounded by a
terminal action, Supervisor-call budget, evidence max rounds, duplicate/no-state-
change detection, capability/tool failure policy or invalid-output retry limit.
Exhaustive small synthetic sequences and repeated deterministic runs did not
expose an infinite path or off-by-one round error.

## Adversarial coverage added

The audit added cases for nonexistent/malformed actions, missing required fields,
direct final-label injection, terminal actions carrying Tool requests, wrong Tool
targets, repeated and parameter-distinct requests, future temporal context,
parameter allow-list violations, unavailable capabilities, repeated Tool failure,
Unknown-forced Fine acceptance, reason/action contradiction, preflight budget
blocking for Expert/Supervisor/Tool, failed-call accounting, max-round termination,
unverified Memory retrieval/write, feedback polarity, backend-only metadata, raw
IP/time markers, nested mutation aliasing, duplicate/conflicting evidence,
evidence-history preservation and byte-for-byte deterministic Runtime results.

## Remaining limitations and deferred work

- The prohibited-field validator is defence in depth; Production adapters still
  need explicit field allow-lists and independent privacy/leakage tests.
- Real backends must provide conservative, side-effect-free estimates. Provider-
  side hard spend/time limits remain necessary because an external service can
  violate its estimate before Runtime observes the response.
- Final Tool parameter sets, maximum rounds, budgets, memory retrieval limit,
  Unknown algorithm, prompts, schema, RAG backend and evidence windows remain
  experiment configuration or deferred research decisions.
- Untrusted evidence is typed and never executed by Runtime, but the future prompt
  adapter must quote/delimit it and receive prompt-injection tests.
- No real data, model, API, vector store, training or paper metric was used in this
  audit.

## Verification

- Runtime tests after audit: **96 passed**.
- Full repository tests after audit: **120 passed**.
- New dependency: **none**.
- Research plans, handoff, root `README.md`, Production paths, reports outside this
  audit, dataset manifests and `pyproject.toml`: **unchanged**. The Runtime-local
  README was updated only to document the corrected integration contract.
