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

import math

from story_generator.generation.providers.types import GenerationRequestInput

CURRENT_PROMPT_VERSION = "story-v4"


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


def _glossary_parts(
    request: GenerationRequestInput, body_placeholder: str
) -> tuple[str, str]:
    """(JSON response shape, glossary instruction line) for v2+: asks for a
    glossary entry for each custom word with no reading/definition."""
    unglossed = [
        item["writing"]
        for item in request.vocabulary_snapshot
        if not item.get("reading") or not item.get("definition_en")
    ]

    if not unglossed:
        shape = f'{{"title": "<Chinese title>", "body": "{body_placeholder}"}}'
        return shape, "\n"

    shape = (
        f'{{"title": "<Chinese title>", "body": "{body_placeholder}", '
        '"glossary": [{"writing": "<word>", "reading": "<pinyin>", '
        '"definition_en": "<short English definition>"}]}'
    )
    glossary_line = (
        "Also include a glossary entry for each of these words: "
        f"{', '.join(unglossed)}. The reading is lowercase pinyin with "
        'tone numbers and no spaces, e.g. "cai4dan1"; the definition is '
        "a short English gloss.\n\n"
    )
    return shape, glossary_line


def build_story_v2_prompt(request: GenerationRequestInput) -> str:
    """Like v1, but tolerates vocabulary with no reading/definition (custom
    words) and asks the model to gloss those in the same response."""
    vocab_lines = "\n".join(
        _v2_vocab_line(item) for item in request.vocabulary_snapshot
    )
    topic_line = f"Topic: {request.topic}\n" if request.topic else ""
    shape, glossary_line = _glossary_parts(request, "<Chinese story body>")

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


# v3's accepted length band, as fractions of target_word_count.
V3_MIN_LENGTH_FRACTION = 0.9
V3_MAX_LENGTH_FRACTION = 1.2
# Roughly one paragraph per this many characters: a paragraph count is
# something a model can plan for, unlike a raw character count.
V3_CHARACTERS_PER_PARAGRAPH = 100


def build_story_v3_prompt(request: GenerationRequestInput) -> str:
    """Like v2, but with a firmer length instruction: models given only
    "approximately N characters" (v1/v2) came back well short — 50-84% of
    target on 5 of 7 eval fixtures for Kimi K2. v3 states a minimum and
    maximum, turns the target into a paragraph plan, repeats the band in
    the JSON shape, and asks for a developed story rather than a list of
    sentences."""
    return _length_band_prompt(request)


# v4's addition to v3. With many words (e.g. 20 in 350 characters), Kimi
# K2 bent the story to fit them: an East German who couldn't speak German
# well (to use 口语能力), "这种玩笑很难看" (难看 of a joke), and a closing
# line stringing words together ("…才是实践能力的意义").
V4_CRAFT_GUIDANCE = (
    "Keep the story plausible and consistent, both with itself and with "
    "real-world facts such as history, geography and who speaks which "
    "language. Never bend a character, place or event just to fit a word "
    "in. Use each word in a natural collocation, the way a native speaker "
    "would; if a word doesn't sit naturally in a sentence, write a "
    "different sentence or scene for it rather than forcing it. Work the "
    "words into events and dialogue, not into a closing summary or moral "
    "that strings them together.\n\n"
)


def build_story_v4_prompt(request: GenerationRequestInput) -> str:
    """Like v3, plus V4_CRAFT_GUIDANCE: keep the story consistent and use
    natural word pairings rather than forcing vocabulary in."""
    return _length_band_prompt(request, craft_guidance=V4_CRAFT_GUIDANCE)


def _length_band_prompt(
    request: GenerationRequestInput, craft_guidance: str = ""
) -> str:
    """The v3 prompt; later versions add craft_guidance before the length
    section. Empty craft_guidance must keep producing v3 exactly."""
    target = request.target_word_count
    min_chars = math.ceil(target * V3_MIN_LENGTH_FRACTION)
    max_chars = math.floor(target * V3_MAX_LENGTH_FRACTION)
    paragraphs = max(1, round(target / V3_CHARACTERS_PER_PARAGRAPH))
    per_paragraph = round(target / paragraphs)
    paragraph_plan = (
        f"one paragraph of about {per_paragraph} characters"
        if paragraphs == 1
        else f"{paragraphs} paragraphs of about {per_paragraph} characters each"
    )

    vocab_lines = "\n".join(
        _v2_vocab_line(item) for item in request.vocabulary_snapshot
    )
    topic_line = f"Topic: {request.topic}\n" if request.topic else ""
    shape, glossary_line = _glossary_parts(
        request, f"<Chinese story body, {min_chars}-{max_chars} characters>"
    )

    return (
        "You are a Chinese language story writer. Write a short story in "
        f"Mandarin Chinese for an HSK level {request.target_hsk_level} learner.\n"
        f"{topic_line}"
        "You MUST naturally use every one of the following vocabulary words "
        "at least once. Where a definition is given, use the word with a "
        "meaning consistent with it; otherwise use the word's standard "
        "meaning:\n"
        f"{vocab_lines}\n"
        f"{glossary_line}"
        f"{craft_guidance}"
        f"Length: the story body MUST be at least {min_chars} Chinese "
        f"characters long and at most {max_chars}; aim for about {target}. "
        "Punctuation counts. Plan it as "
        f"{paragraph_plan}, separated by blank lines. Reach the length by "
        "developing the story — a beginning, a middle and an end, with "
        "scenes, dialogue and detail — not with a list of unrelated "
        "sentences or repetition. Before answering, check the body is at "
        f"least {min_chars} characters; if it is shorter, keep writing.\n\n"
        f"Respond with a single JSON object of the exact shape {shape} "
        "and nothing else — no markdown, no commentary, no code fences."
    )


PROMPT_BUILDERS = {
    "story-v1": build_story_v1_prompt,
    "story-v2": build_story_v2_prompt,
    "story-v3": build_story_v3_prompt,
    "story-v4": build_story_v4_prompt,
}


def build_prompt(request: GenerationRequestInput) -> str:
    try:
        builder = PROMPT_BUILDERS[request.prompt_version]
    except KeyError as exc:
        raise ValueError(f"Unknown prompt version: {request.prompt_version!r}") from exc
    return builder(request)
