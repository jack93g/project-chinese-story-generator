import pytest

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.providers.types import GenerationResult, UsageMetadata
from story_generator.generation.validation import (
    split_paragraphs,
    stray_english,
    validate_story,
    word_appears,
)


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


def _make_result(title, body, translation=None, questions=None):
    return GenerationResult(
        title=title,
        body=body,
        translation=translation,
        questions=questions,
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


@pytest.mark.parametrize(
    ("writing", "text"),
    [
        ("菜单", "请给我菜单。"),
        # spaces as word breaks, from Skritter
        ("口语 能力", "马克的口语能力还不够好。"),
        # spaces as gaps
        ("一旦 就", "一旦下雨，我们就回家。"),
        # grammar patterns, in any ellipsis style
        ("虽然 ... 但是...", "虽然很累，但是他很开心。"),
        ("先 ... 再...", "先吃饭再说。"),
        ("从...开始", "从明天开始学习。"),
        ("既然。。。干脆", "既然没用，干脆躺平。"),
        ("先…再", "先吃饭再说。"),
        # trailing punctuation differs from the entry's
        ("你在吗？", "“你在吗？”她问。"),
        ("别 卖关子 了！", "他说：“别卖关子了。”"),
    ],
)
def test_word_appears_matches(writing, text):
    assert word_appears(writing, text)


@pytest.mark.parametrize(
    ("writing", "text"),
    [
        ("菜单", "请给我水。"),
        # parts out of order
        ("虽然 ... 但是...", "但是他来了，虽然很晚。"),
        # parts in different sentences
        ("先 ... 再...", "他先走了。我们再见吧。"),
        ("口语 能力", "口语很好。能力一般。"),
    ],
)
def test_word_appears_rejects(writing, text):
    assert not word_appears(writing, text)


def test_validate_story_counts_a_spaced_skritter_entry_as_used():
    request = _make_request(
        [{"id": 691, "writing": "口语 能力", "reading": "", "definition_en": ""}]
    )
    result = _make_result("柏林墙边的表情包", "马克的口语能力还不够好。")

    report, used_map = validate_story(request, result)

    assert used_map == {691: True}
    assert report["missing_vocabulary"] == []


def test_split_paragraphs_uses_non_blank_lines():
    body = "第一段。\n\n  第二段。 \n第三段。\n\n\n"

    assert split_paragraphs(body) == ["第一段。", "第二段。", "第三段。"]


def test_validate_story_records_whether_the_translation_lines_up():
    request = _make_request(
        [{"id": 1, "writing": "你好", "reading": "", "definition_en": ""}]
    )

    aligned, _ = validate_story(
        request, _make_result("故事", "你好。\n\n再见。", ["Hello.", "Bye."])
    )
    misaligned, _ = validate_story(
        request, _make_result("故事", "你好。\n\n再见。", ["Hello. Bye."])
    )
    untranslated, _ = validate_story(request, _make_result("故事", "你好。"))

    assert aligned["translation_aligned"] is True
    assert misaligned["translation_aligned"] is False
    assert "translation_aligned" not in untranslated


def test_validate_story_records_how_many_questions_there_are():
    request = _make_request(
        [{"id": 1, "writing": "你好", "reading": "", "definition_en": ""}]
    )
    question = {"question": "谁说你好？", "options": ["小明", "小红"], "answer": 0}

    with_questions, _ = validate_story(
        request, _make_result("故事", "小明说你好。", questions=[question] * 2)
    )
    without_questions, _ = validate_story(request, _make_result("故事", "你好。"))

    assert with_questions["question_count"] == 2
    assert with_questions["meets_coverage_threshold"] is True
    assert "question_count" not in without_questions


def test_stray_english_finds_english_words_in_the_chinese_text():
    result = _make_result(
        "雨中 walking",
        "我们 hurriedly 赶到机场。对方CEO和AI专家都 walking 来了。",
        translation=["We hurried to the airport."],
        questions=[
            {"question": "他们怎么去？", "options": ["走路", "by bus"], "answer": 0}
        ],
    )

    # Once each, in order; abbreviations and the English translation don't count.
    assert stray_english(result) == ["walking", "hurriedly", "by", "bus"]


def test_validate_story_records_stray_english():
    request = _make_request(
        [{"id": 1, "writing": "你好", "reading": "", "definition_en": ""}]
    )

    clean, _ = validate_story(request, _make_result("故事", "CEO说你好。"))
    stray, _ = validate_story(request, _make_result("故事", "他 quickly 说你好。"))

    assert clean["stray_english"] == []
    assert stray["stray_english"] == ["quickly"]
    # Recorded only: the story still passes.
    assert stray["meets_coverage_threshold"] is True
