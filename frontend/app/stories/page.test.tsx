import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import StoriesPage from "./page";

const { fetchAllStories, deleteStory } = vi.hoisted(() => ({
  fetchAllStories: vi.fn(),
  deleteStory: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>(
    "@/lib/api",
  );
  return { ...actual, fetchAllStories, deleteStory };
});

const STORIES = [
  {
    id: 5,
    title: "天气小记",
    created_at: "2026-09-06T17:42:55.413532+02:00",
    target_hsk: 2,
  },
  {
    id: 3,
    title: "市场的颜色",
    created_at: "2026-09-06T14:33:18.079067+02:00",
    target_hsk: null,
  },
];

describe("StoriesPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state while stories are fetched", () => {
    fetchAllStories.mockReturnValue(new Promise(() => {}));
    render(<StoriesPage />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading saved stories",
    );
  });

  it("shows an accessible error state when stories fail to load", async () => {
    fetchAllStories.mockRejectedValueOnce(new ApiError("boom", 500));
    render(<StoriesPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("shows an empty state with a link to Generate when there are no stories", async () => {
    fetchAllStories.mockResolvedValueOnce([]);
    render(<StoriesPage />);
    expect(await screen.findByText(/No stories yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Generate one" })).toHaveAttribute(
      "href",
      "/generate",
    );
  });

  it("lists every story linking to its reader page, showing HSK only when present", async () => {
    fetchAllStories.mockResolvedValueOnce(STORIES);
    render(<StoriesPage />);

    const withHsk = await screen.findByRole("link", { name: /天气小记/ });
    expect(withHsk).toHaveAttribute("href", "/story?id=5");
    expect(withHsk).toHaveTextContent("HSK 2");

    const withoutHsk = screen.getByRole("link", { name: /市场的颜色/ });
    expect(withoutHsk).toHaveAttribute("href", "/story?id=3");
    expect(withoutHsk).not.toHaveTextContent("HSK");
  });

  describe("deleting a story", () => {
    function getDeleteButton(storyName: RegExp) {
      const item = screen.getByRole("link", { name: storyName }).closest("li");
      if (!item) {
        throw new Error("Expected the story link to be inside a list item");
      }
      return within(item).getByRole("button", { name: "Delete" });
    }

    it("asks for confirmation before deleting, without calling the API yet", async () => {
      fetchAllStories.mockResolvedValueOnce(STORIES);
      render(<StoriesPage />);
      await screen.findByRole("link", { name: /天气小记/ });

      fireEvent.click(getDeleteButton(/天气小记/));

      expect(
        screen.getByRole("button", { name: "Confirm delete" }),
      ).toBeInTheDocument();
      expect(deleteStory).not.toHaveBeenCalled();
    });

    it("leaves the story untouched when the confirmation is cancelled", async () => {
      fetchAllStories.mockResolvedValueOnce(STORIES);
      render(<StoriesPage />);
      await screen.findByRole("link", { name: /天气小记/ });

      fireEvent.click(getDeleteButton(/天气小记/));
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

      expect(deleteStory).not.toHaveBeenCalled();
      expect(
        screen.queryByRole("button", { name: "Confirm delete" }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: /天气小记/ })).toBeInTheDocument();
    });

    it("removes the story from the list on a confirmed delete, without a full page reload", async () => {
      fetchAllStories.mockResolvedValueOnce(STORIES);
      deleteStory.mockResolvedValueOnce(undefined);
      render(<StoriesPage />);
      await screen.findByRole("link", { name: /天气小记/ });

      fireEvent.click(getDeleteButton(/天气小记/));
      fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

      await waitFor(() =>
        expect(
          screen.queryByRole("link", { name: /天气小记/ }),
        ).not.toBeInTheDocument(),
      );
      expect(deleteStory).toHaveBeenCalledWith(5);
      // The other story is untouched.
      expect(screen.getByRole("link", { name: /市场的颜色/ })).toBeInTheDocument();
    });

    it("shows an accessible error and keeps the story when the delete fails", async () => {
      fetchAllStories.mockResolvedValueOnce(STORIES);
      deleteStory.mockRejectedValueOnce(new ApiError("boom", 500));
      render(<StoriesPage />);
      await screen.findByRole("link", { name: /天气小记/ });

      fireEvent.click(getDeleteButton(/天气小记/));
      fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("boom");
      expect(screen.getByRole("link", { name: /天气小记/ })).toBeInTheDocument();
    });
  });
});
