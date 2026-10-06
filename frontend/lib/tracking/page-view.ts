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

/**
 * Runs `send` once the document has a title. On a route change Next.js
 * removes the <title> and puts it back a moment later, and a page_view is
 * created in between, so it would otherwise go out with an empty title.
 */
function whenTitleIsSet(send: () => void): void {
  if (document.title) {
    send();
    return;
  }
  let done = false;
  const finish = () => {
    if (done) {
      return;
    }
    done = true;
    observer.disconnect();
    clearTimeout(timer);
    send();
  };
  const observer = new MutationObserver(() => {
    if (document.title) {
      finish();
    }
  });
  observer.observe(document.head, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  const timer = setTimeout(finish, TITLE_WAIT_MS);
}

// The page being shown, as a tracked URL; the one shown before it; and
// whether this page's view has been sent. Kept in memory only.
let shown: string | undefined;
let referrer: string | undefined;
let sent = false;

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
    // First page of this load: where the visitor came from. Afterwards: the
    // page they were just on.
    referrer = shown ?? trackedUrl(document.referrer);
    shown = location;
    sent = false;
  }
  if (sent || !canSend) {
    return;
  }
  const identity = getIdentity();
  if (!identity) {
    return;
  }
  sent = true;

  // Every key on every push, undefined when there's no value: GTM merges
  // pushes, so a key left out would keep its last value (a user_id surviving
  // a logout).
  // Everything but the title is fixed now, when the page was shown.
  const pageView: PageView = {
    event: "page_view",
    event_id: crypto.randomUUID(),
    schema_version: SCHEMA_VERSION,
    event_timestamp: new Date().toISOString(),
    user_id: userId,
    anonymous_id: identity.anonymousId,
    session_id: identity.sessionId,
    page_location: location,
    page_path: new URL(location).pathname,
    page_title: undefined,
    page_referrer: referrer,
  };
  whenTitleIsSet(() => {
    pageView.page_title = document.title || undefined;
    const target = window as Window & { dataLayer?: unknown[] };
    target.dataLayer = target.dataLayer ?? [];
    target.dataLayer.push(pageView);
  });
}

/** Forget the page being shown; for tests, which share this module's state. */
export function resetPageViews(): void {
  shown = undefined;
  referrer = undefined;
  sent = false;
}
