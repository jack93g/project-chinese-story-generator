// Where Google Tag Manager's container script is loaded from.
//
// With only a container ID, that's the Live container, which is what the
// GitHub Pages build uses. `auth` and `preview` select one of the container's
// Environments instead: the local dev server sets them to load "dev".

const GTM_SCRIPT_URL = "https://www.googletagmanager.com/gtm.js";

/** Returns null when no container is configured, so GTM isn't loaded at all. */
export function gtmScriptUrl(
  containerId: string | undefined,
  auth?: string,
  preview?: string,
): string | null {
  if (!containerId) {
    return null;
  }
  const url = `${GTM_SCRIPT_URL}?id=${encodeURIComponent(containerId)}`;
  if (!auth || !preview) {
    if (auth || preview) {
      console.warn(
        "GTM: only one of NEXT_PUBLIC_GTM_AUTH and NEXT_PUBLIC_GTM_PREVIEW is set, so the Live container is loaded.",
      );
    }
    return url;
  }
  // gtm_cookies_win=x is part of every Environment snippet GTM hands out.
  return `${url}&gtm_auth=${encodeURIComponent(auth)}&gtm_preview=${encodeURIComponent(preview)}&gtm_cookies_win=x`;
}
