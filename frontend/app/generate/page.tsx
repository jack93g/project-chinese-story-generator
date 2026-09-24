"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  createStoryGeneration,
  fetchAllVocabularyLists,
  fetchGenerationStatus,
  retryStoryGeneration,
  type GenerationStatusValue,
  type VocabularyListSummary,
} from "@/lib/api";
import { BrushLoader } from "../components/brush-loader";

const HSK_LEVELS = [1, 2, 3, 4, 5, 6];
const DEFAULT_TARGET_WORD_COUNT = 150;
const MAX_TARGET_WORD_COUNT = 1000;
const MAX_VOCABULARY_COUNT = 30;
// The suggested number of vocabulary words is one per this many characters
// of story: dense enough to practise, loose enough to read naturally. It
// depends only on story length, never on list size (lists can hold
// hundreds of words; a story still uses at most MAX_VOCABULARY_COUNT).
const CHARACTERS_PER_VOCABULARY_WORD = 25;
// Denser than this (one word per 15 characters, e.g. 10 in 150) is past
// what stories have been seen to handle, so the form warns, but allows it.
const MIN_CHARACTERS_PER_VOCABULARY_WORD = 15;
const MAX_CUSTOM_WORD_LENGTH = 20;
const CUSTOM_WORD_PATTERN = /^[\u3400-\u4dbf\u4e00-\u9fff]+$/;
const POLL_INTERVAL_MS = 2500;
const MAX_TRANSIENT_STATUS_FAILURES = 5;

type ListsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; lists: VocabularyListSummary[] };

type SubmitState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string };

type GenerationState =
  | { phase: "polling"; id: number; status: GenerationStatusValue }
  | { phase: "failed"; id: number; message: string }
  | { phase: "error"; id: number; message: string };

type TargetWordCountResult =
  | { value: number; error: null }
  | { value: null; error: string };

function parseTargetWordCount(input: string): TargetWordCountResult {
  const trimmed = input.trim();
  if (trimmed === "") {
    return { value: DEFAULT_TARGET_WORD_COUNT, error: null };
  }

  const parsed = Number(trimmed);
  if (
    !Number.isInteger(parsed) ||
    parsed < 1 ||
    parsed > MAX_TARGET_WORD_COUNT
  ) {
    return {
      value: null,
      error: `Enter a whole number from 1 to ${MAX_TARGET_WORD_COUNT}, or leave this blank to use the default of ${DEFAULT_TARGET_WORD_COUNT}.`,
    };
  }

  return { value: parsed, error: null };
}

function suggestedVocabularyCount(targetWordCount: number): number {
  return Math.min(
    MAX_VOCABULARY_COUNT,
    Math.max(1, Math.round(targetWordCount / CHARACTERS_PER_VOCABULARY_WORD)),
  );
}

type VocabularyCountResult =
  | { value: number; error: null }
  | { value: null; error: string };

// A blank input means "use the suggestion", like a blank story length.
function parseVocabularyCount(
  input: string,
  suggested: number,
  customWordCount: number,
): VocabularyCountResult {
  const trimmed = input.trim();
  if (trimmed === "") {
    return { value: Math.max(suggested, customWordCount), error: null };
  }

  const parsed = Number(trimmed);
  if (
    !Number.isInteger(parsed) ||
    parsed < 1 ||
    parsed > MAX_VOCABULARY_COUNT
  ) {
    return {
      value: null,
      error: `Enter a whole number from 1 to ${MAX_VOCABULARY_COUNT}, or leave this blank to use the suggested ${suggested}.`,
    };
  }
  if (parsed < customWordCount) {
    return {
      value: null,
      error: `You entered ${customWordCount} custom words, and they're always used, so enter at least ${customWordCount}.`,
    };
  }

  return { value: parsed, error: null };
}

type CustomWordsResult =
  | { words: string[]; error: null }
  | { words: string[]; error: string };

function parseCustomWords(input: string): CustomWordsResult {
  const words = [
    ...new Set(input.split(/[\s,，、;；]+/).filter((word) => word !== "")),
  ];

  const invalid = words.find(
    (word) =>
      word.length > MAX_CUSTOM_WORD_LENGTH || !CUSTOM_WORD_PATTERN.test(word),
  );
  if (invalid !== undefined) {
    return {
      words,
      error: `"${invalid}" isn't a Chinese word. Use Chinese characters only, up to ${MAX_CUSTOM_WORD_LENGTH} per word.`,
    };
  }
  if (words.length > MAX_VOCABULARY_COUNT) {
    return {
      words,
      error: `Enter at most ${MAX_VOCABULARY_COUNT} custom words (you entered ${words.length}).`,
    };
  }
  return { words, error: null };
}

export default function GeneratePage() {
  const router = useRouter();
  const [listsState, setListsState] = useState<ListsState>({
    status: "loading",
  });
  const [selectedListId, setSelectedListId] = useState("");
  const [customWordsInput, setCustomWordsInput] = useState("");
  const [hskLevel, setHskLevel] = useState("");
  const [topic, setTopic] = useState("");
  const [targetWordCount, setTargetWordCount] = useState(
    String(DEFAULT_TARGET_WORD_COUNT),
  );
  // null until the user types in the field: until then it follows the
  // suggestion, so changing the story length or list updates it.
  const [vocabularyCountInput, setVocabularyCountInput] = useState<
    string | null
  >(null);
  const [submitState, setSubmitState] = useState<SubmitState>({
    status: "idle",
  });
  const [generation, setGeneration] = useState<GenerationState | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchAllVocabularyLists()
      .then((lists) => {
        if (!cancelled) {
          setListsState({ status: "ready", lists });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setListsState({
            status: "error",
            message:
              error instanceof ApiError
                ? error.message
                : "Could not load vocabulary lists.",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (generation === null || generation.phase !== "polling") {
      return;
    }
    const { id } = generation;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;
    let consecutiveFailures = 0;

    const poll = () => {
      fetchGenerationStatus(id)
        .then((result) => {
          if (cancelled) {
            return;
          }
          consecutiveFailures = 0;
          if (result.status === "succeeded" && result.story_id !== null) {
            router.push(`/story?id=${result.story_id}&fresh=1`);
            return;
          }
          if (result.status === "failed") {
            setGeneration({
              phase: "failed",
              id,
              message:
                result.error_message ??
                "Story generation failed. You may retry this request.",
            });
            return;
          }
          setGeneration({ phase: "polling", id, status: result.status });
          timeoutId = setTimeout(poll, POLL_INTERVAL_MS);
        })
        .catch((error: unknown) => {
          if (cancelled) {
            return;
          }
          // A 4xx means this request will never resolve by retrying
          // identically (e.g. 404 — the ID doesn't exist) — stop immediately
          // with a clear error instead of polling forever.
          if (
            error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500
          ) {
            setGeneration({
              phase: "error",
              id,
              message:
                error.status === 404
                  ? "This generation request could not be found."
                  : error.message,
            });
            return;
          }
          // Otherwise treat it as a transient network/5xx hiccup, but only
          // up to a bounded number of consecutive failures.
          consecutiveFailures += 1;
          if (consecutiveFailures >= MAX_TRANSIENT_STATUS_FAILURES) {
            setGeneration({
              phase: "error",
              id,
              message:
                "Lost connection while checking on this request. Refresh the page to try again.",
            });
            return;
          }
          timeoutId = setTimeout(poll, POLL_INTERVAL_MS);
        });
    };

    timeoutId = setTimeout(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only the phase transition (not `status`) should restart polling
  }, [generation?.phase, generation?.id, router]);

  const selectedList =
    listsState.status === "ready"
      ? listsState.lists.find((list) => String(list.id) === selectedListId)
      : undefined;

  const isSelectedListEmpty = selectedList?.item_count === 0;
  const targetWordCountResult = parseTargetWordCount(targetWordCount);
  const customWordsResult = parseCustomWords(customWordsInput);
  const customWords = customWordsResult.words;
  const hasList = selectedListId !== "";
  const storyLength = targetWordCountResult.value ?? DEFAULT_TARGET_WORD_COUNT;
  const suggestedCount = suggestedVocabularyCount(storyLength);
  const vocabularyCountResult = parseVocabularyCount(
    vocabularyCountInput ?? "",
    suggestedCount,
    customWords.length,
  );
  // Custom words always count; the list fills the rest, up to its size.
  const listSlots =
    selectedList && vocabularyCountResult.value !== null
      ? Math.min(
          selectedList.item_count,
          Math.max(vocabularyCountResult.value - customWords.length, 0),
        )
      : 0;
  const vocabularyCount = Math.max(1, customWords.length + listSlots);
  const densityWarning =
    vocabularyCount * MIN_CHARACTERS_PER_VOCABULARY_WORD > storyLength
      ? `${vocabularyCount} words in ${storyLength} characters is dense: the story may read stiffly or leave some out. A longer story helps.`
      : null;
  const canSubmit =
    (hasList || customWords.length > 0) &&
    customWordsResult.error === null &&
    hskLevel !== "" &&
    !(isSelectedListEmpty && customWords.length === 0) &&
    targetWordCountResult.error === null &&
    // The count only applies with a list; without one, it's the custom words.
    (!hasList || vocabularyCountResult.error === null) &&
    submitState.status !== "submitting";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || targetWordCountResult.value === null) {
      return;
    }

    const trimmedTopic = topic.trim();

    setSubmitState({ status: "submitting" });
    try {
      const result = await createStoryGeneration({
        vocabulary_list_id: hasList ? Number(selectedListId) : null,
        ...(customWords.length > 0 ? { custom_words: customWords } : {}),
        target_hsk_level: Number(hskLevel),
        target_word_count: targetWordCountResult.value,
        target_vocabulary_count: vocabularyCount,
        topic: trimmedTopic === "" ? null : trimmedTopic,
      });
      setSubmitState({ status: "idle" });
      setGeneration({ phase: "polling", id: result.id, status: "queued" });
    } catch (error) {
      setSubmitState({
        status: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "Could not start the story generation.",
      });
    }
  }

  async function handleRetry() {
    if (generation === null || generation.phase !== "failed") {
      return;
    }
    setIsRetrying(true);
    setRetryError(null);
    try {
      const result = await retryStoryGeneration(generation.id);
      if (result.status === "succeeded" && result.story_id !== null) {
        router.push(`/story?id=${result.story_id}&fresh=1`);
        return;
      }
      if (result.status === "failed") {
        setGeneration({
          phase: "failed",
          id: generation.id,
          message:
            result.error_message ??
            "Story generation failed. You may retry this request.",
        });
        return;
      }
      setGeneration({
        phase: "polling",
        id: generation.id,
        status: result.status,
      });
    } catch (error) {
      setRetryError(
        error instanceof ApiError
          ? error.message
          : "Could not retry this request.",
      );
    } finally {
      setIsRetrying(false);
    }
  }

  function vocabularyCountHint(): string {
    const requested = vocabularyCountResult.value ?? 0;
    let hint: string;
    if (selectedList && vocabularyCount < requested) {
      hint = `This list has only ${selectedList.item_count} word${selectedList.item_count === 1 ? "" : "s"}, so the story will use ${vocabularyCount}.`;
    } else {
      const lengthNote = `Suggested for a ${storyLength}-character story: ${suggestedCount}.`;
      hint =
        customWords.length > 0
          ? `${lengthNote} Includes your ${customWords.length} custom word${customWords.length === 1 ? "" : "s"}; the list fills the rest.`
          : lengthNote;
    }
    return densityWarning ? `${hint} ${densityWarning}` : hint;
  }

  if (listsState.status === "loading") {
    return (
      <div className="page-content">
        <h1>Generate a story</h1>
        <p role="status" className="state">
          Loading vocabulary lists…
        </p>
      </div>
    );
  }

  if (listsState.status === "error") {
    return (
      <div className="page-content">
        <h1>Generate a story</h1>
        <p role="alert" className="state state-error">
          {listsState.message}
        </p>
      </div>
    );
  }

  if (listsState.lists.length === 0) {
    return (
      <div className="page-content">
        <h1>Generate a story</h1>
        <p className="state">
          No vocabulary lists are available yet. Sync a list from Skritter
          before generating a story.
        </p>
      </div>
    );
  }

  if (generation !== null) {
    return (
      <div className="page-content">
        <h1>Generate a story</h1>
        {generation.phase === "polling" &&
          (generation.status === "running" ? (
            <BrushLoader
              key="writing"
              text="正在写故事"
              pinyin="zhèngzài xiě gùshi"
            />
          ) : (
            <BrushLoader key="queued" text="排队中" pinyin="páiduì zhōng" />
          ))}
        {generation.phase === "polling" && (
          <p role="status" className="state">
            {generation.status === "running"
              ? "Generating your story…"
              : "Queued — waiting for a worker to pick this up…"}{" "}
            This page will update automatically.
          </p>
        )}
        {generation.phase === "failed" && (
          <>
            <p role="alert" className="state state-error">
              {generation.message}
            </p>
            <button
              type="button"
              className="button"
              onClick={handleRetry}
              disabled={isRetrying}
            >
              {isRetrying ? "Retrying…" : "Retry"}
            </button>
            {retryError && (
              <p role="alert" className="state state-error">
                {retryError}
              </p>
            )}
          </>
        )}
        {generation.phase === "error" && (
          <p role="alert" className="state state-error">
            {generation.message}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="page-content">
      <h1>Generate a story</h1>
      <form className="generate-form" onSubmit={handleSubmit} noValidate>
        <div className="form-field">
          <label htmlFor="vocabulary-list">Vocabulary list</label>
          <select
            id="vocabulary-list"
            value={selectedListId}
            onChange={(event) => {
              setSelectedListId(event.target.value);
              // A different list starts from the suggestion again.
              setVocabularyCountInput(null);
            }}
          >
            <option value="">No list (custom words only)</option>
            {listsState.lists.map((list) => (
              <option key={list.id} value={list.id}>
                {list.name} ({list.item_count} words)
              </option>
            ))}
          </select>
          {isSelectedListEmpty && customWords.length === 0 && (
            <p role="alert" className="field-error">
              This list has no vocabulary items yet — choose another list.
            </p>
          )}
        </div>

        <div className="form-field">
          <label htmlFor="custom-words">Custom words (optional)</label>
          <textarea
            id="custom-words"
            rows={3}
            value={customWordsInput}
            onChange={(event) => setCustomWordsInput(event.target.value)}
            placeholder="Paste words here, separated by spaces, commas or new lines"
            aria-invalid={customWordsResult.error !== null}
            aria-describedby="custom-words-hint"
          />
          {customWordsResult.error ? (
            <p id="custom-words-hint" role="alert" className="field-error">
              {customWordsResult.error}
            </p>
          ) : (
            <p id="custom-words-hint" className="field-hint">
              {customWords.length > 0
                ? `${customWords.length} custom word${customWords.length === 1 ? "" : "s"}${hasList ? "; the list fills the remaining slots" : ""}.${!hasList && densityWarning ? ` ${densityWarning}` : ""}`
                : hasList
                  ? "Optional. Custom words are always included; the list fills the remaining slots."
                  : "Choose a vocabulary list above or enter at least one custom word."}
            </p>
          )}
        </div>

        <div className="form-field">
          <label htmlFor="hsk-level">Target HSK level</label>
          <select
            id="hsk-level"
            value={hskLevel}
            onChange={(event) => setHskLevel(event.target.value)}
            required
          >
            <option value="" disabled>
              Select an HSK level
            </option>
            {HSK_LEVELS.map((level) => (
              <option key={level} value={level}>
                HSK {level}
              </option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label htmlFor="topic">Topic (optional)</label>
          <input
            id="topic"
            type="text"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="e.g. a trip to the market"
          />
        </div>

        <div className="form-field">
          <label htmlFor="target-word-count">
            Story length in characters (optional)
          </label>
          <input
            id="target-word-count"
            type="number"
            min={1}
            max={MAX_TARGET_WORD_COUNT}
            step={1}
            value={targetWordCount}
            onChange={(event) => setTargetWordCount(event.target.value)}
            aria-invalid={targetWordCountResult.error !== null}
            aria-describedby={
              targetWordCountResult.error
                ? "target-word-count-error"
                : undefined
            }
          />
          {targetWordCountResult.error && (
            <p
              id="target-word-count-error"
              role="alert"
              className="field-error"
            >
              {targetWordCountResult.error}
            </p>
          )}
        </div>

        {hasList && (
          <div className="form-field">
            <label htmlFor="vocabulary-count">Vocabulary words to use</label>
            <input
              id="vocabulary-count"
              type="number"
              min={Math.max(1, customWords.length)}
              max={MAX_VOCABULARY_COUNT}
              step={1}
              // Until the user types, show the count that will actually be
              // sent: the suggestion, capped by the list's size.
              value={vocabularyCountInput ?? String(vocabularyCount)}
              onChange={(event) => setVocabularyCountInput(event.target.value)}
              aria-invalid={vocabularyCountResult.error !== null}
              aria-describedby="vocabulary-count-hint"
            />
            {vocabularyCountResult.error ? (
              <p
                id="vocabulary-count-hint"
                role="alert"
                className="field-error"
              >
                {vocabularyCountResult.error}
              </p>
            ) : (
              <p id="vocabulary-count-hint" className="field-hint">
                {vocabularyCountHint()}
              </p>
            )}
          </div>
        )}

        {submitState.status === "error" && (
          <p role="alert" className="state state-error">
            {submitState.message}
          </p>
        )}

        <button type="submit" className="button" disabled={!canSubmit}>
          {submitState.status === "submitting" ? "Generating…" : "Generate"}
        </button>
      </form>
    </div>
  );
}
