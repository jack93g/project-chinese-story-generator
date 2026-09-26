"use client";

import { useState, type FormEvent } from "react";
import {
  ApiError,
  flagQuestion,
  submitQuizAttempt,
  type QuizAttemptResult,
  type QuizQuestion,
} from "@/lib/api";

type FlagStatus = "sending" | "flagged" | "failed";

// Multiple-choice questions on a story. The page never has the answers:
// they come back from the API with the marked attempt, which it also
// records, so every "Check answers" is one attempt. Once marked, each
// question shows the sentence that settles it (when there is one) and can
// be reported as wrong, since the questions are machine-written.
export function StoryQuiz({
  storyId,
  questions,
}: {
  storyId: number;
  questions: QuizQuestion[];
}) {
  const [selected, setSelected] = useState<(number | null)[]>(() =>
    questions.map(() => null),
  );
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<QuizAttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Kept across "Try again", so a question is only reported once per visit.
  const [flags, setFlags] = useState<Record<number, FlagStatus>>({});

  const answers = selected.filter((choice): choice is number => choice !== null);
  const allAnswered = answers.length === questions.length;
  const locked = submitting || result !== null;

  function choose(questionIndex: number, optionIndex: number) {
    setSelected(
      selected.map((choice, index) =>
        index === questionIndex ? optionIndex : choice,
      ),
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!allAnswered || locked) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      setResult(await submitQuizAttempt(storyId, answers));
    } catch (caught: unknown) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not check your answers. Try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function report(questionIndex: number) {
    setFlags((current) => ({ ...current, [questionIndex]: "sending" }));
    let status: FlagStatus = "flagged";
    try {
      await flagQuestion(storyId, questionIndex);
    } catch {
      status = "failed";
    }
    setFlags((current) => ({ ...current, [questionIndex]: status }));
  }

  function tryAgain() {
    setSelected(questions.map(() => null));
    setResult(null);
    setError(null);
  }

  return (
    <section aria-labelledby="quiz-heading" className="story-quiz">
      <h2 id="quiz-heading">Check your understanding</h2>
      <form onSubmit={handleSubmit}>
        <ol className="quiz-questions">
          {questions.map((question, questionIndex) => {
            const marked = result?.results[questionIndex];
            return (
              <li key={questionIndex}>
                <fieldset className="quiz-question" disabled={locked}>
                  {/* Numbered here rather than by the list: a legend doesn't
                      line up with the list marker. Hidden from screen
                      readers, which announce the list position already. */}
                  <legend>
                    <span aria-hidden="true" className="quiz-number">
                      {questionIndex + 1}.
                    </span>{" "}
                    <span lang="zh">{question.question}</span>
                  </legend>
                  {question.options.map((option, optionIndex) => {
                    const isAnswer = marked?.answer === optionIndex;
                    const isWrongChoice =
                      marked !== undefined &&
                      !marked.correct &&
                      marked.selected === optionIndex;
                    const classes = ["quiz-option"];
                    if (isAnswer) {
                      classes.push("quiz-option-correct");
                    } else if (isWrongChoice) {
                      classes.push("quiz-option-wrong");
                    }
                    return (
                      <label key={optionIndex} className={classes.join(" ")}>
                        <input
                          type="radio"
                          name={`quiz-${storyId}-${questionIndex}`}
                          checked={selected[questionIndex] === optionIndex}
                          onChange={() => choose(questionIndex, optionIndex)}
                        />
                        <span lang="zh">{option}</span>
                        {/* The space keeps screen readers from running the
                            option and its mark together; flex layout ignores it. */}
                        {isAnswer && (
                          <>
                            {" "}
                            <span className="quiz-mark">
                              {marked.correct ? "✓ Correct" : "✓ Answer"}
                            </span>
                          </>
                        )}
                        {isWrongChoice && (
                          <>
                            {" "}
                            <span className="quiz-mark">✗ Your answer</span>
                          </>
                        )}
                      </label>
                    );
                  })}
                </fieldset>
                {marked && (
                  <div className="quiz-feedback">
                    {marked.evidence && (
                      <p className="quiz-evidence">
                        The story says:{" "}
                        <span lang="zh">{marked.evidence}</span>
                      </p>
                    )}
                    <FlagControl
                      status={flags[questionIndex]}
                      onReport={() => report(questionIndex)}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ol>

        {result === null ? (
          <div className="quiz-actions">
            <button
              type="submit"
              className="button"
              disabled={!allAnswered || submitting}
            >
              {submitting ? "Checking…" : "Check answers"}
            </button>
            {!allAnswered && (
              <p className="field-hint">
                Answer every question to check your answers.
              </p>
            )}
          </div>
        ) : (
          <div className="quiz-actions">
            <p role="status" className="quiz-score">
              {result.correct_count} of {result.question_count} correct
            </p>
            <button type="button" className="button-plain" onClick={tryAgain}>
              Try again
            </button>
          </div>
        )}
        {error && (
          <p role="alert" className="field-error">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

function FlagControl({
  status,
  onReport,
}: {
  status: FlagStatus | undefined;
  onReport: () => void;
}) {
  if (status === "flagged") {
    return (
      <p role="status" className="field-hint">
        Reported. Thanks!
      </p>
    );
  }
  return (
    <>
      <button
        type="button"
        className="quiz-flag"
        onClick={onReport}
        disabled={status === "sending"}
      >
        This question seems wrong
      </button>
      {status === "failed" && (
        <p role="alert" className="field-error">
          Couldn&rsquo;t report it. Try again.
        </p>
      )}
    </>
  );
}
