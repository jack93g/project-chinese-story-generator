import random

import pytest

from story_generator.generation.persistence.models import (
    RawGenerationPayload,
    StoryGenerationRequest,
)
from story_generator.generation.providers.fake import FakeStoryGenerationProvider
from story_generator.generation.worker import GenerationWorker
from story_generator.stories.persistence.models import Story, StoryVocabularyItem
from story_generator.vocabulary.persistence.models import VocabularyItem, VocabularyList

pytestmark = pytest.mark.db


def _make_queued_request(session, *, skritter_list_id: str, writing: str = "你好"):
    vocab_list = VocabularyList(skritter_list_id=skritter_list_id, name="Test list")
    session.add(vocab_list)
    session.flush()

    item = VocabularyItem(
        skritter_vocab_id=f"{skritter_list_id}-item-1",
        language="zh",
        writing=writing,
        reading="ni3 hao3",
        definition_en="hello",
    )
    session.add(item)
    session.flush()
    vocab_list.items.append(item)
    session.flush()

    request = StoryGenerationRequest(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=2,
        target_word_count=100,
        target_vocabulary_count=1,
        selected_vocabulary_snapshot=[
            {
                "id": item.id,
                "writing": writing,
                "reading": "ni3 hao3",
                "definition_en": "hello",
            }
        ],
        prompt_version="story-v1",
        provider="openai",
        model="gpt-test",
    )
    session.add(request)
    session.commit()
    return request


def test_run_once_returns_false_when_queue_is_empty(db_session):
    worker = GenerationWorker(provider=FakeStoryGenerationProvider(scenario="success"))

    assert worker.run_once(db_session) is False


def test_run_once_persists_story_and_marks_request_succeeded_atomically(db_session):
    request = _make_queued_request(
        db_session, skritter_list_id="worker-success", writing="你好"
    )
    provider = FakeStoryGenerationProvider(
        scenario="success",
        raw_response='{"title": "问候", "body": "小明说你好。"}',
    )
    worker = GenerationWorker(provider=provider)

    processed = worker.run_once(db_session)

    assert processed is True
    db_session.refresh(request)
    assert request.status == "succeeded"
    assert request.validation_report["used_vocabulary_count"] == 1
    assert request.validation_report["missing_vocabulary"] == []

    story = db_session.query(Story).filter_by(generation_request_id=request.id).one()
    assert story.title == "问候"
    assert story.content == "小明说你好。"
    assert story.translation_en is None
    assert story.comprehension_questions is None

    associations = (
        db_session.query(StoryVocabularyItem).filter_by(story_id=story.id).all()
    )
    assert len(associations) == 1
    assert associations[0].requested is True
    assert associations[0].used is True

    raw_payloads = (
        db_session.query(RawGenerationPayload)
        .filter_by(generation_request_id=request.id)
        .all()
    )
    assert len(raw_payloads) == 1
    assert raw_payloads[0].response_status == 200
    assert raw_payloads[0].attempt_number == request.attempt_count


def test_run_once_fails_request_and_creates_no_story_when_coverage_below_threshold(
    db_session,
):
    request = _make_queued_request(
        db_session, skritter_list_id="worker-low-coverage", writing="菜单"
    )
    provider = FakeStoryGenerationProvider(
        scenario="success",
        raw_response='{"title": "故事", "body": "小明去了饭馆。"}',  # never uses 菜单 — 0/1 = 0% coverage
    )
    worker = GenerationWorker(provider=provider)

    processed = worker.run_once(db_session)

    assert processed is True
    db_session.refresh(request)
    assert request.status == "failed"
    assert request.error_code == "InsufficientVocabularyCoverage"
    assert request.validation_report["meets_coverage_threshold"] is False
    assert request.validation_report["missing_vocabulary"] == [
        {"id": request.selected_vocabulary_snapshot[0]["id"], "writing": "菜单"}
    ]

    # no story should be created for a failed generation
    assert (
        db_session.query(Story).filter_by(generation_request_id=request.id).first()
        is None
    )

    # the raw exchange should still be captured for diagnosis, even
    # though the request ultimately failed on coverage, not a
    # provider-level error
    raw_payloads = (
        db_session.query(RawGenerationPayload)
        .filter_by(generation_request_id=request.id)
        .all()
    )
    assert len(raw_payloads) == 1
    assert raw_payloads[0].response_status == 200


def test_run_once_marks_request_failed_and_does_not_create_story_on_provider_error(
    db_session,
):
    request = _make_queued_request(db_session, skritter_list_id="worker-failure")
    provider = FakeStoryGenerationProvider(scenario="timeout")
    worker = GenerationWorker(provider=provider)

    processed = worker.run_once(db_session)

    assert processed is True
    db_session.refresh(request)
    assert request.status == "failed"
    assert request.error_code is not None
    assert request.error_message is not None

    assert (
        db_session.query(Story).filter_by(generation_request_id=request.id).first()
        is None
    )

    raw_payloads = (
        db_session.query(RawGenerationPayload)
        .filter_by(generation_request_id=request.id)
        .all()
    )
    assert len(raw_payloads) == 1
    assert raw_payloads[0].response_status is None  # timeout: never got a response


def test_run_once_stores_the_translation_with_the_story(db_session):
    request = _make_queued_request(
        db_session, skritter_list_id="worker-translation", writing="你好"
    )
    provider = FakeStoryGenerationProvider(
        scenario="success",
        raw_response=(
            '{"title": "问候", "body": "小明说你好。\\n\\n小红笑了。", '
            '"translation": ["Xiao Ming says hello.", "Xiao Hong smiles."]}'
        ),
    )

    assert GenerationWorker(provider=provider).run_once(db_session) is True

    story = db_session.query(Story).filter_by(generation_request_id=request.id).one()
    assert story.translation_en == ["Xiao Ming says hello.", "Xiao Hong smiles."]
    db_session.refresh(request)
    assert request.validation_report["translation_aligned"] is True


def test_run_once_stores_the_questions_with_their_options_shuffled(db_session):
    request = _make_queued_request(
        db_session, skritter_list_id="worker-questions", writing="你好"
    )
    options = ["小明", "小红", "老师", "妈妈"]
    provider = FakeStoryGenerationProvider(
        scenario="success",
        raw_response=(
            '{"title": "问候", "body": "小明说你好。", "questions": ['
            '{"question": "谁说你好？", "options": ["小明", "小红", "老师", "妈妈"], '
            '"answer": 0}]}'
        ),
    )
    # Seeded so the shuffle is repeatable; any order must keep the answer on
    # the option that was correct.
    worker = GenerationWorker(provider=provider, rng=random.Random(7))

    assert worker.run_once(db_session) is True

    story = db_session.query(Story).filter_by(generation_request_id=request.id).one()
    [question] = story.comprehension_questions
    assert question["question"] == "谁说你好？"
    assert sorted(question["options"]) == sorted(options)
    assert question["options"][question["answer"]] == "小明"
    db_session.refresh(request)
    assert request.validation_report["question_count"] == 1


def test_shuffling_moves_the_answer_with_its_option():
    from story_generator.generation.worker import _shuffle_options

    question = {"question": "谁？", "options": ["甲", "乙", "丙", "丁"], "answer": 2}
    positions = set()
    for seed in range(40):
        [shuffled] = _shuffle_options([question], random.Random(seed))
        assert shuffled["options"][shuffled["answer"]] == "丙"
        positions.add(shuffled["answer"])

    # The correct option doesn't stay where the model put it.
    assert positions == {0, 1, 2, 3}


def test_shuffling_keeps_the_evidence():
    from story_generator.generation.worker import _shuffle_options

    question = {
        "question": "谁？",
        "options": ["甲", "乙"],
        "answer": 0,
        "evidence": "甲说你好。",
    }

    [shuffled] = _shuffle_options([question], random.Random(1))

    assert shuffled["evidence"] == "甲说你好。"
