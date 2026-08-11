"""Provider-neutral LLM integration preparation layer.

This package contains replaceable configuration, prompt, raw-response, parser,
retry and transport boundaries. Real transports remain explicitly injected.
"""

from .adapters import LLMSupervisorBackend, LLMTrafficExpertBackend
from .contracts import (
    LLMBackendConfig,
    LLMBackendError,
    LLMFailureKind,
    LLMTransportRequest,
    RawLLMResponse,
    ResponseMode,
    RetryPolicy,
)
from .parsing import (
    FixtureSupervisorResponseParserV0,
    FixtureTrafficExpertResponseParserV0,
    RawSmokeTrafficExpertResponseParserV0,
)
from .prompting import (
    SupervisorPromptRenderer,
    ToolSpecification,
    TrafficExpertPromptRenderer,
    fixture_supervisor_prompt,
    fixture_traffic_expert_prompt,
    raw_smoke_traffic_expert_prompt,
)
from .transport import (
    FakeFailure,
    FakeLLMTransport,
    FixtureProviderAProfile,
    FixtureProviderBProfile,
    LLMTransport,
    OpenAICompatibleChatTransport,
)

__all__ = [
    "FakeFailure",
    "FakeLLMTransport",
    "FixtureProviderAProfile",
    "FixtureProviderBProfile",
    "FixtureSupervisorResponseParserV0",
    "FixtureTrafficExpertResponseParserV0",
    "LLMBackendConfig",
    "LLMBackendError",
    "LLMFailureKind",
    "LLMSupervisorBackend",
    "LLMTrafficExpertBackend",
    "LLMTransport",
    "LLMTransportRequest",
    "OpenAICompatibleChatTransport",
    "RawLLMResponse",
    "RawSmokeTrafficExpertResponseParserV0",
    "ResponseMode",
    "RetryPolicy",
    "SupervisorPromptRenderer",
    "ToolSpecification",
    "TrafficExpertPromptRenderer",
    "fixture_supervisor_prompt",
    "fixture_traffic_expert_prompt",
    "raw_smoke_traffic_expert_prompt",
]
