"""
Smoke test that makes a real call to a live OpenAI-compatible API
(e.g. OpenRouter, or OpenAI itself, depending on your .env). Skipped
by default — this must never run in CI or a normal local `pytest`
pass, since it may cost money and needs real credentials configured.
Run explicitly:

    RUN_SMOKE_TESTS=1 pytest -m smoke
"""

import os

import pytest

from story_generator.generation.providers.openai import build_openai_provider
from story_generator.generation.providers.types import GenerationRequestInput

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.getenv("RUN_SMOKE_TESTS") != "1",
        reason="Smoke tests make live provider API calls; set RUN_SMOKE_TESTS=1 to run them.",
    ),
]


def test_generate_against_live_provider():
    provider = build_openai_provider()
    request = GenerationRequestInput(
        target_hsk_level=1,
        target_word_count=50,
        target_vocabulary_count=1,
        vocabulary_snapshot=[
            {"id": 1, "writing": "你好", "reading": "nǐ hǎo", "definition_en": "hello"},
        ],
        prompt_version="story-v1",
    )

    result = provider.generate(request)

    assert result.title
    assert result.body
    assert result.usage.total_tokens > 0
    assert result.usage.latency_ms is not None
    assert result.usage.latency_ms >= 0