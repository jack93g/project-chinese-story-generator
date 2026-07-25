import os

from dotenv import load_dotenv

load_dotenv()


def get_skritter_access_token() -> str:
    token = os.getenv("SKRITTER_ACCESS_TOKEN")
    if token is None:
        raise RuntimeError(
            "SKRITTER_ACCESS_TOKEN environment variable is not set. "
            "Add it to your .env file."
        )
    return token