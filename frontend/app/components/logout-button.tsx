"use client";

import { useState, useSyncExternalStore } from "react";
import { logOut } from "@/lib/api";
import {
  getServerSessionState,
  getSessionState,
  setSignedOut,
  subscribeToSession,
} from "@/lib/session";

export function LogoutButton() {
  const session = useSyncExternalStore(
    subscribeToSession,
    getSessionState,
    getServerSessionState,
  );
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  if (session.status !== "signed-in") {
    return null;
  }

  async function handleClick() {
    setPending(true);
    setFailed(false);
    try {
      await logOut();
      setSignedOut();
    } catch {
      // Stay signed in: the cookie may still be valid, so claiming to be
      // logged out would be misleading on a shared computer.
      setFailed(true);
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="nav-button"
        onClick={handleClick}
        disabled={pending}
      >
        Log out
      </button>
      {failed ? (
        <span role="alert" className="field-error">
          Log out failed. Try again.
        </span>
      ) : null}
    </>
  );
}
