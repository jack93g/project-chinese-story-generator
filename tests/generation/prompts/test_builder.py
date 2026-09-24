from story_generator.generation.prompts.builder import (
    CURRENT_PROMPT_VERSION,
    build_prompt,
    build_story_v1_prompt,
    build_story_v3_prompt,
)
from story_generator.generation.providers.types import GenerationRequestInput


def _make_request(**overrides) -> GenerationRequestInput:
    defaults = dict(
        target_hsk_level=2,
        target_word_count=150,
        target_vocabulary_count=2,
        vocabulary_snapshot=[
            {
                "id": 1,
                "writing": "你好",
                "reading": "ni3 hao3",
                "definition_en": "hello",
            },
            {"id": 2, "writing": "菜单", "reading": "càidān", "definition_en": "menu"},
        ],
        prompt_version="story-v1",
        topic=None,
    )
    defaults.update(overrides)
    return GenerationRequestInput(**defaults)


def test_current_prompt_version_is_registered():
    request = _make_request(prompt_version=CURRENT_PROMPT_VERSION)

    # should not raise
    build_prompt(request)


def test_build_prompt_dispatches_to_correct_version():
    request = _make_request(prompt_version="story-v1")

    assert build_prompt(request) == build_story_v1_prompt(request)


def test_build_prompt_raises_on_unknown_version():
    request = _make_request(prompt_version="story-v99")

    try:
        build_prompt(request)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "story-v99" in str(exc)


def test_prompt_includes_every_required_vocabulary_item():
    request = _make_request()

    prompt = build_story_v1_prompt(request)

    for item in request.vocabulary_snapshot:
        assert item["writing"] in prompt
        assert item["reading"] in prompt
        assert item["definition_en"] in prompt


def test_prompt_includes_hsk_level_and_word_count():
    request = _make_request(target_hsk_level=4, target_word_count=300)

    prompt = build_story_v1_prompt(request)

    assert "HSK level 4" in prompt
    assert "300" in prompt


def test_prompt_omits_topic_line_when_topic_is_none():
    request = _make_request(topic=None)

    prompt = build_story_v1_prompt(request)

    assert "Topic:" not in prompt


def test_prompt_includes_topic_line_when_topic_is_set():
    request = _make_request(topic="a trip to Beijing")

    prompt = build_story_v1_prompt(request)

    assert "Topic: a trip to Beijing" in prompt


def test_prompt_requests_structured_json_output():
    request = _make_request()

    prompt = build_story_v1_prompt(request)

    assert '"title"' in prompt
    assert '"body"' in prompt


def test_current_prompt_version_is_v3():
    assert CURRENT_PROMPT_VERSION == "story-v3"


def test_v3_prompt_states_a_length_band_and_paragraph_plan():
    request = _make_request(prompt_version="story-v3", target_word_count=300)

    prompt = build_story_v3_prompt(request)

    assert "at least 270 Chinese characters long and at most 360" in prompt
    assert "aim for about 300" in prompt
    assert "3 paragraphs of about 100 characters each" in prompt
    # repeated in the JSON shape
    assert '"body": "<Chinese story body, 270-360 characters>"' in prompt


def test_v3_prompt_plans_one_paragraph_for_a_short_target():
    request = _make_request(prompt_version="story-v3", target_word_count=60)

    prompt = build_story_v3_prompt(request)

    assert "one paragraph of about 60 characters" in prompt


def test_v3_prompt_keeps_vocabulary_and_glossary_request():
    request = _make_request(
        prompt_version="story-v3",
        vocabulary_snapshot=[
            {
                "id": 1,
                "writing": "你好",
                "reading": "ni3 hao3",
                "definition_en": "hello",
            },
            {"id": 2, "writing": "饭馆", "reading": None, "definition_en": None},
        ],
    )

    prompt = build_prompt(request)

    assert "- 你好 (ni3 hao3): hello" in prompt
    assert "- 饭馆\n" in prompt
    assert "glossary entry for each of these words: 饭馆" in prompt
    assert '"glossary"' in prompt
