import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import GeneratePage from "./page";

const { fetchAllVocabularyLists, createStoryGeneration } = vi.hoisted(() => ({
  fetchAllVocabularyLists: vi.fn(),
  createStoryGeneration: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>(
    "@/lib/api",
  );
  return { ...actual, fetchAllVocabularyLists, createStoryGeneration };
});

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
      await screen.findByText(/Generation request #42 is queued/),
    ).toBeInTheDocument();
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
});
