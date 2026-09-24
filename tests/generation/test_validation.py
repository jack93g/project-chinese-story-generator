from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.providers.types import GenerationResult, UsageMetadata
from story_generator.generation.validation import validate_story


def _make_request(snapshot):
    return StoryGenerationRequest(
        target_word_count=100,
        target_hsk_level=2,
        target_vocabulary_count=len(snapshot),
        selected_vocabulary_snapshot=snapshot,
        prompt_version="story-v1",
        provider="openai",
        model="gpt-test",
        vocabulary_list_id=1,
    )


def _make_result(title, body):
    return GenerationResult(
        title=title,
        body=body,
        usage=UsageMetadata(
            prompt_tokens=1, completion_tokens=1, total_tokens=2, latency_ms=10
        ),
    )


def test_validate_story_marks_all_present_words_as_used():
    request = _make_request(
        [
            {"id": 1, "writing": "你好", "reading": "", "definition_en": ""},
            {"id": 2, "writing": "菜单", "reading": "", "definition_en": ""},
        ]
    )
    result = _make_result("故事", "你好，请给我菜单。")

    report, used_map = validate_story(request, result)

    assert used_map == {1: True, 2: True}
    assert report["missing_vocabulary"] == []
    assert report["used_vocabulary_count"] == 2


def test_validate_story_flags_missing_words():
    request = _make_request(
        [
            {"id": 1, "writing": "你好", "reading": "", "definition_en": ""},
            {"id": 2, "writing": "菜单", "reading": "", "definition_en": ""},
        ]
    )
    result = _make_result("故事", "你好。")

    report, used_map = validate_story(request, result)

    assert used_map == {1: True, 2: False}
    assert report["missing_vocabulary"] == [{"id": 2, "writing": "菜单"}]
    assert report["used_vocabulary_count"] == 1


def test_validate_story_meets_threshold_with_one_missing_word_out_of_many():
    request = _make_request(
        [
            {"id": 1, "writing": "你好", "reading": "", "definition_en": ""},
            {"id": 2, "writing": "菜单", "reading": "", "definition_en": ""},
            {"id": 3, "writing": "朋友", "reading": "", "definition_en": ""},
            {"id": 4, "writing": "学校", "reading": "", "definition_en": ""},
            {"id": 5, "writing": "天气", "reading": "", "definition_en": ""},
        ]
    )
    # 4/5 = 80% coverage — meets the default 0.8 threshold
    result = _make_result("故事", "你好，菜单，朋友，学校都在这里。")

    report, _ = validate_story(request, result)

    assert report["coverage"] == 0.8
    assert report["meets_coverage_threshold"] is True


def test_validate_story_fails_threshold_when_too_many_words_missing():
    request = _make_request(
        [
            {"id": 1, "writing": "你好", "reading": "", "definition_en": ""},
            {"id": 2, "writing": "菜单", "reading": "", "definition_en": ""},
            {"id": 3, "writing": "朋友", "reading": "", "definition_en": ""},
            {"id": 4, "writing": "学校", "reading": "", "definition_en": ""},
            {"id": 5, "writing": "天气", "reading": "", "definition_en": ""},
        ]
    )
    # 3/5 = 60% coverage — below the default 0.8 threshold
    result = _make_result("故事", "你好，菜单，朋友都在这里。")

    report, _ = validate_story(request, result)

    assert report["coverage"] == 0.6
    assert report["meets_coverage_threshold"] is False


def test_validate_story_records_length_against_target():
    request = _make_request(
        [{"id": 1, "writing": "你好", "reading": "", "definition_en": ""}]
    )
    result = _make_result("故事", "你好" * 45)  # 90 characters, target 100

    report, _ = validate_story(request, result)

    assert report["actual_character_count"] == 90
    assert report["length_ratio"] == 0.9
    assert report["meets_length_threshold"] is True


def test_validate_story_flags_short_story_without_failing_coverage():
    request = _make_request(
        [{"id": 1, "writing": "你好", "reading": "", "definition_en": ""}]
    )
    result = _make_result("故事", "你好" * 25)  # 50 characters, target 100

    report, _ = validate_story(request, result)

    assert report["length_ratio"] == 0.5
    assert report["meets_length_threshold"] is False
    # length is recorded, not enforced: the story is still acceptable
    assert report["meets_coverage_threshold"] is True
