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

        return response.json()
    
    def get_vocabs(self, vocab_id: str):


        response = self.client.get(
            f"{self.BASE_URL}/vocabs",
            params={"ids": vocab_id},
    )
        response.raise_for_status()

        return response.json()