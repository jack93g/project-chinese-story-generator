// Whether this browser is logged in, shared by the login gate and the nav's
// log-out button. The session itself is an HttpOnly cookie that page scripts
// can't read, so this state comes from what the API says (GET /auth/me,
// login, logout, or any 401), never from inspecting the cookie.

export type SessionState =
  | { status: "checking" }
  | { status: "signed-in"; username: string }
  | { status: "signed-out"; expired: boolean };

const CHECKING: SessionState = { status: "checking" };

let state: SessionState = CHECKING;
const listeners = new Set<() => void>();

function setState(next: SessionState): void {
  state = next;
  listeners.forEach((listener) => listener());
}

/** For useSyncExternalStore. */
export function subscribeToSession(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

export function getSessionState(): SessionState {
  return state;
}

/** Server render (and first client render): not known yet. */
export function getServerSessionState(): SessionState {
  return CHECKING;
}

export function setSignedIn(username: string): void {
  setState({ status: "signed-in", username });
}

export function setSignedOut(): void {
  setState({ status: "signed-out", expired: false });
}

/** Called when the API answers 401 to an ordinary request. */
export function reportSessionExpired(): void {
  if (state.status === "signed-in") {
    setState({ status: "signed-out", expired: true });
  }
}

/** Back to "checking"; for tests, which share this module-level state. */
export function resetSessionState(): void {
  setState(CHECKING);
}

// Before login existed, the frontend kept a shared access key in
// localStorage. Remove any leftover copy so the secret doesn't linger.
const LEGACY_ACCESS_KEY_STORAGE_KEY = "story-generator-access-key";

export function forgetLegacyAccessKey(): void {
  try {
    window.localStorage.removeItem(LEGACY_ACCESS_KEY_STORAGE_KEY);
  } catch {
    // Storage unavailable: nothing stored to remove.
  }
}
