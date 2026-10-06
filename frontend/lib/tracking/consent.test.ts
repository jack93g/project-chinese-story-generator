import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getConsent,
  isConsentKnown,
  resetConsent,
  subscribeToConsent,
} from "./consent";

type CookiebotWindow = Window & {
  Cookiebot?: { consent?: { statistics?: boolean }; hasResponse?: boolean };
};

/** What Cookiebot does when the visitor's choice is known or changes. */
function cookiebotReports(statistics: boolean): void {
  (window as CookiebotWindow).Cookiebot = {
    consent: { statistics },
    hasResponse: true,
  };
  window.dispatchEvent(new Event("CookiebotOnConsentReady"));
}

afterEach(() => {
  resetConsent();
  delete (window as CookiebotWindow).Cookiebot;
});

describe("consent", () => {
  it("is denied, and not yet known, until Cookiebot has loaded", () => {
    expect(getConsent()).toBe("denied");
    expect(isConsentKnown()).toBe(false);
  });

  it("is still not known while the visitor hasn't chosen", () => {
    (window as CookiebotWindow).Cookiebot = {
      consent: { statistics: false },
      hasResponse: false,
    };

    expect(getConsent()).toBe("denied");
    expect(isConsentKnown()).toBe(false);
  });

  it("tells listeners when a visitor's refusal becomes known", () => {
    const onChange = vi.fn();
    subscribeToConsent(onChange);

    cookiebotReports(false);

    expect(getConsent()).toBe("denied");
    expect(isConsentKnown()).toBe(true);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("picks up a refusal Cookiebot reported before anything asked", () => {
    cookiebotReports(false);

    expect(isConsentKnown()).toBe(true);
  });

  it("follows Cookiebot when it reports after the app started", () => {
    const onChange = vi.fn();
    subscribeToConsent(onChange);

    cookiebotReports(true);

    expect(getConsent()).toBe("granted");
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("picks up a choice Cookiebot reported before anything asked", () => {
    cookiebotReports(true);

    expect(getConsent()).toBe("granted");
  });

  it("follows a withdrawal", () => {
    cookiebotReports(true);
    const onChange = vi.fn();
    subscribeToConsent(onChange);

    cookiebotReports(false);

    expect(getConsent()).toBe("denied");
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("only notifies when something changes", () => {
    const onChange = vi.fn();
    subscribeToConsent(onChange);

    cookiebotReports(true);
    cookiebotReports(true);

    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("stops notifying after unsubscribing", () => {
    const onChange = vi.fn();
    const unsubscribe = subscribeToConsent(onChange);

    unsubscribe();
    cookiebotReports(true);

    expect(onChange).not.toHaveBeenCalled();
    expect(getConsent()).toBe("granted");
  });

  it("ignores the other Cookiebot categories", () => {
    (window as CookiebotWindow).Cookiebot = {
      consent: { statistics: false, marketing: true, preferences: true } as {
        statistics: boolean;
      },
    };
    window.dispatchEvent(new Event("CookiebotOnConsentReady"));

    expect(getConsent()).toBe("denied");
  });
});
