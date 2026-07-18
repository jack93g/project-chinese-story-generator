from story_generator.database.connection import get_connection


def test_get_connection():
    conn = get_connection()

    assert conn is not None
    assert conn.closed is False

    conn.close()