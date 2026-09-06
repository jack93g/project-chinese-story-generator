import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import StoriesPage from "./page";

const { fetchAllStories } = vi.hoisted(() => ({
  fetchAllStories: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>(
    "@/lib/api",
  );
  return { ...actual, fetchAllStories };
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
    expect(withHsk).toHaveAttribute("href", "/stories/5");
    expect(withHsk).toHaveTextContent("HSK 2");

    const withoutHsk = screen.getByRole("link", { name: /市场的颜色/ });
    expect(withoutHsk).toHaveAttribute("href", "/stories/3");
    expect(withoutHsk).not.toHaveTextContent("HSK");
  });
});
