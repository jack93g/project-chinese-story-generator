import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { reportSessionExpired, resetSessionState } from "@/lib/session";
import { LoginGate } from "./login-gate";

const { fetchCurrentUser, logIn } = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  logIn: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>(
    "@/lib/api",
  );
  return { ...actual, fetchCurrentUser, logIn };
});

function fillAndSubmit(username: string, password: string) {
  fireEvent.change(screen.getByLabelText("Username"), {
    target: { value: username },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));
}

describe("LoginGate", () => {
  beforeEach(() => resetSessionState());
  afterEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
  });

  it("shows the app when the API says a user is logged in", async () => {
    fetchCurrentUser.mockResolvedValue({ username: "jack" });

    render(<LoginGate>secret content</LoginGate>);

    expect(await screen.findByText("secret content")).toBeInTheDocument();
  });

  it("shows nothing while it's still checking", () => {
    fetchCurrentUser.mockReturnValue(new Promise(() => {}));

    const { container } = render(<LoginGate>secret content</LoginGate>);

    expect(container).toBeEmptyDOMElement();
  });

  it("asks for a login when nobody is logged in and hides the app", async () => {
    fetchCurrentUser.mockRejectedValue(new ApiError("Not logged in", 401));

    render(<LoginGate>secret content</LoginGate>);

    expect(
      await screen.findByRole("heading", { name: "Log in" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("logs in with a trimmed username and then shows the app", async () => {
    fetchCurrentUser.mockRejectedValue(new ApiError("Not logged in", 401));
    logIn.mockResolvedValue({ username: "jack" });
    render(<LoginGate>secret content</LoginGate>);
    await screen.findByRole("heading", { name: "Log in" });

    fillAndSubmit("  jack ", "correct horse battery");

    expect(await screen.findByText("secret content")).toBeInTheDocument();
    expect(logIn).toHaveBeenCalledWith("jack", "correct horse battery");
  });

  it("says so and clears the password when the login is rejected", async () => {
    fetchCurrentUser.mockRejectedValue(new ApiError("Not logged in", 401));
    logIn.mockRejectedValue(new ApiError("Incorrect username or password", 401));
    render(<LoginGate>secret content</LoginGate>);
    await screen.findByRole("heading", { name: "Log in" });

    fillAndSubmit("jack", "wrong password");

    expect(
      await screen.findByText("Incorrect username or password."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("explains when login attempts are rate limited", async () => {
    fetchCurrentUser.mockRejectedValue(new ApiError("Not logged in", 401));
    logIn.mockRejectedValue(new ApiError("Too many login attempts", 429));
    render(<LoginGate>secret content</LoginGate>);
    await screen.findByRole("heading", { name: "Log in" });

    fillAndSubmit("jack", "any password");

    expect(
      await screen.findByText(
        "Too many login attempts. Wait a minute and try again.",
      ),
    ).toBeInTheDocument();
  });

  it("doesn't call the API when a field is empty", async () => {
    fetchCurrentUser.mockRejectedValue(new ApiError("Not logged in", 401));
    render(<LoginGate>secret content</LoginGate>);
    await screen.findByRole("heading", { name: "Log in" });

    fillAndSubmit("jack", "");

    expect(
      screen.getByText("Enter your username and password."),
    ).toBeInTheDocument();
    expect(logIn).not.toHaveBeenCalled();
  });

  it("returns to the login form when the session expires", async () => {
    fetchCurrentUser.mockResolvedValue({ username: "jack" });
    render(<LoginGate>secret content</LoginGate>);
    await screen.findByText("secret content");

    act(() => reportSessionExpired());

    expect(
      screen.getByText("Your session has ended. Please log in again."),
    ).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("offers a retry when the server can't be reached", async () => {
    fetchCurrentUser
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({ username: "jack" });
    render(<LoginGate>secret content</LoginGate>);

    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

    expect(await screen.findByText("secret content")).toBeInTheDocument();
  });

  it("removes the access key left over from before login existed", async () => {
    window.localStorage.setItem("story-generator-access-key", "old-secret");
    fetchCurrentUser.mockResolvedValue({ username: "jack" });

    render(<LoginGate>secret content</LoginGate>);
    await screen.findByText("secret content");

    expect(
      window.localStorage.getItem("story-generator-access-key"),
    ).toBeNull();
  });
});
