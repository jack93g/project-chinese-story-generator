import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import GeneratePage from "./page";

const {
  fetchAllVocabularyLists,
  createStoryGeneration,
  fetchGenerationStatus,
  retryStoryGeneration,
  routerPush,
} = vi.hoisted(() => ({
  fetchAllVocabularyLists: vi.fn(),
  createStoryGeneration: vi.fn(),
  fetchGenerationStatus: vi.fn(),
  retryStoryGeneration: vi.fn(),
  routerPush: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>(
    "@/lib/api",
  );
  return {
    ...actual,
    fetchAllVocabularyLists,
    createStoryGeneration,
    fetchGenerationStatus,
    retryStoryGeneration,
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
}));

const LISTS = [
  { id: 1, name: "Love & Relationships", item_count: 12 },
  { id: 2, name: "Empty list", item_count: 0 },
];

async function renderReady() {
  fetchAllVocabularyLists.mockResolvedValueOnce(LISTS);
  render(<GeneratePage />);
  await screen.findByLabelText("Vocabulary list");
}

describe("GeneratePage", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("shows a loading state while vocabulary lists are fetched", () => {
    fetchAllVocabularyLists.mockReturnValue(new Promise(() => {}));
    render(<GeneratePage />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading vocabulary lists",
    );
  });

  it("shows an error state when vocabulary lists fail to load", async () => {
    fetchAllVocabularyLists.mockRejectedValueOnce(new ApiError("boom", 500));
    render(<GeneratePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("shows an empty state when there are no vocabulary lists", async () => {
    fetchAllVocabularyLists.mockResolvedValueOnce([]);
    render(<GeneratePage />);
    expect(
      await screen.findByText(/No vocabulary lists are available yet/),
    ).toBeInTheDocument();
  });

  it("displays every list across a multi-page response, not just the first page", async () => {
    const manyLists = Array.from({ length: 65 }, (_, index) => ({
      id: index + 1,
      name: `List ${index + 1}`,
      item_count: index + 1,
    }));
    fetchAllVocabularyLists.mockResolvedValueOnce(manyLists);
    render(<GeneratePage />);

    await screen.findByLabelText("Vocabulary list");

    expect(
      screen.getByRole("option", { name: "List 1 (1 words)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "List 65 (65 words)" }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Vocabulary list")).getAllByRole(
        "option",
      ),
    ).toHaveLength(manyLists.length + 1);
  });

  it("lists each vocabulary list with its item count and disables Generate until required fields are set", async () => {
    await renderReady();

    expect(
      screen.getByRole("option", { name: "Love & Relationships (12 words)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Generate" }),
    ).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "1" },
    });
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });
    expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled();
  });

  it("disables Generate and warns when the selected list has no vocabulary items", async () => {
    await renderReady();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });

    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
    expect(
      screen.getByText(/This list has no vocabulary items yet/),
    ).toBeInTheDocument();
  });

  it.each([
    ["0", "not at least 1"],
    ["1001", "over the max"],
    ["12.5", "not a whole number"],
    ["-5", "negative"],
  ])(
    "shows a validation error and disables Generate for an invalid target word count (%s: %s)",
    async (invalidValue) => {
      await renderReady();
      fireEvent.change(screen.getByLabelText("Vocabulary list"), {
        target: { value: "1" },
      });
      fireEvent.change(screen.getByLabelText("Target HSK level"), {
        target: { value: "2" },
      });
      expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled();

      fireEvent.change(
        screen.getByLabelText("Target word count (optional)"),
        { target: { value: invalidValue } },
      );

      expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Enter a whole number from 1 to 1000",
      );
      expect(
        screen.getByLabelText("Target word count (optional)"),
      ).toHaveAttribute("aria-invalid", "true");
    },
  );

  it("treats a blank target word count as valid and uses the default on submit", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 9, status: "queued" });
    await renderReady();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Target word count (optional)"), {
      target: { value: "" },
    });

    expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      expect(createStoryGeneration).toHaveBeenCalledWith(
        expect.objectContaining({ target_word_count: 150 }),
      );
    });
  });

  it("submits the exact payload the API expects and shows the queued confirmation", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 42, status: "queued" });
    await renderReady();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText("Topic (optional)"), {
      target: { value: "a trip to the market" },
    });
    fireEvent.change(screen.getByLabelText("Target word count (optional)"), {
      target: { value: "200" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      expect(createStoryGeneration).toHaveBeenCalledWith({
        vocabulary_list_id: 1,
        target_hsk_level: 3,
        target_word_count: 200,
        target_vocabulary_count: 10,
        topic: "a trip to the market",
      });
    });

    expect(
      await screen.findByRole("status"),
    ).toHaveTextContent("Queued");
  });

  it("caps the requested vocabulary count to the list's item count and sends null for a blank topic", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 7, status: "queued" });
    fetchAllVocabularyLists.mockResolvedValueOnce([
      { id: 3, name: "Small list", item_count: 4 },
    ]);
    render(<GeneratePage />);
    await screen.findByLabelText("Vocabulary list");

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      expect(createStoryGeneration).toHaveBeenCalledWith({
        vocabulary_list_id: 3,
        target_hsk_level: 1,
        target_word_count: 150,
        target_vocabulary_count: 4,
        topic: null,
      });
    });
  });

  it("submits custom words only, with no list, using the number of words as the vocabulary count", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 11, status: "queued" });
    await renderReady();

    fireEvent.change(screen.getByLabelText("Custom words (optional)"), {
      target: { value: "菜单, 饭馆、点菜\n菜单" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      expect(createStoryGeneration).toHaveBeenCalledWith({
        vocabulary_list_id: null,
        custom_words: ["菜单", "饭馆", "点菜"],
        target_hsk_level: 2,
        target_word_count: 150,
        target_vocabulary_count: 3,
        topic: null,
      });
    });
  });

  it("combines a list with custom words, leaving the remaining slots to the list", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 12, status: "queued" });
    await renderReady();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Custom words (optional)"), {
      target: { value: "菜单 饭馆" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      expect(createStoryGeneration).toHaveBeenCalledWith(
        expect.objectContaining({
          vocabulary_list_id: 1,
          custom_words: ["菜单", "饭馆"],
          target_vocabulary_count: 10,
        }),
      );
    });
  });

  it("allows an empty list when custom words are provided", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 13, status: "queued" });
    await renderReady();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Custom words (optional)"), {
      target: { value: "菜单" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });

    expect(
      screen.queryByText(/This list has no vocabulary items yet/),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      expect(createStoryGeneration).toHaveBeenCalledWith(
        expect.objectContaining({
          vocabulary_list_id: 2,
          custom_words: ["菜单"],
          target_vocabulary_count: 1,
        }),
      );
    });
  });

  it("tells the user to pick a list or enter custom words when neither is set", async () => {
    await renderReady();

    expect(
      screen.getByText(
        "Choose a vocabulary list above or enter at least one custom word.",
      ),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "1" },
    });
    expect(
      screen.getByText(/Optional\. Custom words are always included/),
    ).toBeInTheDocument();
  });

  it("blocks submission and explains when a custom word is not Chinese", async () => {
    await renderReady();

    fireEvent.change(screen.getByLabelText("Custom words (optional)"), {
      target: { value: "菜单 hello" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });

    expect(screen.getByRole("alert")).toHaveTextContent("hello");
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });

  it("shows an API error message when submission fails", async () => {
    createStoryGeneration.mockRejectedValueOnce(
      new ApiError("Vocabulary list 1 not found", 404),
    );
    await renderReady();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));

    expect(
      await screen.findByText("Vocabulary list 1 not found"),
    ).toBeInTheDocument();
  });

  async function flush() {
    await act(async () => {
      await Promise.resolve();
    });
  }

  // Fake timers must be active *before* the Generate click, since that's
  // what schedules the polling effect's first setTimeout — enabling fake
  // timers afterwards can't retroactively take over a timer that was
  // already scheduled against the real clock.
  async function submitReadyFormWithFakeTimers() {
    vi.useFakeTimers();
    fetchAllVocabularyLists.mockResolvedValueOnce(LISTS);
    const result = render(<GeneratePage />);
    await flush();

    fireEvent.change(screen.getByLabelText("Vocabulary list"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Target HSK level"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    await flush();

    return result;
  }

  it("polls generation status and redirects to the story once it succeeds", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 50, status: "queued" });
    await submitReadyFormWithFakeTimers();
    expect(screen.getByRole("status")).toHaveTextContent("Queued");

    fetchGenerationStatus.mockResolvedValueOnce({
      id: 50,
      status: "running",
      error_code: null,
      error_message: null,
      story_id: null,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(screen.getByRole("status")).toHaveTextContent(
      "Generating your story",
    );

    fetchGenerationStatus.mockResolvedValueOnce({
      id: 50,
      status: "succeeded",
      error_code: null,
      error_message: null,
      story_id: 99,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });

    expect(routerPush).toHaveBeenCalledWith("/story?id=99");
  });

  it("shows the safe failure message and stops polling once a request fails", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 51, status: "queued" });
    await submitReadyFormWithFakeTimers();

    fetchGenerationStatus.mockResolvedValueOnce({
      id: 51,
      status: "failed",
      error_code: "GenericFailure",
      error_message: "Story generation failed. You may retry this request.",
      story_id: null,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Story generation failed. You may retry this request.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();

    const callsAfterFailure = fetchGenerationStatus.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchGenerationStatus).toHaveBeenCalledTimes(callsAfterFailure);
  });

  it("stops polling immediately and shows a clear error on a 404 status response", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 60, status: "queued" });
    await submitReadyFormWithFakeTimers();

    fetchGenerationStatus.mockRejectedValueOnce(
      new ApiError("Generation request 60 not found", 404),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "This generation request could not be found.",
    );

    const callsAfterNotFound = fetchGenerationStatus.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchGenerationStatus).toHaveBeenCalledTimes(callsAfterNotFound);
  });

  it("stops polling immediately on any other 4xx status response", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 61, status: "queued" });
    await submitReadyFormWithFakeTimers();

    fetchGenerationStatus.mockRejectedValueOnce(
      new ApiError("Bad request", 400),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Bad request");
    expect(fetchGenerationStatus).toHaveBeenCalledTimes(1);
  });

  it("retries transient network/5xx status failures a bounded number of times before giving up", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 62, status: "queued" });
    await submitReadyFormWithFakeTimers();

    fetchGenerationStatus.mockRejectedValue(new TypeError("Failed to fetch"));

    for (let i = 0; i < 4; i += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2500);
      });
      expect(screen.getByRole("status")).toHaveTextContent("Queued");
    }

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Lost connection while checking on this request.",
    );
    expect(fetchGenerationStatus).toHaveBeenCalledTimes(5);

    const callsAfterGivingUp = fetchGenerationStatus.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchGenerationStatus).toHaveBeenCalledTimes(callsAfterGivingUp);
  });

  it("resets the transient-failure count after a successful poll", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 63, status: "queued" });
    await submitReadyFormWithFakeTimers();

    // Three failures, then a success, then two more failures — none of
    // this should add up to the bound of 5, since the successful poll
    // in between resets the counter.
    fetchGenerationStatus
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({
        id: 63,
        status: "running",
        error_code: null,
        error_message: null,
        story_id: null,
      })
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));

    for (let i = 0; i < 6; i += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2500);
      });
    }

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(fetchGenerationStatus).toHaveBeenCalledTimes(6);
  });

  it("retries a failed request and resumes polling on success", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 52, status: "queued" });
    await submitReadyFormWithFakeTimers();

    fetchGenerationStatus.mockResolvedValueOnce({
      id: 52,
      status: "failed",
      error_code: "GenericFailure",
      error_message: "Story generation failed. You may retry this request.",
      story_id: null,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();

    retryStoryGeneration.mockResolvedValueOnce({
      id: 52,
      status: "queued",
      error_code: null,
      error_message: null,
      story_id: null,
    });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await flush();

    expect(screen.getByRole("status")).toHaveTextContent("Queued");
    expect(retryStoryGeneration).toHaveBeenCalledWith(52);
  });

  it("shows a retry-specific error when the request is not eligible for retry", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 53, status: "queued" });
    await submitReadyFormWithFakeTimers();

    fetchGenerationStatus.mockResolvedValueOnce({
      id: 53,
      status: "failed",
      error_code: "GenericFailure",
      error_message: "Story generation failed. You may retry this request.",
      story_id: null,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();

    retryStoryGeneration.mockRejectedValueOnce(
      new ApiError(
        "Request 53 is not eligible for retry (current status: 'failed')",
        409,
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await flush();

    expect(screen.getByText(/not eligible for retry/)).toBeInTheDocument();
  });

  it("stops polling once the page is left", async () => {
    createStoryGeneration.mockResolvedValueOnce({ id: 54, status: "queued" });
    const { unmount } = await submitReadyFormWithFakeTimers();

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(fetchGenerationStatus).not.toHaveBeenCalled();
  });
});
