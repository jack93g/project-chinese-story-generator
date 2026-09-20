from story_generator.generation.prompts.builder import (
    CURRENT_PROMPT_VERSION,
    build_prompt,
    build_story_v1_prompt,
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
