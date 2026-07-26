from dataclasses import dataclass


@dataclass(frozen=True)
class SkritterVocabularyRecord:
    """Normalized vocabulary data received from Skritter before persistence."""

    skritter_vocab_id: str
    language: str
    writing: str
    reading: str
    definition_en: str
