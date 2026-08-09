"""
Production StoryGenerationProvider backed by an OpenAI-compatible chat
completions API, called directly over HTTP via httpx (no vendor SDK
dependency — consistent with the rest of this codebase, which already
uses httpx for outbound HTTP and respx for mocking it in tests).

"OpenAI-compatible" is deliberate: the base URL is configurable (see
story_generator.config.get_openai_base_url), so this same adapter
works unmodified against OpenAI itself or any provider implementing
the same /chat/completions request/response shape (e.g. OpenRouter,
Groq) — useful for local development without an OpenAI billing
account.

Everything outside this module — generation.service, the API layer,
tests — depends on the provider-neutral
story_generator.generation.providers.base.StoryGenerationProvider
interface instead, so a future non-OpenAI-shaped adapter (Ollama/Qwen)
can be dropped in without touching the service, the database tables,
or the public API.

User-facing prompt text is NOT built here — it comes from
story_generator.generation.prompts.builder.build_prompt, dispatched by
request.prompt_version, so the exact prompt persisted alongside a
request (via GenerationRequestInput.prompt_version) is the exact
prompt actually sent, regardless of which provider handles it.

Credentials: the API key is only ever placed in the Authorization
header of the outbound HTTP request — it is never included in the
JSON request/response body that generate() works with, and this
module never logs the key or the header. If a future caller wires
add_raw_payload() into this flow, it must continue passing only the
JSON body (never headers) — see GenerationRequestRepository's own
docstring on this same constraint.
"""

import time

import httpx

from story_generator.config import get_openai_api_key, get_openai_base_url, get_openai_model
from story_generator.generation.prompts.builder import build_prompt
from story_generator.generation.providers.errors import (
    ProviderAPIError,
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from story_generator.generation.providers.parser import parse_structured_result
from story_generator.generation.providers.types import (
    GenerationRequestInput,
    GenerationResult,
    UsageMetadata,
)

_DEFAULT_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

_SYSTEM_PROMPT = (
    "You are a Chinese-language story generator for language learners. "
    "Respond with a single JSON object of the form "
    '{"title": "<Chinese title>", "body": "<Chinese story body>"} '
    "and nothing else — no markdown fences, no commentary."
)


class OpenAIStoryGenerationProvider:
    """
    StoryGenerationProvider implementation backed by an OpenAI-
    compatible chat completions API, called via a plain httpx.Client.

    The client is injected rather than constructed internally, both so
    callers control connection pooling/base_url/etc. and so tests can
    pass an httpx.Client that respx is mocking.

    Any transport or API-level failure is caught and translated into
    the provider-neutral taxonomy in providers.errors before it leaves
    generate() — callers never see an httpx exception or a raw
    provider error-response shape directly.
    """

    name = "openai"

    def __init__(
        self,
        client: httpx.Client,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_CHAT_COMPLETIONS_URL,
        timeout: float = 60.0,
    ):
        self._client = client
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout

    def generate(self, request: GenerationRequestInput) -> GenerationResult:
        payload = {
            **request.model_parameters,
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(request)},
            ],
            "response_format": {"type": "json_object"},
        }

        start_time = time.monotonic()
        try:
            response = self._client.post(
                self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            # Connection errors, protocol errors, etc. — anything that
            # isn't a timeout and isn't an HTTP-status-carrying response.
            raise ProviderAPIError(str(exc)) from exc
        latency_ms = int((time.monotonic() - start_time) * 1000)

        self._raise_for_status(response)

        body = self._parse_json_body(response)
        raw_text = self._extract_content(body)
        usage = self._extract_usage(body, latency_ms)
        return parse_structured_result(raw_text, usage)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        message = self._error_message(response)
        if response.status_code in (401, 403):
            raise ProviderAuthenticationError(message)
        if response.status_code == 429:
            raise ProviderRateLimitError(message)
        raise ProviderAPIError(message, status_code=response.status_code)

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
            return str(body.get("error", {}).get("message", body))
        except ValueError:
            return response.text or f"HTTP {response.status_code}"

    @staticmethod
    def _parse_json_body(response: httpx.Response) -> dict:
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderInvalidResponseError(f"Provider response was not valid JSON: {exc}") from exc

    @staticmethod
    def _extract_content(body: dict) -> str:
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderInvalidResponseError(
                f"Provider response did not contain message content: {exc}"
            ) from exc

    @staticmethod
    def _extract_usage(body: dict, latency_ms: int) -> UsageMetadata:
        try:
            usage = body["usage"]
            return UsageMetadata(
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
                latency_ms=latency_ms,
            )
        except (KeyError, TypeError) as exc:
            raise ProviderInvalidResponseError(
                f"Provider response did not contain usage metadata: {exc}"
            ) from exc


def build_openai_provider() -> OpenAIStoryGenerationProvider:
    """
    Construct an OpenAIStoryGenerationProvider from trusted server
    configuration (environment variables via story_generator.config),
    never from client-supplied input — see the AC on M3-3's request
    schema, which deliberately excludes provider/model as fields a
    caller can set.
    """
    return OpenAIStoryGenerationProvider(
        client=httpx.Client(),
        api_key=get_openai_api_key(),
        model=get_openai_model(),
        base_url=get_openai_base_url(),
    )