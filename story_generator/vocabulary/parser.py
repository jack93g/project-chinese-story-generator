from story_generator.ingestion.schemas import (
    SkritterVocabularyResponse,
    validate_skritter_response,
)
from story_generator.vocabulary.types import SkritterVocabularyRecord


def parse_vocab(response: dict) -> SkritterVocabularyRecord:
    vocab = validate_skritter_response(
        SkritterVocabularyResponse, response, "/vocabs"
    ).vocabs[0]

    definition = vocab.customDefinition or vocab.definitions.en or ""

    return SkritterVocabularyRecord(
        skritter_vocab_id=vocab.id,
        language=vocab.language or vocab.lang,
        writing=vocab.writing,
        reading=vocab.reading,
        definition_en=definition,
    )
