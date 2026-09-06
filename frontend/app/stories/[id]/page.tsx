"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
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

export default function StoryPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<StoryState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetchStory(params.id)
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
  }, [params.id]);

  if (state.status === "loading") {
    return (
      <div className="page-content">
        <p role="status">Loading story…</p>
      </div>
    );
  }

  if (state.status === "not-found") {
    return (
      <div className="page-content">
        <h1>Story not found</h1>
        <p>
          There&rsquo;s no saved story with this ID. It may have been removed,
          or the link may be incorrect.
        </p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="page-content">
        <h1>Something went wrong</h1>
        <p role="alert" className="field-error">
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
          HSK {story.target_hsk} &middot; {formatDate(story.created_at)}
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
