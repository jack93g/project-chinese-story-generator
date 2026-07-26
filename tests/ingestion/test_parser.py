from story_generator.vocabulary.parser import parse_vocab
from story_generator.vocabulary.types import SkritterVocabularyRecord


def test_parse_vocab():
    raw = {
        "Vocabs": [
            {
                "id": "zh-刻板印象-0",
                "language":"zh",
                "writing": "刻板印象",
                "reading": "ke4ban3yin4xiang4",
                "definitions": {
                    "en": "Stereotype"
                },
            }
        ]
    }

    result = parse_vocab(raw)

    assert result == SkritterVocabularyRecord(
        skritter_vocab_id="zh-刻板印象-0",
        language="zh",
        writing="刻板印象",
        reading="ke4ban3yin4xiang4",
        definition_en="Stereotype",
    )
