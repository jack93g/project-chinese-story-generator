from typing import Protocol, runtime_checkable

from story_generator.generation.providers.types import GenerationRequestInput, GenerationResult


@runtime_checkable
class StoryGenerationProvider(Protocol):
    """
    The interface every story-generation provider adapter implements
    (OpenAIStoryGenerationProvider, a future Ollama/Qwen adapter,
    FakeStoryGenerationProvider, ...).

    This is a structural Protocol rather than an ABC deliberately:
    generation.service and anything else that calls a provider should
    depend only on this shape (plus providers.types and
    providers.errors), and never import a concrete adapter — let alone
    a provider SDK — directly. Swapping providers is a matter of
    dependency injection, not a code change in the service layer.

    generate() must either return a GenerationResult or raise one of
    the errors in story_generator.generation.providers.errors. It must
    not raise a provider-SDK-specific exception.
    """

    def generate(self, request: GenerationRequestInput) -> GenerationResult:
        ...