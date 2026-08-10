# Real Backend Integration Preparation v1

This package is the provider-neutral boundary between the deterministic Runtime
and future real language-model services. It defines explicit backend
configuration, versioned fixture prompts, structured instruction/data message
parts, an untrusted raw-response contract, strict replaceable parsers, bounded
retry, secret redaction and deterministic fake provider envelopes.

The package deliberately has no HTTP implementation and no production defaults.
Provider/model identifiers, endpoint, timeout, retry policy, generation options,
response mapping and prompt profile are caller-supplied. The current prompt and
parser profiles are named `SYNTHETIC`/`FIXTURE`/`V0_EXAMPLE`; they are test
fixtures, not frozen Qwen or Supervisor research schemas.

`LLMTrafficExpertBackend` and `LLMSupervisorBackend` implement the existing
Runtime protocols without changing component authority. Raw provider output is
never evidence: it must pass mechanical JSON extraction, strict schema parsing,
model-safe validation and a detached Runtime-contract projection. The Supervisor
still proposes one action only; Runtime retains tool execution, budget, terminal
semantics, memory permissions and final-label authority.

Untrusted payload or retrieval text is emitted as a `DATA` block with explicit
trust, never as a system instruction. This is a software framing guarantee, not a
claim that a future real model is immune to prompt injection.
