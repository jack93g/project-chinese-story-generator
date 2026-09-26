import json

import pytest

from story_generator.generation.providers.errors import ProviderInvalidResponseError
from story_generator.generation.providers.parser import parse_structured_result
from story_generator.generation.providers.types import GenerationResult, UsageMetadata

USAGE = UsageMetadata(prompt_tokens=10, completion_tokens=20, total_tokens=30)


def test_parses_valid_structured_output_into_generation_result():
    raw = '{"title": "菜单的故事", "body": "小明去饭馆点了一份菜。"}'

    result = parse_structured_result(raw, USAGE)

    assert result == GenerationResult(
        title="菜单的故事", body="小明去饭馆点了一份菜。", usage=USAGE
    )


def test_raises_on_invalid_json():
    with pytest.raises(ProviderInvalidResponseError, match="not valid JSON"):
        parse_structured_result("not json at all {", USAGE)


def test_raises_when_top_level_json_is_not_an_object():
    with pytest.raises(ProviderInvalidResponseError, match="must be a JSON object"):
        parse_structured_result('["菜单的故事", "小明去饭馆"]', USAGE)


def test_raises_when_title_is_missing():
    with pytest.raises(
        ProviderInvalidResponseError, match="missing required field.*title"
    ):
        parse_structured_result('{"body": "小明去饭馆点了一份菜。"}', USAGE)


def test_raises_when_body_is_missing():
    with pytest.raises(
        ProviderInvalidResponseError, match="missing required field.*body"
    ):
        parse_structured_result('{"title": "菜单的故事"}', USAGE)


def test_raises_when_title_is_empty_string():
    with pytest.raises(
        ProviderInvalidResponseError, match="'title' must be a non-empty string"
    ):
        parse_structured_result(
            '{"title": "", "body": "小明去饭馆点了一份菜。"}', USAGE
        )


def test_raises_when_body_is_wrong_type():
    with pytest.raises(
        ProviderInvalidResponseError, match="'body' must be a non-empty string"
    ):
        parse_structured_result('{"title": "菜单的故事", "body": 12345}', USAGE)


def test_raises_when_title_has_no_chinese_characters():
    with pytest.raises(
        ProviderInvalidResponseError, match="'title' must contain Chinese"
    ):
        parse_structured_result(
            '{"title": "Menu Story", "body": "小明去饭馆点了一份菜。"}', USAGE
        )


def test_raises_when_body_has_no_chinese_characters():
    with pytest.raises(
        ProviderInvalidResponseError, match="'body' must contain Chinese"
    ):
        parse_structured_result(
            '{"title": "菜单的故事", "body": "Xiao Ming went to a restaurant."}', USAGE
        )


def test_parses_a_translation_list():
    raw = (
        '{"title": "菜单的故事", "body": "小明去饭馆。\\n\\n他点了菜。", '
        '"translation": [" Xiao Ming goes to a restaurant. ", "He orders."]}'
    )

    result = parse_structured_result(raw, USAGE)

    assert result.translation == ["Xiao Ming goes to a restaurant.", "He orders."]


def test_translation_is_none_when_absent():
    raw = '{"title": "菜单的故事", "body": "小明去饭馆点了一份菜。"}'

    assert parse_structured_result(raw, USAGE).translation is None


@pytest.mark.parametrize(
    "translation",
    ['"Xiao Ming goes to a restaurant."', "[]", '["ok", ""]', '["ok", 3]', "null"],
)
def test_drops_a_malformed_translation_without_failing(translation):
    raw = (
        '{"title": "菜单的故事", "body": "小明去饭馆点了一份菜。", '
        f'"translation": {translation}}}'
    )

    result = parse_structured_result(raw, USAGE)

    assert result.body == "小明去饭馆点了一份菜。"
    assert result.translation is None


def test_parses_questions():
    raw = (
        '{"title": "菜单的故事", "body": "小明去饭馆点了一份菜。", '
        '"questions": [{"question": " 小明去了哪里？ ", '
        '"options": ["学校", " 饭馆 ", "商店", "医院"], "answer": 1}]}'
    )

    result = parse_structured_result(raw, USAGE)

    assert result.questions == [
        {
            "question": "小明去了哪里？",
            "options": ["学校", "饭馆", "商店", "医院"],
            "answer": 1,
        }
    ]


def test_questions_are_none_when_absent():
    raw = '{"title": "菜单的故事", "body": "小明去饭馆点了一份菜。"}'

    assert parse_structured_result(raw, USAGE).questions is None


@pytest.mark.parametrize(
    "question",
    [
        '"小明去了哪里？"',
        '{"options": ["学校", "饭馆"], "answer": 1}',
        '{"question": " ", "options": ["学校", "饭馆"], "answer": 1}',
        '{"question": "哪里？", "options": ["饭馆"], "answer": 0}',
        '{"question": "哪里？", "options": "饭馆", "answer": 0}',
        '{"question": "哪里？", "options": ["学校", ""], "answer": 0}',
        '{"question": "哪里？", "options": ["饭馆", " 饭馆"], "answer": 0}',
        '{"question": "哪里？", "options": ["学校", "饭馆"], "answer": 2}',
        '{"question": "哪里？", "options": ["学校", "饭馆"], "answer": -1}',
        '{"question": "哪里？", "options": ["学校", "饭馆"], "answer": "1"}',
        '{"question": "哪里？", "options": ["学校", "饭馆"], "answer": true}',
    ],
)
def test_drops_a_malformed_question_and_keeps_the_rest(question):
    good = '{"question": "谁去了饭馆？", "options": ["小明", "小红"], "answer": 0}'
    raw = (
        '{"title": "菜单的故事", "body": "小明去饭馆点了一份菜。", '
        f'"questions": [{question}, {good}]}}'
    )

    result = parse_structured_result(raw, USAGE)

    assert result.questions == [
        {"question": "谁去了饭馆？", "options": ["小明", "小红"], "answer": 0}
    ]


@pytest.mark.parametrize("questions", ["[]", '"none"', "null", '[{"answer": 0}]'])
def test_questions_are_none_when_none_is_usable(questions):
    raw = (
        '{"title": "菜单的故事", "body": "小明去饭馆点了一份菜。", '
        f'"questions": {questions}}}'
    )

    result = parse_structured_result(raw, USAGE)

    assert result.body == "小明去饭馆点了一份菜。"
    assert result.questions is None


def _raw_with_question(evidence_json: str) -> str:
    return (
        '{"title": "菜单的故事", "body": "小明饿了。\\n\\n他说：“我们去饭馆吧！” 他们去了饭馆。", '
        '"questions": [{"question": "他们去了哪里？", "options": ["学校", "饭馆"], '
        f'"answer": 1{evidence_json}}}]}}'
    )


@pytest.mark.parametrize(
    "evidence",
    [
        "他们去了饭馆。",
        # quotation marks and final punctuation added or dropped
        "他说：“我们去饭馆吧！”",
        "“我们去饭馆吧",
        "他们去了饭馆",
        # a clause or list mark added at the end
        "他们去了饭馆；",
        "他们去了饭馆：",
        "他们去了饭馆、",
        # whitespace ignored
        " 他说：“我们去饭馆吧！” 他们去了饭馆。 ",
    ],
)
def test_keeps_a_question_whose_evidence_is_in_the_body(evidence):
    raw = _raw_with_question(
        f', "evidence": {json.dumps(evidence, ensure_ascii=False)}'
    )

    [question] = parse_structured_result(raw, USAGE).questions

    assert question["evidence"] == evidence.strip()


@pytest.mark.parametrize(
    "evidence",
    ['"他们去了学校。"', '"他们很快就去了饭馆。"', '"。"', '""', "1", "null"],
)
def test_drops_a_question_whose_evidence_is_not_in_the_body(evidence):
    raw = _raw_with_question(f', "evidence": {evidence}')

    assert parse_structured_result(raw, USAGE).questions is None


def test_a_question_without_evidence_is_kept_as_before_story_v9():
    [question] = parse_structured_result(_raw_with_question(""), USAGE).questions

    assert "evidence" not in question
