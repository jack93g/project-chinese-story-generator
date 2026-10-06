// The page_view event, pushed to GTM's dataLayer in the shape the tracking
// spec defines ("The frontend's dataLayer").
//
// Nothing here decides *when* a page view may be sent: the Tracking
// component calls showPage() on every route change and says whether the
// conditions (consent, session check) are met.

import { getIdentity } from "./identity";

/** The contract version this code was built against. Changed by hand. */
export const SCHEMA_VERSION = "1.0.0";

// Query parameters that are part of what the page *is*. Everything else is
// dropped before a URL is tracked, so tokens, emails and one-off flags such
// as ?fresh=1 never leave the browser.
const ALLOWED_QUERY_PARAMETERS: Record<string, string[]> = {
  "/story": ["id"],
};

type PageView = {
  event: "page_view";
  event_id: string;
  schema_version: string;
  event_timestamp: string;
  user_id: string | undefined;
  anonymous_id: string;
  session_id: string;
  page_location: string;
  page_path: string;
  page_title: string | undefined;
  page_referrer: string | undefined;
};

/**
 * `url` without its fragment and with only the allowlisted query parameters.
 * The allowlist only applies to this site's own pages: another site's URL (a
 * referrer) loses its whole query string. Undefined if `url` isn't a URL.
 */
export function trackedUrl(url: string): string | undefined {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return undefined;
  }
  const path = parsed.pathname.replace(/(.)\/$/, "$1");
  const allowed =
    parsed.origin === window.location.origin
      ? (ALLOWED_QUERY_PARAMETERS[path] ?? [])
      : [];
  const query = new URLSearchParams();
  for (const name of allowed) {
    const value = parsed.searchParams.get(name);
    if (value !== null) {
      query.set(name, value);
    }
  }
  const queryString = query.toString();
  return `${parsed.origin}${parsed.pathname}${queryString ? `?${queryString}` : ""}`;
}

// How long a page_view waits for the page's title before going without one.
const TITLE_WAIT_MS = 1000;

// A page_view that is waiting for its page's title. At most one at a time.
type Pending = {
  /** Send it now, without a title, because the visitor has moved on. */
  flush: () => void;
  /** Drop it. */
  cancel: () => void;
};
let pending: Pending | undefined;

/**
 * Calls `send` with the document's title once it has one. On a route change
 * Next.js removes the <title> and puts it back a moment later, and a
 * page_view is created in between, so it would otherwise go out with an
 * empty title. Gives up after a second and sends without one.
 */
function sendWithTitle(send: (title: string | undefined) => void): void {
  if (document.title) {
    send(document.title);
    return;
  }
  const settle = (deliver: boolean, title?: string) => {
    observer.disconnect();
    clearTimeout(timer);
    pending = undefined;
    if (deliver) {
      send(title);
    }
  };
  const observer = new MutationObserver(() => {
    if (document.title) {
      settle(true, document.title);
    }
  });
  observer.observe(document.head, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  const timer = setTimeout(() => settle(true), TITLE_WAIT_MS);
  pending = { flush: () => settle(true), cancel: () => settle(false) };
}

// The page being shown, as a tracked URL; the one shown before it; and
// whether this page's view has been sent. Kept in memory only.
let shown: string | undefined;
let referrer: string | undefined;
let sent = false;
// The user_id on the last push, which is what GTM's merged dataLayer holds.
let userIdInDataLayer: string | undefined;

function push(entry: object): void {
  const target = window as Window & { dataLayer?: unknown[] };
  target.dataLayer = target.dataLayer ?? [];
  target.dataLayer.push(entry);
}

/**
 * Call whenever the URL may have changed, and whenever `canSend` may have.
 * Sends at most one page_view per page shown: a URL change that only touches
 * dropped parameters (the story page removing ?fresh=1) isn't a new page.
 *
 * `canSend` is false while consent isn't granted or the session check is
 * still running. The view is then sent by a later call, once it's true.
 */
export function showPage(
  url: string,
  canSend: boolean,
  userId: string | undefined,
): void {
  const location = trackedUrl(url);
  if (location === undefined) {
    return;
  }
  if (location !== shown) {
    // The previous page's view goes out first, so views stay in order. The
    // title in the document may no longer be that page's, so it goes without.
    pending?.flush();
    // First page of this load: where the visitor came from. Afterwards: the
    // page they were just on.
    referrer = shown ?? trackedUrl(document.referrer);
    shown = location;
    sent = false;
  }
  if (sent || !canSend || !getIdentity()) {
    return;
  }
  sent = true;

  // What is true of the page when it's shown is fixed now. The title and the
  // identifiers are read when the view is sent, which can be a moment later.
  const eventId = crypto.randomUUID();
  const eventTimestamp = new Date().toISOString();
  const pageReferrer = referrer;
  sendWithTitle((title) => {
    // Null if consent was withdrawn while this waited: nothing is sent, and
    // the page's view is owed again if consent comes back while it's shown.
    const identity = getIdentity();
    if (!identity) {
      if (shown === location) {
        sent = false;
      }
      return;
    }
    // Every key on every push, undefined when there's no value: GTM merges
    // pushes, so a key left out would keep its last value (a user_id
    // surviving a logout).
    const pageView: PageView = {
      event: "page_view",
      event_id: eventId,
      schema_version: SCHEMA_VERSION,
      event_timestamp: eventTimestamp,
      user_id: userId,
      anonymous_id: identity.anonymousId,
      session_id: identity.sessionId,
      page_location: location,
      page_path: new URL(location).pathname,
      page_title: title,
      page_referrer: pageReferrer,
    };
    push(pageView);
    userIdInDataLayer = userId;
  });
}

/**
 * Call when nobody is logged in any more. GTM keeps the last user_id it was
 * given until the next page_view replaces it, and a logout doesn't change the
 * page, so without this a tag firing in between would still read the ID of
 * the person who just left. Pushes no event, only the cleared key.
 */
export function clearUserId(): void {
  // A view still waiting for its title was shown while they were logged in.
  pending?.flush();
  if (userIdInDataLayer !== undefined) {
    push({ user_id: undefined });
    userIdInDataLayer = undefined;
  }
}

/** Forget the page being shown; for tests, which share this module's state. */
export function resetPageViews(): void {
  pending?.cancel();
  userIdInDataLayer = undefined;
  shown = undefined;
  referrer = undefined;
  sent = false;
}
