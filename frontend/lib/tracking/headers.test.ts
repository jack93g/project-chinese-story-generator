import { afterEach, describe, expect, it } from "vitest";
import { resetConsent } from "./consent";
import { trackingHeaders } from "./headers";
import { getIdentity } from "./identity";

function cookiebotReports(statistics: boolean): void {
  Object.assign(window, {
    Cookiebot: { consent: { statistics }, hasResponse: true },
  });
  window.dispatchEvent(new Event("CookiebotOnConsentReady"));
}

afterEach(() => {
  resetConsent();
  Reflect.deleteProperty(window, "Cookiebot");
  document.cookie = "huaben_anonymous_id=; Max-Age=0; Path=/";
  document.cookie = "huaben_session_id=; Max-Age=0; Path=/";
});

describe("trackingHeaders", () => {
  it("says denied, with no identifiers, before Cookiebot reports", () => {
    expect(trackingHeaders()).toEqual({ "X-Tracking-Consent": "denied" });
    expect(document.cookie).toBe("");
  });

  it("says denied, with no identifiers, when consent is refused", () => {
    cookiebotReports(false);

    expect(trackingHeaders()).toEqual({ "X-Tracking-Consent": "denied" });
    expect(document.cookie).toBe("");
  });

  it("carries both identifiers with consent", () => {
    cookiebotReports(true);

    const headers = trackingHeaders();

    const identity = getIdentity();
    expect(headers).toEqual({
      "X-Tracking-Consent": "granted",
      "X-Anonymous-Id": identity?.anonymousId,
      "X-Session-Id": identity?.sessionId,
    });
  });

  it("stops sending the identifiers once consent is withdrawn", () => {
    cookiebotReports(true);
    trackingHeaders();

    cookiebotReports(false);

    expect(trackingHeaders()).toEqual({ "X-Tracking-Consent": "denied" });
  });
});
