// The two identifiers tracking uses for a browser (see the tracking spec,
// D-020). Both live in first-party cookies, are created only with analytics
// consent, and are deleted when it's withdrawn.
//
// - anonymous_id identifies the browser. Its cookie lasts 13 months from when
//   it was first set and is never rewritten, so later visits don't extend it.
// - session_id identifies one visit. Its cookie is rewritten on every use, so
//   it ends after 30 minutes without activity.
//
// Logging out leaves both alone: only user_id is cleared, through the
// session state.

import { getConsent, isConsentKnown, subscribeToConsent } from "./consent";

export type Identity = { anonymousId: string; sessionId: string };

export const ANONYMOUS_ID_COOKIE = "huaben_anonymous_id";
export const SESSION_ID_COOKIE = "huaben_session_id";

const ANONYMOUS_ID_MONTHS = 13;
const SESSION_IDLE_SECONDS = 30 * 60;
const PROD_DOMAIN = "huaben.app";
const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/**
 * On the real site the cookies belong to huaben.app, so www.huaben.app
 * shares them. Anywhere else (localhost) they're host-only.
 */
export function cookieAttributes(hostname: string): string {
  const base = "; Path=/; SameSite=Lax";
  const onProd =
    hostname === PROD_DOMAIN || hostname.endsWith(`.${PROD_DOMAIN}`);
  return onProd ? `${base}; Domain=${PROD_DOMAIN}; Secure` : base;
}

function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  const entry = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith(prefix));
  const value = entry?.slice(prefix.length);
  // Anything that isn't one of our IDs is treated as missing and replaced.
  return value && UUID_V4.test(value) ? value : null;
}

function writeCookie(name: string, value: string, lifetime: string): void {
  document.cookie = `${name}=${value}; ${lifetime}${cookieAttributes(window.location.hostname)}`;
}

function deleteCookie(name: string): void {
  writeCookie(name, "", "Max-Age=0");
}

function writeAnonymousId(value: string): void {
  const expires = new Date();
  expires.setUTCMonth(expires.getUTCMonth() + ANONYMOUS_ID_MONTHS);
  writeCookie(ANONYMOUS_ID_COOKIE, value, `Expires=${expires.toUTCString()}`);
}

function writeSessionId(value: string): void {
  writeCookie(SESSION_ID_COOKIE, value, `Max-Age=${SESSION_IDLE_SECONDS}`);
}

/**
 * The identifiers, or null without consent. Each call counts as activity:
 * it creates whichever is missing and gives the session another 30 minutes.
 */
export function getIdentity(): Identity | null {
  if (typeof document === "undefined" || getConsent() !== "granted") {
    return null;
  }
  let anonymousId = readCookie(ANONYMOUS_ID_COOKIE);
  if (!anonymousId) {
    anonymousId = crypto.randomUUID();
    writeAnonymousId(anonymousId);
  }
  const sessionId = readCookie(SESSION_ID_COOKIE) ?? crypto.randomUUID();
  writeSessionId(sessionId);
  return { anonymousId, sessionId };
}

export function deleteIdentity(): void {
  deleteCookie(ANONYMOUS_ID_COOKIE);
  deleteCookie(SESSION_ID_COOKIE);
}

function followConsent(): void {
  if (getConsent() === "granted") {
    getIdentity();
  } else if (isConsentKnown()) {
    // Only once the visitor's refusal is known: before Cookiebot reports,
    // "denied" would wrongly delete a returning visitor's identifiers.
    deleteIdentity();
  }
}

/**
 * Keeps the cookies in step with consent: created as soon as it's granted,
 * deleted as soon as it's withdrawn. Returns the function that stops it.
 */
export function keepIdentityInStepWithConsent(): () => void {
  const unsubscribe = subscribeToConsent(followConsent);
  followConsent();
  return unsubscribe;
}
