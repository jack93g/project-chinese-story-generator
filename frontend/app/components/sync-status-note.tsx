"use client";

import { useEffect, useState } from "react";
import { fetchSyncStatus, type SyncRun } from "@/lib/api";
import { formatTimeAgo } from "@/lib/dates";

// The Droplet syncs daily, so a sync older than this means the schedule has
// stopped.
const STALE_AFTER_MS = 2 * 24 * 60 * 60 * 1000;
// A full --refresh sync takes about 15 minutes, so one "running" for longer
// than this has almost certainly died.
const STUCK_AFTER_MS = 60 * 60 * 1000;

type Note = { text: string; warning: boolean };

function describe(run: SyncRun | null, now: Date): Note {
  if (run === null) {
    return {
      text: "Vocabulary has never been synced from Skritter.",
      warning: true,
    };
  }
  if (run.status === "running") {
    if (now.getTime() - new Date(run.started_at).getTime() > STUCK_AFTER_MS) {
      return {
        text: `A Skritter sync started ${formatTimeAgo(run.started_at, now)} and hasn't finished, so recently added words may be missing.`,
        warning: true,
      };
    }
    return {
      text: `Syncing vocabulary from Skritter now (started ${formatTimeAgo(run.started_at, now)}).`,
      warning: false,
    };
  }
  const finished = run.completed_at ?? run.started_at;
  const ago = formatTimeAgo(finished, now);
  if (run.status === "failed") {
    return {
      text: `The last Skritter sync failed (${ago}), so recently added words may be missing.`,
      warning: true,
    };
  }
  if (now.getTime() - new Date(finished).getTime() > STALE_AFTER_MS) {
    return {
      text: `Vocabulary was last synced from Skritter ${ago}, so recently added words may be missing.`,
      warning: true,
    };
  }
  return {
    text: `Vocabulary last synced from Skritter ${ago}.`,
    warning: false,
  };
}

/**
 * One line saying how fresh the Skritter vocabulary is, so a failing or
 * stopped scheduled sync gets noticed. Informational only: if the status
 * can't be loaded it renders nothing rather than getting in the way.
 */
export function SyncStatusNote() {
  const [note, setNote] = useState<Note | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSyncStatus()
      .then((status) => {
        if (!cancelled) {
          setNote(describe(status.latest_run, new Date()));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (note === null) {
    return null;
  }
  return (
    <p className={note.warning ? "field-error" : "field-hint"}>{note.text}</p>
  );
}
