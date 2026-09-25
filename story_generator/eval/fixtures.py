"""
Fixtures for the provider-comparison eval harness (M3-7).

Each EvalFixture is a self-contained input for a single generation
call — it does NOT depend on a live database or on
select_vocabulary(). The `vocabulary_snapshot` shape matches exactly
what select_vocabulary() would normally produce (see
story_generator.generation.vocabulary_selection), so a fixture can be
fed straight into GenerationRequestInput.

IDs here are synthetic, in a 9000+ range deliberately outside any real
autoincrement sequence, so nothing here is mistakable for a real
VocabularyItem.id.

Categories (per M3-7 acceptance criteria):
  - "hsk_level"     — spread across HSK difficulty tiers
  - "ambiguous_words" — heteronyms / polysemous characters, which
    stress both the model (does it use the *intended* sense?) and the
    validator (substring-containment can't tell readings apart)
  - "short_list"    — fewer vocabulary items than target_vocabulary_count,
    exercising select_vocabulary()'s "short list" capping behavior and
    the coverage calculation's small-denominator edge case
  - "mixed_known"   — very common words mixed with rare/literary ones
    in the same request, checking the model blends registers naturally
    rather than defaulting to only the easy words

  Bonus, not required by the AC but useful for the latency/length
  columns the report also has to record:
  - "stress_length" — a large vocabulary list near
    MAX_TARGET_WORD_COUNT, to see how latency and length-adherence
    hold up under load
  - "stress_density" — many words in a short story, to see whether
    the story stays plausible and its collocations natural
"""

from dataclasses import dataclass

from story_generator.generation.prompts.builder import CURRENT_PROMPT_VERSION


@dataclass(frozen=True)
class EvalFixture:
    name: str
    category: str
    description: str
    target_hsk_level: int
    target_word_count: int
    target_vocabulary_count: int
    vocabulary_snapshot: list[dict]
    topic: str | None = None
    # The prompt production sends, so a report measures what users get.
    prompt_version: str = CURRENT_PROMPT_VERSION


EVAL_FIXTURES: list[EvalFixture] = [
    EvalFixture(
        name="hsk1_basic",
        category="hsk_level",
        description="Five very common HSK1 words. Baseline sanity check.",
        target_hsk_level=1,
        target_word_count=150,
        target_vocabulary_count=5,
        vocabulary_snapshot=[
            {
                "id": 9001,
                "writing": "你好",
                "reading": "nǐhǎo",
                "definition_en": "hello",
            },
            {
                "id": 9002,
                "writing": "谢谢",
                "reading": "xièxie",
                "definition_en": "thank you",
            },
            {
                "id": 9003,
                "writing": "朋友",
                "reading": "péngyou",
                "definition_en": "friend",
            },
            {"id": 9004, "writing": "水", "reading": "shuǐ", "definition_en": "water"},
            {"id": 9005, "writing": "吃", "reading": "chī", "definition_en": "to eat"},
        ],
    ),
    EvalFixture(
        name="hsk3_intermediate",
        category="hsk_level",
        description="Six HSK3-ish abstract-ish words (experience, environment, decision...).",
        target_hsk_level=3,
        target_word_count=300,
        target_vocabulary_count=6,
        vocabulary_snapshot=[
            {
                "id": 9010,
                "writing": "经验",
                "reading": "jīngyàn",
                "definition_en": "experience",
            },
            {
                "id": 9011,
                "writing": "环境",
                "reading": "huánjìng",
                "definition_en": "environment",
            },
            {
                "id": 9012,
                "writing": "建议",
                "reading": "jiànyì",
                "definition_en": "suggestion; to suggest",
            },
            {
                "id": 9013,
                "writing": "讨论",
                "reading": "tǎolùn",
                "definition_en": "to discuss",
            },
            {
                "id": 9014,
                "writing": "机会",
                "reading": "jīhuì",
                "definition_en": "opportunity",
            },
            {
                "id": 9015,
                "writing": "决定",
                "reading": "juédìng",
                "definition_en": "decision; to decide",
            },
        ],
    ),
    EvalFixture(
        name="hsk6_advanced",
        category="hsk_level",
        description="Five HSK6 abstract/formal words. Checks fluency doesn't collapse at the top of the range.",
        target_hsk_level=6,
        target_word_count=400,
        target_vocabulary_count=5,
        vocabulary_snapshot=[
            {
                "id": 9020,
                "writing": "战略",
                "reading": "zhànlüè",
                "definition_en": "strategy",
            },
            {
                "id": 9021,
                "writing": "潜力",
                "reading": "qiánlì",
                "definition_en": "potential",
            },
            {
                "id": 9022,
                "writing": "谈判",
                "reading": "tánpàn",
                "definition_en": "negotiation",
            },
            {
                "id": 9023,
                "writing": "妥协",
                "reading": "tuǒxié",
                "definition_en": "compromise",
            },
            {
                "id": 9024,
                "writing": "权衡",
                "reading": "quánhéng",
                "definition_en": "to weigh (pros and cons)",
            },
        ],
    ),
    EvalFixture(
        name="ambiguous_heteronyms",
        category="ambiguous_words",
        description=(
            "Words/characters with multiple readings or senses (银行 as bank vs. "
            "银 'silver' + 行 'go/row'; 长/还/重/差 as heteronyms). Stresses whether "
            "the model uses the *intended* sense, and exposes that substring "
            "validation can't distinguish readings — worth reading the transcripts "
            "here manually, not just trusting the coverage number."
        ),
        target_hsk_level=4,
        target_word_count=300,
        target_vocabulary_count=5,
        vocabulary_snapshot=[
            {
                "id": 9030,
                "writing": "银行",
                "reading": "yínháng",
                "definition_en": "bank",
            },
            {
                "id": 9031,
                "writing": "长",
                "reading": "zhǎng / cháng",
                "definition_en": "to grow (zhǎng) / long (cháng)",
            },
            {
                "id": 9032,
                "writing": "还",
                "reading": "hái / huán",
                "definition_en": "still (hái) / to return (huán)",
            },
            {
                "id": 9033,
                "writing": "重",
                "reading": "zhòng / chóng",
                "definition_en": "heavy (zhòng) / to repeat (chóng)",
            },
            {
                "id": 9034,
                "writing": "差",
                "reading": "chà / chāi / chā",
                "definition_en": "poor/lacking (chà) / dispatch (chāi) / difference (chā)",
            },
        ],
    ),
    EvalFixture(
        name="short_list_single_word",
        category="short_list",
        description=(
            "Only one vocabulary item, but target_vocabulary_count=5 — mirrors "
            "select_vocabulary()'s 'short list' capping. Also a coverage-math edge "
            "case: denominator is 1, so coverage is either 0.0 or 1.0, nothing "
            "between — worth checking the report doesn't misrepresent this as a "
            "meaningful percentage."
        ),
        target_hsk_level=1,
        target_word_count=100,
        target_vocabulary_count=5,
        vocabulary_snapshot=[
            {"id": 9040, "writing": "猫", "reading": "māo", "definition_en": "cat"},
        ],
    ),
    EvalFixture(
        name="mixed_known_vocabulary",
        category="mixed_known",
        description=(
            "Two very common HSK1 words mixed with two rare/literary words in the "
            "same request. Checks whether the model naturally blends registers or "
            "just leans on the easy words and awkwardly bolts on the hard ones."
        ),
        target_hsk_level=5,
        target_word_count=300,
        target_vocabulary_count=5,
        vocabulary_snapshot=[
            {"id": 9050, "writing": "你", "reading": "nǐ", "definition_en": "you"},
            {"id": 9051, "writing": "水", "reading": "shuǐ", "definition_en": "water"},
            {
                "id": 9052,
                "writing": "朋友",
                "reading": "péngyou",
                "definition_en": "friend",
            },
            {
                "id": 9053,
                "writing": "邂逅",
                "reading": "xièhòu",
                "definition_en": "a chance encounter (literary)",
            },
            {
                "id": 9054,
                "writing": "踌躇",
                "reading": "chóuchú",
                "definition_en": "to hesitate (literary)",
            },
        ],
    ),
    EvalFixture(
        name="large_vocabulary_near_max_length",
        category="stress_length",
        description=(
            "12 words, target_word_count near MAX_TARGET_WORD_COUNT. Not required "
            "by the AC categories but useful for the latency/length columns: shows "
            "whether a provider's latency and length-adherence hold up on the "
            "largest realistic request."
        ),
        target_hsk_level=4,
        target_word_count=900,
        target_vocabulary_count=12,
        vocabulary_snapshot=[
            {
                "id": 9060,
                "writing": "旅行",
                "reading": "lǚxíng",
                "definition_en": "travel",
            },
            {
                "id": 9061,
                "writing": "计划",
                "reading": "jìhuà",
                "definition_en": "plan",
            },
            {
                "id": 9062,
                "writing": "天气",
                "reading": "tiānqì",
                "definition_en": "weather",
            },
            {
                "id": 9063,
                "writing": "行李",
                "reading": "xínglǐ",
                "definition_en": "luggage",
            },
            {
                "id": 9064,
                "writing": "机场",
                "reading": "jīchǎng",
                "definition_en": "airport",
            },
            {
                "id": 9065,
                "writing": "护照",
                "reading": "hùzhào",
                "definition_en": "passport",
            },
            {
                "id": 9066,
                "writing": "预订",
                "reading": "yùdìng",
                "definition_en": "to book/reserve",
            },
            {
                "id": 9067,
                "writing": "延误",
                "reading": "yánwù",
                "definition_en": "delay",
            },
            {
                "id": 9068,
                "writing": "导游",
                "reading": "dǎoyóu",
                "definition_en": "tour guide",
            },
            {
                "id": 9069,
                "writing": "风景",
                "reading": "fēngjǐng",
                "definition_en": "scenery",
            },
            {
                "id": 9070,
                "writing": "纪念品",
                "reading": "jìniànpǐn",
                "definition_en": "souvenir",
            },
            {
                "id": 9071,
                "writing": "预算",
                "reading": "yùsuàn",
                "definition_en": "budget",
            },
        ],
        topic="a delayed flight during a family trip",
    ),
    EvalFixture(
        name="dense_vocabulary",
        category="stress_density",
        description=(
            "20 mostly abstract HSK5 words in 350 characters, from a real "
            "request whose story bent itself to fit them (an East German who "
            "couldn't speak German well, to use 口语能力). Shows whether a "
            "prompt keeps the story plausible and the collocations natural "
            "under dense vocabulary. 口语 能力 keeps Skritter's space, to "
            "exercise the coverage matcher."
        ),
        target_hsk_level=5,
        target_word_count=350,
        target_vocabulary_count=20,
        topic="德国的社会",
        vocabulary_snapshot=[
            {
                "id": 9070,
                "writing": "实践",
                "reading": "shi2jian4",
                "definition_en": "to put into practice; practice",
            },
            {
                "id": 9071,
                "writing": "理由",
                "reading": "li3you2",
                "definition_en": "reason; grounds",
            },
            {
                "id": 9072,
                "writing": "监狱",
                "reading": "jian1yu4",
                "definition_en": "prison",
            },
            {
                "id": 9073,
                "writing": "反抗",
                "reading": "fan3kang4",
                "definition_en": "to resist; to rebel",
            },
            {
                "id": 9074,
                "writing": "怼",
                "reading": "dui4",
                "definition_en": "(slang) to talk back to; to call out",
            },
            {
                "id": 9075,
                "writing": "移民",
                "reading": "yi2min2",
                "definition_en": "to emigrate; immigrant",
            },
            {
                "id": 9076,
                "writing": "特意",
                "reading": "te4yi4",
                "definition_en": "specially; on purpose",
            },
            {
                "id": 9077,
                "writing": "暴力",
                "reading": "bao4li4",
                "definition_en": "violence",
            },
            {
                "id": 9078,
                "writing": "表情包",
                "reading": "biao3qing2bao1",
                "definition_en": "meme image; sticker",
            },
            {
                "id": 9079,
                "writing": "带来",
                "reading": "dai4lai2",
                "definition_en": "to bring; to bring about",
            },
            {
                "id": 9080,
                "writing": "地位",
                "reading": "di4wei4",
                "definition_en": "position; status",
            },
            {
                "id": 9081,
                "writing": "身边",
                "reading": "shen1bian1",
                "definition_en": "at one's side; around one",
            },
            {
                "id": 9082,
                "writing": "干脆",
                "reading": "gan1cui4",
                "definition_en": "simply; might as well; straightforward",
            },
            {
                "id": 9083,
                "writing": "理论",
                "reading": "li3lun4",
                "definition_en": "theory",
            },
            {
                "id": 9084,
                "writing": "污染",
                "reading": "wu1ran3",
                "definition_en": "pollution; to pollute",
            },
            {
                "id": 9085,
                "writing": "难看",
                "reading": "nan2kan4",
                "definition_en": "ugly; unsightly",
            },
            {
                "id": 9086,
                "writing": "阅读能力",
                "reading": "yue4du2neng2li4",
                "definition_en": "reading ability",
            },
            {
                "id": 9087,
                "writing": "口语 能力",
                "reading": "kou3yu3 neng2li4",
                "definition_en": "speaking ability",
            },
            {
                "id": 9088,
                "writing": "洋气",
                "reading": "yang2qi4",
                "definition_en": "stylish; Western in style",
            },
            {
                "id": 9089,
                "writing": "个人主义",
                "reading": "ge4ren2 zhu3yi4",
                "definition_en": "individualism",
            },
        ],
    ),
]
