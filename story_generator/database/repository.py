import psycopg

from story_generator.vocabulary.models import VocabularyItem


class Repository:
    def __init__(self, connection: psycopg.Connection):
        self.connection = connection

    def ensure_list(self, skritter_list_id: str, name: str) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO vocabulary_lists (
                    skritter_list_id,
                    name
                )
                VALUES (%s, %s)
                ON CONFLICT (skritter_list_id)
                DO NOTHING
                """,
                (skritter_list_id, name),
            )

            cursor.execute(
                """
                SELECT id
                FROM vocabulary_lists
                WHERE skritter_list_id = %s
                """,
                (skritter_list_id,),
            )

            list_id = cursor.fetchone()[0]

        self.connection.commit()

        return list_id

    def ensure_vocab(self, vocab: VocabularyItem) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO vocabulary_items (
                    skritter_vocab_id,
                    language,
                    writing,
                    reading,
                    definition_en
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (skritter_vocab_id)
                DO NOTHING
                """,
                (
                    vocab.skritter_vocab_id,
                    vocab.language,
                    vocab.writing,
                    vocab.reading,
                    vocab.definition_en,
                ),
            )

            cursor.execute(
                """
                SELECT id
                FROM vocabulary_items
                WHERE skritter_vocab_id = %s
                """,
                (vocab.skritter_vocab_id,),
            )

            vocab_id = cursor.fetchone()[0]

        self.connection.commit()

        return vocab_id

    def link_vocab_to_list(
        self,
        list_id: int,
        vocabulary_id: int,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO list_vocabulary (
                    list_id,
                    vocabulary_id
                )
                VALUES (%s, %s)
                ON CONFLICT (list_id, vocabulary_id)
                DO NOTHING
                """,
                (list_id, vocabulary_id),
            )

        self.connection.commit()