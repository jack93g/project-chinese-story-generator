"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import {
  getServerSessionState,
  getSessionState,
  subscribeToSession,
} from "@/lib/session";
import {
  getConsent,
  subscribeToConsent,
  type Consent,
} from "@/lib/tracking/consent";
import { keepIdentityInStepWithConsent } from "@/lib/tracking/identity";
import { showPage } from "@/lib/tracking/page-view";

function getServerConsent(): Consent {
  return "denied";
}

// Runs the tracking code that has to live for as long as the page does:
// keeping the identity cookies in step with consent, and sending page_view.
// Renders nothing. It reads the URL's query string, so the root layout wraps
// it in <Suspense>, as the static build requires.
export function Tracking() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const session = useSyncExternalStore(
    subscribeToSession,
    getSessionState,
    getServerSessionState,
  );
  const consent = useSyncExternalStore(
    subscribeToConsent,
    getConsent,
    getServerConsent,
  );

  useEffect(() => keepIdentityInStepWithConsent(), []);

  // Runs on first load, on every client-side route change, and when consent
  // or the session check settles. A page_view goes out only once both have:
  // without consent nothing is sent, and waiting for the session check lets
  // the first one carry user_id for someone who is logged in.
  const sessionChecked = session.status !== "checking";
  const userId = session.status === "signed-in" ? session.userId : undefined;
  useEffect(() => {
    const query = searchParams.toString();
    showPage(
      `${window.location.origin}${pathname}${query ? `?${query}` : ""}`,
      consent === "granted" && sessionChecked,
      userId,
    );
  }, [pathname, searchParams, consent, sessionChecked, userId]);

  return null;
}
