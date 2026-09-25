from story_generator.generation.prompts.builder import (
    CURRENT_PROMPT_VERSION,
    build_prompt,
    build_story_v1_prompt,
    build_story_v3_prompt,
    build_story_v4_prompt,
    build_story_v5_prompt,
    build_story_v6_prompt,
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


def test_current_prompt_version_is_v6():
    assert CURRENT_PROMPT_VERSION == "story-v6"


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


def test_v4_prompt_adds_consistency_and_collocation_guidance_to_v3():
    request = _make_request(prompt_version="story-v4", target_word_count=300)

    v3 = build_story_v3_prompt(request)
    v4 = build_story_v4_prompt(request)

    assert "plausible and consistent" in v4
    assert "natural collocation" in v4
    assert "not into a closing summary or moral" in v4
    assert "plausible and consistent" not in v3
    # the guidance sits between the vocabulary and the length section,
    # and v4 is otherwise v3
    guidance_start = v4.index("Keep the story plausible")
    assert guidance_start < v4.index("Length:")
    assert v4.replace(v4[guidance_start : v4.index("Length:")], "") == v3


def test_v5_prompt_adds_setting_guidance_before_v4_guidance():
    request = _make_request(prompt_version="story-v5", target_word_count=300)

    v4 = build_story_v4_prompt(request)
    v5 = build_story_v5_prompt(request)

    assert "Choose a setting where every word fits naturally" not in v4
    setting_start = v5.index("Choose a setting where every word fits naturally")
    assert setting_start < v5.index("Keep the story plausible")
    assert (
        v5.replace(v5[setting_start : v5.index("Keep the story plausible")], "") == v4
    )


def test_v6_prompt_adds_a_per_paragraph_translation_to_v3():
    request = _make_request(prompt_version="story-v6", target_word_count=300)

    v3 = build_story_v3_prompt(request)
    v6 = build_story_v6_prompt(request)

    assert build_prompt(request) == v6
    assert '"translation"' not in v3
    assert "one English string per paragraph of the body" in v6
    # one example entry per planned paragraph, right after the body
    assert (
        '"body": "<Chinese story body, 270-360 characters>", "translation": '
        '["<English translation of paragraph 1>", '
        '"<English translation of paragraph 2>", '
        '"<English translation of paragraph 3>"]}'
    ) in v6
    # the guidance follows the length section, and v6 is otherwise v3
    guidance_start = v6.index("Translation:")
    assert v6.index("Length:") < guidance_start < v6.index("Respond with")
    guidance = v6[guidance_start : v6.index("Respond with")]
    translation_field = v6[v6.index(', "translation": [') : v6.index("]}") + 1]
    assert v6.replace(guidance, "").replace(translation_field, "") == v3


def test_v6_prompt_shows_one_translation_entry_for_a_one_paragraph_story():
    request = _make_request(prompt_version="story-v6", target_word_count=60)

    prompt = build_story_v6_prompt(request)

    assert '"translation": ["<English translation of the paragraph>"]' in prompt


def test_v6_prompt_keeps_the_glossary_after_the_translation():
    request = _make_request(
        prompt_version="story-v6",
        vocabulary_snapshot=[
            {"id": 2, "writing": "饭馆", "reading": None, "definition_en": None},
        ],
    )

    prompt = build_story_v6_prompt(request)

    assert "glossary entry for each of these words: 饭馆" in prompt
    assert prompt.index('"translation"') < prompt.index('"glossary"')
