import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetConsent } from "./consent";
import {
  ANONYMOUS_ID_COOKIE,
  SESSION_ID_COOKIE,
  cookieAttributes,
  deleteIdentity,
  getIdentity,
  keepIdentityInStepWithConsent,
} from "./identity";

const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

type CookiebotWindow = Window & {
  Cookiebot?: { consent: { statistics: boolean }; hasResponse: boolean };
};

function cookiebotReports(statistics: boolean): void {
  (window as CookiebotWindow).Cookiebot = {
    consent: { statistics },
    hasResponse: true,
  };
  window.dispatchEvent(new Event("CookiebotOnConsentReady"));
}

function cookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`))
    ?.split("=")[1];
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-06T09:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
  resetConsent();
  delete (window as CookiebotWindow).Cookiebot;
  deleteIdentity();
});

describe("cookieAttributes", () => {
  it("shares the cookies across huaben.app and its subdomains", () => {
    const expected = "; Path=/; SameSite=Lax; Domain=huaben.app; Secure";
    expect(cookieAttributes("huaben.app")).toBe(expected);
    expect(cookieAttributes("www.huaben.app")).toBe(expected);
  });

  it("is host-only anywhere else", () => {
    expect(cookieAttributes("localhost")).toBe("; Path=/; SameSite=Lax");
    expect(cookieAttributes("nothuaben.app")).toBe("; Path=/; SameSite=Lax");
  });
});

describe("getIdentity", () => {
  it("is null and sets no cookies without consent", () => {
    expect(getIdentity()).toBeNull();
    cookiebotReports(false);
    expect(getIdentity()).toBeNull();
    expect(document.cookie).toBe("");
  });

  it("creates both identifiers once consent is granted", () => {
    cookiebotReports(true);

    const identity = getIdentity();

    expect(identity?.anonymousId).toMatch(UUID_V4);
    expect(identity?.sessionId).toMatch(UUID_V4);
    expect(identity?.anonymousId).not.toBe(identity?.sessionId);
    expect(cookie(ANONYMOUS_ID_COOKIE)).toBe(identity?.anonymousId);
    expect(cookie(SESSION_ID_COOKIE)).toBe(identity?.sessionId);
  });

  it("returns the same identifiers on later calls", () => {
    cookiebotReports(true);

    expect(getIdentity()).toEqual(getIdentity());
  });

  it("keeps the session alive while there is activity", () => {
    cookiebotReports(true);
    const first = getIdentity();

    vi.advanceTimersByTime(29 * 60 * 1000);
    const second = getIdentity();
    vi.advanceTimersByTime(29 * 60 * 1000);

    expect(second?.sessionId).toBe(first?.sessionId);
    expect(getIdentity()?.sessionId).toBe(first?.sessionId);
  });

  it("starts a new session after 30 minutes without activity", () => {
    cookiebotReports(true);
    const first = getIdentity();

    vi.advanceTimersByTime(30 * 60 * 1000 + 1000);
    const second = getIdentity();

    expect(second?.sessionId).not.toBe(first?.sessionId);
    expect(second?.anonymousId).toBe(first?.anonymousId);
  });

  it("sets anonymous_id for 13 months and doesn't extend it", () => {
    const write = vi.spyOn(document, "cookie", "set");
    cookiebotReports(true);

    getIdentity();
    vi.advanceTimersByTime(24 * 60 * 60 * 1000);
    getIdentity();

    const anonymousWrites = write.mock.calls
      .map(([value]) => value)
      .filter((value) => value.startsWith(`${ANONYMOUS_ID_COOKIE}=`));
    expect(anonymousWrites).toHaveLength(1);
    expect(anonymousWrites[0]).toContain(
      `Expires=${new Date("2027-11-06T09:00:00Z").toUTCString()}`,
    );
    write.mockRestore();
  });

  it("replaces a cookie value that isn't a UUID", () => {
    cookiebotReports(true);
    document.cookie = `${ANONYMOUS_ID_COOKIE}=not-a-uuid; Path=/`;

    expect(getIdentity()?.anonymousId).toMatch(UUID_V4);
  });
});

describe("keepIdentityInStepWithConsent", () => {
  it("creates the identifiers when a new visitor accepts", () => {
    const stop = keepIdentityInStepWithConsent();
    expect(document.cookie).toBe("");

    cookiebotReports(true);

    expect(cookie(ANONYMOUS_ID_COOKIE)).toMatch(UUID_V4);
    expect(cookie(SESSION_ID_COOKIE)).toMatch(UUID_V4);
    stop();
  });

  it("deletes them when consent is withdrawn", () => {
    const stop = keepIdentityInStepWithConsent();
    cookiebotReports(true);

    cookiebotReports(false);

    expect(document.cookie).toBe("");
    stop();
  });

  it("keeps a returning visitor's identifiers until Cookiebot reports", () => {
    cookiebotReports(true);
    const before = getIdentity();
    // A new page load: consent isn't known yet.
    resetConsent();
    delete (window as CookiebotWindow).Cookiebot;

    const stop = keepIdentityInStepWithConsent();
    expect(cookie(ANONYMOUS_ID_COOKIE)).toBe(before?.anonymousId);
    cookiebotReports(true);

    expect(getIdentity()).toEqual(before);
    stop();
  });

  it("deletes leftover identifiers when a returning visitor's refusal is reported", () => {
    cookiebotReports(true);
    getIdentity();
    resetConsent();
    delete (window as CookiebotWindow).Cookiebot;

    const stop = keepIdentityInStepWithConsent();
    cookiebotReports(false);

    expect(document.cookie).toBe("");
    stop();
  });
});
