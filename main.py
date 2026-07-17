from story_generator.ingestion.skritter_client import SkritterClient
import os

from dotenv import load_dotenv

load_dotenv()

access_token = os.getenv("SKRITTER_ACCESS_TOKEN")
