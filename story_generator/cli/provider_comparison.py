"""
CLI: python -m story_generator.cli.provider_comparison <run|render> ...

Two subcommands:

  run     Executes the full EVAL_FIXTURES matrix against one or more
          providers and writes a markdown + JSON comparison report to
          reports/provider-comparisons/. manual_quality_notes starts
          empty on every outcome — nothing here reads the transcripts
          for you.

  render  Re-renders the markdown report from a JSON report file,
          after a human has edited manual_quality_notes directly in
          that JSON. This is the persistence step for review notes:
          the JSON is the source of truth (see eval/comparison.py's
          module docstring); `render` is how those notes make it back
          into a readable markdown report.

Typical flow:
    python -m story_generator.cli.provider_comparison run --provider ...
    # -> writes reports/provider-comparisons/<ts>.json and .md
    # edit manual_quality_notes fields in <ts>.json by hand
    python -m story_generator.cli.provider_comparison render --input reports/provider-comparisons/<ts>.json
    # -> rewrites <ts>.md with those notes included

Standalone tool — `run` does not touch the database and does not
persist anything to story_generation_requests / raw_generation_payloads.
It exists to answer "should this provider/model be usable at all"
before that decision is wired into config.py / the worker.

Every candidate provider in `run` is spoken to via
OpenAIStoryGenerationProvider itself, not a new adapter class — Ollama
(and most local-model servers) expose an OpenAI-compatible
/chat/completions endpoint, which is exactly the case
OpenAIStoryGenerationProvider's docstring already calls out as
supported via a configurable base_url.

Examples:
    python -m story_generator.cli.provider_comparison run \\
      --provider "groq|https://api.groq.com/openai/v1/chat/completions|openai/gpt-oss-120b|OPENAI_API_KEY" \\
      --provider "ollama-qwen|http://localhost:11434/v1/chat/completions|qwen2.5:7b|OLLAMA_API_KEY"

    python -m story_generator.cli.provider_comparison render \\
      --input reports/provider-comparisons/2026-08-23T120000Z.json
"""

import argparse
import dataclasses
import datetime as dt
import os
from pathlib import Path

import httpx

from story_generator.eval.comparison import (
    ProviderSpec,
    load_outcomes,
    run_comparison,
    to_json,
    to_markdown,
)
from story_generator.eval.fixtures import EVAL_FIXTURES
from story_generator.generation.prompts.builder import (
    CURRENT_PROMPT_VERSION,
    PROMPT_BUILDERS,
)
from story_generator.generation.providers.openai import OpenAIStoryGenerationProvider

_PROVIDER_SPEC_HELP = (
    "Provider to include, repeatable. Format: "
    "LABEL|BASE_URL|MODEL|API_KEY_ENV_VAR. The pipe delimiter is used "
    "(instead of ':') because BASE_URL itself contains colons. "
    "API_KEY_ENV_VAR names an environment variable to read the key from; "
    "for servers like local Ollama that don't check the key, point it at "
    "any env var (even an unset one — an empty key is fine)."
)


def _build_provider_spec(spec_str: str) -> ProviderSpec:
    parts = spec_str.split("|")
    if len(parts) != 4:
        raise ValueError(
            f"Malformed --provider value: {spec_str!r}. Expected "
            "LABEL|BASE_URL|MODEL|API_KEY_ENV_VAR."
        )
    label, base_url, model, api_key_env = parts
    api_key = os.getenv(api_key_env, "")
    provider = OpenAIStoryGenerationProvider(
        client=httpx.Client(),
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
    return ProviderSpec(label=label, provider=provider, model=model, base_url=base_url)


def _run(args: argparse.Namespace) -> None:
    if not args.provider:
        raise SystemExit("--provider is required for `run`. See --help for the format.")

    if args.prompt_version not in PROMPT_BUILDERS:
        raise SystemExit(
            f"Unknown --prompt-version {args.prompt_version!r}. "
            f"Known: {', '.join(PROMPT_BUILDERS)}."
        )

    known_fixtures = {fixture.name for fixture in EVAL_FIXTURES}
    unknown = [name for name in args.fixture if name not in known_fixtures]
    if unknown:
        raise SystemExit(
            f"Unknown --fixture {', '.join(unknown)}. "
            f"Known: {', '.join(sorted(known_fixtures))}."
        )
    if args.repeat < 1:
        raise SystemExit("--repeat must be at least 1.")

    provider_specs = [_build_provider_spec(spec_str) for spec_str in args.provider]
    fixtures = [
        dataclasses.replace(fixture, prompt_version=args.prompt_version)
        for fixture in EVAL_FIXTURES
        if not args.fixture or fixture.name in args.fixture
    ]

    total = len(fixtures) * len(provider_specs) * args.repeat
    print(
        f"Running {len(fixtures)} fixtures x {len(provider_specs)} providers "
        f"x {args.repeat} = {total} generations (prompt {args.prompt_version})..."
    )
    outcomes = run_comparison(fixtures, provider_specs, repeat=args.repeat)

    timestamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H%M%SZ")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / f"{timestamp}.md"
    json_path = output_dir / f"{timestamp}.json"
    md_path.write_text(to_markdown(outcomes), encoding="utf-8")
    json_path.write_text(to_json(outcomes), encoding="utf-8")

    failures = [o for o in outcomes if not o.schema_valid]
    print(f"\nWrote {md_path}")
    print(f"Wrote {json_path}")
    print(
        f"{len(outcomes) - len(failures)}/{len(outcomes)} generations returned a valid schema."
    )
    print(
        "\nNOTE: schema validity / coverage / length / latency are recorded "
        "automatically. Manual quality notes are NOT. Read the transcripts in "
        f"{md_path} (especially the ambiguous_heteronyms fixture — coverage can "
        "look perfect while the model used the wrong sense of a word), then edit "
        f"manual_quality_notes directly in {json_path} — that JSON file is the "
        "persisted record of your review, not the markdown. Run "
        "`provider_comparison render --input "
        f"{json_path}` to regenerate the markdown with your notes included, and "
        "only then add an entry to "
        "story_generator/generation/providers/provider_registry.py."
    )


def _render(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    outcomes = load_outcomes(input_path)

    output_path = Path(args.output) if args.output else input_path.with_suffix(".md")
    output_path.write_text(to_markdown(outcomes), encoding="utf-8")

    with_notes = sum(1 for o in outcomes if o.manual_quality_notes)
    print(
        f"Wrote {output_path} ({with_notes}/{len(outcomes)} outcomes have manual quality notes)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run the comparison against one or more providers"
    )
    run_parser.add_argument(
        "--provider",
        action="append",
        default=[],
        metavar="SPEC",
        help=_PROVIDER_SPEC_HELP,
    )
    run_parser.add_argument(
        "--prompt-version",
        default=CURRENT_PROMPT_VERSION,
        help=(
            "Prompt version to send (default: the one production uses, "
            f"{CURRENT_PROMPT_VERSION}). Pass an older one to measure a "
            "baseline for a prompt change."
        ),
    )
    run_parser.add_argument(
        "--fixture",
        action="append",
        default=[],
        metavar="NAME",
        help="Only run this fixture, repeatable (default: all of them).",
    )
    run_parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=(
            "Generate each fixture this many times. One sample is enough for "
            "length and coverage, but too noisy to judge a prompt on quality."
        ),
    )
    run_parser.add_argument("--output-dir", default="reports/provider-comparisons")
    run_parser.set_defaults(func=_run)

    render_parser = subparsers.add_parser(
        "render",
        help="Regenerate a markdown report from a (possibly hand-edited) JSON report",
    )
    render_parser.add_argument(
        "--input",
        required=True,
        metavar="JSON_PATH",
        help="Path to a report .json file",
    )
    render_parser.add_argument(
        "--output",
        metavar="MD_PATH",
        help="Path to write the .md to (default: same basename as --input)",
    )
    render_parser.set_defaults(func=_render)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
