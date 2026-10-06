import Script from "next/script";
import { gtmScriptUrl } from "@/lib/gtm";

// Google Tag Manager's <head> snippet, built from the build's env vars. The
// <noscript> iframe is left out on purpose: the app needs JavaScript anyway,
// and the iframe would load whatever the visitor's consent choice.
export function GoogleTagManager() {
  const src = gtmScriptUrl(
    process.env.NEXT_PUBLIC_GTM_ID,
    process.env.NEXT_PUBLIC_GTM_AUTH,
    process.env.NEXT_PUBLIC_GTM_PREVIEW,
  );
  if (!src) {
    return null;
  }

  return (
    <Script id="google-tag-manager" strategy="afterInteractive">
      {`window.dataLayer=window.dataLayer||[];window.dataLayer.push({"gtm.start":new Date().getTime(),event:"gtm.js"});var s=document.createElement("script");s.async=true;s.src=${JSON.stringify(src)};document.head.appendChild(s);`}
    </Script>
  );
}
