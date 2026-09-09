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

const HSK_LEVELS = [1, 2, 3, 4, 5, 6];
const DEFAULT_TARGET_WORD_COUNT = 150;
const DEFAULT_TARGET_VOCABULARY_COUNT = 10;
const MAX_TARGET_WORD_COUNT = 1000;
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

export default function GeneratePage() {
  const router = useRouter();
  const [listsState, setListsState] = useState<ListsState>({
    status: "loading",
  });
  const [selectedListId, setSelectedListId] = useState("");
  const [hskLevel, setHskLevel] = useState("");
  const [topic, setTopic] = useState("");
  const [targetWordCount, setTargetWordCount] = useState(
    String(DEFAULT_TARGET_WORD_COUNT),
  );
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
            router.push(`/stories/${result.story_id}`);
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
  const canSubmit =
    selectedListId !== "" &&
    hskLevel !== "" &&
    !isSelectedListEmpty &&
    targetWordCountResult.error === null &&
    submitState.status !== "submitting";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || !selectedList || targetWordCountResult.value === null) {
      return;
    }

    const vocabularyCount = Math.max(
      1,
      Math.min(DEFAULT_TARGET_VOCABULARY_COUNT, selectedList.item_count),
    );
    const trimmedTopic = topic.trim();

    setSubmitState({ status: "submitting" });
    try {
      const result = await createStoryGeneration({
        vocabulary_list_id: Number(selectedListId),
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
        router.push(`/stories/${result.story_id}`);
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
            onChange={(event) => setSelectedListId(event.target.value)}
            required
          >
            <option value="" disabled>
              Select a vocabulary list
            </option>
            {listsState.lists.map((list) => (
              <option key={list.id} value={list.id}>
                {list.name} ({list.item_count} words)
              </option>
            ))}
          </select>
          {isSelectedListEmpty && (
            <p role="alert" className="field-error">
              This list has no vocabulary items yet — choose another list.
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
            Target word count (optional)
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
