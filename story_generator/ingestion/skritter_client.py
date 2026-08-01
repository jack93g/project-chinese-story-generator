import httpx

from story_generator.ingestion.schemas import (
    SkritterResponseError,
    SkritterVocabularyListResponse,
    SkritterVocabularyListsResponse,
    SkritterVocabularyResponse,
    validate_skritter_response,
)


class SkritterClient:
    BASE_URL = "https://legacy.skritter.com/api/v0"

    def __init__(self, access_token: str, on_response=None):
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }
        )
        # Optional hook: called as on_response(request_path, request_params,
        # response_status, payload) after every successful request. Lets
        # callers (e.g. the ingestion service) capture raw responses for
        # persistence without this client knowing anything about storage.
        self.on_response = on_response

    def _notify(self, request_path, request_params, response):
        if self.on_response is not None:
            try:
                body = response.json()
            except ValueError:
                # Non-JSON error body (e.g. HTML error page, empty body) —
                # still record something rather than losing the payload entirely.
                body = {"_raw_text": response.text}
            self.on_response(request_path, request_params, response.status_code, body)

    @staticmethod
    def _json(response: httpx.Response, endpoint: str) -> object:
        try:
            return response.json()
        except ValueError as exc:
            raise SkritterResponseError(
                f"Malformed Skritter response from {endpoint}: invalid JSON body"
            ) from exc

    def get_list(self, list_id: str):
        url = f"{self.BASE_URL}/vocablists/{list_id}"
        request_path = f"/vocablists/{list_id}"

        response = self.client.get(url)
        self._notify(request_path, {}, response)
        response.raise_for_status()

        parsed = validate_skritter_response(
            SkritterVocabularyListResponse, self._json(response, request_path), request_path
        )
        vocab_list = parsed.vocab_list
        vocab_ids = [row.vocabId for section in vocab_list.sections for row in section.rows]

        return {
            "id": vocab_list.id,
            "name": vocab_list.name,
            "vocab_ids": vocab_ids,
        }

    def get_vocab(self, vocab_id: str) -> dict:
        params = {"ids": vocab_id}
        response = self.client.get(f"{self.BASE_URL}/vocabs", params=params)
        self._notify("/vocabs", params, response)
        response.raise_for_status()

        data = self._json(response, "/vocabs")
        validate_skritter_response(SkritterVocabularyResponse, data, "/vocabs")
        return data

    def get_lists(self):
        all_lists = []
        cursor = None

        while True:
            params = {
                "sort": "custom",
                "limit": 100,
            }

            if cursor:
                params["cursor"] = cursor

            response = self.client.get(
                f"{self.BASE_URL}/vocablists",
                params=params,
            )
            self._notify("/vocablists", params, response)
            response.raise_for_status()

            parsed = validate_skritter_response(
                SkritterVocabularyListsResponse,
                self._json(response, "/vocablists"),
                "/vocablists",
            )
            all_lists.extend(parsed.vocab_lists)
            cursor = parsed.cursor

            if not cursor:
                break

        return [
            {
                "id": vocab_list.id,
                "name": vocab_list.name,
            }
            for vocab_list in all_lists
        ]
    
