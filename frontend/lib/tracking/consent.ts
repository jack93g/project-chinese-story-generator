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
  Cookiebot?: { consent?: { statistics?: boolean }; hasResponse?: boolean };
};

let consent: Consent = "denied";
// Whether Cookiebot has reported the visitor's choice. "denied" before that
// only means "not known yet", which must not undo an earlier "granted".
let known = false;
let watching = false;
const listeners = new Set<() => void>();

function update(next: Consent, nextKnown: boolean): void {
  if (next !== consent || nextKnown !== known) {
    consent = next;
    known = nextKnown;
    listeners.forEach((listener) => listener());
  }
}

function onConsentReady(): void {
  const cookiebot = (window as CookiebotWindow).Cookiebot;
  update(cookiebot?.consent?.statistics === true ? "granted" : "denied", true);
}

// Started on first use, not at import, so importing this module during the
// static build touches no browser API.
function watchCookiebot(): void {
  if (watching || typeof window === "undefined") {
    return;
  }
  watching = true;
  window.addEventListener(CONSENT_READY_EVENT, onConsentReady);
  // Cookiebot may have reported before anything asked: its event isn't
  // repeated, so read what it already knows. Without a response there is
  // nothing to read yet: its `statistics` is false until the visitor chooses.
  const cookiebot = (window as CookiebotWindow).Cookiebot;
  if (cookiebot?.consent?.statistics === true || cookiebot?.hasResponse) {
    onConsentReady();
  }
}

export function getConsent(): Consent {
  watchCookiebot();
  return consent;
}

/** False until Cookiebot has reported: `getConsent()` is then a placeholder. */
export function isConsentKnown(): boolean {
  watchCookiebot();
  return known;
}

/**
 * `onChange` runs when the answer flips, and when it first becomes known.
 * Returns the unsubscribe.
 */
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
    window.removeEventListener(CONSENT_READY_EVENT, onConsentReady);
  }
  watching = false;
  consent = "denied";
  known = false;
  listeners.clear();
}
