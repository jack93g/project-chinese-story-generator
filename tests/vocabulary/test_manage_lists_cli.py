import pytest

from story_generator.cli.lists import run
from story_generator.vocabulary.persistence.models import VocabularyList
from story_generator.vocabulary.service import SkritterListNotFoundError

pytestmark = pytest.mark.db


@pytest.fixture
def lists(db_session):
    basics = VocabularyList(skritter_list_id="111", name="Basics")
    radicals = VocabularyList(skritter_list_id="222", name="Radicals")
    db_session.add_all([basics, radicals])
    db_session.flush()
    return basics, radicals


def test_hide_then_show(db_session, client, lists):
    basics, radicals = lists

    assert run(["hide", "222"], db_session) == "Hidden: 'Radicals'."
    names = [item["name"] for item in client.get("/vocabulary-lists").json()["items"]]
    assert names == ["Basics"]
    assert client.get(f"/vocabulary-lists/{radicals.id}").status_code == 404

    assert run(["show", "222"], db_session) == "Visible again: 'Radicals'."
    names = [item["name"] for item in client.get("/vocabulary-lists").json()["items"]]
    assert names == ["Basics", "Radicals"]


def test_unknown_id_changes_nothing(db_session, lists):
    basics, _ = lists

    with pytest.raises(SkritterListNotFoundError, match="999"):
        run(["hide", "111", "999"], db_session)

    db_session.refresh(basics)
    assert basics.hidden is False


def test_list_shows_status(db_session, lists):
    run(["hide", "222"], db_session)

    lines = run(["list"], db_session).splitlines()
    radicals = next(line for line in lines if line.endswith("Radicals"))
    assert radicals.split()[:3] == ["222", "0", "hidden"]
