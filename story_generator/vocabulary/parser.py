from story_generator.vocabulary.models import VocabularyItem


def parse_vocab(response: dict) -> VocabularyItem:
    vocab = response["Vocabs"][0]

    definition = (
        vocab.get("customDefinition")
        or vocab.get("definitions", {}).get("en", "")
    )

    return VocabularyItem(
        skritter_vocab_id=vocab["id"],
        language=vocab.get("language") or vocab["lang"],
        writing=vocab["writing"],
        reading=vocab["reading"],
        definition_en=definition,
    )