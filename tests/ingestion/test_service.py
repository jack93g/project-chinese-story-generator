from unittest.mock import Mock

from story_generator.ingestion.service import IngestionService
from story_generator.vocabulary.models import VocabularyItem


def test_import_list():

    client = Mock()
    repository = Mock()

    client.get_list.return_value = {
        "VocabList": {
            "vocab_ids": [
                "zh-你好-0",
                "zh-谢谢-0",
            ]
        }
    }

    client.get_vocabs.side_effect = [
        {
            "Vocabs": [
                {
                    "id": "zh-你好-0",
                    "language": "zh",
                    "writing": "你好",
                    "reading": "ni3 hao3",
                    "definitions": {"en": "hello"},
                }
            ]
        },
        {
            "Vocabs": [
                {
                    "id": "zh-谢谢-0",
                    "language": "zh",
                    "writing": "谢谢",
                    "reading": "xie4 xie",
                    "definitions": {"en": "thanks"},
                }
            ]
        },
    ]

    service = IngestionService(client, repository)

    service.import_list("123")

    assert repository.insert_vocab.call_count == 2