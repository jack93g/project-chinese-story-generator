from dataclasses import dataclass

@dataclass

class VocabularyItem:
    skritter_vocab_id: str
    language: str
    writing: str
    reading: str
    definition_en: str
