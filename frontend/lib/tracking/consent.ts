// Whether the visitor has agreed to analytics, for the rest of the tracking
// code: the identity cookies, the tracking headers on API calls, and
// page_view all depend on it.
//
// The answer comes from Cookiebot, which is the only thing this module
// knows about: swapping the consent platform means rewriting this file and
// nothing else. "Analytics" is Cookiebot's Statistics category, the one its
// GTM tag maps to Consent Mode's analytics_storage.
//
// Cookiebot's script is loaded by GTM, after the app has started, so the
// state is followed, not read once. Until Cookiebot reports, consent is
// unknown, which counts as denied.

export type Consent = "granted" | "denied";

// Fires on every page load once the visitor's choice is known (a returning
// visitor's saved one included), and again whenever they change it.
const CONSENT_READY_EVENT = "CookiebotOnConsentReady";

type CookiebotWindow = Window & {
  Cookiebot?: { consent?: { statistics?: boolean } };
};

let consent: Consent = "denied";
let watching = false;
const listeners = new Set<() => void>();

function readCookiebot(): void {
  const granted = (window as CookiebotWindow).Cookiebot?.consent?.statistics;
  const next: Consent = granted === true ? "granted" : "denied";
  if (next !== consent) {
    consent = next;
    listeners.forEach((listener) => listener());
  }
}

// Started on first use, not at import, so importing this module during the
// static build touches no browser API.
function watchCookiebot(): void {
  if (watching || typeof window === "undefined") {
    return;
  }
  watching = true;
  window.addEventListener(CONSENT_READY_EVENT, readCookiebot);
  // Cookiebot may have reported before anything asked: its event isn't
  // repeated, so read what it already knows.
  readCookiebot();
}

export function getConsent(): Consent {
  watchCookiebot();
  return consent;
}

/** `onChange` runs whenever the answer flips. Returns the unsubscribe. */
export function subscribeToConsent(onChange: () => void): () => void {
  watchCookiebot();
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

/** Back to the unstarted state; for tests, which share this module's state. */
export function resetConsent(): void {
  if (watching) {
    window.removeEventListener(CONSENT_READY_EVENT, readCookiebot);
  }
  watching = false;
  consent = "denied";
  listeners.clear();
}
