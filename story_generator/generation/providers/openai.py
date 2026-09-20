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

User-facing prompt text is NOT built here — it comes from
story_generator.generation.prompts.builder.build_prompt, dispatched by
request.prompt_version, so the exact prompt persisted alongside a
request (via GenerationRequestInput.prompt_version) is the exact
prompt actually sent, regardless of which provider handles it.

Credentials: the API key is only ever placed in the Authorization
header of the outbound HTTP request — it is never included in the
JSON request/response body reported via on_raw_exchange, and this
module never logs the key or the header.

build_openai_provider() additionally gates on
story_generator.generation.providers.provider_registry: the current
(provider_label, model, base_url) combination must have a recorded,
reviewed comparison entry before it can be resolved into a live
provider (M3-7). This is ONE of two required call sites — the other is
process startup for anything long-running (see
provider_registry.assert_current_provider_approved's docstring for
why both are needed).
"""

import time

import httpx

from story_generator.config import (
    get_openai_api_key,
    get_openai_base_url,
    get_openai_model,
)
from story_generator.generation.prompts.builder import build_prompt
from story_generator.generation.providers.base import RawExchangeCallback
from story_generator.generation.providers.errors import (
    ProviderAPIError,
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from story_generator.generation.providers.parser import parse_structured_result
from story_generator.generation.providers.provider_registry import (
    assert_current_provider_approved,
)
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

    def generate(
        self,
        request: GenerationRequestInput,
        on_raw_exchange: RawExchangeCallback | None = None,
    ) -> GenerationResult:
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
            if on_raw_exchange is not None:
                on_raw_exchange(payload, None, None)
            raise ProviderTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            if on_raw_exchange is not None:
                on_raw_exchange(payload, None, None)
            raise ProviderAPIError(str(exc)) from exc
        latency_ms = int((time.monotonic() - start_time) * 1000)

        response_body = self._try_parse_json_body(response)

        if on_raw_exchange is not None:
            on_raw_exchange(payload, response.status_code, response_body)

        self._raise_for_status(response, response_body)

        if response_body is None:
            raise ProviderInvalidResponseError("Provider response was not valid JSON")

        raw_text = self._extract_content(response_body)
        usage = self._extract_usage(response_body, latency_ms)
        return parse_structured_result(raw_text, usage)

    def _raise_for_status(
        self, response: httpx.Response, response_body: dict | None
    ) -> None:
        if response.status_code < 400:
            return
        message = self._error_message(response, response_body)
        if response.status_code in (401, 403):
            raise ProviderAuthenticationError(message)
        if response.status_code == 429:
            raise ProviderRateLimitError(message)
        raise ProviderAPIError(message, status_code=response.status_code)

    @staticmethod
    def _error_message(response: httpx.Response, response_body: dict | None) -> str:
        if response_body is not None:
            return str(response_body.get("error", {}).get("message", response_body))
        return response.text or f"HTTP {response.status_code}"

    @staticmethod
    def _try_parse_json_body(response: httpx.Response) -> dict | None:
        try:
            return response.json()
        except ValueError:
            return None

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
    assert_current_provider_approved()
    return OpenAIStoryGenerationProvider(
        client=httpx.Client(),
        api_key=get_openai_api_key(),
        model=get_openai_model(),
        base_url=get_openai_base_url(),
    )
