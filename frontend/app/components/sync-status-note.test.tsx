import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SyncStatusNote } from "./sync-status-note";

const { fetchSyncStatus } = vi.hoisted(() => ({ fetchSyncStatus: vi.fn() }));

vi.mock("@/lib/api", () => ({ fetchSyncStatus }));

const NOW = new Date("2026-09-24T12:00:00Z");

describe("SyncStatusNote", () => {
  beforeEach(() => {
    // Fake only Date, so promises and findBy's polling still run normally.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("shows how long ago a recent sync succeeded", async () => {
    fetchSyncStatus.mockResolvedValueOnce({
      latest_run: {
        status: "succeeded",
        started_at: "2026-09-24T08:50:00Z",
        completed_at: "2026-09-24T09:00:00Z",
      },
    });
    render(<SyncStatusNote />);
    const note = await screen.findByText(
      "Vocabulary last synced from Skritter 3 hours ago.",
    );
    expect(note).toHaveClass("field-hint");
  });

  it("warns when the last sync is more than two days old", async () => {
    fetchSyncStatus.mockResolvedValueOnce({
      latest_run: {
        status: "succeeded",
        started_at: "2026-09-20T12:00:00Z",
        completed_at: "2026-09-20T12:10:00Z",
      },
    });
    render(<SyncStatusNote />);
    const note = await screen.findByText(/last synced from Skritter 3 days ago/);
    expect(note).toHaveClass("field-error");
  });

  it("warns when the last sync failed", async () => {
    fetchSyncStatus.mockResolvedValueOnce({
      latest_run: {
        status: "failed",
        started_at: "2026-09-23T10:00:00Z",
        completed_at: "2026-09-23T10:01:00Z",
      },
    });
    render(<SyncStatusNote />);
    const note = await screen.findByText(
      /The last Skritter sync failed \(yesterday\)/,
    );
    expect(note).toHaveClass("field-error");
  });

  it("says when a sync is in progress", async () => {
    fetchSyncStatus.mockResolvedValueOnce({
      latest_run: {
        status: "running",
        started_at: "2026-09-24T11:55:00Z",
        completed_at: null,
      },
    });
    render(<SyncStatusNote />);
    expect(
      await screen.findByText(
        "Syncing vocabulary from Skritter now (started 5 minutes ago).",
      ),
    ).toBeInTheDocument();
  });

  it("warns when there has never been a sync", async () => {
    fetchSyncStatus.mockResolvedValueOnce({ latest_run: null });
    render(<SyncStatusNote />);
    expect(
      await screen.findByText(
        "Vocabulary has never been synced from Skritter.",
      ),
    ).toHaveClass("field-error");
  });

  it("shows nothing when the status can't be loaded", async () => {
    fetchSyncStatus.mockRejectedValueOnce(new Error("offline"));
    const { container } = render(<SyncStatusNote />);
    await vi.waitFor(() => expect(fetchSyncStatus).toHaveBeenCalled());
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });
});
