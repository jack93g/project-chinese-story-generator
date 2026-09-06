import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SiteNav } from "./site-nav";

describe("SiteNav", () => {
  it("links to the Generate and Saved stories pages", () => {
    render(<SiteNav />);

    expect(screen.getByRole("link", { name: "Generate" })).toHaveAttribute(
      "href",
      "/generate",
    );
    expect(
      screen.getByRole("link", { name: "Saved stories" }),
    ).toHaveAttribute("href", "/stories");
  });
});
