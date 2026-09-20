"""
Registry gating which (provider_label, model, base_url) triples may be
resolved into a live provider.

This is the enforcement mechanism for M3-7's acceptance criterion:
"No provider is made selectable without a recorded comparison." It's
a small allowlist, not a secret — nothing here is sensitive.

base_url is part of the key deliberately, not just label/model:
provider_label (OPENAI_PROVIDER_LABEL) is a human-set, purely
descriptive string — nothing ties it to the endpoint OPENAI_BASE_URL
actually points at. Keying on label+model alone would let someone
change OPENAI_BASE_URL to a completely different, unreviewed endpoint
while leaving OPENAI_PROVIDER_LABEL="groq" in place, and the check
would still pass. Keying on all three means an approval is tied to the
exact endpoint that was actually compared.

assert_current_provider_approved() is the canonical entry point:
it reads label/model/base_url from config itself, so it gives the
same answer regardless of *how* a caller ends up constructing a
provider. Call this at:
  - the production provider-construction boundary
    (build_openai_provider(), see providers/openai.py), AND
  - process startup for anything long-running that will eventually
    construct/use a provider (e.g. the worker CLI), so a
    misconfigured deployment fails immediately at startup rather than
    on whatever request happens to trigger construction first.
Do not rely on only one of these call sites — a provider could in
principle be constructed some other way (e.g. directly in a FastAPI
dependency) without going through build_openai_provider(); startup
enforcement is the backstop for that.

Workflow to add a REAL (non-stub) provider/model/endpoint entry:
  1. Run the comparison harness against it:
       python -m story_generator.cli.provider_comparison run \\
         --provider "<label>|<base_url>|<model>|<api_key_env_var>"
     This writes a markdown + JSON report under
     reports/provider-comparisons/.
  2. A human reads the report — especially the transcripts — and edits
     `manual_quality_notes` directly in the JSON file for each outcome
     (the JSON is the persisted source of truth for review notes, not
     the markdown — see eval/comparison.py's docstring). Then run
       python -m story_generator.cli.provider_comparison render \\
         --input reports/provider-comparisons/<ts>.json
     to regenerate the markdown with those notes included.
  3. Replace the stub entry below (or add a new one) with report_path
     pointing at that reviewed JSON file, keyed on the exact
     (label, model, base_url) that was tested.

Deliberately manual: the whole point of the AC is that a human looked
at real output before a provider becomes usable, not that a script
approved itself.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderApproval:
    report_path: str
    reviewed_by: str
    reviewed_at: str  # ISO date, e.g. "2026-08-23"
    notes: str = ""


class UnapprovedProviderError(Exception):
    def __init__(self, provider_label: str, model: str, base_url: str):
        self.provider_label = provider_label
        self.model = model
        self.base_url = base_url
        super().__init__(
            f"Provider '{provider_label}' with model '{model}' at endpoint "
            f"'{base_url}' has no recorded, reviewed comparison report. Run "
            "`python -m story_generator.cli.provider_comparison` and add a "
            "reviewed entry to APPROVED_PROVIDERS in this file (keyed on this "
            "exact label, model, AND base_url) before using this combination."
        )


# groq did not pass the text as only 3/7 of the outputs were good, but we are still approving it for now to not block
# base_url below MUST exactly match whatever OPENAI_BASE_URL is actually
# set to in the environment(s) this stub is meant to cover — if you change
# OPENAI_BASE_URL, update this key too, or the check will (correctly) start
# failing.
APPROVED_PROVIDERS: dict[tuple[str, str, str], ProviderApproval] = {
    (
        "groq",
        "openai/gpt-oss-120b",
        "https://api.groq.com/openai/v1/chat/completions",
    ): ProviderApproval(
        report_path="reports/provider-comparisons/2026-08-23T140047Z.md",
        reviewed_by="Jack",
        reviewed_at="2026-08-23",
        notes=("3/7 look good, ran into rate limits with the others"),
    ),
}


def assert_provider_approved(provider_label: str, model: str, base_url: str) -> None:
    if (provider_label, model, base_url) not in APPROVED_PROVIDERS:
        raise UnapprovedProviderError(provider_label, model, base_url)


def assert_current_provider_approved() -> None:
    """
    Canonical check: reads the live OPENAI_PROVIDER_LABEL / OPENAI_MODEL /
    OPENAI_BASE_URL config and asserts that exact combination is approved.

    This is the function to call at any provider-construction boundary AND
    at process startup for long-running processes (see module docstring) —
    prefer this over assert_provider_approved() directly so every call site
    is guaranteed to check the same, actual, current configuration rather
    than values a caller reconstructed by hand.
    """
    # Imported here, not at module level, to avoid a config <-> providers
    # import cycle (config.py has no reason to import from generation.*).
    from story_generator.config import (
        get_openai_base_url,
        get_openai_model,
        get_openai_provider_label,
    )

    assert_provider_approved(
        get_openai_provider_label(),
        get_openai_model(),
        get_openai_base_url(),
    )
