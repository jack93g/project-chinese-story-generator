"use client";

import {
  useEffect,
  useState,
  useSyncExternalStore,
  type FormEvent,
  type ReactNode,
} from "react";
import { ApiError, fetchCurrentUser, logIn } from "@/lib/api";
import {
  forgetLegacyAccessKey,
  getServerSessionState,
  getSessionState,
  setSignedIn,
  setSignedOut,
  subscribeToSession,
} from "@/lib/session";

// Shows the app only to a logged-in browser. On load it asks the API who is
// logged in (the session cookie is invisible to page scripts); if nobody is,
// or the session later expires, it shows the login form instead.
export function LoginGate({ children }: { children: ReactNode }) {
  const session = useSyncExternalStore(
    subscribeToSession,
    getSessionState,
    getServerSessionState,
  );
  const [checkFailed, setCheckFailed] = useState(false);

  useEffect(() => {
    forgetLegacyAccessKey();
    void resolveSession().then((reached) => setCheckFailed(!reached));
  }, []);

  function retry() {
    setCheckFailed(false);
    void resolveSession().then((reached) => setCheckFailed(!reached));
  }

  if (session.status === "signed-in") {
    return <>{children}</>;
  }

  if (session.status === "signed-out") {
    return <LoginForm expired={session.expired} />;
  }

  if (checkFailed) {
    return (
      <div className="page-content">
        <p role="alert" className="state state-error">
          Couldn&apos;t reach the server. Check your connection and try again.
        </p>
        <button type="button" className="button" onClick={retry}>
          Try again
        </button>
      </div>
    );
  }

  return null;
}

/** Ask the API who is logged in. Returns false if it couldn't be reached. */
async function resolveSession(): Promise<boolean> {
  try {
    const user = await fetchCurrentUser();
    setSignedIn(user.username);
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) {
      return false;
    }
    setSignedOut();
  }
  return true;
}

type SubmitState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string };

function LoginForm({ expired }: { expired: boolean }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitState, setSubmitState] = useState<SubmitState>({
    status: "idle",
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setSubmitState({
        status: "error",
        message: "Enter your username and password.",
      });
      return;
    }

    setSubmitState({ status: "submitting" });
    try {
      const user = await logIn(username.trim(), password);
      setSignedIn(user.username);
    } catch (error) {
      setPassword("");
      setSubmitState({ status: "error", message: loginErrorMessage(error) });
    }
  }

  const submitting = submitState.status === "submitting";

  return (
    <div className="page-content">
      <h1 id="login-heading">Log in</h1>
      {expired ? (
        <p role="status" className="state">
          Your session has ended. Please log in again.
        </p>
      ) : null}
      <form
        className="generate-form"
        onSubmit={handleSubmit}
        aria-labelledby="login-heading"
        noValidate
      >
        <div className="form-field">
          <label htmlFor="login-username">Username</label>
          <input
            id="login-username"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={username}
            disabled={submitting}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>

        <div className="form-field">
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            disabled={submitting}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {submitState.status === "error" ? (
          <p role="alert" className="state state-error">
            {submitState.message}
          </p>
        ) : null}

        <button type="submit" className="button" disabled={submitting}>
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>
    </div>
  );
}

function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "Incorrect username or password.";
    }
    if (error.status === 429) {
      return "Too many login attempts. Wait a minute and try again.";
    }
  }
  return "Couldn't log in. Check your connection and try again.";
}
