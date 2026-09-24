"""
Versioned prompt builders for story generation.

Provider adapters call build_prompt(request) to get the prompt text
they send upstream. The version used is request.prompt_version —
stamped onto GenerationRequestInput (and persisted on
StoryGenerationRequest.prompt_version) at request-creation time, so a
stored request always regenerates the exact same prompt regardless of
what CURRENT_PROMPT_VERSION becomes later.

Never mutate an existing build_story_vN_prompt function's output
shape after it has shipped — add a new version and register it below
instead.
"""

from story_generator.generation.providers.types import GenerationRequestInput

CURRENT_PROMPT_VERSION = "story-v2"


def build_story_v1_prompt(request: GenerationRequestInput) -> str:
    vocab_lines = "\n".join(
        f"- {item['writing']} ({item['reading']}): {item['definition_en']}"
        for item in request.vocabulary_snapshot
    )
    topic_line = f"Topic: {request.topic}\n" if request.topic else ""

    return (
        "You are a Chinese language story writer. Write a short story in "
        f"Mandarin Chinese for an HSK level {request.target_hsk_level} learner.\n"
        f"{topic_line}"
        f"Target length: approximately {request.target_word_count} Chinese characters.\n"
        "You MUST naturally use every one of the following vocabulary words "
        "at least once, with meanings consistent with the definitions given:\n"
        f"{vocab_lines}\n\n"
        "Respond with a single JSON object of the exact shape "
        '{"title": "<Chinese title>", "body": "<Chinese story body>"} '
        "and nothing else — no markdown, no commentary, no code fences."
    )


def _v2_vocab_line(item: dict) -> str:
    line = f"- {item['writing']}"
    if item.get("reading"):
        line += f" ({item['reading']})"
    if item.get("definition_en"):
        line += f": {item['definition_en']}"
    return line


def build_story_v2_prompt(request: GenerationRequestInput) -> str:
    """Like v1, but tolerates vocabulary with no reading/definition (custom
    words) and asks the model to gloss those in the same response."""
    vocab_lines = "\n".join(_v2_vocab_line(item) for item in request.vocabulary_snapshot)
    topic_line = f"Topic: {request.topic}\n" if request.topic else ""
    unglossed = [
        item["writing"]
        for item in request.vocabulary_snapshot
        if not item.get("reading") or not item.get("definition_en")
    ]

    if unglossed:
        shape = (
            '{"title": "<Chinese title>", "body": "<Chinese story body>", '
            '"glossary": [{"writing": "<word>", "reading": "<pinyin>", '
            '"definition_en": "<short English definition>"}]}'
        )
        glossary_line = (
            "Also include a glossary entry for each of these words: "
            f"{', '.join(unglossed)}. The reading is lowercase pinyin with "
            'tone numbers and no spaces, e.g. "cai4dan1"; the definition is '
            "a short English gloss.\n\n"
        )
    else:
        shape = '{"title": "<Chinese title>", "body": "<Chinese story body>"}'
        glossary_line = "\n"

    return (
        "You are a Chinese language story writer. Write a short story in "
        f"Mandarin Chinese for an HSK level {request.target_hsk_level} learner.\n"
        f"{topic_line}"
        f"Target length: approximately {request.target_word_count} Chinese characters.\n"
        "You MUST naturally use every one of the following vocabulary words "
        "at least once. Where a definition is given, use the word with a "
        "meaning consistent with it; otherwise use the word's standard "
        "meaning:\n"
        f"{vocab_lines}\n"
        f"{glossary_line}"
        f"Respond with a single JSON object of the exact shape {shape} "
        "and nothing else — no markdown, no commentary, no code fences."
    )


PROMPT_BUILDERS = {
    "story-v1": build_story_v1_prompt,
    "story-v2": build_story_v2_prompt,
}


def build_prompt(request: GenerationRequestInput) -> str:
    try:
        builder = PROMPT_BUILDERS[request.prompt_version]
    except KeyError as exc:
        raise ValueError(f"Unknown prompt version: {request.prompt_version!r}") from exc
    return builder(request)
