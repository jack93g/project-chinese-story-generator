import pytest

from story_generator.vocabulary.persistence.models import VocabularyItem


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
