"""
Parses a provider's raw structured-output text into a canonical
GenerationResult.

All providers are prompted to emit a single JSON object of the shape
{"title": "<Chinese title>", "body": "<Chinese story body>"}. This
module is the single place that turns that raw text (plus
out-of-band usage metadata from the API response) into the canonical
GenerationResult type — every provider adapter should route its
output through parse_structured_result rather than building
GenerationResult by hand, so "what counts as valid model output" is
defined once.
"""

import json
import re

from story_generator.generation.providers.errors import ProviderInvalidResponseError
from story_generator.generation.providers.types import GenerationResult, UsageMetadata

_REQUIRED_FIELDS = ("title", "body")

# Matches any CJK Unified Ideographs codepoint. Used as a cheap sanity
# check that the model actually produced Chinese content rather than,
# e.g., an empty string, an apology in English, or placeholder text.
_CHINESE_CHARACTER_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def parse_structured_result(raw_text: str, usage: UsageMetadata) -> GenerationResult:
    """
    Parse a provider's raw text output into a GenerationResult.

    Raises ProviderInvalidResponseError for any of:
      - raw_text is not valid JSON
      - the parsed JSON is not an object
      - "title" or "body" is missing
      - "title" or "body" is not a non-empty string
      - "title" or "body" contains no Chinese characters
    """
    data = _parse_json(raw_text)

    if not isinstance(data, dict):
        raise ProviderInvalidResponseError(
            f"Provider output must be a JSON object, got {type(data).__name__}"
        )

    missing = [name for name in _REQUIRED_FIELDS if name not in data]
    if missing:
        raise ProviderInvalidResponseError(
            f"Provider output missing required field(s): {', '.join(missing)}"
        )

    title = _require_chinese_text(data["title"], field_name="title")
    body = _require_chinese_text(data["body"], field_name="body")

    return GenerationResult(title=title, body=body, usage=usage)


def _parse_json(raw_text: str):
    try:
        return json.loads(raw_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProviderInvalidResponseError(f"Provider output was not valid JSON: {exc}") from exc


def _require_chinese_text(value, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderInvalidResponseError(f"Provider output '{field_name}' must be a non-empty string")
    if not _CHINESE_CHARACTER_PATTERN.search(value):
        raise ProviderInvalidResponseError(
            f"Provider output '{field_name}' must contain Chinese characters"
        )
    return value