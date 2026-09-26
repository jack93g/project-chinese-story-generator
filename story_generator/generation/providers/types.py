from dataclasses import dataclass, field


@dataclass(frozen=True)
class GenerationRequestInput:
    """
    Provider-neutral input for a single story-generation call.

    Deliberately mirrors the subset of StoryGenerationRequest fields a
    provider needs to build a prompt (target_hsk_level, topic,
    target_word_count, target_vocabulary_count, the vocabulary
    snapshot, prompt_version, model_parameters). Providers receive this
    plain dataclass rather than the ORM model itself, so provider
    adapters stay decoupled from the persistence layer and are
    trivially testable without a database.

    vocabulary_snapshot mirrors the shape of
    StoryGenerationRequest.selected_vocabulary_snapshot, e.g.
    [{"id": 10, "writing": "菜单", "reading": "càidān",
      "definition_en": "menu"}].
    """

    target_hsk_level: int
    target_word_count: int
    target_vocabulary_count: int
    vocabulary_snapshot: list[dict]
    prompt_version: str
    topic: str | None = None
    model_parameters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class UsageMetadata:
    """Token accounting for a single provider call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int | None = None


@dataclass(frozen=True)
class GenerationResult:
    """
    Canonical provider output, independent of which provider produced it.

    title/body are the generated Chinese story content. usage carries
    token accounting for cost/observability.

    This is the only shape story_generator.generation.service (and
    anything downstream of it) should depend on. No provider-specific
    response object should ever escape a provider adapter — adapters
    are responsible for translating their SDK's response into this
    type via the shared parser in providers.parser.
    """

    title: str
    body: str
    usage: UsageMetadata
    # Optional model-supplied glosses [{"writing", "reading", "definition_en"}]
    # for requested words that had none; best-effort, never required.
    glossary: list[dict] = field(default_factory=list)
    # Optional English translation, one string per paragraph of body
    # (story-v6+); best-effort, None when absent or malformed.
    translation: list[str] | None = None
    # Optional multiple-choice comprehension questions (story-v7+):
    # [{"question": str, "options": [str, ...], "answer": int}], answer
    # being the index of the correct option, plus "evidence" (story-v9+):
    # the sentence of body that settles the answer. Best-effort, None when
    # absent or when none of them is well-formed.
    questions: list[dict] | None = None
