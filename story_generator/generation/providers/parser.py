"""
Parses a provider's raw structured-output text into a canonical
GenerationResult.

All providers are prompted to emit a single JSON object of the shape
{"title": "<Chinese title>", "body": "<Chinese story body>"}, plus an
optional "glossary" (story-v2+), "translation" (story-v6+) and
"questions" (story-v7+, with "evidence" from story-v9). This
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

    return GenerationResult(
        title=title,
        body=body,
        usage=usage,
        glossary=_parse_glossary(data.get("glossary")),
        translation=_parse_translation(data.get("translation")),
        questions=_parse_questions(data.get("questions"), body),
    )


# Stripped from both ends of a question's evidence before looking for it in
# the body: a model quoting a sentence often adds or drops its quotation
# marks or final punctuation.
_EVIDENCE_EDGES = "\"'“”‘’「」『』。！？!?.，,；;：:、"
_WHITESPACE = re.compile(r"\s+")


def _evidence_in_body(evidence: str, body: str) -> bool:
    """Whether evidence was copied from body, ignoring whitespace and the
    punctuation or quotation marks at its ends."""
    quote = _WHITESPACE.sub("", evidence).strip(_EVIDENCE_EDGES)
    return bool(quote) and quote in _WHITESPACE.sub("", body)


def _parse_questions(value, body: str) -> list[dict] | None:
    """Best-effort, like the translation, but per question: a malformed one
    is dropped and the rest kept, since each stands alone. A question needs
    non-blank text, at least two distinct non-blank options, and an integer
    answer that indexes one of them. None if no question survives.

    "evidence" (story-v9+), the sentence that settles the answer, may be
    left out, but a question that has one must have copied it from body:
    a quote the story doesn't contain means the model made up support for
    its answer, so the question is dropped."""
    if not isinstance(value, list):
        return None
    questions = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        question = entry.get("question")
        options = entry.get("options")
        answer = entry.get("answer")
        if not isinstance(question, str) or not question.strip():
            continue
        if not isinstance(options, list) or len(options) < 2:
            continue
        if not all(isinstance(option, str) and option.strip() for option in options):
            continue
        options = [option.strip() for option in options]
        if len(set(options)) != len(options):
            continue
        # bool is an int subclass; true/false isn't an index.
        if isinstance(answer, bool) or not isinstance(answer, int):
            continue
        if not 0 <= answer < len(options):
            continue
        parsed = {"question": question.strip(), "options": options, "answer": answer}
        # Present but null counts as missing support, not as no evidence.
        if "evidence" in entry:
            evidence = entry["evidence"]
            if not isinstance(evidence, str) or not _evidence_in_body(evidence, body):
                continue
            parsed["evidence"] = evidence.strip()
        questions.append(parsed)
    return questions or None


def _parse_translation(value) -> list[str] | None:
    """Best-effort, like the glossary: anything but a non-empty list of
    non-blank strings is dropped, never an error, so a bad translation
    can't fail an otherwise good story."""
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(entry, str) and entry.strip() for entry in value):
        return None
    return [entry.strip() for entry in value]


def _parse_glossary(value) -> list[dict]:
    """Best-effort: malformed glossary data is dropped, never an error."""
    if not isinstance(value, list):
        return []
    entries = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        writing = entry.get("writing")
        if not isinstance(writing, str) or not writing.strip():
            continue
        reading = entry.get("reading")
        definition = entry.get("definition_en")
        entries.append(
            {
                "writing": writing.strip(),
                "reading": reading.strip()[:100]
                if isinstance(reading, str) and reading.strip()
                else None,
                "definition_en": definition.strip()[:300]
                if isinstance(definition, str) and definition.strip()
                else None,
            }
        )
    return entries


def _parse_json(raw_text: str):
    try:
        return json.loads(raw_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProviderInvalidResponseError(
            f"Provider output was not valid JSON: {exc}"
        ) from exc


def _require_chinese_text(value, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderInvalidResponseError(
            f"Provider output '{field_name}' must be a non-empty string"
        )
    if not _CHINESE_CHARACTER_PATTERN.search(value):
        raise ProviderInvalidResponseError(
            f"Provider output '{field_name}' must contain Chinese characters"
        )
    return value
