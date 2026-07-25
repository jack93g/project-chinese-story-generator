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

@respx.mock
def test_get_list_notifies_on_response():
    received = []
    client = SkritterClient("my_token", on_response=lambda *args: received.append(args))

    api_response = {
        "VocabList": {"id": "123", "name": "My List", "sections": []},
        "statusCode": 200,
    }
    respx.get(
        "https://legacy.skritter.com/api/v0/vocablists/123"
    ).mock(return_value=httpx.Response(200, json=api_response))

    client.get_list("123")

    assert len(received) == 1
    path, params, status, body = received[0]
    assert path == "/vocablists/123"
    assert status == 200
    assert body == api_response


@respx.mock
def test_get_list_notifies_on_response_even_when_request_fails():
    received = []
    client = SkritterClient("my_token", on_response=lambda *args: received.append(args))

    respx.get(
        "https://legacy.skritter.com/api/v0/vocablists/does-not-exist"
    ).mock(return_value=httpx.Response(404, json={"error": "not found"}))

    try:
        client.get_list("does-not-exist")
        assert False, "expected HTTPStatusError to propagate"
    except httpx.HTTPStatusError:
        pass

    # The failure was still captured before the exception propagated.
    assert len(received) == 1
    path, params, status, body = received[0]
    assert path == "/vocablists/does-not-exist"
    assert status == 404
    assert body == {"error": "not found"}


@respx.mock
def test_get_lists_notifies_per_page():
    received = []
    client = SkritterClient("my_token", on_response=lambda *args: received.append(args))

    page_one = {
        "VocabLists": [{"id": "1", "name": "List One"}],
        "cursor": "next-page",
    }
    page_two = {
        "VocabLists": [{"id": "2", "name": "List Two"}],
    }

    route = respx.get("https://legacy.skritter.com/api/v0/vocablists")
    route.side_effect = [
        httpx.Response(200, json=page_one),
        httpx.Response(200, json=page_two),
    ]

    result = client.get_lists()

    assert result == [
        {"id": "1", "name": "List One"},
        {"id": "2", "name": "List Two"},
    ]
    # One notify call per page fetched.
    assert len(received) == 2
    assert received[0][2] == 200
    assert received[0][3] == page_one
    assert received[1][3] == page_two