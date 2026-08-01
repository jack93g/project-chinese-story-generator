import pytest

from story_generator.generation.providers.errors import ProviderInvalidResponseError
from story_generator.generation.providers.parser import parse_structured_result
from story_generator.generation.providers.types import GenerationResult, UsageMetadata

USAGE = UsageMetadata(prompt_tokens=10, completion_tokens=20, total_tokens=30)


def test_parses_valid_structured_output_into_generation_result():
    raw = '{"title": "菜单的故事", "body": "小明去饭馆点了一份菜。"}'

    result = parse_structured_result(raw, USAGE)

    assert result == GenerationResult(title="菜单的故事", body="小明去饭馆点了一份菜。", usage=USAGE)


def test_raises_on_invalid_json():
    with pytest.raises(ProviderInvalidResponseError, match="not valid JSON"):
        parse_structured_result("not json at all {", USAGE)


def test_raises_when_top_level_json_is_not_an_object():
    with pytest.raises(ProviderInvalidResponseError, match="must be a JSON object"):
        parse_structured_result('["菜单的故事", "小明去饭馆"]', USAGE)


def test_raises_when_title_is_missing():
    with pytest.raises(ProviderInvalidResponseError, match="missing required field.*title"):
        parse_structured_result('{"body": "小明去饭馆点了一份菜。"}', USAGE)


def test_raises_when_body_is_missing():
    with pytest.raises(ProviderInvalidResponseError, match="missing required field.*body"):
        parse_structured_result('{"title": "菜单的故事"}', USAGE)


def test_raises_when_title_is_empty_string():
    with pytest.raises(ProviderInvalidResponseError, match="'title' must be a non-empty string"):
        parse_structured_result('{"title": "", "body": "小明去饭馆点了一份菜。"}', USAGE)


def test_raises_when_body_is_wrong_type():
    with pytest.raises(ProviderInvalidResponseError, match="'body' must be a non-empty string"):
        parse_structured_result('{"title": "菜单的故事", "body": 12345}', USAGE)


def test_raises_when_title_has_no_chinese_characters():
    with pytest.raises(ProviderInvalidResponseError, match="'title' must contain Chinese"):
        parse_structured_result('{"title": "Menu Story", "body": "小明去饭馆点了一份菜。"}', USAGE)


def test_raises_when_body_has_no_chinese_characters():
    with pytest.raises(ProviderInvalidResponseError, match="'body' must contain Chinese"):
        parse_structured_result('{"title": "菜单的故事", "body": "Xiao Ming went to a restaurant."}', USAGE)