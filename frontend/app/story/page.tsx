"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, fetchStory, type StoryDetail } from "@/lib/api";

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
  const id = useSearchParams().get("id");
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

  const { story } = state;

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
      </header>

      <p lang="zh" className="story-body">
        {story.content}
      </p>

      <section aria-labelledby="glossary-heading" className="story-glossary">
        <h2 id="glossary-heading">Glossary</h2>
        <dl>
          {story.selected_vocabulary.map((item) => (
            <div key={item.id} className="glossary-item">
              <dt lang="zh">
                {item.writing}
                {item.reading && (
                  <span className="glossary-reading"> ({item.reading})</span>
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
