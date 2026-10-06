import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetConsent } from "./consent";
import { deleteIdentity, getIdentity } from "./identity";
import {
  clearIdentifiers,
  clearUserId,
  resetPageViews,
  showPage,
  trackedUrl,
} from "./page-view";

const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ORIGIN = window.location.origin;

type TrackedWindow = Window & { dataLayer?: Record<string, unknown>[] };

function cookiebotReports(statistics: boolean): void {
  Object.assign(window, {
    Cookiebot: { consent: { statistics }, hasResponse: true },
  });
  window.dispatchEvent(new Event("CookiebotOnConsentReady"));
}

function pushed(): Record<string, unknown>[] {
  return (window as TrackedWindow).dataLayer ?? [];
}

beforeEach(() => {
  document.title = "话本 Huaben";
  (window as TrackedWindow).dataLayer = [];
  cookiebotReports(true);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  resetPageViews();
  resetConsent();
  Reflect.deleteProperty(window, "Cookiebot");
  delete (window as TrackedWindow).dataLayer;
  deleteIdentity();
});

describe("trackedUrl", () => {
  it("keeps the story's id and drops everything else", () => {
    expect(trackedUrl(`${ORIGIN}/story?fresh=1&id=12&email=a@b.c`)).toBe(
      `${ORIGIN}/story?id=12`,
    );
  });

  it("drops the whole query string on other pages", () => {
    expect(trackedUrl(`${ORIGIN}/stories?id=12&token=abc`)).toBe(
      `${ORIGIN}/stories`,
    );
  });

  it("drops the fragment", () => {
    expect(trackedUrl(`${ORIGIN}/story?id=12#access_token=abc`)).toBe(
      `${ORIGIN}/story?id=12`,
    );
  });

  it("applies the allowlist to a path with a trailing slash", () => {
    expect(trackedUrl(`${ORIGIN}/story/?id=12&fresh=1`)).toBe(
      `${ORIGIN}/story/?id=12`,
    );
  });

  it("drops another site's whole query string, whatever its path", () => {
    expect(trackedUrl("https://example.com/story?id=12&q=secret")).toBe(
      "https://example.com/story",
    );
  });

  it("is undefined for something that isn't a URL", () => {
    expect(trackedUrl("")).toBeUndefined();
  });
});

describe("showPage", () => {
  it("pushes a page_view with every field of the spec", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-04T09:30:00.123Z"));

    showPage(`${ORIGIN}/story?id=12&fresh=1`, true, "42");

    const identity = getIdentity();
    expect(pushed()).toEqual([
      {
        event: "page_view",
        event_id: expect.stringMatching(UUID_V4),
        schema_version: "1.0.0",
        event_timestamp: "2026-10-04T09:30:00.123Z",
        user_id: "42",
        anonymous_id: identity?.anonymousId,
        session_id: identity?.sessionId,
        page_location: `${ORIGIN}/story?id=12`,
        page_path: "/story",
        page_title: "话本 Huaben",
        page_referrer: undefined,
      },
    ]);
  });

  it("carries every key even when a value is absent", () => {
    showPage(`${ORIGIN}/`, true, undefined);

    const [pageView] = pushed();
    expect(Object.keys(pageView)).toContain("user_id");
    expect(Object.keys(pageView)).toContain("page_referrer");
    expect(pageView.user_id).toBeUndefined();
  });

  it("uses the stripped document.referrer on the first page", () => {
    vi.spyOn(document, "referrer", "get").mockReturnValue(
      "https://example.com/search?q=chinese+stories",
    );

    showPage(`${ORIGIN}/`, true, undefined);

    expect(pushed()[0].page_referrer).toBe("https://example.com/search");
  });

  it("uses the previous page as the referrer after a route change", () => {
    showPage(`${ORIGIN}/stories`, true, "42");
    showPage(`${ORIGIN}/story?id=12&fresh=1`, true, "42");

    expect(pushed()).toHaveLength(2);
    expect(pushed()[1].page_location).toBe(`${ORIGIN}/story?id=12`);
    expect(pushed()[1].page_referrer).toBe(`${ORIGIN}/stories`);
    expect(pushed()[1].event_id).not.toBe(pushed()[0].event_id);
  });

  it("sends one page_view per page, however often it's called", () => {
    showPage(`${ORIGIN}/story?id=12&fresh=1`, true, "42");
    showPage(`${ORIGIN}/story?id=12&fresh=1`, true, "42");
    // The story page tidies its URL once the entrance has played.
    showPage(`${ORIGIN}/story?id=12`, true, "42");

    expect(pushed()).toHaveLength(1);
  });

  it("counts another story as another page", () => {
    showPage(`${ORIGIN}/story?id=12`, true, "42");
    showPage(`${ORIGIN}/story?id=13`, true, "42");

    expect(pushed()).toHaveLength(2);
  });

  it("holds the page_view back until it may be sent", () => {
    showPage(`${ORIGIN}/stories`, false, undefined);
    expect(pushed()).toEqual([]);

    showPage(`${ORIGIN}/stories`, true, "42");

    expect(pushed()).toHaveLength(1);
    expect(pushed()[0].user_id).toBe("42");
  });

  it("remembers the page before, even if its view was never sent", () => {
    showPage(`${ORIGIN}/stories`, false, undefined);
    showPage(`${ORIGIN}/generate`, true, undefined);

    expect(pushed()).toHaveLength(1);
    expect(pushed()[0].page_referrer).toBe(`${ORIGIN}/stories`);
  });

  it("clears user_id on the page_view after a logout", () => {
    showPage(`${ORIGIN}/stories`, true, "42");
    showPage(`${ORIGIN}/`, true, undefined);

    expect(pushed()[1]).toHaveProperty("user_id", undefined);
    expect(pushed()[1].anonymous_id).toBe(pushed()[0].anonymous_id);
    expect(pushed()[1].session_id).toBe(pushed()[0].session_id);
  });

  it("waits for the title Next.js puts back just after a route change", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-04T09:30:00.123Z"));
    document.querySelector("title")?.remove();

    showPage(`${ORIGIN}/stories`, true, "42");
    expect(pushed()).toEqual([]);
    vi.setSystemTime(new Date("2026-10-04T09:30:00.125Z"));
    document.title = "话本 Huaben";

    await vi.waitFor(() => expect(pushed()).toHaveLength(1));
    expect(pushed()[0].page_title).toBe("话本 Huaben");
    // Still the moment the page was shown, not the moment the title arrived.
    expect(pushed()[0].event_timestamp).toBe("2026-10-04T09:30:00.123Z");
  });

  it("goes without a title if none arrives", () => {
    vi.useFakeTimers();
    document.querySelector("title")?.remove();

    showPage(`${ORIGIN}/stories`, true, "42");
    expect(pushed()).toEqual([]);
    vi.advanceTimersByTime(1000);

    expect(pushed()).toHaveLength(1);
    expect(pushed()[0]).toHaveProperty("page_title", undefined);
  });

  it("sends a waiting page_view first, without a title, when the visitor moves on", async () => {
    document.querySelector("title")?.remove();
    showPage(`${ORIGIN}/stories`, true, "42");
    expect(pushed()).toEqual([]);

    showPage(`${ORIGIN}/generate`, true, "42");
    document.title = "话本 Huaben";

    await vi.waitFor(() => expect(pushed()).toHaveLength(2));
    expect(pushed().map((view) => view.page_path)).toEqual([
      "/stories",
      "/generate",
    ]);
    expect(pushed()[0]).toHaveProperty("page_title", undefined);
    expect(pushed()[1].page_title).toBe("话本 Huaben");
    // Nothing more arrives once the wait would have run out.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(pushed()).toHaveLength(2);
  });

  it("drops a waiting page_view if consent is withdrawn meanwhile", async () => {
    vi.useFakeTimers();
    document.querySelector("title")?.remove();
    showPage(`${ORIGIN}/stories`, true, "42");

    cookiebotReports(false);
    document.title = "话本 Huaben";
    vi.advanceTimersByTime(1000);
    await Promise.resolve();

    expect(pushed()).toEqual([]);
  });

  it("sends the dropped page_view if consent comes back on the same page", async () => {
    vi.useFakeTimers();
    document.querySelector("title")?.remove();
    showPage(`${ORIGIN}/stories`, true, "42");
    cookiebotReports(false);
    vi.advanceTimersByTime(1000);
    document.title = "话本 Huaben";

    cookiebotReports(true);
    showPage(`${ORIGIN}/stories`, true, "42");

    expect(pushed()).toHaveLength(1);
    expect(pushed()[0].anonymous_id).toBe(getIdentity()?.anonymousId);
  });

  it("sends nothing and sets no cookies without consent", () => {
    cookiebotReports(false);

    showPage(`${ORIGIN}/stories`, true, "42");

    expect(pushed()).toEqual([]);
    expect(document.cookie).toBe("");
  });
});

describe("clearUserId", () => {
  it("clears the user_id GTM is holding, without sending an event", () => {
    showPage(`${ORIGIN}/stories`, true, "42");

    clearUserId();

    expect(pushed()).toHaveLength(2);
    expect(pushed()[1]).toEqual({ user_id: undefined });
    expect(Object.keys(pushed()[1])).toEqual(["user_id"]);
  });

  it("pushes nothing when no user_id was ever sent", () => {
    clearUserId();
    showPage(`${ORIGIN}/`, true, undefined);
    clearUserId();

    expect(pushed()).toHaveLength(1);
  });

  it("clears it only once", () => {
    showPage(`${ORIGIN}/stories`, true, "42");

    clearUserId();
    clearUserId();

    expect(pushed()).toHaveLength(2);
  });

  it("pushes nothing more once a withdrawal of consent has cleared it", () => {
    showPage(`${ORIGIN}/stories`, true, "42");
    cookiebotReports(false);
    clearIdentifiers();

    clearUserId();

    expect(pushed()).toHaveLength(2);
  });

  it("sends a waiting page_view before clearing, so its user_id doesn't come back", () => {
    document.querySelector("title")?.remove();
    showPage(`${ORIGIN}/stories`, true, "42");

    clearUserId();

    expect(pushed()).toHaveLength(2);
    expect(pushed()[0]).toMatchObject({ event: "page_view", user_id: "42" });
    expect(pushed()[1]).toEqual({ user_id: undefined });
  });
});

describe("clearIdentifiers", () => {
  const CLEARED = {
    user_id: undefined,
    anonymous_id: undefined,
    session_id: undefined,
  };

  it("clears all three identifiers, without sending an event", () => {
    showPage(`${ORIGIN}/stories`, true, "42");
    cookiebotReports(false);

    clearIdentifiers();

    expect(pushed()).toHaveLength(2);
    expect(pushed()[1]).toEqual(CLEARED);
    expect(Object.keys(pushed()[1]).sort()).toEqual(
      Object.keys(CLEARED).sort(),
    );
  });

  it("clears the identifiers of a visitor who wasn't logged in", () => {
    showPage(`${ORIGIN}/`, true, undefined);
    cookiebotReports(false);

    clearIdentifiers();

    expect(Object.keys(pushed()[1]).sort()).toEqual(
      Object.keys(CLEARED).sort(),
    );
  });

  it("pushes nothing when no page_view was ever sent", () => {
    cookiebotReports(false);

    clearIdentifiers();

    expect(pushed()).toEqual([]);
  });

  it("clears them only once", () => {
    showPage(`${ORIGIN}/stories`, true, "42");
    cookiebotReports(false);

    clearIdentifiers();
    clearIdentifiers();

    expect(pushed()).toHaveLength(2);
  });

  it("drops a page_view that was still waiting for its title", () => {
    document.querySelector("title")?.remove();
    showPage(`${ORIGIN}/stories`, true, "42");
    cookiebotReports(false);

    clearIdentifiers();

    expect(pushed()).toEqual([]);
  });

  it("is followed by a new page_view for the same page if consent returns there", () => {
    showPage(`${ORIGIN}/stories`, true, "42");
    cookiebotReports(false);
    clearIdentifiers();

    cookiebotReports(true);
    showPage(`${ORIGIN}/stories`, true, "42");
    showPage(`${ORIGIN}/stories`, true, "42");

    const views = pushed().filter((entry) => entry.event === "page_view");
    expect(views).toHaveLength(2);
    expect(views[1].page_location).toBe(views[0].page_location);
    expect(views[1].event_id).not.toBe(views[0].event_id);
    expect(views[1].anonymous_id).toBe(getIdentity()?.anonymousId);
  });

  it("is followed by current identifiers on the next page_view once consent returns", () => {
    showPage(`${ORIGIN}/stories`, true, "42");
    cookiebotReports(false);
    clearIdentifiers();

    cookiebotReports(true);
    showPage(`${ORIGIN}/generate`, true, "42");

    expect(pushed()).toHaveLength(3);
    expect(pushed()[2]).toMatchObject({
      event: "page_view",
      user_id: "42",
      anonymous_id: getIdentity()?.anonymousId,
    });
  });
});
