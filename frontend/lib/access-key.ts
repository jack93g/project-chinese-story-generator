// The API access key is entered by the user at runtime and kept only in this
// browser's localStorage. It must never be baked into the build or a
// NEXT_PUBLIC_* variable: the static export is public.

const STORAGE_KEY = "story-generator-access-key";

// Used when localStorage is unavailable (e.g. blocked site data), so the key
// still lasts until the next reload instead of the gate never letting you in.
let memoryKey: string | null = null;

export const ACCESS_KEY_REJECTED_EVENT = "access-key-rejected";
const ACCESS_KEY_CHANGED_EVENT = "access-key-changed";

/** For useSyncExternalStore: notifies on any change to the stored key. */
export function subscribeToAccessKey(onChange: () => void): () => void {
  window.addEventListener(ACCESS_KEY_CHANGED_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(ACCESS_KEY_CHANGED_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function getAccessKey(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? memoryKey;
  } catch {
    return memoryKey;
  }
}

export function setAccessKey(key: string): void {
  memoryKey = key;
  try {
    window.localStorage.setItem(STORAGE_KEY, key);
  } catch {
    // Storage unavailable; memoryKey above keeps the key for this page load.
  }
  window.dispatchEvent(new Event(ACCESS_KEY_CHANGED_EVENT));
}

export function clearAccessKey(): void {
  memoryKey = null;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clear.
  }
  window.dispatchEvent(new Event(ACCESS_KEY_CHANGED_EVENT));
}

/** Called when the API answers 401: drop the stale key and tell the gate. */
export function reportAccessKeyRejected(): void {
  clearAccessKey();
  window.dispatchEvent(new Event(ACCESS_KEY_REJECTED_EVENT));
}
