import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getSessionState,
  resetSessionState,
  setSignedIn,
} from "@/lib/session";
import { LogoutButton } from "./logout-button";

const { logOut } = vi.hoisted(() => ({ logOut: vi.fn() }));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>(
    "@/lib/api",
  );
  return { ...actual, logOut };
});

describe("LogoutButton", () => {
  beforeEach(() => resetSessionState());
  afterEach(() => vi.resetAllMocks());

  it("is hidden unless someone is logged in", () => {
    render(<LogoutButton />);

    expect(
      screen.queryByRole("button", { name: "Log out" }),
    ).not.toBeInTheDocument();
  });

  it("logs out and signs the page out", async () => {
    logOut.mockResolvedValue(undefined);
    act(() => setSignedIn("jack"));
    render(<LogoutButton />);

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await vi.waitFor(() =>
      expect(getSessionState()).toEqual({
        status: "signed-out",
        expired: false,
      }),
    );
    expect(logOut).toHaveBeenCalledOnce();
  });

  it("stays signed in and says so when logging out fails", async () => {
    logOut.mockRejectedValue(new TypeError("Failed to fetch"));
    act(() => setSignedIn("jack"));
    render(<LogoutButton />);

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(
      await screen.findByText("Log out failed. Try again."),
    ).toBeInTheDocument();
    expect(getSessionState().status).toBe("signed-in");
  });
});
