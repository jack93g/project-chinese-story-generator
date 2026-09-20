import pytest

from story_generator.generation.providers.base import StoryGenerationProvider
from story_generator.generation.providers.errors import (
    ProviderAPIError,
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from story_generator.generation.providers.fake import FakeStoryGenerationProvider
from story_generator.generation.providers.types import (
    GenerationRequestInput,
    UsageMetadata,
)

SAMPLE_REQUEST = GenerationRequestInput(
    target_hsk_level=3,
    target_word_count=200,
    target_vocabulary_count=5,
    vocabulary_snapshot=[
        {"id": 10, "writing": "菜单", "reading": "càidān", "definition_en": "menu"},
    ],
    prompt_version="v1",
    topic="a restaurant",
)


def test_fake_provider_conforms_to_the_provider_protocol():
    provider = FakeStoryGenerationProvider()

    assert isinstance(provider, StoryGenerationProvider)


def test_success_scenario_returns_generation_result_with_chinese_content():
    provider = FakeStoryGenerationProvider(scenario="success")

    result = provider.generate(SAMPLE_REQUEST)

    assert result.title
    assert result.body
    assert isinstance(result.usage, UsageMetadata)


def test_success_scenario_is_the_default():
    provider = FakeStoryGenerationProvider()

    result = provider.generate(SAMPLE_REQUEST)

    assert result.title == "菜单的故事"


def test_success_scenario_uses_provided_raw_response_and_usage():
    usage = UsageMetadata(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    provider = FakeStoryGenerationProvider(
        scenario="success",
        raw_response='{"title": "自定义标题", "body": "自定义正文内容。"}',
        usage=usage,
    )

    result = provider.generate(SAMPLE_REQUEST)

    assert result.title == "自定义标题"
    assert result.body == "自定义正文内容。"
    assert result.usage == usage


def test_provider_records_every_call():
    provider = FakeStoryGenerationProvider()

    provider.generate(SAMPLE_REQUEST)
    provider.generate(SAMPLE_REQUEST)

    assert provider.calls == [SAMPLE_REQUEST, SAMPLE_REQUEST]


def test_malformed_scenario_raises_provider_invalid_response_error():
    provider = FakeStoryGenerationProvider(
        scenario="malformed", raw_response="not json"
    )

    with pytest.raises(ProviderInvalidResponseError):
        provider.generate(SAMPLE_REQUEST)


def test_malformed_scenario_with_missing_field_raises_provider_invalid_response_error():
    provider = FakeStoryGenerationProvider(
        scenario="malformed", raw_response='{"title": "标题"}'
    )

    with pytest.raises(ProviderInvalidResponseError, match="body"):
        provider.generate(SAMPLE_REQUEST)


def test_timeout_scenario_raises_provider_timeout_error():
    provider = FakeStoryGenerationProvider(scenario="timeout")

    with pytest.raises(ProviderTimeoutError):
        provider.generate(SAMPLE_REQUEST)


def test_rate_limit_scenario_raises_provider_rate_limit_error():
    provider = FakeStoryGenerationProvider(scenario="rate_limit")

    with pytest.raises(ProviderRateLimitError):
        provider.generate(SAMPLE_REQUEST)


def test_auth_error_scenario_raises_provider_authentication_error():
    provider = FakeStoryGenerationProvider(scenario="auth_error")

    with pytest.raises(ProviderAuthenticationError):
        provider.generate(SAMPLE_REQUEST)


def test_api_error_scenario_raises_provider_api_error_with_status_code():
    provider = FakeStoryGenerationProvider(scenario="api_error")

    with pytest.raises(ProviderAPIError) as exc_info:
        provider.generate(SAMPLE_REQUEST)
    assert exc_info.value.status_code == 500


def test_error_scenarios_do_not_attempt_to_parse_raw_response():
    # raw_response is garbage, but timeout should raise before parsing
    # is ever attempted.
    provider = FakeStoryGenerationProvider(scenario="timeout", raw_response="garbage")

    with pytest.raises(ProviderTimeoutError):
        provider.generate(SAMPLE_REQUEST)


def test_unknown_scenario_raises_value_error_at_construction():
    with pytest.raises(ValueError, match="Unknown scenario"):
        FakeStoryGenerationProvider(scenario="not_a_real_scenario")
