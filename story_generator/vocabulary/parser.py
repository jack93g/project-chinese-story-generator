from story_generator.vocabulary.models import VocabularyItem


def parse_vocab(raw):
    vocab = raw["Vocabs"][0]

    return VocabularyItem(
        skritter_vocab_id=vocab["id"],
        language=vocab["language"],
        writing=vocab["writing"],
        reading=vocab["reading"],
        definition_en=vocab["definitions"]["en"],
    )