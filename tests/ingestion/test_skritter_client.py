import httpx
import respx

from story_generator.ingestion.skritter_client import SkritterClient


def test_client_sets_authorization_header():
    client = SkritterClient("my_token")

    assert client.client.headers["Authorization"] == "Bearer my_token"


@respx.mock
def test_get_list_returns_json():
    client = SkritterClient("my_token")

    api_response = {
        "VocabList": {
            "id": "123",
            "name": "My List",
            "sections": [
                {
                    "rows": [
                        {"vocabId": "v1"},
                        {"vocabId": "v2"},
                    ]
                }
            ],
        },
        "statusCode": 200,
    }

    respx.get(
        "https://legacy.skritter.com/api/v0/vocablists/5667140514938880"
    ).mock(
        return_value=httpx.Response(
            200,
            json=api_response,
        )
    )

    result = client.get_list("5667140514938880")

    assert result == {
        "id": "123",
        "name": "My List",
        "vocab_ids": ["v1", "v2"],
    }


@respx.mock
def test_get_vocab_returns_json():
    client = SkritterClient("my_token")

    expected = {
        "Vocabs": [
            {
                "id": "zh-刻板印象-0",
                "writing": "刻板印象",
                "reading": "ke4ban3yin4xiang4",
                "definitions": {
                    "en": "Stereotype",
                },
            }
        ],
        "statusCode": 200,
    }

    respx.get(
        "https://legacy.skritter.com/api/v0/vocabs",
        params={"ids": "zh-刻板印象-0"},
    ).mock(
        return_value=httpx.Response(
            200,
            json=expected,
        )
    )

    result = client.get_vocabs("zh-刻板印象-0")

    assert result == expected