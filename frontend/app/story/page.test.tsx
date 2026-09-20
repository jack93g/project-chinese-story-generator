import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import StoryPage from "./page";

const { fetchStory, useSearchParams } = vi.hoisted(() => ({
  fetchStory: vi.fn(),
  useSearchParams: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>(
    "@/lib/api",
  );
  return { ...actual, fetchStory };
});

vi.mock("next/navigation", () => ({ useSearchParams }));

const STORY = {
  id: 5,
  title: "天气小记",
  created_at: "2026-09-06T17:42:55.413532+02:00",
  target_hsk: 2,
  content: "第一行。\n第二行。",
  selected_vocabulary: [
    {
      id: 1738,
      skritter_vocab_id: "zh-天气-0",
      language: "zh",
      writing: "天气",
      reading: "tian1qi4",
      definition_en: "weather",
    },
    {
      id: 1739,
      skritter_vocab_id: "zh-下雨-0",
      language: "zh",
      writing: "下雨",
      reading: "xia4yu3",
      definition_en: "to rain",
    },
  ],
};

describe("StoryPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state while the story is fetched", () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockReturnValue(new Promise(() => {}));
    render(<StoryPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading story");
  });

  it("shows a not-found state for an unknown story", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=999999"));
    fetchStory.mockRejectedValueOnce(
      new ApiError("Story 999999 not found", 404),
    );
    render(<StoryPage />);
    expect(
      await screen.findByRole("heading", { name: "Story not found" }),
    ).toBeInTheDocument();
  });

  it("shows an accessible error state for a non-404 failure", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockRejectedValueOnce(new ApiError("boom", 500));
    render(<StoryPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("renders the title, body with preserved line breaks, and glossary", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce(STORY);
    render(<StoryPage />);

    expect(
      await screen.findByRole("heading", { name: "天气小记" }),
    ).toBeInTheDocument();
    expect(screen.getByText("HSK 2", { exact: false })).toBeInTheDocument();

    const body = screen.getByText((_, element) =>
      element?.classList.contains("story-body") ?? false,
    );
    expect(body.textContent).toBe("第一行。\n第二行。");

    expect(screen.getByText("天气")).toBeInTheDocument();
    expect(screen.getByText("(tian1qi4)")).toBeInTheDocument();
    expect(screen.getByText("weather")).toBeInTheDocument();
    expect(screen.getByText("下雨")).toBeInTheDocument();
    expect(screen.getByText("to rain")).toBeInTheDocument();
  });

  it("omits the HSK badge when target_hsk is null but still shows the date", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({ ...STORY, target_hsk: null });
    render(<StoryPage />);

    await screen.findByRole("heading", { name: "天气小记" });

    expect(screen.queryByText(/HSK/)).not.toBeInTheDocument();
    expect(screen.getByText(/September 6, 2026/)).toBeInTheDocument();
  });

  it("omits pinyin parentheses and shows an explicit missing-definition note for null glossary fields", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({
      ...STORY,
      selected_vocabulary: [
        {
          id: 1740,
          skritter_vocab_id: "zh-颜色-0",
          language: "zh",
          writing: "颜色",
          reading: null,
          definition_en: null,
        },
      ],
    });
    render(<StoryPage />);

    await screen.findByRole("heading", { name: "天气小记" });

    const term = screen.getByText("颜色");
    expect(term.textContent).toBe("颜色");
    expect(screen.queryByText("()", { exact: false })).not.toBeInTheDocument();
    expect(
      screen.getByText("No definition available"),
    ).toBeInTheDocument();
  });

  it("refetches when the story id changes", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce(STORY);
    const { rerender } = render(<StoryPage />);
    await screen.findByRole("heading", { name: "天气小记" });

    useSearchParams.mockReturnValue(new URLSearchParams("id=6"));
    fetchStory.mockResolvedValueOnce({ ...STORY, id: 6, title: "换了故事" });
    rerender(<StoryPage />);

    expect(
      await screen.findByRole("heading", { name: "换了故事" }),
    ).toBeInTheDocument();
    expect(fetchStory).toHaveBeenCalledWith("6");
  });
});
