import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "./page";

describe("Home", () => {
  it("links to the Generate and saved-stories pages", () => {
    render(<Home />);

    expect(
      screen.getByRole("link", { name: "Generate a story" }),
    ).toHaveAttribute("href", "/generate");
    expect(
      screen.getByRole("link", { name: "Browse saved stories" }),
    ).toHaveAttribute("href", "/stories");
  });
});
