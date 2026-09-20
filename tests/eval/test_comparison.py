"""
No database needed — FakeStoryGenerationProvider and the eval fixtures
are both plain Python, so this whole module runs under
`pytest -m "not db"` (or with no DB configured at all).
"""

from story_generator.eval.comparison import (
    ProviderSpec,
    compute_coverage,
    load_outcomes,
    run_comparison,
    run_single,
    to_json,
    to_markdown,
)
from story_generator.eval.fixtures import EVAL_FIXTURES, EvalFixture
from story_generator.generation.providers.fake import FakeStoryGenerationProvider
from story_generator.generation.providers.types import GenerationResult, UsageMetadata


def _fixture(vocabulary_snapshot, **overrides) -> EvalFixture:
    defaults = dict(
        name="test_fixture",
        category="hsk_level",
        description="",
        target_hsk_level=3,
        target_word_count=200,
        target_vocabulary_count=len(vocabulary_snapshot),
        vocabulary_snapshot=vocabulary_snapshot,
    )
    defaults.update(overrides)
    return EvalFixture(**defaults)


def test_compute_coverage_full_match():
    snapshot = [
        {"id": 1, "writing": "你好", "reading": "nǐhǎo", "definition_en": "hello"}
    ]
    result = GenerationResult(
        title="标题", body="你好，世界。", usage=UsageMetadata(1, 1, 2)
    )

    info = compute_coverage(snapshot, result)

    assert info["coverage"] == 1.0
    assert info["missing_vocabulary"] == []
    assert info["used_vocabulary_count"] == 1


def test_compute_coverage_missing_word():
    snapshot = [
        {"id": 1, "writing": "你好", "reading": "nǐhǎo", "definition_en": "hello"},
        {"id": 2, "writing": "再见", "reading": "zàijiàn", "definition_en": "goodbye"},
    ]
    result = GenerationResult(
        title="标题", body="你好，世界。", usage=UsageMetadata(1, 1, 2)
    )

    info = compute_coverage(snapshot, result)

    assert info["coverage"] == 0.5
    assert info["missing_vocabulary"] == [{"id": 2, "writing": "再见"}]


def test_run_single_success_records_coverage_and_latency():
    snapshot = [
        {"id": 1, "writing": "菜单", "reading": "càidān", "definition_en": "menu"}
    ]
    fixture = _fixture(snapshot)
    provider = FakeStoryGenerationProvider(scenario="success")
    spec = ProviderSpec(
        label="fake",
        provider=provider,
        model="fake-model",
        base_url="https://fake.test/v1/chat/completions",
    )

    outcome = run_single(fixture, spec)

    assert outcome.schema_valid is True
    assert outcome.base_url == "https://fake.test/v1/chat/completions"
    assert (
        outcome.coverage == 1.0
    )  # FakeStoryGenerationProvider's default body contains 菜单
    assert outcome.meets_coverage_threshold is True
    assert outcome.title and outcome.body


def test_run_single_provider_error_recorded_not_raised():
    snapshot = [
        {"id": 1, "writing": "菜单", "reading": "càidān", "definition_en": "menu"}
    ]
    fixture = _fixture(snapshot)
    provider = FakeStoryGenerationProvider(scenario="timeout")
    spec = ProviderSpec(
        label="fake",
        provider=provider,
        model="fake-model",
        base_url="https://fake.test/v1/chat/completions",
    )

    outcome = run_single(fixture, spec)

    assert outcome.schema_valid is False
    assert outcome.error_code == "ProviderTimeoutError"
    assert outcome.coverage is None


def test_run_comparison_covers_full_matrix():
    fixtures = [
        _fixture(
            [
                {
                    "id": 1,
                    "writing": "菜单",
                    "reading": "càidān",
                    "definition_en": "menu",
                }
            ],
            name="f1",
        ),
        _fixture(
            [{"id": 2, "writing": "水", "reading": "shuǐ", "definition_en": "water"}],
            name="f2",
        ),
    ]
    specs = [
        ProviderSpec(
            label="fake-a",
            provider=FakeStoryGenerationProvider(scenario="success"),
            model="a",
            base_url="https://fake-a.test",
        ),
        ProviderSpec(
            label="fake-b",
            provider=FakeStoryGenerationProvider(scenario="success"),
            model="b",
            base_url="https://fake-b.test",
        ),
    ]

    outcomes = run_comparison(fixtures, specs)

    assert len(outcomes) == 4
    pairs = {(o.fixture_name, o.provider_label) for o in outcomes}
    assert pairs == {
        ("f1", "fake-a"),
        ("f1", "fake-b"),
        ("f2", "fake-a"),
        ("f2", "fake-b"),
    }


def test_eval_fixtures_cover_required_categories():
    categories = {f.category for f in EVAL_FIXTURES}
    assert {"hsk_level", "ambiguous_words", "short_list", "mixed_known"}.issubset(
        categories
    )


def test_short_list_fixture_has_fewer_items_than_target_count():
    short_list = next(f for f in EVAL_FIXTURES if f.category == "short_list")
    assert len(short_list.vocabulary_snapshot) < short_list.target_vocabulary_count


def test_to_markdown_renders_supplied_manual_quality_notes():
    snapshot = [
        {"id": 1, "writing": "菜单", "reading": "càidān", "definition_en": "menu"}
    ]
    fixture = _fixture(snapshot)
    provider = FakeStoryGenerationProvider(scenario="success")
    spec = ProviderSpec(
        label="fake",
        provider=provider,
        model="fake-model",
        base_url="https://fake.test",
    )
    outcome = run_single(fixture, spec)
    outcome.manual_quality_notes = "Natural phrasing, correct sense of 菜单."

    markdown = to_markdown([outcome])

    assert "Natural phrasing, correct sense of 菜单." in markdown
    assert "_(fill in)_" not in markdown


def test_to_markdown_still_shows_placeholder_when_notes_absent():
    snapshot = [
        {"id": 1, "writing": "菜单", "reading": "càidān", "definition_en": "menu"}
    ]
    fixture = _fixture(snapshot)
    provider = FakeStoryGenerationProvider(scenario="success")
    spec = ProviderSpec(
        label="fake",
        provider=provider,
        model="fake-model",
        base_url="https://fake.test",
    )
    outcome = run_single(fixture, spec)

    markdown = to_markdown([outcome])

    assert "_(fill in)_" in markdown


def test_to_markdown_escapes_pipes_and_newlines_in_notes_table_cell():
    snapshot = [
        {"id": 1, "writing": "菜单", "reading": "càidān", "definition_en": "menu"}
    ]
    fixture = _fixture(snapshot)
    provider = FakeStoryGenerationProvider(scenario="success")
    spec = ProviderSpec(
        label="fake",
        provider=provider,
        model="fake-model",
        base_url="https://fake.test",
    )
    outcome = run_single(fixture, spec)
    outcome.manual_quality_notes = "Uses A | B\nand a second line."

    markdown = to_markdown([outcome])

    # the raw pipe/newline would break the table row if left unescaped
    assert "Uses A \\| B<br>and a second line." in markdown
    # table structure should still have exactly one row per outcome in Summary:
    # header + separator + one data row = 3 lines starting with "|"
    summary_section = markdown.split("## Summary")[1].split("## ")[0]
    table_lines = [
        line for line in summary_section.splitlines() if line.startswith("|")
    ]
    assert len(table_lines) == 3


def test_load_outcomes_round_trips_through_json_including_notes():
    snapshot = [
        {"id": 1, "writing": "菜单", "reading": "càidān", "definition_en": "menu"}
    ]
    fixture = _fixture(snapshot)
    provider = FakeStoryGenerationProvider(scenario="success")
    spec = ProviderSpec(
        label="fake",
        provider=provider,
        model="fake-model",
        base_url="https://fake.test",
    )
    outcome = run_single(fixture, spec)
    outcome.manual_quality_notes = "Reviewed: looks good."

    json_text = to_json([outcome])

    import json as json_module
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.json"
        path.write_text(json_text, encoding="utf-8")

        loaded = load_outcomes(path)

    assert len(loaded) == 1
    assert loaded[0] == outcome
    assert loaded[0].manual_quality_notes == "Reviewed: looks good."

    # sanity: raw JSON actually contains the note, confirming it's the
    # persisted source of truth described in the module docstring
    raw = json_module.loads(json_text)
    assert raw[0]["manual_quality_notes"] == "Reviewed: looks good."


def test_render_workflow_end_to_end(tmp_path):
    """
    Simulates the full documented review workflow: run -> hand-edit
    notes in the JSON -> render -> markdown reflects the edited notes.
    """
    snapshot = [
        {"id": 1, "writing": "菜单", "reading": "càidān", "definition_en": "menu"}
    ]
    fixture = _fixture(snapshot)
    provider = FakeStoryGenerationProvider(scenario="success")
    spec = ProviderSpec(
        label="fake",
        provider=provider,
        model="fake-model",
        base_url="https://fake.test",
    )
    outcome = run_single(fixture, spec)

    json_path = tmp_path / "report.json"
    json_path.write_text(to_json([outcome]), encoding="utf-8")

    # simulate a human hand-editing the JSON
    import json as json_module

    data = json_module.loads(json_path.read_text(encoding="utf-8"))
    data[0]["manual_quality_notes"] = "Human reviewed this after the fact."
    json_path.write_text(json_module.dumps(data, ensure_ascii=False), encoding="utf-8")

    reloaded = load_outcomes(json_path)
    markdown = to_markdown(reloaded)

    assert "Human reviewed this after the fact." in markdown
