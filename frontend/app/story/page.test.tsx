import { fireEvent, render, screen } from "@testing-library/react";
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
    localStorage.clear();
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

  it("shows not-found without calling the API when there is no id", () => {
    useSearchParams.mockReturnValue(new URLSearchParams(""));
    render(<StoryPage />);
    expect(
      screen.getByRole("heading", { name: "Story not found" }),
    ).toBeInTheDocument();
    expect(fetchStory).not.toHaveBeenCalled();
  });

  it("shows not-found without calling the API when the id is not numeric", () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=../vocabulary"));
    render(<StoryPage />);
    expect(
      screen.getByRole("heading", { name: "Story not found" }),
    ).toBeInTheDocument();
    expect(fetchStory).not.toHaveBeenCalled();
  });

  it("shows an accessible error state for a non-404 failure", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockRejectedValueOnce(new ApiError("boom", 500));
    render(<StoryPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("renders the title, a paragraph per line, and glossary", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce(STORY);
    const { container } = render(<StoryPage />);

    expect(
      await screen.findByRole("heading", { name: "天气小记" }),
    ).toBeInTheDocument();
    expect(screen.getByText("HSK 2", { exact: false })).toBeInTheDocument();

    const paragraphs = container.querySelectorAll(".story-body .story-paragraph");
    expect([...paragraphs].map((p) => p.textContent)).toEqual([
      "第一行。",
      "第二行。",
    ]);

    expect(screen.getByText("天气")).toBeInTheDocument();
    expect(screen.getByText("(tiānqì)")).toBeInTheDocument();
    expect(screen.getByText("weather")).toBeInTheDocument();
    expect(screen.getByText("下雨")).toBeInTheDocument();
    expect(screen.getByText("to rain")).toBeInTheDocument();
  });

  it("shows tone-marked pinyin above vocabulary words in the story", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({ ...STORY, content: "今天天气好。" });
    const { container } = render(<StoryPage />);

    await screen.findByRole("heading", { name: "天气小记" });

    const rubies = container.querySelectorAll(".story-body ruby");
    expect(rubies).toHaveLength(1);
    expect(rubies[0].firstChild?.textContent).toBe("天气");
    expect(rubies[0].querySelector("rt")?.textContent).toBe("tiānqì");
  });

  it("toggles pinyin and remembers the choice", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValue(STORY);
    const { container, unmount } = render(<StoryPage />);

    const pinyin = await screen.findByRole("button", { name: "拼音 Pinyin" });
    const body = container.querySelector(".story-body")!;
    expect(pinyin).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(pinyin);
    expect(pinyin).toHaveAttribute("aria-pressed", "false");
    expect(body).toHaveClass("hide-pinyin");

    unmount();
    render(<StoryPage />);
    expect(
      await screen.findByRole("button", { name: "拼音 Pinyin" }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("has no translation toggle for a story without a translation", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({ ...STORY, translation_en: null });
    const { container } = render(<StoryPage />);

    await screen.findByRole("button", { name: "拼音 Pinyin" });

    expect(
      screen.queryByRole("button", { name: "翻译 Translation" }),
    ).not.toBeInTheDocument();
    expect(container.querySelector(".story-translation")).toBeNull();
  });

  it("shows each paragraph's English under it when toggled on, and remembers the choice", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValue({
      ...STORY,
      content: "第一行。\n\n第二行。",
      translation_en: ["The first line.", "The second line."],
    });
    const { container, unmount } = render(<StoryPage />);

    const toggle = await screen.findByRole("button", {
      name: "翻译 Translation",
    });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(container.querySelector(".story-translation")).toBeNull();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    const body = container.querySelector(".story-body")!;
    expect(
      [...body.children].map((child) => [
        child.className,
        child.getAttribute("lang"),
        child.textContent,
      ]),
    ).toEqual([
      ["story-paragraph", "zh", "第一行。"],
      ["story-translation", "en", "The first line."],
      ["story-paragraph", "zh", "第二行。"],
      ["story-translation", "en", "The second line."],
    ]);

    unmount();
    render(<StoryPage />);
    expect(
      await screen.findByRole("button", { name: "翻译 Translation" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("shows a translation that doesn't match the paragraphs as one block", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({
      ...STORY,
      translation_en: ["Both lines at once."],
    });
    const { container } = render(<StoryPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "翻译 Translation" }),
    );

    expect(container.querySelector(".story-body .story-translation")).toBeNull();
    expect(screen.getByRole("region", { name: "Translation" })).toHaveTextContent(
      "Both lines at once.",
    );
  });

  it("credits the model that wrote the story", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({
      ...STORY,
      provider: "groq",
      model: "openai/gpt-oss-120b",
    });
    render(<StoryPage />);

    await screen.findByRole("heading", { name: "天气小记" });

    expect(
      screen.getByText(/Written by gpt-oss-120b via Groq/),
    ).toBeInTheDocument();
  });

  it("omits the model credit when the API doesn't say", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce(STORY);
    render(<StoryPage />);

    await screen.findByRole("heading", { name: "天气小记" });

    expect(screen.queryByText(/Written by/)).not.toBeInTheDocument();
  });

  it("plays the entrance for a freshly generated story, then tidies the URL", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5&fresh=1"));
    fetchStory.mockResolvedValueOnce(STORY);
    const replaceState = vi.spyOn(window.history, "replaceState");
    const { container } = render(<StoryPage />);

    await screen.findByRole("heading", { name: "天气小记" });

    expect(container.querySelector("article")).toHaveClass("story-entrance");
    expect(replaceState).toHaveBeenCalledWith(null, "", "/story?id=5");
    // One animated span per sentence, delayed in turn across paragraphs.
    const sentences = container.querySelectorAll<HTMLElement>(".sentence");
    expect(sentences).toHaveLength(2);
    expect(sentences[0].style.getPropertyValue("--ink-delay")).toBe("150ms");
    expect(sentences[1].style.getPropertyValue("--ink-delay")).toBe("260ms");
    replaceState.mockRestore();
  });

  it("skips the entrance when opening a saved story", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce(STORY);
    const { container } = render(<StoryPage />);

    await screen.findByRole("heading", { name: "天气小记" });

    expect(container.querySelector("article")).not.toHaveClass(
      "story-entrance",
    );
  });

  it("omits the HSK badge when target_hsk is null but still shows the date", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({ ...STORY, target_hsk: null });
    render(<StoryPage />);

    await screen.findByRole("heading", { name: "天气小记" });

    expect(screen.queryByText(/HSK/)).not.toBeInTheDocument();
    expect(screen.getByText("二〇二六年九月六日")).toHaveAttribute(
      "title",
      "September 6, 2026",
    );
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

  it("offers a quiz after the glossary when the story has questions", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({
      ...STORY,
      questions: [{ question: "今天天气怎么样？", options: ["下雨", "很热"] }],
    });
    render(<StoryPage />);

    const quiz = await screen.findByRole("heading", {
      name: "Check your understanding",
    });
    const glossary = screen.getByRole("heading", { name: "Glossary" });

    expect(
      glossary.compareDocumentPosition(quiz) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByRole("group", { name: "今天天气怎么样？" }),
    ).toBeInTheDocument();
  });

  it("has no quiz for a story without questions", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({ ...STORY, questions: null });
    render(<StoryPage />);

    await screen.findByRole("heading", { name: "Glossary" });

    expect(
      screen.queryByRole("heading", { name: "Check your understanding" }),
    ).not.toBeInTheDocument();
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

  it("starts the quiz afresh when the story id changes", async () => {
    useSearchParams.mockReturnValue(new URLSearchParams("id=5"));
    fetchStory.mockResolvedValueOnce({
      ...STORY,
      questions: [{ question: "今天下雨吗？", options: ["下雨", "不下雨"] }],
    });
    const { rerender } = render(<StoryPage />);
    fireEvent.click(await screen.findByRole("radio", { name: "下雨" }));

    useSearchParams.mockReturnValue(new URLSearchParams("id=6"));
    fetchStory.mockResolvedValueOnce({
      ...STORY,
      id: 6,
      title: "换了故事",
      questions: [{ question: "谁来了？", options: ["小明", "小红"] }],
    });
    rerender(<StoryPage />);

    // Without a fresh quiz, the first option would stay chosen.
    expect(await screen.findByRole("radio", { name: "小明" })).not.toBeChecked();
  });
});
