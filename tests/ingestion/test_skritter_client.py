import httpx
import respx
from story_generator.ingestion.skritter_client import SkritterClient


def test_client_sets_authorization_header():
    client = SkritterClient("my_token")

    assert client.client.headers["Authorization"] == "Bearer my_token"

@respx.mock
def test_get_list_returns_json():
    client = SkritterClient("my_token")

    expected = {
        "VocabList": {
            "id": "5667140514938880",
            "name": "Discussing social concepts, stereotypes etc",
            "lang": "zh",
            "sections": [
                {
                    "rows": [
                        {
                            "vocabId": "zh-刻板印象-0",
                            "tradVocabId": "zh-刻板印象-2"
                        }
                    ]
                }
            ]
        },
        "statusCode": 200
    }
    respx.get(
    "https://legacy.skritter.com/api/v0/vocablists/5667140514938880"
    ).mock(
        return_value=httpx.Response(
            200,
            json=expected,
        )
    )
    


    result = client.get_list("5667140514938880")

    assert result == expected


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
                    "en": "Stereotype"
                }
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