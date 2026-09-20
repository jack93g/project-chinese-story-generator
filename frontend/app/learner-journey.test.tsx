/**
 * Integration test for the M4-5 learner journey: unlike the per-page unit
 * tests (which mock `@/lib/api` entirely), this exercises the real
 * `lib/api.ts` HTTP client — only `fetch` itself is stubbed, with responses
 * keyed by method + URL — through generation submission, polling to a
 * terminal status, navigating to the story reader, and the failed/retry
 * branch. `next/navigation` is faked with a tiny in-memory router so
 * `router.push` genuinely swaps which page is mounted, the way real
 * client-side navigation would.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useEffect, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GeneratePage from "./generate/page";
import StoryPage from "./story/page";

let currentPath = "/generate";
let setCurrentPath: (path: string) => void = () => {};

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: (path: string) => {
      currentPath = path;
      setCurrentPath(path);
    },
  }),
  useSearchParams: () => new URLSearchParams(currentPath.split("?")[1] ?? ""),
}));

function Harness() {
  const [path, setPath] = useState(currentPath);
  useEffect(() => {
    setCurrentPath = setPath;
    return () => {
      setCurrentPath = () => {};
    };
  }, [setPath]);
  return path.startsWith("/story?") ? <StoryPage /> : <GeneratePage />;
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

async function flush() {
  // Several microtask turns, not just one — a chain like fetch().then(json).then(setState)
  // needs multiple ticks to fully settle, and fake timers are active in these
  // tests, so `findBy`/`waitFor`'s own timer-based retry loop can't be relied on.
  await act(async () => {
    for (let i = 0; i < 20; i += 1) {
      await Promise.resolve();
    }
  });
}

const LIST = { id: 1, name: "Colours", item_count: 5 };
const GLOSSARY_ITEM = {
  id: 1,
  skritter_vocab_id: "zh-颜色-0",
  language: "zh",
  writing: "颜色",
  reading: "yan2se4",
  definition_en: "color",
};

describe("learner journey (real API client, fake HTTP + navigation)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    currentPath = "/generate";
    setCurrentPath = () => {};
  });

  it("submits a generation, polls to success, and navigates to the finished story", async () => {
    let statusPolls = 0;
    const fetchMock = vi.fn(
      async (url: string, init?: RequestInit): Promise<Response> => {
        const method = init?.method ?? "GET";

        if (url.startsWith("http://127.0.0.1:8000/vocabulary-lists")) {
          return jsonResponse({
            items: [LIST],
            total: 1,
            limit: 100,
            offset: 0,
          });
        }
        if (
          url === "http://127.0.0.1:8000/story-generations" &&
          method === "POST"
        ) {
          return jsonResponse({ id: 10, status: "queued" }, 202);
        }
        if (url === "http://127.0.0.1:8000/story-generations/10") {
          statusPolls += 1;
          if (statusPolls === 1) {
            return jsonResponse({
              id: 10,
              status: "running",
              error_code: null,
              error_message: null,
              story_id: null,
            });
          }
          return jsonResponse({
            id: 10,
            status: "succeeded",
            error_code: null,
            error_message: null,
            story_id: 55,
          });
        }
        if (url === "http://127.0.0.1:8000/stories/55") {
          return jsonResponse({
            id: 55,
            title: "颜色的公园",
            created_at: "2026-09-06T00:00:00Z",
            target_hsk: 2,
            content: "公园里有很多颜色。",
            selected_vocabulary: [GLOSSARY_ITEM],
          });
        }
        throw new Error(`Unhandled fetch in test: ${method} ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    vi.useFakeTimers();
    render(<Harness />);
    await flush();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    await flush();

    expect(screen.getByRole("status")).toHaveTextContent("Queued");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(screen.getByRole("status")).toHaveTextContent(
      "Generating your story",
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    // The redirect swaps the harness to StoryPage, which fetches on mount.
    await flush();

    expect(
      screen.getByRole("heading", { name: "颜色的公园" }),
    ).toBeInTheDocument();
    expect(screen.getByText("颜色")).toBeInTheDocument();
    expect(screen.getByText("color")).toBeInTheDocument();
  });

  it("shows the failed status and lets the learner retry through the real client", async () => {
    let retried = false;
    const fetchMock = vi.fn(
      async (url: string, init?: RequestInit): Promise<Response> => {
        const method = init?.method ?? "GET";

        if (url.startsWith("http://127.0.0.1:8000/vocabulary-lists")) {
          return jsonResponse({
            items: [LIST],
            total: 1,
            limit: 100,
            offset: 0,
          });
        }
        if (
          url === "http://127.0.0.1:8000/story-generations" &&
          method === "POST"
        ) {
          return jsonResponse({ id: 20, status: "queued" }, 202);
        }
        if (
          url === "http://127.0.0.1:8000/story-generations/20" &&
          method === "GET"
        ) {
          if (!retried) {
            return jsonResponse({
              id: 20,
              status: "failed",
              error_code: "GenericFailure",
              error_message:
                "Story generation failed. You may retry this request.",
              story_id: null,
            });
          }
          return jsonResponse({
            id: 20,
            status: "queued",
            error_code: null,
            error_message: null,
            story_id: null,
          });
        }
        if (
          url === "http://127.0.0.1:8000/story-generations/20/retry" &&
          method === "POST"
        ) {
          retried = true;
          return jsonResponse({
            id: 20,
            status: "queued",
            error_code: null,
            error_message: null,
            story_id: null,
          });
        }
        throw new Error(`Unhandled fetch in test: ${method} ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    vi.useFakeTimers();
    render(<Harness />);
    await flush();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    await flush();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Story generation failed. You may retry this request.",
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await flush();

    expect(screen.getByRole("status")).toHaveTextContent("Queued");
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          url === "http://127.0.0.1:8000/story-generations/20/retry" &&
          init?.method === "POST",
      ),
    ).toBe(true);
  });
});
