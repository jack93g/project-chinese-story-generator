// The tracking headers sent with every API call (see the tracking spec,
// "Reaching the API"). The consent header always goes; the two identifiers
// only with consent. The API must allow all three in its CORS setup.

import { getConsent } from "./consent";
import { getIdentity } from "./identity";

export function trackingHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "X-Tracking-Consent": getConsent(),
  };
  const identity = getIdentity();
  if (identity) {
    headers["X-Anonymous-Id"] = identity.anonymousId;
    headers["X-Session-Id"] = identity.sessionId;
  }
  return headers;
}
