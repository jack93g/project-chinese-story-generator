"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { annotateVocabulary } from "@/lib/annotate";
import { ApiError, fetchStory, type StoryDetail } from "@/lib/api";
import { toToneMarks } from "@/lib/pinyin";
import { Seal } from "../components/seal";

type StoryState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "error"; message: string }
  | { status: "ready"; story: StoryDetail };

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

const PINYIN_KEY = "story-reader:show-pinyin";
const VERTICAL_KEY = "story-reader:vertical";

// Reading options are a per-browser convenience; if storage is unavailable
// (private window, blocked site data) the reader just uses the defaults.
function readPreference(key: string, fallback: boolean): boolean {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value === "true";
  } catch {
    return fallback;
  }
}

function writePreference(key: string, value: boolean) {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // Not remembered, but the toggle still works for this visit.
  }
}

// A static export can't pre-render one page per story ID (IDs are created at
// runtime), so the story is addressed as /story?id=<id> and fetched client-side.
export default function StoryPage() {
  return (
    <Suspense fallback={<StoryLoading />}>
      <StoryContent />
    </Suspense>
  );
}

function StoryLoading() {
  return (
    <div className="page-content">
      <p role="status" className="state">
        Loading story…
      </p>
    </div>
  );
}

function StoryNotFound() {
  return (
    <div className="page-content">
      <h1>Story not found</h1>
      <p className="state">
        There&rsquo;s no saved story with this ID. It may have been removed, or
        the link may be incorrect.
      </p>
    </div>
  );
}

function StoryContent() {
  // The ID comes from the URL, so only accept plain digits; anything else
  // (missing, or something like "../vocabulary") is treated as not found.
  const rawId = useSearchParams().get("id");
  const id = rawId !== null && /^\d+$/.test(rawId) ? rawId : null;
  const [state, setState] = useState<StoryState>({ status: "loading" });

  useEffect(() => {
    if (!id) {
      return;
    }

    let cancelled = false;

    fetchStory(id)
      .then((story) => {
        if (!cancelled) {
          setState({ status: "ready", story });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiError && error.status === 404) {
          setState({ status: "not-found" });
        } else {
          setState({
            status: "error",
            message:
              error instanceof ApiError
                ? error.message
                : "Could not load this story.",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  if (!id) {
    return <StoryNotFound />;
  }

  if (state.status === "loading") {
    return <StoryLoading />;
  }

  if (state.status === "not-found") {
    return <StoryNotFound />;
  }

  if (state.status === "error") {
    return (
      <div className="page-content">
        <h1>Something went wrong</h1>
        <p role="alert" className="state state-error">
          {state.message}
        </p>
      </div>
    );
  }

  return <StoryReader story={state.story} />;
}

// Rendered only once the story has loaded in the browser, so reading
// localStorage while initialising state can't cause a hydration mismatch.
function StoryReader({ story }: { story: StoryDetail }) {
  const [showPinyin, setShowPinyin] = useState(() =>
    readPreference(PINYIN_KEY, true),
  );
  const [vertical, setVertical] = useState(() =>
    readPreference(VERTICAL_KEY, false),
  );
  const segments = useMemo(
    () => annotateVocabulary(story.content, story.selected_vocabulary),
    [story],
  );

  function togglePinyin() {
    setShowPinyin(!showPinyin);
    writePreference(PINYIN_KEY, !showPinyin);
  }

  function toggleVertical() {
    setVertical(!vertical);
    writePreference(VERTICAL_KEY, !vertical);
  }

  const bodyClasses = ["story-body"];
  if (!showPinyin) {
    bodyClasses.push("hide-pinyin");
  }
  if (vertical) {
    bodyClasses.push("story-body-vertical");
  }

  return (
    <article className="page-content story">
      <header className="story-header">
        <h1 lang="zh" className="story-title">
          {story.title}
        </h1>
        <p className="story-meta">
          {story.target_hsk !== null && <>HSK {story.target_hsk} &middot; </>}
          {formatDate(story.created_at)}
        </p>
        <div role="group" aria-label="Reading options" className="story-options">
          <button
            type="button"
            className="toggle"
            aria-pressed={showPinyin}
            onClick={togglePinyin}
          >
            <span lang="zh">拼音</span> Pinyin
          </button>
          <button
            type="button"
            className="toggle"
            aria-pressed={vertical}
            onClick={toggleVertical}
          >
            <span lang="zh">竖排</span> Vertical
          </button>
        </div>
      </header>

      {/* In vertical mode the body scrolls sideways, so it takes focus to let
          keyboard users scroll it. */}
      <p
        lang="zh"
        className={bodyClasses.join(" ")}
        tabIndex={vertical ? 0 : undefined}
      >
        {segments.map((segment, index) =>
          segment.kind === "word" ? (
            <ruby key={index}>
              {segment.text}
              <rt>{segment.reading}</rt>
            </ruby>
          ) : (
            segment.text
          ),
        )}
      </p>

      <Seal decorative className="seal-stamp" />

      <section aria-labelledby="glossary-heading" className="story-glossary">
        <h2 id="glossary-heading">Glossary</h2>
        <dl>
          {story.selected_vocabulary.map((item) => (
            <div key={item.id} className="glossary-item">
              <dt lang="zh">
                {item.writing}
                {item.reading && (
                  <span className="glossary-reading">
                    {` (${toToneMarks(item.reading)})`}
                  </span>
                )}
              </dt>
              <dd>
                {item.definition_en ?? (
                  <span className="glossary-missing">
                    No definition available
                  </span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </article>
  );
}
