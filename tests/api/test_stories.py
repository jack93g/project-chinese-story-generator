import pytest

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.stories.persistence.models import (
    QuestionFlag,
    QuizAttempt,
    Story,
    StoryVocabularyItem,
)
from story_generator.vocabulary.persistence.models import VocabularyItem

pytestmark = pytest.mark.db


def test_list_stories_returns_empty_result(client):
    response = client.get("/stories")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_list_stories_returns_items(client, db_session):
    story_1 = Story(title="第一次点菜", content="……", target_hsk=2)
    story_2 = Story(title="在机场", content="……", target_hsk=3)

    db_session.add_all([story_1, story_2])
    db_session.flush()

    response = client.get("/stories")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 2
    assert data["limit"] == 50
    assert data["offset"] == 0

    assert data["items"] == [
        {
            "id": story_1.id,
            "title": "第一次点菜",
            "created_at": data["items"][0]["created_at"],
            "target_hsk": 2,
        },
        {
            "id": story_2.id,
            "title": "在机场",
            "created_at": data["items"][1]["created_at"],
            "target_hsk": 3,
        },
    ]


def test_list_stories_respects_limit(client, db_session):
    for i in range(5):
        db_session.add(Story(title=f"Story {i}", content="……", target_hsk=1))

    db_session.flush()

    response = client.get("/stories?limit=2")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2


def test_list_stories_respects_offset(client, db_session):
    for i in range(5):
        db_session.add(Story(title=f"Story {i}", content="……", target_hsk=1))

    db_session.flush()

    response = client.get("/stories?limit=2&offset=2")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 2

    assert [item["title"] for item in data["items"]] == [
        "Story 2",
        "Story 3",
    ]


def test_list_stories_rejects_limit_less_than_one(client):
    response = client.get("/stories?limit=0")

    assert response.status_code == 422


def test_list_stories_rejects_limit_greater_than_one_hundred(client):
    response = client.get("/stories?limit=101")

    assert response.status_code == 422


def test_list_stories_rejects_negative_offset(client):
    response = client.get("/stories?offset=-1")

    assert response.status_code == 422


def test_get_story_returns_detail_with_vocabulary(client, db_session):
    story = Story(title="第一次点菜", content="我们去饭馆点菜。", target_hsk=2)

    item_1 = VocabularyItem(
        id=20,
        skritter_vocab_id="zh-菜单-0",
        language="zh",
        writing="菜单",
        reading="cai4 dan1",
        definition_en="menu",
    )
    item_2 = VocabularyItem(
        id=10,
        skritter_vocab_id="zh-饭馆-0",
        language="zh",
        writing="饭馆",
        reading="fan4 guan3",
        definition_en="restaurant",
    )

    story.vocabulary_items.append(item_2)
    story.vocabulary_items.append(item_1)

    db_session.add(story)
    db_session.flush()

    response = client.get(f"/stories/{story.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == story.id
    assert data["title"] == "第一次点菜"
    assert data["content"] == "我们去饭馆点菜。"
    assert data["target_hsk"] == 2

    assert data["selected_vocabulary"] == [
        {
            "id": item_2.id,
            "skritter_vocab_id": "zh-饭馆-0",
            "language": "zh",
            "writing": "饭馆",
            "reading": "fan4 guan3",
            "definition_en": "restaurant",
        },
        {
            "id": item_1.id,
            "skritter_vocab_id": "zh-菜单-0",
            "language": "zh",
            "writing": "菜单",
            "reading": "cai4 dan1",
            "definition_en": "menu",
        },
    ]

    # Contract check: only the expected public fields are exposed —
    # no raw provider payload or generation-request internals leak through.
    assert set(data.keys()) == {
        "id",
        "title",
        "created_at",
        "target_hsk",
        "content",
        "translation_en",
        "questions",
        "selected_vocabulary",
        "provider",
        "model",
    }

    # This story has no generation request, so there's no model to credit.
    assert data["provider"] is None
    assert data["model"] is None
    # Nor a translation, like every story from before story-v6, or
    # questions, like every story from before story-v7.
    assert data["translation_en"] is None
    assert data["questions"] is None


def test_get_story_returns_its_translation(client, db_session):
    story = Story(
        title="第一次点菜",
        content="我们去饭馆。\n\n我们点菜。",
        translation_en=["We go to a restaurant.", "We order."],
    )
    db_session.add(story)
    db_session.flush()

    response = client.get(f"/stories/{story.id}")

    assert response.status_code == 200
    assert response.json()["translation_en"] == [
        "We go to a restaurant.",
        "We order.",
    ]


def test_get_story_returns_provider_and_model_from_its_generation_request(
    client, db_session
):
    request = StoryGenerationRequest(
        target_hsk_level=2,
        target_word_count=150,
        target_vocabulary_count=1,
        selected_vocabulary_snapshot=[],
        prompt_version="story-v1",
        provider="groq",
        model="openai/gpt-oss-120b",
    )
    db_session.add(request)
    db_session.flush()

    story = Story(
        title="第一次点菜",
        content="我们去饭馆点菜。",
        target_hsk=2,
        generation_request_id=request.id,
    )
    db_session.add(story)
    db_session.flush()

    response = client.get(f"/stories/{story.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "groq"
    assert data["model"] == "openai/gpt-oss-120b"


def test_get_story_returns_detail_with_no_vocabulary(client, db_session):
    story = Story(title="Empty story", content="……", target_hsk=None)

    db_session.add(story)
    db_session.flush()

    response = client.get(f"/stories/{story.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["target_hsk"] is None
    assert data["selected_vocabulary"] == []


def test_get_story_returns_404_for_unknown_id(client):
    response = client.get("/stories/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Story 999999 not found"}


def test_delete_story_removes_story_and_vocabulary_associations(client, db_session):
    story = Story(title="第一次点菜", content="我们去饭馆点菜。", target_hsk=2)
    item = VocabularyItem(
        id=30,
        skritter_vocab_id="zh-菜单-0",
        language="zh",
        writing="菜单",
        reading="cai4 dan1",
        definition_en="menu",
    )
    story.vocabulary_items.append(item)

    db_session.add(story)
    db_session.flush()
    story_id = story.id

    response = client.delete(f"/stories/{story_id}")

    assert response.status_code == 204
    assert response.content == b""

    assert db_session.get(Story, story_id) is None
    assert (
        db_session.query(StoryVocabularyItem).filter_by(story_id=story_id).count() == 0
    )

    get_response = client.get(f"/stories/{story_id}")
    assert get_response.status_code == 404


def test_delete_story_returns_404_for_unknown_id(client):
    response = client.delete("/stories/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Story 999999 not found"}


QUESTIONS = [
    {
        "question": "他们去哪里？",
        "options": ["学校", "饭馆", "商店"],
        "answer": 1,
        "evidence": "我们去饭馆。",
    },
    # From before story-v9: no evidence.
    {"question": "他们做什么？", "options": ["点菜", "看书"], "answer": 0},
]


def _story_with_questions(db_session):
    story = Story(
        title="第一次点菜",
        content="我们去饭馆。\n\n我们点菜。",
        comprehension_questions=QUESTIONS,
    )
    db_session.add(story)
    db_session.flush()
    return story


def test_get_story_returns_its_questions_without_the_answers(client, db_session):
    story = _story_with_questions(db_session)

    response = client.get(f"/stories/{story.id}")

    assert response.status_code == 200
    assert response.json()["questions"] == [
        {"question": "他们去哪里？", "options": ["学校", "饭馆", "商店"]},
        {"question": "他们做什么？", "options": ["点菜", "看书"]},
    ]


def test_quiz_attempt_is_marked_and_recorded(client, db_session):
    story = _story_with_questions(db_session)

    response = client.post(
        f"/stories/{story.id}/quiz-attempts", json={"answers": [1, 1]}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["correct_count"] == 1
    assert data["question_count"] == 2
    assert data["results"] == [
        {"selected": 1, "answer": 1, "correct": True, "evidence": "我们去饭馆。"},
        {"selected": 1, "answer": 0, "correct": False, "evidence": None},
    ]

    attempt = db_session.get(QuizAttempt, data["id"])
    assert attempt.story_id == story.id
    # The API key has no user.
    assert attempt.user_id is None
    assert attempt.answers == [1, 1]
    assert attempt.correct_count == 1
    assert attempt.question_count == 2
    assert attempt.created_at is not None


def test_every_quiz_attempt_is_kept(client, db_session):
    story = _story_with_questions(db_session)

    for answers in ([0, 0], [1, 0]):
        client.post(f"/stories/{story.id}/quiz-attempts", json={"answers": answers})

    scores = [
        attempt.correct_count
        for attempt in db_session.query(QuizAttempt)
        .filter_by(story_id=story.id)
        .order_by(QuizAttempt.id)
    ]
    assert scores == [1, 2]


def test_quiz_attempt_returns_404_for_unknown_story(client):
    response = client.post("/stories/999999/quiz-attempts", json={"answers": [0]})

    assert response.status_code == 404
    assert response.json() == {"detail": "Story 999999 not found"}


def test_quiz_attempt_returns_404_for_a_story_without_questions(client, db_session):
    story = Story(title="第一次点菜", content="我们去饭馆。")
    db_session.add(story)
    db_session.flush()

    response = client.post(f"/stories/{story.id}/quiz-attempts", json={"answers": [0]})

    assert response.status_code == 404
    assert response.json() == {
        "detail": f"Story {story.id} has no comprehension questions"
    }


@pytest.mark.parametrize(
    ("answers", "detail"),
    [
        ([1], "Expected 2 answers, one per question, got 1"),
        ([1, 0, 0], "Expected 2 answers, one per question, got 3"),
        ([3, 0], "Question 1 has 3 options; answer 3 is out of range"),
        ([1, 2], "Question 2 has 2 options; answer 2 is out of range"),
    ],
)
def test_quiz_attempt_rejects_answers_that_dont_fit_the_questions(
    client, db_session, answers, detail
):
    story = _story_with_questions(db_session)

    response = client.post(
        f"/stories/{story.id}/quiz-attempts", json={"answers": answers}
    )

    assert response.status_code == 422
    assert response.json() == {"detail": detail}
    assert db_session.query(QuizAttempt).count() == 0


@pytest.mark.parametrize("answers", [[], [-1, 0], ["a", 0]])
def test_quiz_attempt_rejects_malformed_answers(client, db_session, answers):
    story = _story_with_questions(db_session)

    response = client.post(
        f"/stories/{story.id}/quiz-attempts", json={"answers": answers}
    )

    assert response.status_code == 422


def test_deleting_a_story_deletes_its_quiz_attempts(client, db_session):
    story = _story_with_questions(db_session)
    story_id = story.id
    client.post(f"/stories/{story_id}/quiz-attempts", json={"answers": [1, 0]})

    assert client.delete(f"/stories/{story_id}").status_code == 204

    db_session.expire_all()
    assert db_session.query(QuizAttempt).filter_by(story_id=story_id).count() == 0


def test_question_flag_is_recorded(client, db_session):
    story = _story_with_questions(db_session)

    response = client.post(
        f"/stories/{story.id}/question-flags", json={"question_index": 1}
    )

    assert response.status_code == 201
    flag = db_session.get(QuestionFlag, response.json()["id"])
    assert flag.story_id == story.id
    assert flag.question_index == 1
    assert flag.user_id is None
    assert flag.created_at is not None


def test_question_flag_returns_404_for_unknown_story(client):
    response = client.post("/stories/999999/question-flags", json={"question_index": 0})

    assert response.status_code == 404
    assert response.json() == {"detail": "Story 999999 not found"}


def test_question_flag_returns_404_for_a_story_without_questions(client, db_session):
    story = Story(title="第一次点菜", content="我们去饭馆。")
    db_session.add(story)
    db_session.flush()

    response = client.post(
        f"/stories/{story.id}/question-flags", json={"question_index": 0}
    )

    assert response.status_code == 404


def test_question_flag_rejects_a_question_the_story_does_not_have(client, db_session):
    story = _story_with_questions(db_session)

    response = client.post(
        f"/stories/{story.id}/question-flags", json={"question_index": 2}
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": f"Story {story.id} has 2 questions; question 2 is out of range"
    }
    assert db_session.query(QuestionFlag).count() == 0


@pytest.mark.parametrize("question_index", [-1, "first", None])
def test_question_flag_rejects_a_malformed_index(client, db_session, question_index):
    story = _story_with_questions(db_session)

    response = client.post(
        f"/stories/{story.id}/question-flags", json={"question_index": question_index}
    )

    assert response.status_code == 422


def test_deleting_a_story_deletes_its_question_flags(client, db_session):
    story = _story_with_questions(db_session)
    story_id = story.id
    client.post(f"/stories/{story_id}/question-flags", json={"question_index": 0})

    assert client.delete(f"/stories/{story_id}").status_code == 204

    db_session.expire_all()
    assert db_session.query(QuestionFlag).filter_by(story_id=story_id).count() == 0
