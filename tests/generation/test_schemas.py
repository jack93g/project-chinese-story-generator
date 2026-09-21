import pytest
from pydantic import ValidationError

from story_generator.generation.schemas import (
    MAX_TARGET_WORD_COUNT,
    MAX_TOPIC_LENGTH,
    CreateGenerationRequestSchema,
)


def test_rejects_missing_vocabulary_list_id():
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(
            target_hsk_level=1, target_word_count=100, target_vocabulary_count=1
        )


@pytest.mark.parametrize("hsk_level", [0, 7, -1])
def test_rejects_invalid_hsk_level(hsk_level):
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(
            vocabulary_list_id=1,
            target_hsk_level=hsk_level,
            target_word_count=100,
            target_vocabulary_count=1,
        )


@pytest.mark.parametrize("word_count", [0, -50])
def test_rejects_invalid_word_count(word_count):
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(
            vocabulary_list_id=1,
            target_hsk_level=1,
            target_word_count=word_count,
            target_vocabulary_count=1,
        )


def test_rejects_word_count_above_maximum():
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(
            vocabulary_list_id=1,
            target_hsk_level=1,
            target_word_count=MAX_TARGET_WORD_COUNT + 1,
            target_vocabulary_count=1,
        )


def test_accepts_word_count_at_maximum():
    schema = CreateGenerationRequestSchema(
        vocabulary_list_id=1,
        target_hsk_level=1,
        target_word_count=MAX_TARGET_WORD_COUNT,
        target_vocabulary_count=1,
    )

    assert schema.target_word_count == MAX_TARGET_WORD_COUNT


@pytest.mark.parametrize("vocab_count", [0, 16, -1])
def test_rejects_invalid_vocabulary_count(vocab_count):
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(
            vocabulary_list_id=1,
            target_hsk_level=1,
            target_word_count=100,
            target_vocabulary_count=vocab_count,
        )


def test_blank_topic_normalized_to_none():
    schema = CreateGenerationRequestSchema(
        vocabulary_list_id=1,
        target_hsk_level=1,
        target_word_count=100,
        target_vocabulary_count=1,
        topic="   ",
    )

    assert schema.topic is None


def test_provider_and_model_are_not_accepted_as_input():
    # provider/model are resolved server-side, not client-supplied —
    # passing them should simply be ignored, not raise, since Pydantic
    # ignores unknown fields by default (extra="ignore").
    schema = CreateGenerationRequestSchema(
        vocabulary_list_id=1,
        target_hsk_level=1,
        target_word_count=100,
        target_vocabulary_count=1,
        provider="malicious-provider",
        model="malicious-model",
    )

    assert not hasattr(schema, "provider")
    assert not hasattr(schema, "model")


def test_topic_over_max_length_is_rejected():
    base = dict(
        vocabulary_list_id=1,
        target_hsk_level=2,
        target_word_count=100,
        target_vocabulary_count=2,
    )
    CreateGenerationRequestSchema(**base, topic="x" * MAX_TOPIC_LENGTH)
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(**base, topic="x" * (MAX_TOPIC_LENGTH + 1))
