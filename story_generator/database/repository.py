from story_generator.vocabulary.models import VocabularyItem

class VocabularyRepository:
    def __init__(self, connection):
        self.connection = connection

    def insert_vocab(self, vocab: VocabularyItem):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO vocabulary_items (
                skritter_id,
                language,
                writing,
                reading,
                definition_en
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                vocab.skritter_vocab_id,
                vocab.language,
                vocab.writing,
                vocab.reading,
                vocab.definition_en,
            ),
        )

        self.connection.commit()