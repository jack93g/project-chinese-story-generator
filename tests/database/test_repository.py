from story_generator.database.connection import get_connection
from story_generator.database.repository import VocabularyRepository
from story_generator.vocabulary.models import VocabularyItem


def test_insert_vocab():
    conn = get_connection()
    repo = VocabularyRepository(conn)

    vocab = VocabularyItem(
        skritter_vocab_id="test-123",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )

    repo.insert_vocab(vocab)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT skritter_id, writing, reading, definition_en
        FROM vocabulary_items
        WHERE skritter_id = %s
        """,
        ("test-123",),
    )

    row = cur.fetchone()

    assert row == (
        "test-123",
        "你好",
        "ni3 hao3",
        "hello",
    )

    conn.close()