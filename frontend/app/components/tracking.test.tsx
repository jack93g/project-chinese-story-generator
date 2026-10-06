import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetSessionState, setSignedIn, setSignedOut } from "@/lib/session";
import { resetConsent } from "@/lib/tracking/consent";
import { deleteIdentity } from "@/lib/tracking/identity";
import { resetPageViews } from "@/lib/tracking/page-view";
import { Tracking } from "./tracking";

const route = vi.hoisted(() => ({ pathname: "/", search: "" }));

vi.mock("next/navigation", () => ({
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(route.search),
}));

const ORIGIN = window.location.origin;

type TrackedWindow = Window & { dataLayer?: Record<string, unknown>[] };

function cookiebotReports(statistics: boolean): void {
  Object.assign(window, {
    Cookiebot: { consent: { statistics }, hasResponse: true },
  });
  window.dispatchEvent(new Event("CookiebotOnConsentReady"));
}

function pageViews(): Record<string, unknown>[] {
  return ((window as TrackedWindow).dataLayer ?? []).filter(
    (entry) => entry.event === "page_view",
  );
}

function hasIdentityCookies(): boolean {
  return document.cookie.includes("huaben_");
}

beforeEach(() => {
  route.pathname = "/";
  route.search = "";
  document.title = "话本 Huaben";
  (window as TrackedWindow).dataLayer = [];
});

afterEach(() => {
  resetSessionState();
  resetPageViews();
  resetConsent();
  Reflect.deleteProperty(window, "Cookiebot");
  delete (window as TrackedWindow).dataLayer;
  deleteIdentity();
});

describe("Tracking", () => {
  it("sends the first page_view once consent and the session check are both in, with user_id", () => {
    render(<Tracking />);
    expect(pageViews()).toEqual([]);

    // A returning visitor who accepted: Cookiebot reports first...
    act(() => cookiebotReports(true));
    expect(pageViews()).toEqual([]);
    // ...then the session check finds them logged in.
    act(() => setSignedIn({ id: "42", username: "jack" }));

    expect(pageViews()).toHaveLength(1);
    expect(pageViews()[0]).toMatchObject({
      user_id: "42",
      page_location: `${ORIGIN}/`,
    });
  });

  it("sends it without user_id on the login screen", () => {
    render(<Tracking />);

    act(() => setSignedOut());
    act(() => cookiebotReports(true));

    expect(pageViews()).toHaveLength(1);
    expect(pageViews()[0]).toHaveProperty("user_id", undefined);
  });

  it("doesn't send another when someone logs in on the same page", () => {
    render(<Tracking />);
    act(() => setSignedOut());
    act(() => cookiebotReports(true));

    act(() => setSignedIn({ id: "42", username: "jack" }));

    expect(pageViews()).toHaveLength(1);
  });

  it("sends a page_view on each route change", () => {
    const { rerender } = render(<Tracking />);
    act(() => cookiebotReports(true));
    act(() => setSignedIn({ id: "42", username: "jack" }));

    route.pathname = "/story";
    route.search = "id=12&fresh=1";
    rerender(<Tracking />);
    // The story page drops ?fresh=1: still the same page.
    route.search = "id=12";
    rerender(<Tracking />);

    expect(pageViews()).toHaveLength(2);
    expect(pageViews()[1]).toMatchObject({
      page_location: `${ORIGIN}/story?id=12`,
      page_path: "/story",
      page_referrer: `${ORIGIN}/`,
    });
  });

  it("sends one for the page being shown when a new visitor accepts", () => {
    const { rerender } = render(<Tracking />);
    act(() => setSignedIn({ id: "42", username: "jack" }));
    route.pathname = "/stories";
    rerender(<Tracking />);
    expect(pageViews()).toEqual([]);
    expect(hasIdentityCookies()).toBe(false);

    act(() => cookiebotReports(true));

    expect(pageViews()).toHaveLength(1);
    expect(pageViews()[0].page_location).toBe(`${ORIGIN}/stories`);
    expect(hasIdentityCookies()).toBe(true);
  });

  it("sends nothing and sets no cookies when consent is refused", () => {
    const { rerender } = render(<Tracking />);
    act(() => setSignedIn({ id: "42", username: "jack" }));
    act(() => cookiebotReports(false));
    route.pathname = "/stories";
    rerender(<Tracking />);

    expect(pageViews()).toEqual([]);
    expect(hasIdentityCookies()).toBe(false);
  });

  it("clears user_id in the dataLayer as soon as someone logs out", () => {
    render(<Tracking />);
    act(() => cookiebotReports(true));
    act(() => setSignedIn({ id: "42", username: "jack" }));

    act(() => setSignedOut());

    const dataLayer = (window as TrackedWindow).dataLayer ?? [];
    expect(pageViews()).toHaveLength(1);
    expect(dataLayer.at(-1)).toEqual({ user_id: undefined });
    expect(Object.keys(dataLayer.at(-1) ?? {})).toEqual(["user_id"]);
  });

  it("clears all three identifiers in the dataLayer when consent is withdrawn", () => {
    render(<Tracking />);
    act(() => cookiebotReports(true));
    act(() => setSignedIn({ id: "42", username: "jack" }));

    act(() => cookiebotReports(false));

    const last = ((window as TrackedWindow).dataLayer ?? []).at(-1) ?? {};
    expect(pageViews()).toHaveLength(1);
    expect(Object.keys(last).sort()).toEqual([
      "anonymous_id",
      "session_id",
      "user_id",
    ]);
    expect(Object.values(last)).toEqual([undefined, undefined, undefined]);
    expect(hasIdentityCookies()).toBe(false);
  });

  it("sends a page_view for the page being shown when consent is granted again", () => {
    render(<Tracking />);
    act(() => cookiebotReports(true));
    act(() => setSignedIn({ id: "42", username: "jack" }));
    act(() => cookiebotReports(false));

    act(() => cookiebotReports(true));

    expect(pageViews()).toHaveLength(2);
    expect(pageViews()[1]).toMatchObject({
      user_id: "42",
      page_location: `${ORIGIN}/`,
    });
    expect(pageViews()[1].anonymous_id).not.toBe(pageViews()[0].anonymous_id);
  });

  it("keeps the identifiers and drops user_id after a logout", () => {
    const { rerender } = render(<Tracking />);
    act(() => cookiebotReports(true));
    act(() => setSignedIn({ id: "42", username: "jack" }));

    act(() => setSignedOut());
    route.pathname = "/generate";
    rerender(<Tracking />);

    const [before, after] = pageViews();
    expect(after).toHaveProperty("user_id", undefined);
    expect(after.anonymous_id).toBe(before.anonymous_id);
    expect(after.session_id).toBe(before.session_id);
  });
});
