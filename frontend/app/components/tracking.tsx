"use client";

import { useEffect } from "react";
import { keepIdentityInStepWithConsent } from "@/lib/tracking/identity";

// Runs the tracking code that has to live for as long as the page does.
// Renders nothing.
export function Tracking() {
  useEffect(() => keepIdentityInStepWithConsent(), []);
  return null;
}
