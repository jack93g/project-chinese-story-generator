"""
Production StoryGenerationProvider backed by the OpenAI chat
completions API, called directly over HTTP via httpx (no vendor SDK
dependency — consistent with the rest of this codebase, which already
uses httpx for outbound HTTP and respx for mocking it in tests).

Everything outside this module — generation.service, the API layer,
tests — depends on the provider-neutral
story_generator.generation.providers.base.StoryGenerationProvider
interface instead, so a future Ollama/Qwen adapter can be dropped in
without touching the service, the database tables, or the public API.

User-facing prompt text is NOT built here — it comes from
story_generator.generation.prompts.builder.build_prompt, dispatched by
request.prompt_version, so the exact prompt persisted alongside a
request (via GenerationRequestInput.prompt_version) is the exact
prompt actually sent, regardless of which provider handles it.
"""

import httpx

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

_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

_SYSTEM_PROMPT = (
    "You are a Chinese-language story generator for language learners. "
    "Respond with a single JSON object of the form "
    '{"title": "<Chinese title>", "body": "<Chinese story body>"} '
    "and nothing else — no markdown fences, no commentary."
)


class OpenAIStoryGenerationProvider:
    """
    StoryGenerationProvider implementation backed by the OpenAI chat
    completions API, called via a plain httpx.Client.

    The client is injected rather than constructed internally, both so
    callers control connection pooling/base_url/etc. and so tests can
    pass an httpx.Client that respx is mocking.

    Any transport or API-level failure is caught and translated into
    the provider-neutral taxonomy in providers.errors before it leaves
    generate() — callers never see an httpx exception or an OpenAI
    error-response shape directly.
    """

    name = "openai"

    def __init__(self, client: httpx.Client, api_key: str, model: str, timeout: float = 60.0):
        self._client = client
        self._api_key = api_key
        self._model = model
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

        try:
            response = self._client.post(
                _CHAT_COMPLETIONS_URL,
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

        self._raise_for_status(response)

        body = self._parse_json_body(response)
        raw_text = self._extract_content(body)
        usage = self._extract_usage(body)
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
    def _extract_usage(body: dict) -> UsageMetadata:
        try:
            usage = body["usage"]
            return UsageMetadata(
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
            )
        except (KeyError, TypeError) as exc:
            raise ProviderInvalidResponseError(
                f"Provider response did not contain usage metadata: {exc}"
            ) from exc