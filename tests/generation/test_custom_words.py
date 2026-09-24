import pytest
from pydantic import ValidationError

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.prompts.builder import (
    CURRENT_PROMPT_VERSION,
    build_prompt,
)
from story_generator.generation.providers.fake import FakeStoryGenerationProvider
from story_generator.generation.providers.types import GenerationRequestInput
from story_generator.generation.schemas import CreateGenerationRequestSchema
from story_generator.generation.vocabulary_selection import (
    EmptyVocabularyListError,
    select_vocabulary,
)
from story_generator.generation.worker import GenerationWorker
from story_generator.stories.persistence.models import Story
from story_generator.vocabulary.persistence.models import VocabularyItem, VocabularyList
from story_generator.vocabulary.persistence.repository import VocabularyRepository

BASE = dict(target_hsk_level=2, target_word_count=150, target_vocabulary_count=5)


# ---- schema (no database) ----


def test_schema_accepts_custom_words_without_a_list():
    schema = CreateGenerationRequestSchema(custom_words=["菜单", "饭馆"], **BASE)

    assert schema.vocabulary_list_id is None
    assert schema.custom_words == ["菜单", "饭馆"]


def test_schema_requires_a_list_or_custom_words():
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(**BASE)


def test_schema_strips_dedupes_and_drops_blank_custom_words():
    schema = CreateGenerationRequestSchema(
        vocabulary_list_id=1, custom_words=[" 菜单 ", "菜单", "", "  ", "饭馆"], **BASE
    )

    assert schema.custom_words == ["菜单", "饭馆"]


@pytest.mark.parametrize(
    "word",
    ["hello", "菜单 and more", "菜单。", "菜\n单", "字" * 21],
)
def test_schema_rejects_non_chinese_or_overlong_custom_words(word):
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(vocabulary_list_id=1, custom_words=[word], **BASE)


def test_schema_rejects_more_custom_words_than_target_count():
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(
            custom_words=["一", "二", "三"],
            **{**BASE, "target_vocabulary_count": 2},
        )


def test_schema_rejects_more_than_fifteen_custom_words():
    words = [f"词{chr(0x4E00 + i)}" for i in range(16)]
    with pytest.raises(ValidationError):
        CreateGenerationRequestSchema(
            custom_words=words, **{**BASE, "target_vocabulary_count": 15}
        )


def test_schema_dedupes_before_applying_the_count_limit():
    schema = CreateGenerationRequestSchema(custom_words=["菜单"] * 20, **BASE)

    assert schema.custom_words == ["菜单"]


# ---- prompt v2 (no database) ----


def _prompt_request(snapshot, prompt_version="story-v2"):
    return GenerationRequestInput(
        target_hsk_level=2,
        target_word_count=150,
        target_vocabulary_count=len(snapshot),
        vocabulary_snapshot=snapshot,
        prompt_version=prompt_version,
    )


def test_current_prompt_version_asks_for_a_glossary_of_custom_words():
    prompt = build_prompt(
        _prompt_request(
            [{"id": 2, "writing": "饭馆", "reading": None, "definition_en": None}],
            prompt_version=CURRENT_PROMPT_VERSION,
        )
    )

    assert '"glossary"' in prompt
    assert "glossary entry for each of these words: 饭馆" in prompt


def test_v2_prompt_omits_missing_reading_and_definition():
    prompt = build_prompt(
        _prompt_request(
            [
                {
                    "id": 1,
                    "writing": "菜单",
                    "reading": "càidān",
                    "definition_en": "menu",
                },
                {"id": 2, "writing": "饭馆", "reading": None, "definition_en": None},
            ]
        )
    )

    assert "- 菜单 (càidān): menu" in prompt
    assert "- 饭馆\n" in prompt
    assert "None" not in prompt


# ---- database ----


def _make_list(db_session, *, skritter_list_id: str, writings: list[str]):
    vocab_list = VocabularyList(skritter_list_id=skritter_list_id, name="Test list")
    db_session.add(vocab_list)
    db_session.flush()
    for i, writing in enumerate(writings):
        item = VocabularyItem(
            skritter_vocab_id=f"{skritter_list_id}-{i}",
            language="zh",
            writing=writing,
            reading=f"py{i}",
            definition_en=f"def {i}",
        )
        db_session.add(item)
        db_session.flush()
        vocab_list.items.append(item)
    db_session.flush()
    return vocab_list


@pytest.mark.db
def test_get_or_create_custom_items_creates_then_reuses(db_session):
    repo = VocabularyRepository(db_session)

    first = repo.get_or_create_custom_items(["菜单", "饭馆"])
    second = repo.get_or_create_custom_items(["饭馆", "菜单"])

    assert [i.writing for i in first] == ["菜单", "饭馆"]
    assert [i.id for i in second] == [first[1].id, first[0].id]
    assert all(i.skritter_vocab_id is None for i in first)
    assert all(i.reading is None and i.definition_en is None for i in first)


@pytest.mark.db
def test_get_or_create_custom_items_reuses_existing_skritter_item(db_session):
    vocab_list = _make_list(db_session, skritter_list_id="reuse", writings=["菜单"])
    skritter_item = vocab_list.items[0]

    [resolved] = VocabularyRepository(db_session).get_or_create_custom_items(["菜单"])

    assert resolved.id == skritter_item.id
    assert resolved.definition_en == "def 0"


@pytest.mark.db
def test_vocabulary_listing_excludes_custom_items(db_session):
    repo = VocabularyRepository(db_session)
    repo.get_or_create_custom_items(["独特"])
    before = repo.count()
    _make_list(db_session, skritter_list_id="listing", writings=["普通"])

    assert repo.count() == before + 1
    assert all(i.skritter_vocab_id is not None for i in repo.list_page(100, 0))


@pytest.mark.db
def test_select_puts_custom_first_and_fills_from_list_without_duplicates(db_session):
    vocab_list = _make_list(
        db_session, skritter_list_id="mix", writings=["甲", "乙", "丙", "丁"]
    )
    custom = VocabularyRepository(db_session).get_or_create_custom_items(["丙", "新词"])

    result = select_vocabulary(db_session, vocab_list, 4, custom)

    assert [e["writing"] for e in result] == ["丙", "新词", "甲", "乙"]


@pytest.mark.db
def test_select_custom_only_and_custom_filling_all_slots(db_session):
    vocab_list = _make_list(db_session, skritter_list_id="full", writings=["甲", "乙"])
    custom = VocabularyRepository(db_session).get_or_create_custom_items(["新词"])

    assert [e["writing"] for e in select_vocabulary(db_session, None, 3, custom)] == [
        "新词"
    ]
    assert [
        e["writing"] for e in select_vocabulary(db_session, vocab_list, 1, custom)
    ] == ["新词"]


@pytest.mark.db
def test_select_with_empty_list_and_no_custom_still_raises(db_session):
    vocab_list = _make_list(db_session, skritter_list_id="empty", writings=[])

    with pytest.raises(EmptyVocabularyListError):
        select_vocabulary(db_session, vocab_list, 3)


@pytest.mark.db
def test_post_custom_words_only_end_to_end(client, db_session):
    response = client.post(
        "/story-generations",
        json={**BASE, "target_vocabulary_count": 2, "custom_words": ["菜单", "饭馆"]},
    )
    assert response.status_code == 202
    request_id = response.json()["id"]

    request = db_session.get(StoryGenerationRequest, request_id)
    assert request.vocabulary_list_id is None
    assert request.prompt_version == CURRENT_PROMPT_VERSION
    assert [e["writing"] for e in request.selected_vocabulary_snapshot] == [
        "菜单",
        "饭馆",
    ]

    provider = FakeStoryGenerationProvider(
        scenario="success", raw_response='{"title": "故事", "body": "菜单和饭馆。"}'
    )
    GenerationWorker(provider=provider).run_once(db_session)
    db_session.commit()

    status = client.get(f"/story-generations/{request_id}").json()
    assert status["status"] == "succeeded"
    story = db_session.get(Story, status["story_id"])
    assert {i.writing for i in story.vocabulary_items} == {"菜单", "饭馆"}


@pytest.mark.db
def test_post_list_plus_custom_words(client, db_session):
    vocab_list = _make_list(
        db_session, skritter_list_id="post-mix", writings=["甲", "乙", "丙"]
    )

    response = client.post(
        "/story-generations",
        json={
            **BASE,
            "target_vocabulary_count": 3,
            "vocabulary_list_id": vocab_list.id,
            "custom_words": ["新词"],
        },
    )

    assert response.status_code == 202
    request = db_session.get(StoryGenerationRequest, response.json()["id"])
    assert [e["writing"] for e in request.selected_vocabulary_snapshot] == [
        "新词",
        "甲",
        "乙",
    ]


@pytest.mark.db
def test_post_without_list_or_custom_words_returns_422(client):
    assert client.post("/story-generations", json=BASE).status_code == 422


@pytest.mark.db
def test_post_english_custom_word_returns_422(client):
    response = client.post(
        "/story-generations", json={**BASE, "custom_words": ["hello"]}
    )
    assert response.status_code == 422


# ---- glossary for custom words ----


def test_v2_prompt_requests_glossary_only_for_words_missing_details():
    with_gap = build_prompt(
        _prompt_request(
            [
                {
                    "id": 1,
                    "writing": "菜单",
                    "reading": "cai4dan1",
                    "definition_en": "menu",
                },
                {"id": 2, "writing": "饭馆", "reading": None, "definition_en": None},
            ]
        )
    )
    complete = build_prompt(
        _prompt_request(
            [
                {
                    "id": 1,
                    "writing": "菜单",
                    "reading": "cai4dan1",
                    "definition_en": "menu",
                }
            ]
        )
    )

    assert '"glossary"' in with_gap
    assert "for each of these words: 饭馆." in with_gap
    assert "glossary" not in complete


def test_parser_reads_glossary_and_drops_malformed_entries():
    from story_generator.generation.providers.parser import parse_structured_result
    from story_generator.generation.providers.types import UsageMetadata

    usage = UsageMetadata(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    raw = (
        '{"title": "故事", "body": "菜单。", "glossary": ['
        '{"writing": "饭馆", "reading": "fan4guan3", "definition_en": "restaurant"},'
        '"junk", {"reading": "x"}, {"writing": "点菜", "reading": 5}]}'
    )

    result = parse_structured_result(raw, usage)

    assert result.glossary == [
        {"writing": "饭馆", "reading": "fan4guan3", "definition_en": "restaurant"},
        {"writing": "点菜", "reading": None, "definition_en": None},
    ]
    assert (
        parse_structured_result(
            '{"title": "故事", "body": "菜单。", "glossary": "nope"}', usage
        ).glossary
        == []
    )


@pytest.mark.db
def test_worker_saves_glossary_on_custom_words_but_never_overwrites_skritter(
    client, db_session
):
    vocab_list = _make_list(db_session, skritter_list_id="gloss", writings=["菜单"])
    skritter_item = vocab_list.items[0]
    response = client.post(
        "/story-generations",
        json={**BASE, "target_vocabulary_count": 2, "custom_words": ["饭馆", "菜单"]},
    )
    assert response.status_code == 202

    provider = FakeStoryGenerationProvider(
        scenario="success",
        raw_response=(
            '{"title": "故事", "body": "菜单和饭馆。", "glossary": ['
            '{"writing": "饭馆", "reading": "fan4guan3", "definition_en": "restaurant"},'
            '{"writing": "菜单", "reading": "WRONG", "definition_en": "WRONG"}]}'
        ),
    )
    GenerationWorker(provider=provider).run_once(db_session)
    db_session.commit()

    custom = db_session.query(VocabularyItem).filter_by(writing="饭馆").one()
    assert (custom.reading, custom.definition_en) == ("fan4guan3", "restaurant")
    db_session.refresh(skritter_item)
    assert (skritter_item.reading, skritter_item.definition_en) == ("py0", "def 0")


@pytest.mark.db
def test_lookup_prefers_skritter_item_even_if_custom_row_is_older(db_session):
    repo = VocabularyRepository(db_session)
    [custom] = repo.get_or_create_custom_items(["菜单"])
    skritter = VocabularyItem(
        skritter_vocab_id="zh-菜单-0",
        language="zh",
        writing="菜单",
        reading="cai4dan1",
        definition_en="menu",
    )
    db_session.add(skritter)
    db_session.flush()
    assert custom.id < skritter.id

    [resolved] = repo.get_or_create_custom_items(["菜单"])

    assert resolved.id == skritter.id


@pytest.mark.db
def test_glossary_never_writes_to_skritter_rows(client, db_session):
    vocab_list = _make_list(db_session, skritter_list_id="partial", writings=["菜单"])
    item = vocab_list.items[0]
    item.definition_en = None
    db_session.flush()
    client.post(
        "/story-generations",
        json={
            **BASE,
            "vocabulary_list_id": vocab_list.id,
            "target_vocabulary_count": 1,
        },
    )

    provider = FakeStoryGenerationProvider(
        scenario="success",
        raw_response=(
            '{"title": "故事", "body": "菜单。", "glossary": '
            '[{"writing": "菜单", "reading": "OTHER", "definition_en": "menu"}]}'
        ),
    )
    GenerationWorker(provider=provider).run_once(db_session)
    db_session.commit()

    db_session.refresh(item)
    assert (item.reading, item.definition_en) == ("py0", None)


@pytest.mark.db
def test_post_more_custom_words_than_target_count_returns_422(client):
    response = client.post(
        "/story-generations",
        json={**BASE, "target_vocabulary_count": 2, "custom_words": ["一", "二", "三"]},
    )

    assert response.status_code == 422
