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

CURRENT_PROMPT_VERSION = "story-v1"


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


PROMPT_BUILDERS = {
    "story-v1": build_story_v1_prompt,
}


def build_prompt(request: GenerationRequestInput) -> str:
    try:
        builder = PROMPT_BUILDERS[request.prompt_version]
    except KeyError as exc:
        raise ValueError(f"Unknown prompt version: {request.prompt_version!r}") from exc
    return builder(request)
