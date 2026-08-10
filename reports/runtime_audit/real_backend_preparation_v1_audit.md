# Real Backend Integration Preparation v1 Self-Audit

> Audit date: 2026-08-10
>
> Branch: `feat/real-backend-preparation`
>
> Scope: provider-neutral integration contracts, fixture prompt/response profiles,
> deterministic fake transports, Runtime integration tests and adversarial boundary tests
>
> This is an engineering and architecture audit, not a model, dataset or paper result.

## Verdict

`AUDIT_STATUS = PASS_WITH_FIXES`

`REAL_PROVIDER_SMOKE_READY = true`

No unresolved architecture conflict or blocking boundary defect remains in this
preparation layer. The verdict means that a separately authorized, very small real
provider smoke can be implemented next through the new interfaces. It does not
validate a provider, model, prompt, response schema, Unknown method or scientific
experiment.

## Implementation scope

The implementation adds `flowsec.integrations.llm` outside Runtime core:

- explicit provider/model/endpoint, timeout, retry, response-mode, generation,
  prompt-profile and secret-reference contracts;
- provider-neutral `LLMTransportRequest` and untrusted `RawLLMResponse`;
- replaceable Traffic Expert and Supervisor prompt renderers and response parsers;
- `LLMTrafficExpertBackend` and `LLMSupervisorBackend`, preserving the existing
  Runtime `estimate()` and call protocols;
- two synthetic provider-envelope profiles and a deterministic sequence-driven
  `FakeLLMTransport`;
- typed failure taxonomy, bounded caller-configured retry, mechanical-only JSON
  repair, attempt audit and conservative usage accounting;
- runtime-only secret providers and centralized redaction;
- fake-provider multi-round, Unknown-like, failure, determinism, injection and
  cross-provider tests.

There is no HTTP implementation, provider SDK, API key, real endpoint, real model,
real data, GPU path or Production adapter in scope.

## Independent findings and fixes

| ID | Severity | Adversarial finding | Fix and regression coverage | Status |
| --- | --- | --- | --- | --- |
| RB-01 | High | A secret could be accidentally embedded in endpoint/query, generation metadata or a prompt/evidence block; arbitrary `estimate()` exceptions also needed a redacted boundary. | Reject credential-bearing endpoints and secret-like config fields, scan final requests for injected runtime secrets before Transport, wrap estimate exceptions, hide raw content/secret references in repr and verify the sentinel secret is absent from exceptions, audit records, Trace and `RuntimeResult`. | Fixed |
| RB-02 | High | Direct Adapter use could pass a structurally valid `EvidenceItem` with `model_safe=false`; bypass-constructed nested prohibited fields also required revalidation at this last boundary. | Revalidate detached Evidence/Supervisor inputs and require every outbound evidence item to be model-safe before request construction. Tests cover bypassed nested truth fields and direct false projections. | Fixed |
| RB-03 | High | A provider usage record above the preflight estimate could be treated as a retryable unsupported response, risking an additional call after a budget-contract violation. | Estimate violations now force immediate safe stop regardless of retry configuration; Runtime retains its conservative reservation. | Fixed |
| RB-04 | Medium | Structured payloads could contain non-finite nested values, and provider usage accepted coercible scalar types. | Require finite JSON throughout parsed payloads and strict non-negative usage types; invalid usage/envelopes fail explicitly. | Fixed |
| RB-05 | Medium | Provider/model/response-mode mismatches were classified but could be retried if a broad caller policy included `UNSUPPORTED_RESPONSE`. | Treat identity and configured response-mode mismatches as non-retryable boundary violations. | Fixed |
| RB-06 | Medium | A malicious Transport or Parser could mutate nested request data or return a bypass-constructed Runtime object. | Send deep-detached requests, rebuild future requests from immutable config, and revalidate parser results into their Runtime contract before return. | Fixed |
| RB-07 | Low | Tightening non-finite JSON handling initially intercepted ordinary prefix/suffix extraction because `JSONDecodeError` is also a `ValueError`. | Restored the intended exception ordering and retained the limited unique-object repair test. | Fixed |

Finding counts: **critical 0, high 3, medium 3, low 1**.

## Provider independence

Synthetic provider A returns a text-oriented envelope and provider-style usage;
synthetic provider B can return a structured envelope with differently named
metering and finish fields. Both normalize to `RawLLMResponse`, then produce the
same `TrafficExpertResult`, `SupervisorDecision` and serialized Runtime semantic
result for the same logical scenario. No provider-specific import or envelope is
present in `flowsec.runtime`.

## Secret safety

Secrets are supplied only by an injected/environment `SecretProvider` or an
explicit runtime-only redaction value. They do not enter backend configuration as
values, Transport request metadata, repr, Runtime Trace or output contracts. The
sentinel test secret was exercised through request rejection,
Transport exceptions, timeout-style failures, repr, backend audit and serialized
Runtime results without disclosure. The audit artifact contains neither its value
nor any runtime credential.

## Model-visible and authority safety

- Final FakeTransport messages exclude sample identity, truth/evaluation labels,
  dataset/capture/scenario identity, raw IP and absolute timestamps.
- Backend metadata is ignored by parsers and never projected into Runtime results.
- Traffic Expert remains the only component that creates fine/coarse candidates.
- Supervisor parser accepts one action plus optional request parameters and short
  reason. Direct labels, tool execution, memory writes, system overrides, future
  context fields and multiple actions fail strict fixture validation or existing
  Runtime action validation.
- Unknown Scorer remains an independent backend and is rerun after each expert
  evaluation. An initial `UNKNOWN_LIKELY` state can still request evidence.
- Runtime still owns Tool execution, terminal semantics, budgets, memory and final
  results.

## Parsing and repair strictness

The fixture parsers accept raw structured data or one JSON object. Repair is
limited to trimming, removing a full Markdown JSON fence, or extracting one
unambiguous object with surrounding text. Each repair is recorded. Missing fields,
wrong types, invalid enums, duplicates, extra privilege fields, multiple objects,
truncation, empty output, non-finite values and unsupported envelopes fail
explicitly. No label, action or other scientific decision is inferred from prose.

The profiles are named `SYNTHETIC_*_V0_EXAMPLE`; they are replaceable examples and
are not the final Qwen or Supervisor response schema.

## Prompt-injection software framing

Evidence containing `IGNORE ALL PREVIOUS INSTRUCTIONS`, system-role imitation,
Tool requests and a claimed final label remains an explicitly typed `DATA` block.
Untrusted RAG evidence retains `UNTRUSTED_EVIDENCE` through the second Traffic
Expert request. System instruction, Tool specification and evidence occupy
separate structured parts, and Runtime actions originate only from the parsed
Supervisor response contract. This verifies software framing only; it does not
claim a future real model is immune to prompt injection.

## Retry, budget and termination

Retry limits and retryable failure classes are mandatory caller config, not
defaults. Adapter estimates reserve the per-attempt bound multiplied by the
configured maximum attempts before Runtime permits a call. Successful responses
reconcile to accumulated actual/conservative attempt usage; failures without
usage keep conservative attempt accounting, and an output-less final failure
keeps the Runtime reservation. Estimate violations do not retry. Existing Runtime
round, call, duplicate, invalid-output and terminal limits remain unchanged.

The end-to-end fake chain completes:

```text
model-safe evidence
→ LLM Traffic Expert adapter
→ independent Unknown scorer
→ LLM Supervisor adapter
→ one Temporal Tool action
→ second Traffic Expert evaluation
→ Unknown re-score
→ Supervisor terminal action
→ RuntimeResult
```

Traffic Expert timeout, Supervisor malformed/transport failure and second-round
Traffic Expert malformed output all terminate safely without fabricating a fine
result.

## Determinism and dependency audit

Identical fake sequences, inputs, budgets and configuration produce byte-identical
serialized Runtime results and request sequences. Cross-provider raw envelopes
produce the same semantic Runtime result. The new layer has no global provider
configuration, module-level secret, real endpoint, network call, Windows/server
path, circular Runtime import or provider SDK. No dependency was added.

## Architecture constraint mapping

| Constraint | Result |
| --- | --- |
| Qwen role remains Traffic Expert | PASS |
| High-capability LLM role remains Supervisor | PASS |
| Supervisor cannot create Fine label | PASS |
| Unknown remains independent | PASS |
| Runtime owns execution | PASS |
| One legal action per round | PASS |
| External model content is model-safe only | PASS |
| Experience/Class Memory permissions unchanged | PASS |
| Untrusted evidence remains data | PASS |
| API/local future provider remains replaceable | PASS |
| Deferred scientific choices remain deferred | PASS |

## Remaining limitations and deferred items

- No real HTTP/OpenAI-compatible/vLLM transport exists yet. A future provider
  adapter must normalize errors and usage into these contracts and apply a
  provider-side hard timeout/spend bound.
- The final Qwen and Supervisor model identifiers, prompts, response schemas,
  generation settings, timeouts, retry policy and provider/API versions remain
  deferred and must be frozen before formal evaluation.
- Final Unknown method/threshold, Tool costs, Agent rounds, Temporal windows,
  payload length, RAG and Memory retrieval settings remain deferred.
- A real-provider smoke must independently verify actual envelope mapping, token
  usage, timeout/cancellation, secret handling and local/API interchangeability.
- Production allow-list projection and data leakage tests remain mandatory; these
  lexical and typed defences do not replace the Production Adapter Gate.

## Verification

- Baseline before implementation: **120 passed** (including **96 Runtime tests**).
- New integration/adversarial tests: **74 passed**.
- Runtime tests after implementation: **96 passed**.
- Full repository tests after self-audit: **194 passed**.
- New dependency: **none**.
- Real network/API/model/data/GPU call: **none**.
- Runtime core, Production, research plans, `PROJECT_HANDOFF`, root `README.md`,
  `SERVER_MIGRATION.md` and `pyproject.toml`: **unchanged**.
