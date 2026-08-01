from story_generator.generation.redaction import redact


def test_redact_masks_denylisted_keys_at_top_level():
    body = {"api_key": "sk-123", "model": "claude-sonnet-5"}

    result = redact(body)

    assert result == {"api_key": "[REDACTED]", "model": "claude-sonnet-5"}


def test_redact_is_case_insensitive():
    body = {"Authorization": "Bearer xyz", "Model": "claude-sonnet-5"}

    result = redact(body)

    assert result["Authorization"] == "[REDACTED]"
    assert result["Model"] == "claude-sonnet-5"


def test_redact_matches_substrings_not_just_exact_keys():
    body = {"x-api-key": "sk-123", "provider_request_id": "req-456"}

    result = redact(body)

    assert result["x-api-key"] == "[REDACTED]"
    assert result["provider_request_id"] == "req-456"


def test_redact_recurses_into_nested_dicts():
    body = {
        "request": {
            "headers": {"authorization": "Bearer xyz"},
            "model": "claude-sonnet-5",
        }
    }

    result = redact(body)

    assert result["request"]["headers"]["authorization"] == "[REDACTED]"
    assert result["request"]["model"] == "claude-sonnet-5"


def test_redact_recurses_into_lists():
    body = {"items": [{"token": "abc"}, {"writing": "你好"}]}

    result = redact(body)

    assert result["items"][0]["token"] == "[REDACTED]"
    assert result["items"][1]["writing"] == "你好"


def test_redact_does_not_mutate_input():
    body = {"secret": "value"}

    redact(body)

    assert body == {"secret": "value"}


def test_redact_leaves_non_dict_non_list_values_untouched():
    assert redact("plain string") == "plain string"
    assert redact(42) == 42
    assert redact(None) is None