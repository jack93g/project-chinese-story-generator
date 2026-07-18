import httpx


class SkritterClient:
    BASE_URL = "https://legacy.skritter.com/api/v0"

    def __init__(self, access_token: str):
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }
        )

    def get_list(self, list_id: str):
        url = f"{self.BASE_URL}/vocablists/{list_id}"

        response = self.client.get(url)
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
        response = self.client.get(
            f"{self.BASE_URL}/vocabs",
            params={"ids": vocab_id},
        )
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
    
