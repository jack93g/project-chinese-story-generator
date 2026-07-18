from story_generator.database.connection import get_connection
from story_generator.database.repository import Repository
from story_generator.vocabulary.models import VocabularyItem


def test_ensure_vocab():
    conn = get_connection()
    repo = Repository(conn)

    vocab = VocabularyItem(
        skritter_vocab_id="test-123",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )

    repo.ensure_vocab(vocab)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT skritter_vocab_id, writing, reading, definition_en
        FROM vocabulary_items
        WHERE skritter_vocab_id = %s
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

def test_ensure_duplicate_vocab_does_not_raise():
    conn = get_connection()
    repo = Repository(conn)

    vocab = VocabularyItem(
        skritter_vocab_id="duplicate-test",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )

    cur = conn.cursor()
    cur.execute(
        "DELETE FROM vocabulary_items WHERE skritter_vocab_id = %s",
        ("duplicate-test",),
    )
    conn.commit()

    repo.ensure_vocab(vocab)

    # Importing the same vocab again should not raise an exception
    repo.ensure_vocab(vocab)

    conn.close()