"""
Post-generation validation: checks whether the generated story
actually used the vocabulary it was asked to use, and records a
summary for StoryGenerationRequest.validation_report.

Deliberately simple — substring containment on the raw Chinese text,
not real word-segmentation/tokenization. Good enough to flag gross
mismatches (a requested word never appearing at all) and cheap to
compute; swap in real segmentation later if false negatives (e.g.
compound-word boundary issues) turn out to matter in practice.

Coverage is NOT required to be 100% — models occasionally drop one
requested word from an otherwise good story, and treating that as a
hard failure would waste a generation that's still usable. Instead,
a story is only rejected as insufficient when fewer than
VOCABULARY_COVERAGE_THRESHOLD of the requested words actually appear.

Length is recorded but NOT enforced. Retries are manual (the Retry
button, at most MAX_ATTEMPTS per request), so rejecting a short story
throws away a readable one and costs the learner a click and another
paid call — and a short story usually comes back short again, because
the shortfall is systematic to the prompt/model pairing rather than
random. The fix for short stories is the prompt (see story-v3);
meets_length_threshold is there so shortfalls stay visible in
validation_report and in the provider-comparison report.
"""

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.providers.types import GenerationResult

# TODO: placeholder until product specifies the real tolerance.
# 0.8 means: at least 80% of requested vocabulary must appear in the
# generated text for the story to be considered acceptable.
VOCABULARY_COVERAGE_THRESHOLD = 0.8

# Recorded, not enforced (see module docstring): a body shorter than this
# fraction of target_word_count is flagged meets_length_threshold=False.
MIN_LENGTH_RATIO = 0.8


def length_ratio(body: str, target_word_count: int) -> float:
    """Body length (characters, punctuation included) over the target."""
    return len(body) / target_word_count


def validate_story(
    request: StoryGenerationRequest, result: GenerationResult
) -> tuple[dict, dict[int, bool]]:
    """
    Returns (validation_report, used_map) where used_map maps each
    requested vocabulary item's id to whether it appeared in the
    generated text — used directly to set StoryVocabularyItem.used.

    validation_report["meets_coverage_threshold"] tells the caller
    whether this result is acceptable to persist as a successful
    story, or should be treated as a failed generation instead.
    """
    combined_text = f"{result.title}{result.body}"

    used_map: dict[int, bool] = {}
    missing_vocabulary = []
    for item in request.selected_vocabulary_snapshot:
        is_used = item["writing"] in combined_text
        used_map[item["id"]] = is_used
        if not is_used:
            missing_vocabulary.append({"id": item["id"], "writing": item["writing"]})

    requested_count = len(request.selected_vocabulary_snapshot)
    used_count = requested_count - len(missing_vocabulary)
    coverage = used_count / requested_count if requested_count else 1.0

    ratio = length_ratio(result.body, request.target_word_count)

    report = {
        "requested_vocabulary_count": requested_count,
        "used_vocabulary_count": used_count,
        "missing_vocabulary": missing_vocabulary,
        "target_word_count": request.target_word_count,
        "actual_character_count": len(result.body),
        "length_ratio": ratio,
        "length_threshold": MIN_LENGTH_RATIO,
        "meets_length_threshold": ratio >= MIN_LENGTH_RATIO,
        "coverage": coverage,
        "coverage_threshold": VOCABULARY_COVERAGE_THRESHOLD,
        "meets_coverage_threshold": coverage >= VOCABULARY_COVERAGE_THRESHOLD,
    }
    return report, used_map
