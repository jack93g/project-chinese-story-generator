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

# story-v6 is v3 plus an English translation. On Kimi K2 it matched v3 on
# coverage and length, and every translation lined up with its paragraphs;
# it takes about twice as long (~11s vs ~5s) for ~2.4x the output tokens
# (2026-09-25T14* reports). story-v4/v5 are registered for evaluation but
# not current: across 5 samples each on the dense_vocabulary fixture,
# neither was clearly better than v3 (2026-09-24T18* reports). story-v7 is
# v6 plus comprehension questions. Over 3 samples of every fixture on Kimi
# K2 it matched v6 on coverage, length and translation alignment, taking
# ~12s (slowest 33s), and 78 of its 84 questions had a clear answer the
# story settles; the other 6 were weak, mostly "why" questions the story
# doesn't answer, but none had a wrong key (2026-09-25T181959Z report). It
# put the answer second 49 times of 84, hence the worker's shuffle.
# story-v8 (v7 with rules against those weak questions) halved them to 3
# of 81 with no cost to the stories (2026-09-26T034648Z report). story-v9
# (v8 plus a quoted sentence as evidence for each answer) matched v8 within
# noise: 5 weak questions of 80, as the model always found a real sentence
# to quote, but most quotes do settle their answer, which helps the reader
# (2026-09-26T060123Z report). story-v10 is v9 written only in Chinese, as
# v7 and v9 each left an English word in a story. It had no stray English
# and 1 weak question of 79 (plus 2 borderline), and matched v9 on
# coverage, translation alignment and speed (~12s), but 3 of 23 stories came
# back under 80% of their length against v9's 1: possibly the model
# juggling a prompt now ~550 words long, possibly chance
# (2026-09-26T073113Z report). If real stories keep coming back short, try
# a consolidated rewrite of the questions section, which has grown by
# patching (v7 asks "why" questions, v8 limits them).
CURRENT_PROMPT_VERSION = "story-v10"


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
    request: GenerationRequestInput, body_placeholder: str, extra_fields: str = ""
) -> tuple[str, str]:
    """(JSON response shape, glossary instruction line) for v2+: asks for a
    glossary entry for each custom word with no reading/definition.
    extra_fields (e.g. ', "translation": [...]') goes right after the body."""
    unglossed = [
        item["writing"]
        for item in request.vocabulary_snapshot
        if not item.get("reading") or not item.get("definition_en")
    ]

    if not unglossed:
        shape = (
            f'{{"title": "<Chinese title>", "body": "{body_placeholder}"'
            f"{extra_fields}}}"
        )
        return shape, "\n"

    shape = (
        f'{{"title": "<Chinese title>", "body": "{body_placeholder}"'
        f'{extra_fields}, "glossary": '
        '[{"writing": "<word>", "reading": "<pinyin>", '
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


# v5's addition to v4. On the dense_vocabulary fixture, v4 set the story
# in 1989 for 监狱/反抗/暴力, then showed a meme (表情包) on a phone: the
# randomly chosen words pulled toward different eras.
V5_SETTING_GUIDANCE = (
    "Choose a setting where every word fits naturally, usually the present "
    "day. If some words belong to different eras or worlds (for example "
    "internet slang alongside historical terms), pick a present-day setting "
    "that can hold them all, such as characters talking about or remembering "
    "the past, rather than putting modern things in the past.\n\n"
)


def build_story_v5_prompt(request: GenerationRequestInput) -> str:
    """Like v4, with V5_SETTING_GUIDANCE first: pick a setting, usually the
    present day, where all the words fit."""
    return _length_band_prompt(
        request, craft_guidance=V5_SETTING_GUIDANCE + V4_CRAFT_GUIDANCE
    )


# v6's addition to v3: an English translation, one entry per paragraph, so
# the reader can show each paragraph's English under it.
V6_TRANSLATION_GUIDANCE = (
    "Translation: also translate the body into natural, faithful English "
    'for the learner to check their reading, as the "translation" list: '
    "one English string per paragraph of the body, in the same order, so "
    "it has exactly as many entries as the body has paragraphs. Never break "
    "a line inside a paragraph. Only the body counts towards its length, "
    "not the translation.\n\n"
)


def build_story_v6_prompt(request: GenerationRequestInput) -> str:
    """Like v3, plus an English translation per paragraph
    (V6_TRANSLATION_GUIDANCE after the length section, and a "translation"
    field in the JSON shape)."""
    return _length_band_prompt(request, translation=True)


# v7's addition to v6: multiple-choice comprehension questions, one per
# planned paragraph but at least V7_MIN_QUESTIONS and at most V7_MAX_QUESTIONS.
V7_MIN_QUESTIONS = 3
V7_MAX_QUESTIONS = 5


def _v7_questions_guidance(question_count: int, rules: str = "") -> str:
    """rules (story-v8+) goes right after "The story alone must settle every
    answer." With none, this is v7's guidance exactly."""
    return (
        f"Questions: also write {question_count} multiple-choice questions "
        'that check the learner understood the story, as the "questions" '
        "list. Write each question and its options in Chinese at the same "
        "HSK level as the story. Each question has exactly 4 options: one "
        "that the story shows is correct, and three that are plausible but "
        'wrong according to the story. "answer" is the index (0 to 3) of '
        "the correct option. Ask about what happens and why (events, and "
        "what characters do and why) rather than details a reader could "
        "guess without reading the story, and make at least one question "
        "depend on understanding one of the vocabulary words above. The "
        f"story alone must settle every answer. {rules}The questions don't "
        "count towards the story's length.\n\n"
    )


def build_story_v7_prompt(request: GenerationRequestInput) -> str:
    """Like v6, plus multiple-choice comprehension questions (the questions
    guidance after the translation guidance, and a "questions" field after
    "translation" in the JSON shape)."""
    return _length_band_prompt(request, translation=True, questions=True)


# v8's addition to v7. In the 2026-09-25T181959Z report, 6 of v7's 84
# questions were weak: mostly "why" questions the story never answers (a
# family booked flights three months early "because Dad likes to plan",
# which the story doesn't say), plus wrong options that were partly true
# (a manager "enjoying the city view" when he was looking at it while
# thinking) and one "the story doesn't say" answer.
V8_QUESTION_RULES = (
    "So only ask why something happened if the story says why. Each "
    "correct option must be something the story states or plainly shows, "
    "not a guess about motives or feelings. Each wrong option must be "
    "clearly false according to the story, never partly true; don't use "
    'options like "the story doesn\'t say". '
)


def build_story_v8_prompt(request: GenerationRequestInput) -> str:
    """Like v7, with V8_QUESTION_RULES in the questions guidance: answers
    the story actually states, and wrong options that are clearly wrong."""
    return _length_band_prompt(
        request, translation=True, questions=True, question_rules=V8_QUESTION_RULES
    )


# v9's addition to v8: each question quotes the sentence that settles its
# answer. Writing it makes the model check the story really answers the
# question; the parser drops a question whose quote isn't in the body; and
# the reader shows the quote once the quiz is marked. The 3 weak questions
# left in v8's 2026-09-26T034648Z report were an unstated reason, an
# inferred purpose, and a wait the story gave two figures for.
V9_EVIDENCE_RULE = (
    'For each question, also give "evidence": the one sentence of the '
    "story body that settles the answer, copied exactly, character for "
    "character. If no single sentence settles it, ask a different "
    "question. "
)


def build_story_v9_prompt(request: GenerationRequestInput) -> str:
    """Like v8, plus V9_EVIDENCE_RULE and an "evidence" field on each
    question in the JSON shape."""
    return _length_band_prompt(
        request,
        translation=True,
        questions=True,
        question_rules=V8_QUESTION_RULES + V9_EVIDENCE_RULE,
        evidence=True,
    )


# v10's addition to v9, after the length section. v7 and v9 each left an
# English word in a story ("hurriedly", "walking"), apparently where the
# model reached for a word it didn't produce in Chinese.
V10_CHINESE_ONLY_RULE = (
    "Language: write the title, the body, and the questions and their "
    "options only in Chinese. Never switch to an English word, even where "
    "you can't think of the Chinese one; rephrase instead. Abbreviations "
    "Chinese writers use as they are, such as CEO or AI, are fine. Only "
    "the translation is in English.\n\n"
)


def build_story_v10_prompt(request: GenerationRequestInput) -> str:
    """Like v9, plus V10_CHINESE_ONLY_RULE between the length section and
    the translation guidance."""
    return _length_band_prompt(
        request,
        translation=True,
        questions=True,
        question_rules=V8_QUESTION_RULES + V9_EVIDENCE_RULE,
        evidence=True,
        language_rule=V10_CHINESE_ONLY_RULE,
    )


def _question_count(paragraphs: int) -> int:
    return min(V7_MAX_QUESTIONS, max(V7_MIN_QUESTIONS, paragraphs))


def _questions_field(evidence: bool) -> str:
    """v7's "questions" JSON field; v9+ adds "evidence" to each question."""
    evidence_field = (
        ', "evidence": "<sentence copied exactly from the body>"' if evidence else ""
    )
    return (
        ', "questions": [{"question": "<question in Chinese>", "options": '
        '["<option>", "<option>", "<option>", "<option>"], '
        f'"answer": <index of the correct option, 0-3>{evidence_field}}}]'
    )


def _translation_field(paragraphs: int) -> str:
    """v6's "translation" JSON field, with one example entry per planned
    paragraph (so a one-paragraph story isn't shown two)."""
    if paragraphs == 1:
        entries = '"<English translation of the paragraph>"'
    else:
        entries = ", ".join(
            f'"<English translation of paragraph {n}>"'
            for n in range(1, paragraphs + 1)
        )
    return f', "translation": [{entries}]'


def _length_band_prompt(
    request: GenerationRequestInput,
    craft_guidance: str = "",
    translation: bool = False,
    questions: bool = False,
    question_rules: str = "",
    evidence: bool = False,
    language_rule: str = "",
) -> str:
    """The v3 prompt; later versions add craft_guidance before the length
    section, or translation and questions requests after it. With none of
    them, this must keep producing v3 exactly."""
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
    extra_fields = _translation_field(paragraphs) if translation else ""
    if questions:
        extra_fields += _questions_field(evidence)
    shape, glossary_line = _glossary_parts(
        request,
        f"<Chinese story body, {min_chars}-{max_chars} characters>",
        extra_fields,
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
        f"{language_rule}"
        f"{V6_TRANSLATION_GUIDANCE if translation else ''}"
        f"{_v7_questions_guidance(_question_count(paragraphs), question_rules) if questions else ''}"
        f"Respond with a single JSON object of the exact shape {shape} "
        "and nothing else — no markdown, no commentary, no code fences."
    )


PROMPT_BUILDERS = {
    "story-v1": build_story_v1_prompt,
    "story-v2": build_story_v2_prompt,
    "story-v3": build_story_v3_prompt,
    "story-v4": build_story_v4_prompt,
    "story-v5": build_story_v5_prompt,
    "story-v6": build_story_v6_prompt,
    "story-v7": build_story_v7_prompt,
    "story-v8": build_story_v8_prompt,
    "story-v9": build_story_v9_prompt,
    "story-v10": build_story_v10_prompt,
}


def build_prompt(request: GenerationRequestInput) -> str:
    try:
        builder = PROMPT_BUILDERS[request.prompt_version]
    except KeyError as exc:
        raise ValueError(f"Unknown prompt version: {request.prompt_version!r}") from exc
    return builder(request)
