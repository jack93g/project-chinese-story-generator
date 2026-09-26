"""
Runs the EVAL_FIXTURES matrix against one or more providers and
produces a report recording, per (fixture, provider) pair: schema
validity, target-word coverage, length, latency, and manual quality
notes.

Manual quality notes workflow: to_json()'s output is the persisted
source of truth for review notes, not the markdown. After running a
comparison, a human edits `manual_quality_notes` directly in the
written JSON file (one string field per outcome), then regenerates
the markdown from that edited JSON via load_outcomes() + to_markdown()
— see cli/provider_comparison.py's `render` subcommand. The markdown
is always a rendering of whatever is in the JSON; editing the markdown
by hand does not persist anything and will be overwritten on the next
render.

Deliberately standalone: no database, no persistence.* imports beyond
the thresholds and length_ratio() reused from generation.validation.
This harness is meant to be run offline/locally before a provider or
model is ever wired into the live pipeline.
"""

import dataclasses
import itertools
import json
from pathlib import Path

from story_generator.eval.fixtures import EvalFixture
from story_generator.generation.providers.base import StoryGenerationProvider
from story_generator.generation.providers.errors import ProviderError
from story_generator.generation.providers.types import (
    GenerationRequestInput,
    GenerationResult,
)
from story_generator.generation.validation import (
    MIN_LENGTH_RATIO,
    VOCABULARY_COVERAGE_THRESHOLD,
    length_ratio,
    split_paragraphs,
    stray_english,
    word_appears,
)


@dataclasses.dataclass(frozen=True)
class ProviderSpec:
    """
    One provider configuration to include in the comparison run.

    base_url is required (not inferred from the provider instance)
    because it's part of the approval key in
    generation.providers.provider_registry — the report needs to
    record the exact endpoint tested so whoever adds the registry
    entry copies the right value.
    """

    label: str
    provider: StoryGenerationProvider
    model: str
    base_url: str


@dataclasses.dataclass
class EvalOutcome:
    fixture_name: str
    category: str
    provider_label: str
    model: str
    base_url: str
    schema_valid: bool
    error_code: str | None
    error_message: str | None
    requested_vocabulary_count: int | None
    used_vocabulary_count: int | None
    coverage: float | None
    meets_coverage_threshold: bool | None
    missing_vocabulary: list[dict]
    target_word_count: int
    actual_character_count: int | None
    length_ratio: float | None
    latency_ms: int | None
    title: str | None
    body: str | None
    manual_quality_notes: str = ""
    # Defaulted so reports written before these fields existed still load.
    prompt_version: str | None = None
    meets_length_threshold: bool | None = None
    # 1-based; >1 only when a run repeats each fixture (--repeat).
    sample: int = 1
    # story-v6+: the English per paragraph, and whether it has one entry
    # per paragraph of body (None when the model gave no translation).
    translation: list[str] | None = None
    translation_aligned: bool | None = None
    # story-v7+: the comprehension questions as the model wrote them (answer
    # keys unshuffled, so a model that always puts the answer first shows).
    questions: list[dict] | None = None
    # English words left in the Chinese text (see validation.stray_english).
    stray_english: list[str] = dataclasses.field(default_factory=list)


def compute_coverage(vocabulary_snapshot: list[dict], result: GenerationResult) -> dict:
    """
    Mirrors the coverage math in
    story_generator.generation.validation.validate_story(), sharing its
    word_appears() matcher. validate_story() itself takes a
    StoryGenerationRequest ORM instance, which this harness
    intentionally avoids depending on (no DB needed to run an eval).
    """
    combined_text = f"{result.title}\n{result.body}"
    missing = []
    for item in vocabulary_snapshot:
        if not word_appears(item["writing"], combined_text):
            missing.append({"id": item["id"], "writing": item["writing"]})

    requested = len(vocabulary_snapshot)
    used = requested - len(missing)
    coverage = used / requested if requested else 1.0

    return {
        "requested_vocabulary_count": requested,
        "used_vocabulary_count": used,
        "missing_vocabulary": missing,
        "coverage": coverage,
    }


def run_single(fixture: EvalFixture, provider_spec: ProviderSpec) -> EvalOutcome:
    request = GenerationRequestInput(
        target_hsk_level=fixture.target_hsk_level,
        target_word_count=fixture.target_word_count,
        target_vocabulary_count=fixture.target_vocabulary_count,
        vocabulary_snapshot=fixture.vocabulary_snapshot,
        prompt_version=fixture.prompt_version,
        topic=fixture.topic,
    )

    try:
        result = provider_spec.provider.generate(request)
    except ProviderError as exc:
        return EvalOutcome(
            fixture_name=fixture.name,
            category=fixture.category,
            provider_label=provider_spec.label,
            model=provider_spec.model,
            base_url=provider_spec.base_url,
            schema_valid=False,
            error_code=type(exc).__name__,
            error_message=str(exc),
            requested_vocabulary_count=len(fixture.vocabulary_snapshot),
            used_vocabulary_count=None,
            coverage=None,
            meets_coverage_threshold=None,
            missing_vocabulary=[],
            target_word_count=fixture.target_word_count,
            actual_character_count=None,
            length_ratio=None,
            latency_ms=None,
            title=None,
            body=None,
            prompt_version=fixture.prompt_version,
        )

    coverage_info = compute_coverage(fixture.vocabulary_snapshot, result)
    ratio = length_ratio(result.body, fixture.target_word_count)

    return EvalOutcome(
        fixture_name=fixture.name,
        category=fixture.category,
        provider_label=provider_spec.label,
        model=provider_spec.model,
        base_url=provider_spec.base_url,
        schema_valid=True,
        error_code=None,
        error_message=None,
        requested_vocabulary_count=coverage_info["requested_vocabulary_count"],
        used_vocabulary_count=coverage_info["used_vocabulary_count"],
        coverage=coverage_info["coverage"],
        meets_coverage_threshold=coverage_info["coverage"]
        >= VOCABULARY_COVERAGE_THRESHOLD,
        missing_vocabulary=coverage_info["missing_vocabulary"],
        target_word_count=fixture.target_word_count,
        actual_character_count=len(result.body),
        length_ratio=ratio,
        latency_ms=result.usage.latency_ms,
        title=result.title,
        body=result.body,
        prompt_version=fixture.prompt_version,
        meets_length_threshold=ratio >= MIN_LENGTH_RATIO,
        translation=result.translation,
        translation_aligned=None
        if result.translation is None
        else len(result.translation) == len(split_paragraphs(result.body)),
        questions=result.questions,
        stray_english=stray_english(result),
    )


def run_comparison(
    fixtures: list[EvalFixture],
    provider_specs: list[ProviderSpec],
    repeat: int = 1,
) -> list[EvalOutcome]:
    """Every fixture against every provider, `repeat` times each: a single
    sample is too noisy to judge a prompt change on quality."""
    outcomes = []
    for fixture, provider_spec in itertools.product(fixtures, provider_specs):
        for sample in range(1, repeat + 1):
            outcome = run_single(fixture, provider_spec)
            outcome.sample = sample
            outcomes.append(outcome)
    return outcomes


def _fixture_label(outcome: EvalOutcome, repeated: bool) -> str:
    return (
        f"{outcome.fixture_name} #{outcome.sample}"
        if repeated
        else outcome.fixture_name
    )


def to_json(outcomes: list[EvalOutcome]) -> str:
    return json.dumps(
        [dataclasses.asdict(o) for o in outcomes], indent=2, ensure_ascii=False
    )


def load_outcomes(path: str | Path) -> list[EvalOutcome]:
    """
    Load outcomes previously written by to_json() — including any
    manual_quality_notes a human has since edited directly into that
    JSON file. This is the read side of the review-notes persistence
    workflow described in this module's docstring: the JSON file is
    the source of truth, and to_markdown(load_outcomes(path)) is how
    a reviewed report gets (re-)rendered with those notes included.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalOutcome(**item) for item in data]


def _markdown_table_cell(text: str) -> str:
    """Escape a string for safe use inside a single Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", "<br>")


def to_markdown(outcomes: list[EvalOutcome]) -> str:
    lines = [
        "# Provider comparison report",
        "",
        "Automated columns (schema validity, coverage, length, latency) are filled "
        "in by the script. **Manual quality notes are not** — read each transcript "
        "below and fill that column in by hand before treating a provider/model as "
        "usable. Coverage alone can look perfect on an ambiguous-word fixture while "
        "the model still used the wrong sense of a heteronym.",
        "",
        "**To persist notes:** edit `manual_quality_notes` directly in the sibling "
        "`.json` report (not this file — this file is only ever a rendering of the "
        "JSON and gets overwritten). Then regenerate this markdown with "
        "`python -m story_generator.cli.provider_comparison render --input <path-to-json>`.",
        "",
        "## Summary",
        "",
        f"Length is flagged when the body is under {MIN_LENGTH_RATIO:.0%} of the "
        "target. It doesn't fail a generation in production, but a model that is "
        "routinely short needs a prompt fix before it's approved.",
        "",
        "Translation (story-v6+) shows English entries/paragraphs; ❌ means they "
        "don't line up, so the reader shows the English as one block.",
        "",
        "Questions (story-v7+) counts the well-formed comprehension questions; "
        "check each answer key against the story in the transcripts below. "
        "From story-v9, a question whose evidence isn't a sentence of the story "
        "is dropped, so a count below the one asked for can mean made-up "
        "evidence.",
        "",
        "English lists English words left in the Chinese text (title, body, "
        "questions); abbreviations like CEO don't count.",
        "",
        "| Fixture | Category | Provider | Model | Base URL | Prompt | Schema valid | Coverage | Meets threshold | Chars (actual/target) | Meets length | Translation | Questions | English | Latency (ms) | Error | Manual quality notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    repeated = any(o.sample > 1 for o in outcomes)
    for o in outcomes:
        coverage_str = f"{o.coverage:.0%}" if o.coverage is not None else "—"
        meets_str = (
            "✅"
            if o.meets_coverage_threshold
            else ("❌" if o.meets_coverage_threshold is not None else "—")
        )
        chars_str = (
            f"{o.actual_character_count}/{o.target_word_count} ({o.length_ratio:.0%})"
            if o.actual_character_count is not None
            else f"—/{o.target_word_count}"
        )
        length_str = (
            "—"
            if o.meets_length_threshold is None
            else ("✅" if o.meets_length_threshold else "❌")
        )
        translation_str = (
            "—"
            if o.translation is None
            else f"{len(o.translation)}/{len(split_paragraphs(o.body or ''))} "
            f"{'✅' if o.translation_aligned else '❌'}"
        )
        questions_str = "—" if o.questions is None else str(len(o.questions))
        english_str = ", ".join(o.stray_english) or "—"
        latency_str = str(o.latency_ms) if o.latency_ms is not None else "—"
        error_str = o.error_code or "—"
        notes_str = (
            _markdown_table_cell(o.manual_quality_notes)
            if o.manual_quality_notes
            else "_(fill in)_"
        )
        lines.append(
            f"| {_fixture_label(o, repeated)} | {o.category} | {o.provider_label} | {o.model} | `{o.base_url}` | "
            f"{o.prompt_version or '—'} | "
            f"{'✅' if o.schema_valid else '❌'} | {coverage_str} | {meets_str} | "
            f"{chars_str} | {length_str} | {translation_str} | {questions_str} | "
            f"{english_str} | "
            f"{latency_str} | "
            f"{error_str} | {notes_str} |"
        )

    lines += [
        "",
        "## Approval snippet",
        "",
        "Once reviewed, the registry key for each provider/model/endpoint tested "
        "here (for pasting into `provider_registry.py`):",
        "",
    ]
    seen = set()
    for o in outcomes:
        key = (o.provider_label, o.model, o.base_url)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f'- `("{o.provider_label}", "{o.model}", "{o.base_url}")`')
    lines.append("")

    lines += ["## Transcripts", ""]
    for o in outcomes:
        lines.append(
            f"### {_fixture_label(o, repeated)} — {o.provider_label} "
            f"({o.model} @ {o.base_url})"
        )
        lines.append("")
        if not o.schema_valid:
            lines.append(f"**Failed:** `{o.error_code}` — {o.error_message}")
            lines.append("")
            continue
        if o.missing_vocabulary:
            missing_words = ", ".join(item["writing"] for item in o.missing_vocabulary)
            lines.append(f"**Missing vocabulary:** {missing_words}")
            lines.append("")
        lines.append(f"**Title:** {o.title}")
        lines.append("")
        lines.append(f"**Body:**\n\n{o.body}")
        lines.append("")
        if o.translation is not None:
            translation = "\n\n".join(o.translation)
            lines.append(f"**Translation:**\n\n{translation}")
            lines.append("")
        if o.questions is not None:
            lines.append("**Questions** (✅ marks the answer key):")
            lines.append("")
            for number, question in enumerate(o.questions, 1):
                lines.append(f"{number}. {question['question']}")
                for index, option in enumerate(question["options"]):
                    mark = " ✅" if index == question["answer"] else ""
                    lines.append(f"    - {option}{mark}")
                if question.get("evidence"):
                    lines.append(f"    - _Evidence:_ {question['evidence']}")
            lines.append("")
        if o.manual_quality_notes:
            lines.append(f"**Manual quality notes:** {o.manual_quality_notes}")
        else:
            lines.append(
                "**Manual quality notes:** _(fill in — correct sense of any "
                "ambiguous words? natural phrasing? does it read like it was "
                "written for the target HSK level?)_"
            )
        lines.append("")

    return "\n".join(lines)
