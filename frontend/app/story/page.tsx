"use client";

import {
  Fragment,
  Suspense,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import { useSearchParams } from "next/navigation";
import {
  annotateVocabulary,
  groupSentences,
  type TextSegment,
} from "@/lib/annotate";
import { ApiError, fetchStory, type StoryDetail } from "@/lib/api";
import { describeModel } from "@/lib/model-label";
import { splitParagraphs } from "@/lib/paragraphs";
import { toToneMarks } from "@/lib/pinyin";
import { CloudDivider } from "../components/cloud-divider";
import { Seal } from "../components/seal";
import { StoryDate } from "../components/story-date";

type StoryState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "error"; message: string }
  | { status: "ready"; story: StoryDetail };

const PINYIN_KEY = "story-reader:show-pinyin";
const TRANSLATION_KEY = "story-reader:show-translation";

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

// Entrance for a story that has just been generated (timings in ms; the
// animations themselves are in globals.css): the text soaks in sentence by
// sentence, then the seal is stamped and the translation (if shown) and
// glossary fade in.
const INK_START = 150;
const INK_STAGGER = 110;
const INK_STAGGER_MAX_SENTENCES = 24;
const INK_DURATION = 800;
const STAMP_AND_GLOSSARY = 1400;

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
  const searchParams = useSearchParams();
  const rawId = searchParams.get("id");
  // Set by the generate page when it sends the reader here with a new story.
  const fresh = searchParams.get("fresh") === "1";
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

  return <StoryReader story={state.story} fresh={fresh} />;
}

// Rendered only once the story has loaded in the browser, so reading
// localStorage while initialising state can't cause a hydration mismatch.
function StoryReader({
  story,
  fresh,
}: {
  story: StoryDetail;
  fresh: boolean;
}) {
  const [showPinyin, setShowPinyin] = useState(() =>
    readPreference(PINYIN_KEY, true),
  );
  const [showTranslation, setShowTranslation] = useState(() =>
    readPreference(TRANSLATION_KEY, false),
  );
  const writtenBy = describeModel(story.provider, story.model);
  // Each paragraph's sentences, numbered across the whole story so the
  // entrance soaks them in one after another.
  const { paragraphs, sentenceCount } = useMemo(() => {
    const result: { sentences: TextSegment[][]; firstSentence: number }[] = [];
    let count = 0;
    for (const paragraph of splitParagraphs(story.content)) {
      const sentences = groupSentences(
        annotateVocabulary(paragraph, story.selected_vocabulary),
      );
      result.push({ sentences, firstSentence: count });
      count += sentences.length;
    }
    return { paragraphs: result, sentenceCount: count };
  }, [story]);
  const translation = story.translation_en ?? null;
  // One English entry per paragraph goes under its paragraph; a list that
  // doesn't line up is shown as one block after the story instead.
  const translationAligned =
    translation !== null && translation.length === paragraphs.length;

  // Captured once: `fresh` turns false when the URL is tidied below, but the
  // entrance should still finish.
  const [entrance, setEntrance] = useState(fresh);
  const stampDelay =
    INK_START +
    Math.min(sentenceCount - 1, INK_STAGGER_MAX_SENTENCES) * INK_STAGGER +
    INK_DURATION * 0.6;

  useEffect(() => {
    if (!entrance) {
      return;
    }
    // Drop ?fresh=1 so reloading or sharing the page doesn't replay it.
    window.history.replaceState(null, "", `/story?id=${story.id}`);
    // Afterwards, remove the animation classes so that toggling a reading
    // option doesn't restart them.
    const timer = setTimeout(
      () => setEntrance(false),
      stampDelay + STAMP_AND_GLOSSARY,
    );
    return () => clearTimeout(timer);
  }, [entrance, stampDelay, story.id]);

  function togglePinyin() {
    setShowPinyin(!showPinyin);
    writePreference(PINYIN_KEY, !showPinyin);
  }

  function toggleTranslation() {
    setShowTranslation(!showTranslation);
    writePreference(TRANSLATION_KEY, !showTranslation);
  }

  const bodyClasses = ["story-body"];
  if (!showPinyin) {
    bodyClasses.push("hide-pinyin");
  }

  return (
    <article
      className={
        entrance ? "page-content story story-entrance" : "page-content story"
      }
      style={{ "--stamp-delay": `${stampDelay}ms` } as CSSProperties}
    >
      <header className="story-header">
        <h1 lang="zh" className="story-title">
          {story.title}
        </h1>
        <p className="story-meta">
          {story.target_hsk !== null && <>HSK {story.target_hsk} &middot; </>}
          <StoryDate isoDate={story.created_at} />
          {writtenBy && <> &middot; Written by {writtenBy}</>}
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
          {translation !== null && (
            <button
              type="button"
              className="toggle"
              aria-pressed={showTranslation}
              onClick={toggleTranslation}
            >
              <span lang="zh">翻译</span> Translation
            </button>
          )}
        </div>
      </header>

      <div className={bodyClasses.join(" ")}>
        {paragraphs.map(({ sentences, firstSentence }, paragraphIndex) => (
          <Fragment key={paragraphIndex}>
            <p lang="zh" className="story-paragraph">
              {sentences.map((sentence, index) => (
                <Sentence
                  key={index}
                  segments={sentence}
                  index={firstSentence + index}
                />
              ))}
            </p>
            {showTranslation && translationAligned && (
              <p lang="en" className="story-translation">
                {translation[paragraphIndex]}
              </p>
            )}
          </Fragment>
        ))}
      </div>

      {showTranslation && translation !== null && !translationAligned && (
        <section
          aria-label="Translation"
          lang="en"
          className="story-translation"
        >
          {translation.map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
          ))}
        </section>
      )}

      <Seal decorative className="seal-stamp" />

      <CloudDivider />

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

// One sentence of the story, soaked in at its turn during the entrance.
function Sentence({
  segments,
  index,
}: {
  segments: TextSegment[];
  index: number;
}) {
  return (
    <span
      className="sentence"
      style={
        {
          "--ink-delay": `${
            INK_START + Math.min(index, INK_STAGGER_MAX_SENTENCES) * INK_STAGGER
          }ms`,
        } as CSSProperties
      }
    >
      {segments.map((segment, segmentIndex) =>
        segment.kind === "word" ? (
          <ruby key={segmentIndex}>
            {segment.text}
            <rt>{segment.reading}</rt>
          </ruby>
        ) : (
          segment.text
        ),
      )}
    </span>
  );
}
