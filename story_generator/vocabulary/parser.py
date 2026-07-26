from story_generator.vocabulary.types import SkritterVocabularyRecord


def parse_vocab(response: dict) -> SkritterVocabularyRecord:
    vocab = response["Vocabs"][0]

    definition = (
        vocab.get("customDefinition")
        or vocab.get("definitions", {}).get("en", "")
    )

    return SkritterVocabularyRecord(
        skritter_vocab_id=vocab["id"],
        language=vocab.get("language") or vocab["lang"],
        writing=vocab["writing"],
        reading=vocab["reading"],
        definition_en=definition,
    )
