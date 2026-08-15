from typing import Callable, Protocol, runtime_checkable

from story_generator.generation.providers.types import GenerationRequestInput, GenerationResult

# Called by a provider with (request_body, response_status, response_body)
# right before generate() returns or raises, so callers can persist the
# raw exchange without the provider needing to know about persistence.
# response_status/response_body are None when no response was ever
# received (e.g. a timeout or connection error).
RawExchangeCallback = Callable[[dict | None, int | None, dict | None], None]


@runtime_checkable
class StoryGenerationProvider(Protocol):
    """
    The interface every story-generation provider adapter implements
    (OpenAIStoryGenerationProvider, a future Ollama/Qwen adapter,
    FakeStoryGenerationProvider, ...).

    generate() must either return a GenerationResult or raise one of
    the errors in story_generator.generation.providers.errors. It must
    not raise a provider-SDK-specific exception.

    on_raw_exchange, if given, must be invoked exactly once per call —
    with the request body, response status, and response body it
    actually sent/received — before generate() returns or raises, so
    a caller can persist the raw exchange (e.g. to
    raw_generation_payloads) regardless of the outcome.
    """

    def generate(
        self,
        request: GenerationRequestInput,
        on_raw_exchange: RawExchangeCallback | None = None,
    ) -> GenerationResult:
        ...