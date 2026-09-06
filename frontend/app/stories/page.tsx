"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, fetchAllStories, type StorySummary } from "@/lib/api";

type StoriesState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; stories: StorySummary[] };

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function StoriesPage() {
  const [state, setState] = useState<StoriesState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetchAllStories()
      .then((stories) => {
        if (!cancelled) {
          setState({ status: "ready", stories });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "error",
            message:
              error instanceof ApiError
                ? error.message
                : "Could not load saved stories.",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <div className="page-content">
        <h1>Saved stories</h1>
        <p role="status">Loading saved stories…</p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="page-content">
        <h1>Saved stories</h1>
        <p role="alert" className="field-error">
          {state.message}
        </p>
      </div>
    );
  }

  if (state.stories.length === 0) {
    return (
      <div className="page-content">
        <h1>Saved stories</h1>
        <p>
          No stories yet. <Link href="/generate">Generate one</Link> to get
          started.
        </p>
      </div>
    );
  }

  return (
    <div className="page-content">
      <h1>Saved stories</h1>
      <ul className="story-list">
        {state.stories.map((story) => (
          <li key={story.id}>
            <Link href={`/stories/${story.id}`} className="story-list-item">
              <span lang="zh" className="story-list-title">
                {story.title}
              </span>
              <span className="story-list-meta">
                {story.target_hsk !== null && (
                  <>HSK {story.target_hsk} &middot; </>
                )}
                {formatDate(story.created_at)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
