"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiError,
  deleteStory,
  fetchAllStories,
  type StorySummary,
} from "@/lib/api";
import { StoryDate } from "../components/story-date";

type StoriesState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; stories: StorySummary[] };

type DeleteState =
  | { status: "idle" }
  | { status: "confirming" }
  | { status: "deleting" }
  | { status: "error"; message: string };

export default function StoriesPage() {
  const [state, setState] = useState<StoriesState>({ status: "loading" });
  const [deleteStates, setDeleteStates] = useState<
    Record<number, DeleteState>
  >({});

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

  function getDeleteState(storyId: number): DeleteState {
    return deleteStates[storyId] ?? { status: "idle" };
  }

  function requestDelete(storyId: number) {
    setDeleteStates((prev) => ({ ...prev, [storyId]: { status: "confirming" } }));
  }

  function cancelDelete(storyId: number) {
    setDeleteStates((prev) => ({ ...prev, [storyId]: { status: "idle" } }));
  }

  async function confirmDelete(storyId: number) {
    setDeleteStates((prev) => ({ ...prev, [storyId]: { status: "deleting" } }));
    try {
      await deleteStory(storyId);
      setState((prev) =>
        prev.status === "ready"
          ? {
              status: "ready",
              stories: prev.stories.filter((story) => story.id !== storyId),
            }
          : prev,
      );
      setDeleteStates((prev) => {
        const next = { ...prev };
        delete next[storyId];
        return next;
      });
    } catch (error) {
      setDeleteStates((prev) => ({
        ...prev,
        [storyId]: {
          status: "error",
          message:
            error instanceof ApiError
              ? error.message
              : "Could not delete this story.",
        },
      }));
    }
  }

  if (state.status === "loading") {
    return (
      <div className="page-content">
        <h1>Saved stories</h1>
        <p role="status" className="state">
          Loading saved stories…
        </p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="page-content">
        <h1>Saved stories</h1>
        <p role="alert" className="state state-error">
          {state.message}
        </p>
      </div>
    );
  }

  if (state.stories.length === 0) {
    return (
      <div className="page-content">
        <h1>Saved stories</h1>
        <p className="state">
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
        {state.stories.map((story) => {
          const deleteState = getDeleteState(story.id);

          return (
            <li key={story.id} className="story-list-row">
              <Link
                href={`/story?id=${story.id}`}
                className="story-list-item"
              >
                <span lang="zh" className="story-list-title">
                  {story.title}
                </span>
                <span className="story-list-meta">
                  {story.target_hsk !== null && (
                    <>HSK {story.target_hsk} &middot; </>
                  )}
                  <StoryDate isoDate={story.created_at} />
                </span>
              </Link>

              <div className="story-list-actions">
                {deleteState.status === "confirming" ? (
                  <>
                    <span className="story-list-confirm-text">
                      Delete this story?
                    </span>
                    <button
                      type="button"
                      className="button button-danger"
                      onClick={() => confirmDelete(story.id)}
                    >
                      Confirm delete
                    </button>
                    <button
                      type="button"
                      className="button-plain"
                      onClick={() => cancelDelete(story.id)}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="button-plain"
                    onClick={() => requestDelete(story.id)}
                    disabled={deleteState.status === "deleting"}
                  >
                    {deleteState.status === "deleting"
                      ? "Deleting…"
                      : "Delete"}
                  </button>
                )}
                {deleteState.status === "error" && (
                  <p role="alert" className="field-error">
                    {deleteState.message}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
