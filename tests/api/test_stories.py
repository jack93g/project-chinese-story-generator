import pytest

from story_generator.stories.persistence.models import Story, StoryVocabularyItem
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
        "selected_vocabulary",
    }


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
    assert db_session.query(StoryVocabularyItem).filter_by(story_id=story_id).count() == 0

    get_response = client.get(f"/stories/{story_id}")
    assert get_response.status_code == 404


def test_delete_story_returns_404_for_unknown_id(client):
    response = client.delete("/stories/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Story 999999 not found"}
