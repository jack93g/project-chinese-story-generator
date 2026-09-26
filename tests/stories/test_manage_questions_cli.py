from datetime import UTC, datetime

import pytest

from story_generator.cli.questions import run
from story_generator.stories.persistence.models import QuestionFlag, QuizAttempt, Story
from story_generator.stories.service import StoryHasNoQuizError, StoryNotFoundError

pytestmark = pytest.mark.db


def _story(db_session, title="点菜", questions=None):
    story = Story(
        title=title,
        content="我们去饭馆。我们点菜。",
        comprehension_questions=questions
        or [
            {
                "question": "去哪里？",
                "options": ["学校", "饭馆"],
                "answer": 1,
                "evidence": "我们去饭馆。",
            },
            {"question": "做什么？", "options": ["点菜", "看书"], "answer": 0},
        ],
    )
    db_session.add(story)
    db_session.flush()
    return story


def _flag(db_session, story, index, day):
    db_session.add(
        QuestionFlag(
            story_id=story.id,
            question_index=index,
            created_at=datetime(2026, 9, day, tzinfo=UTC),
        )
    )
    db_session.flush()


def test_flagged_says_so_when_nothing_is_flagged(db_session):
    _story(db_session)

    assert run(["flagged"], db_session) == "No questions have been flagged."


def test_flagged_lists_questions_most_flagged_first(db_session):
    first = _story(db_session, title="点菜")
    second = _story(db_session, title="买书")
    _flag(db_session, first, 0, day=20)
    _flag(db_session, second, 1, day=21)
    _flag(db_session, second, 1, day=22)
    db_session.add_all(
        [
            QuizAttempt(
                story_id=second.id, answers=[1, 1], correct_count=1, question_count=2
            ),
            QuizAttempt(
                story_id=second.id, answers=[1, 0], correct_count=2, question_count=2
            ),
        ]
    )
    db_session.flush()

    assert run(["flagged"], db_session) == (
        f"Story {second.id} · 买书 · Q2 · flagged 2x, last 2026-09-22\n"
        "  做什么？\n"
        "    ✓ 点菜\n"
        "      看书\n"
        "  Answered right in 1 of 2 attempts\n"
        "\n"
        f"Story {first.id} · 点菜 · Q1 · flagged 1x, last 2026-09-20\n"
        "  去哪里？\n"
        "      学校\n"
        "    ✓ 饭馆\n"
        "  Evidence: 我们去饭馆。\n"
        "  Not answered yet"
    )


def test_show_prints_the_story_and_every_question(db_session):
    story = _story(db_session)
    _flag(db_session, story, 1, day=23)

    assert run(["show", str(story.id)], db_session) == (
        f"Story {story.id} · 点菜\n"
        "\n"
        "我们去饭馆。我们点菜。\n"
        "\n"
        "Q1\n"
        "  去哪里？\n"
        "      学校\n"
        "    ✓ 饭馆\n"
        "  Evidence: 我们去饭馆。\n"
        "  Not answered yet\n"
        "\n"
        "Q2 · flagged 1x, last 2026-09-23\n"
        "  做什么？\n"
        "    ✓ 点菜\n"
        "      看书\n"
        "  Not answered yet"
    )


def test_show_rejects_unknown_stories_and_stories_without_questions(db_session):
    story = Story(title="点菜", content="我们去饭馆。")
    db_session.add(story)
    db_session.flush()

    with pytest.raises(StoryNotFoundError):
        run(["show", "999999"], db_session)
    with pytest.raises(StoryHasNoQuizError):
        run(["show", str(story.id)], db_session)
