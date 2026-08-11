# Real Backend Integration Preparation v1

This package is the provider-neutral boundary between the deterministic Runtime
and explicitly configured language-model services. It defines explicit backend
configuration, versioned fixture prompts, structured instruction/data message
parts, an untrusted raw-response contract, strict replaceable parsers, bounded
retry, secret redaction and deterministic fake provider envelopes.

The package has no implicit network side effects or production defaults. Its
explicitly injected `OpenAICompatibleChatTransport` supports audited local or
provider endpoints; provider/model identifiers, endpoint, timeout, retry policy,
generation options, response mapping and prompt profile remain caller-supplied.
The `SYNTHETIC`/`FIXTURE` profiles remain offline test fixtures.
`RAW_SMOKE_TRAFFIC_EXPERT_PROMPT_V0` and its strict parser exist only for local
deployment smoke and do not freeze the later Qwen training/experiment schema.

`LLMTrafficExpertBackend` and `LLMSupervisorBackend` implement the existing
Runtime protocols without changing component authority. Raw provider output is
never evidence: it must pass mechanical JSON extraction, strict schema parsing,
model-safe validation and a detached Runtime-contract projection. The Supervisor
still proposes one action only; Runtime retains tool execution, budget, terminal
semantics, memory permissions and final-label authority.

Untrusted payload or retrieval text is emitted as a `DATA` block with explicit
trust, never as a system instruction. This is a software framing guarantee, not a
claim that a future real model is immune to prompt injection.

Production Parquet rows, SQLite/catalog objects and PCAP data are not accepted
by this boundary. They must first pass through the versioned Production safe
adapter and arrive as revalidated, model-safe Runtime `EvidenceItem` values.
