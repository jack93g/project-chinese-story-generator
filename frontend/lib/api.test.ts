import { afterEach, describe, expect, it, vi } from "vitest";

const ENV_KEY = "NEXT_PUBLIC_API_BASE_URL";
const originalValue = process.env[ENV_KEY];

describe("apiUrl", () => {
  afterEach(() => {
    if (originalValue === undefined) {
      delete process.env[ENV_KEY];
    } else {
      process.env[ENV_KEY] = originalValue;
    }
    vi.resetModules();
  });

  it("defaults to the local API when no env var is set", async () => {
    delete process.env[ENV_KEY];
    const { apiUrl } = await import("./api");
    expect(apiUrl("/vocabulary-lists")).toBe(
      "http://127.0.0.1:8000/vocabulary-lists",
    );
  });

  it("uses NEXT_PUBLIC_API_BASE_URL when set", async () => {
    process.env[ENV_KEY] = "https://api.example.com";
    const { apiUrl } = await import("./api");
    expect(apiUrl("stories")).toBe("https://api.example.com/stories");
  });
});

describe("fetchVocabularyLists", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the given limit and offset as query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 10, offset: 5 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchVocabularyLists } = await import("./api");
    await fetchVocabularyLists({ limit: 10, offset: 5 });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/vocabulary-lists?limit=10&offset=5",
      undefined,
    );
  });
});

describe("fetchAllVocabularyLists", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("follows pagination until every list has been fetched", async () => {
    const pageOne = {
      items: [
        { id: 1, name: "List 1", item_count: 3 },
        { id: 2, name: "List 2", item_count: 5 },
      ],
      total: 3,
      limit: 2,
      offset: 0,
    };
    const pageTwo = {
      items: [{ id: 3, name: "List 3", item_count: 1 }],
      total: 3,
      limit: 2,
      offset: 2,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => pageOne })
      .mockResolvedValueOnce({ ok: true, json: async () => pageTwo });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchAllVocabularyLists } = await import("./api");
    const items = await fetchAllVocabularyLists(2);

    expect(items).toEqual([...pageOne.items, ...pageTwo.items]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8000/vocabulary-lists?limit=2&offset=2",
      undefined,
    );
  });

  it("stops after a single page when everything already fits", async () => {
    const onlyPage = {
      items: [{ id: 1, name: "List 1", item_count: 3 }],
      total: 1,
      limit: 100,
      offset: 0,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => onlyPage });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchAllVocabularyLists } = await import("./api");
    const items = await fetchAllVocabularyLists();

    expect(items).toEqual(onlyPage.items);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("stops if the API reports more items than it actually returns", async () => {
    const shortPage = {
      items: [{ id: 1, name: "List 1", item_count: 3 }],
      total: 5,
      limit: 100,
      offset: 0,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => shortPage });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchAllVocabularyLists } = await import("./api");
    const items = await fetchAllVocabularyLists();

    expect(items).toEqual(shortPage.items);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("fetchStories / fetchAllStories", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetchStories sends the given limit and offset as query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 10, offset: 0 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchStories } = await import("./api");
    await fetchStories({ limit: 10, offset: 0 });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/stories?limit=10&offset=0",
      undefined,
    );
  });

  it("fetchAllStories paginates across multiple pages, reusing the same guard as vocabulary lists", async () => {
    const pageOne = {
      items: [
        { id: 1, title: "Story 1", created_at: "2026-01-01", target_hsk: 1 },
        { id: 2, title: "Story 2", created_at: "2026-01-02", target_hsk: 2 },
      ],
      total: 3,
      limit: 2,
      offset: 0,
    };
    const pageTwo = {
      items: [
        { id: 3, title: "Story 3", created_at: "2026-01-03", target_hsk: 3 },
      ],
      total: 3,
      limit: 2,
      offset: 2,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => pageOne })
      .mockResolvedValueOnce({ ok: true, json: async () => pageTwo });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchAllStories } = await import("./api");
    const items = await fetchAllStories(2);

    expect(items).toEqual([...pageOne.items, ...pageTwo.items]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("deleteStory", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends a DELETE request to the story's URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    const { deleteStory } = await import("./api");
    await deleteStory(7);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/stories/7",
      { method: "DELETE" },
    );
  });

  it("throws an ApiError with the response detail when the request fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Story 7 not found" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { deleteStory, ApiError } = await import("./api");

    await expect(deleteStory(7)).rejects.toMatchObject(
      new ApiError("Story 7 not found", 404),
    );
  });
});
