"""
Deterministic fake provider for tests and local development.

FakeStoryGenerationProvider never makes a network call and never reads
an API key. It implements the same StoryGenerationProvider interface
OpenAIStoryGenerationProvider does, so the generation service,
database workflow, validation, and API tests can exercise every
provider outcome (success, malformed output, timeout, provider error)
without cost, latency, or nondeterministic model output.
"""

from story_generator.generation.providers.base import RawExchangeCallback
from story_generator.generation.providers.errors import (
    ProviderAPIError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from story_generator.generation.providers.parser import parse_structured_result
from story_generator.generation.providers.types import (
    GenerationRequestInput,
    GenerationResult,
    UsageMetadata,
)

DEFAULT_RAW_RESPONSE = (
    '{"title": "菜单的故事", "body": "小明去饭馆点了一份菜单上的菜。", '
    '"translation": ["Xiao Ming went to a restaurant and ordered a dish '
    'from the menu."], '
    '"questions": [{"question": "小明去了哪里？", '
    '"options": ["学校", "饭馆", "商店", "医院"], "answer": 1, '
    '"evidence": "小明去饭馆点了一份菜单上的菜。"}]}'
)
DEFAULT_USAGE = UsageMetadata(prompt_tokens=120, completion_tokens=80, total_tokens=200)

_SCENARIOS = (
    "success",
    "malformed",
    "timeout",
    "rate_limit",
    "auth_error",
    "api_error",
)


class FakeStoryGenerationProvider:
    """
    Test double implementing StoryGenerationProvider.

    `scenario` controls generate()'s behavior:
      - "success" (default): parses `raw_response` (a valid structured
        JSON string by default) and returns the resulting
        GenerationResult.
      - "malformed": parses `raw_response` exactly like "success"
        does — the caller is expected to pass a malformed
        `raw_response` (bad JSON, missing fields, non-Chinese content,
        etc.) so the test exercises the real parser rather than a
        shortcut, and gets back the real ProviderInvalidResponseError.
      - "timeout": raises ProviderTimeoutError, no parsing attempted.
      - "rate_limit": raises ProviderRateLimitError.
      - "auth_error": raises ProviderAuthenticationError.
      - "api_error": raises ProviderAPIError.

    Every call is recorded on `self.calls` for assertions about what
    the service passed to the provider.
    """

    name = "fake"

    def __init__(
        self,
        scenario: str = "success",
        raw_response: str = DEFAULT_RAW_RESPONSE,
        usage: UsageMetadata = DEFAULT_USAGE,
    ):
        if scenario not in _SCENARIOS:
            raise ValueError(
                f"Unknown scenario '{scenario}', expected one of {_SCENARIOS}"
            )
        self.scenario = scenario
        self.raw_response = raw_response
        self.usage = usage
        self.calls: list[GenerationRequestInput] = []

    def generate(
        self,
        request: GenerationRequestInput,
        on_raw_exchange: RawExchangeCallback | None = None,
    ) -> GenerationResult:
        self.calls.append(request)
        fake_request_body = {
            "model": "fake-model",
            "vocabulary_snapshot": request.vocabulary_snapshot,
        }

        if self.scenario == "timeout":
            if on_raw_exchange is not None:
                on_raw_exchange(fake_request_body, None, None)
            raise ProviderTimeoutError("Fake provider timed out")
        if self.scenario == "rate_limit":
            if on_raw_exchange is not None:
                on_raw_exchange(fake_request_body, 429, {"error": "rate limited"})
            raise ProviderRateLimitError("Fake provider rate limit exceeded")
        if self.scenario == "auth_error":
            if on_raw_exchange is not None:
                on_raw_exchange(fake_request_body, 401, {"error": "unauthorized"})
            raise ProviderAuthenticationError("Fake provider rejected credentials")
        if self.scenario == "api_error":
            if on_raw_exchange is not None:
                on_raw_exchange(fake_request_body, 500, {"error": "server error"})
            raise ProviderAPIError(
                "Fake provider returned a server error", status_code=500
            )

        if on_raw_exchange is not None:
            on_raw_exchange(fake_request_body, 200, {"content": self.raw_response})

        return parse_structured_result(self.raw_response, self.usage)
