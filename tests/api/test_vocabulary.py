from datetime import UTC, datetime

import pytest

from story_generator.vocabulary.persistence.models import VocabularyItem, VocabularyList

pytestmark = pytest.mark.db


def test_list_vocabulary_returns_empty_result(client):
    response = client.get("/vocabulary")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_list_vocabulary_returns_items(client, db_session):
    item_1 = VocabularyItem(
        skritter_vocab_id="zh-你好-0",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )

    item_2 = VocabularyItem(
        skritter_vocab_id="zh-谢谢-0",
        language="zh",
        writing="谢谢",
        reading="xie4 xie",
        definition_en="thank you",
    )

    db_session.add_all([item_1, item_2])
    db_session.flush()

    response = client.get("/vocabulary")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 2
    assert data["limit"] == 50
    assert data["offset"] == 0

    assert data["items"] == [
        {
            "id": item_1.id,
            "skritter_vocab_id": "zh-你好-0",
            "language": "zh",
            "writing": "你好",
            "reading": "ni3 hao3",
            "definition_en": "hello",
        },
        {
            "id": item_2.id,
            "skritter_vocab_id": "zh-谢谢-0",
            "language": "zh",
            "writing": "谢谢",
            "reading": "xie4 xie",
            "definition_en": "thank you",
        },
    ]


def test_list_vocabulary_respects_limit(client, db_session):
    for i in range(5):
        db_session.add(
            VocabularyItem(
                skritter_vocab_id=f"zh-{i}",
                language="zh",
                writing=f"词{i}",
                reading=f"ci{i}",
                definition_en=f"word {i}",
            )
        )

    db_session.flush()

    response = client.get("/vocabulary?limit=2")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2


def test_list_vocabulary_respects_offset(client, db_session):
    for i in range(5):
        db_session.add(
            VocabularyItem(
                skritter_vocab_id=f"zh-{i}",
                language="zh",
                writing=f"词{i}",
                reading=f"ci{i}",
                definition_en=f"word {i}",
            )
        )

    db_session.flush()

    response = client.get("/vocabulary?limit=2&offset=2")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 2

    assert [item["writing"] for item in data["items"]] == [
        "词2",
        "词3",
    ]


def test_list_vocabulary_rejects_limit_less_than_one(client):
    response = client.get("/vocabulary?limit=0")

    assert response.status_code == 422


def test_list_vocabulary_rejects_limit_greater_than_one_hundred(client):
    response = client.get("/vocabulary?limit=101")

    assert response.status_code == 422


def test_list_vocabulary_rejects_negative_offset(client):
    response = client.get("/vocabulary?offset=-1")

    assert response.status_code == 422


def test_list_vocabulary_lists_returns_empty_result(client):
    response = client.get("/vocabulary-lists")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_list_vocabulary_lists_returns_items(client, db_session):
    vocab_list = VocabularyList(
        skritter_list_id="5490369014333440",
        name="Love & Relationships",
    )

    item_1 = VocabularyItem(
        skritter_vocab_id="zh-爱-0",
        language="zh",
        writing="爱",
        reading="ai4",
        definition_en="love",
    )

    item_2 = VocabularyItem(
        skritter_vocab_id="zh-心-0",
        language="zh",
        writing="心",
        reading="xin1",
        definition_en="heart",
    )

    vocab_list.items.append(item_1)
    vocab_list.items.append(item_2)

    db_session.add(vocab_list)
    db_session.flush()

    response = client.get("/vocabulary-lists")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert len(data["items"]) == 1

    summary = data["items"][0]

    assert summary["id"] == vocab_list.id
    assert summary["skritter_list_id"] == "5490369014333440"
    assert summary["name"] == "Love & Relationships"
    assert summary["item_count"] == 2
    assert summary["created_at"] is not None
    assert summary["updated_at"] is not None


def test_list_vocabulary_lists_respects_limit_and_offset(client, db_session):
    for i in range(5):
        db_session.add(
            VocabularyList(
                skritter_list_id=f"skritter-list-{i}",
                name=f"List {i}",
            )
        )

    db_session.flush()

    response = client.get("/vocabulary-lists?limit=2&offset=2")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 2
    assert len(data["items"]) == 2

    # Ordered by id ascending, so offset=2 skips the first two lists created.
    assert [item["name"] for item in data["items"]] == [
        "List 2",
        "List 3",
    ]


def test_get_vocabulary_list_returns_detail_with_items(client, db_session):
    vocab_list = VocabularyList(
        skritter_list_id="5490369014333440",
        name="Love & Relationships",
    )

    item_1 = VocabularyItem(
        skritter_vocab_id="zh-爱-0",
        language="zh",
        writing="爱",
        reading="ai4",
        definition_en="love",
    )

    item_2 = VocabularyItem(
        skritter_vocab_id="zh-心-0",
        language="zh",
        writing="心",
        reading="xin1",
        definition_en="heart",
    )

    vocab_list.items.append(item_1)
    vocab_list.items.append(item_2)

    db_session.add(vocab_list)
    db_session.flush()

    response = client.get(f"/vocabulary-lists/{vocab_list.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == vocab_list.id
    assert data["skritter_list_id"] == "5490369014333440"
    assert data["name"] == "Love & Relationships"
    assert data["item_count"] == 2

    assert data["items"] == [
        {
            "id": item_1.id,
            "skritter_vocab_id": "zh-爱-0",
            "language": "zh",
            "writing": "爱",
            "reading": "ai4",
            "definition_en": "love",
        },
        {
            "id": item_2.id,
            "skritter_vocab_id": "zh-心-0",
            "language": "zh",
            "writing": "心",
            "reading": "xin1",
            "definition_en": "heart",
        },
    ]


def test_get_vocabulary_list_returns_404_for_unknown_id(client):
    response = client.get("/vocabulary-lists/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Vocabulary list 999999 not found"}


def test_archived_lists_are_hidden(client, db_session):
    active = VocabularyList(skritter_list_id="active", name="Active")
    archived = VocabularyList(
        skritter_list_id="gone", name="Gone", archived_at=datetime.now(UTC)
    )
    db_session.add_all([active, archived])
    db_session.flush()

    body = client.get("/vocabulary-lists").json()
    assert [item["name"] for item in body["items"]] == ["Active"]
    assert body["total"] == 1

    assert client.get(f"/vocabulary-lists/{archived.id}").status_code == 404
    assert client.get(f"/vocabulary-lists/{active.id}").status_code == 200
