import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearAccessKey,
  getAccessKey,
  reportAccessKeyRejected,
} from "@/lib/access-key";
import { AccessKeyGate } from "./access-key-gate";

describe("AccessKeyGate", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it("asks for a key when none is stored and hides the app", () => {
    render(<AccessKeyGate>secret content</AccessKeyGate>);

    expect(
      screen.getByRole("heading", { name: "Enter access key" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("stores the entered key and shows the app", () => {
    render(<AccessKeyGate>secret content</AccessKeyGate>);

    fireEvent.change(screen.getByLabelText("Access key"), {
      target: { value: "  my-key  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(screen.getByText("secret content")).toBeInTheDocument();
    expect(getAccessKey()).toBe("my-key");
  });

  it("shows the app straight away when a key is already stored", () => {
    window.localStorage.setItem("story-generator-access-key", "stored");

    render(<AccessKeyGate>secret content</AccessKeyGate>);

    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("returns to the prompt and clears the key when the API rejects it", async () => {
    window.localStorage.setItem("story-generator-access-key", "stale");
    render(<AccessKeyGate>secret content</AccessKeyGate>);

    reportAccessKeyRejected();

    expect(
      await screen.findByText("That access key was rejected. Please try again."),
    ).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(getAccessKey()).toBeNull();
  });
});

describe("AccessKeyGate with storage blocked", () => {
  afterEach(() => vi.restoreAllMocks());

  it("still lets the user in for this page load", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    clearAccessKey();

    render(<AccessKeyGate>secret content</AccessKeyGate>);
    fireEvent.change(screen.getByLabelText("Access key"), {
      target: { value: "k" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(screen.getByText("secret content")).toBeInTheDocument();
    clearAccessKey();
  });
});
