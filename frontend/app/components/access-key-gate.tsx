"use client";

import {
  useEffect,
  useState,
  useSyncExternalStore,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ACCESS_KEY_REJECTED_EVENT,
  getAccessKey,
  setAccessKey,
  subscribeToAccessKey,
} from "@/lib/access-key";

const hasStoredKey = () => getAccessKey() !== null;
// localStorage only exists in the browser, so the server render (and the
// first client render) show nothing until we know whether a key is stored.
const serverSnapshot = () => null;

export function AccessKeyGate({ children }: { children: ReactNode }) {
  const keyStored = useSyncExternalStore(
    subscribeToAccessKey,
    hasStoredKey,
    serverSnapshot,
  );
  const [rejected, setRejected] = useState(false);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    function handleRejected() {
      setDraft("");
      setRejected(true);
    }

    window.addEventListener(ACCESS_KEY_REJECTED_EVENT, handleRejected);
    return () =>
      window.removeEventListener(ACCESS_KEY_REJECTED_EVENT, handleRejected);
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const key = draft.trim();
    if (!key) {
      return;
    }
    setDraft("");
    setRejected(false);
    setAccessKey(key);
  }

  if (keyStored === null) {
    return null;
  }

  if (!keyStored) {
    return (
      <form onSubmit={handleSubmit} aria-labelledby="access-key-heading">
        <h1 id="access-key-heading">Enter access key</h1>
        <p>
          This site is private. Enter your access key to continue. It is stored
          only in this browser.
        </p>
        {rejected ? (
          <p role="alert">That access key was rejected. Please try again.</p>
        ) : null}
        <label>
          Access key
          <input
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        <button type="submit">Continue</button>
      </form>
    );
  }

  return <>{children}</>;
}
