import httpx


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

    def get_list(self, list_id: str):
        url = f"{self.BASE_URL}/vocablists/{list_id}"
        request_path = f"/vocablists/{list_id}"

        response = self.client.get(url)
        self._notify(request_path, {}, response)
        response.raise_for_status()

        data = response.json()

        vocab_list = data["VocabList"]

        vocab_ids = []

        for section in vocab_list["sections"]:
            for row in section["rows"]:
                vocab_ids.append(row["vocabId"])

        return {
            "id": vocab_list["id"],
            "name": vocab_list["name"],
            "vocab_ids": vocab_ids,
        }

    def get_vocabs(self, vocab_id: str):
        params = {"ids": vocab_id}
        response = self.client.get(f"{self.BASE_URL}/vocabs", params=params)
        self._notify("/vocabs", params, response)
        response.raise_for_status()

        return response.json()

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

            data = response.json()

            all_lists.extend(data["VocabLists"])

            cursor = data.get("cursor")

            if not cursor:
                break

        return [
            {
                "id": vocab_list["id"],
                "name": vocab_list["name"],
            }
            for vocab_list in all_lists
        ]
    
