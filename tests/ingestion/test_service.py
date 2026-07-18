from unittest.mock import Mock

from story_generator.ingestion.service import IngestionService


def test_import_list():
    client = Mock()
    repository = Mock()

    client.get_list.return_value = {
        "id": "123",
        "name": "Test List",
        "vocab_ids": [
            "zh-你好-0",
            "zh-谢谢-0",
        ],
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

    repository.ensure_list.return_value = 1
    repository.ensure_vocab.side_effect = [10, 11]

    service = IngestionService(client, repository)

    result = service.import_list("123")

    assert result == {
        "imported": 0,
        "skipped": 0,
    }

    repository.ensure_list.assert_called_once_with("123", "Test List")

    assert repository.ensure_vocab.call_count == 2
    assert repository.link_vocab_to_list.call_count == 2