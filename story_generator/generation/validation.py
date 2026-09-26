"""
Post-generation validation: checks whether the generated story
actually used the vocabulary it was asked to use, and records a
summary for StoryGenerationRequest.validation_report.

Deliberately simple — matching on the raw Chinese text, not real
word-segmentation/tokenization. Good enough to flag gross mismatches (a
requested word never appearing at all) and cheap to compute; swap in
real segmentation later if false negatives (e.g. compound-word boundary
issues) turn out to matter in practice.

Skritter entries aren't always plain words. Some have spaces, either as
word breaks ("口语 能力", written 口语能力 in a story) or as gaps ("一旦
就", as in 一旦下雨就); some are grammar patterns ("虽然 ... 但是...");
some end in punctuation ("你在吗？"). So word_appears() splits an entry
on spaces and ellipses, drops trailing punctuation, and looks for the
parts in order within one sentence. That can accept a stray match for
a spaced entry, which is the cheaper mistake: a false miss can fail a
good story on coverage.

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

import re

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.providers.types import GenerationResult

# TODO: placeholder until product specifies the real tolerance.
# 0.8 means: at least 80% of requested vocabulary must appear in the
# generated text for the story to be considered acceptable.
VOCABULARY_COVERAGE_THRESHOLD = 0.8

# Recorded, not enforced (see module docstring): a body shorter than this
# fraction of target_word_count is flagged meets_length_threshold=False.
MIN_LENGTH_RATIO = 0.8


# Spaces and ellipses (..., …, 。。。) separate the parts of an entry.
_PART_SEPARATOR = re.compile(r"\s+|\.{2,}|…+|。{2,}")
_TRAILING_PUNCTUATION = "。！？!?，,"
# Parts may be separated by anything short of the end of a sentence.
_GAP = "[^。！？!?\n]*?"


def word_appears(writing: str, text: str) -> bool:
    """Whether a vocabulary entry appears in text (see module docstring)."""
    parts = _PART_SEPARATOR.split(writing.strip().rstrip(_TRAILING_PUNCTUATION))
    pattern = _GAP.join(re.escape(part) for part in parts if part)
    return re.search(pattern, text) is not None


# A run of Latin letters with a lowercase letter in it: an English word
# left in the Chinese text (Kimi K2 wrote "hurriedly" and "walking" in 2 of
# ~70 evaluation stories), as opposed to an abbreviation Chinese writers
# use as it is ("CEO", "AI").
_ENGLISH_WORD = re.compile(r"[A-Za-z]*[a-z][A-Za-z]*")


def stray_english(result: GenerationResult) -> list[str]:
    """English words in the text meant to be Chinese: the title, body, and
    questions and their options (not the translation, which is English).
    Each word once, in order of appearance."""
    texts = [result.title, result.body]
    for question in result.questions or []:
        texts += [question["question"], *question["options"]]
    words = [word for text in texts for word in _ENGLISH_WORD.findall(text)]
    return list(dict.fromkeys(words))


def split_paragraphs(body: str) -> list[str]:
    """A story body's paragraphs: its non-blank lines. story-v3+ asks for
    blank lines between paragraphs, but a single line break also separates
    them. The reader (frontend/lib/paragraphs.ts) must split the same way,
    as it pairs paragraph i with translation entry i."""
    return [line.strip() for line in body.split("\n") if line.strip()]


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
    # Newline-separated so a pattern can't match across title and body.
    combined_text = f"{result.title}\n{result.body}"

    used_map: dict[int, bool] = {}
    missing_vocabulary = []
    for item in request.selected_vocabulary_snapshot:
        is_used = word_appears(item["writing"], combined_text)
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
        # Recorded, not enforced: one stray word leaves the story readable,
        # and it's rare enough that the fix is the prompt (story-v10).
        "stray_english": stray_english(result),
    }
    # Recorded, not enforced, like length: the reader shows an English list
    # that doesn't line up with the paragraphs as one block instead.
    if result.translation is not None:
        report["translation_aligned"] = len(result.translation) == len(
            split_paragraphs(result.body)
        )
    # Also recorded only: a story with no usable questions is still readable.
    if result.questions is not None:
        report["question_count"] = len(result.questions)
    return report, used_map
