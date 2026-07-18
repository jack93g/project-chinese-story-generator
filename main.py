import os

from dotenv import load_dotenv

from story_generator.database.connection import get_connection
from story_generator.database.repository import Repository
from story_generator.ingestion.service import IngestionService
from story_generator.ingestion.skritter_client import SkritterClient

load_dotenv()

client = SkritterClient(
    access_token=os.environ["SKRITTER_ACCESS_TOKEN"]
)

connection = get_connection()

repository = Repository(connection)

service = IngestionService(client, repository)

service.import_all_lists()