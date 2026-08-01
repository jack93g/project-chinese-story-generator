"""
Provider-neutral error taxonomy.

Every provider adapter (OpenAIStoryGenerationProvider, a future
Ollama/Qwen adapter, FakeStoryGenerationProvider, ...) must translate
whatever it can fail with — SDK exceptions, HTTP errors, malformed
model output — into one of these types. Callers (generation.service,
the API layer) only ever need to catch ProviderError and its
subclasses; they never need to know which concrete provider raised it
or import a provider SDK to do so.
"""


class ProviderError(Exception):
    """Base class for all provider-related errors."""


class ProviderTimeoutError(ProviderError):
    """The provider did not respond within the configured timeout."""


class ProviderRateLimitError(ProviderError):
    """The provider rejected the request due to rate limiting."""


class ProviderAuthenticationError(ProviderError):
    """The provider rejected the request due to invalid/missing credentials."""


class ProviderAPIError(ProviderError):
    """
    The provider's API returned an error response that doesn't fit a
    more specific category above (5xx, malformed request, unexpected
    upstream failure, etc.).
    """

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class ProviderInvalidResponseError(ProviderError):
    """
    The provider responded successfully at the transport level, but the
    response body could not be parsed into a canonical GenerationResult
    (not valid JSON, missing required fields, empty/non-Chinese
    content, etc.). Raised by providers.parser.parse_structured_result.
    """