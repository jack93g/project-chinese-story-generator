import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BrushLoader } from "./brush-loader";

describe("BrushLoader", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the characters without animating when the reader prefers reduced motion", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({ matches: true }),
    );
    const { container } = render(
      <BrushLoader text="正在写故事" pinyin="zhèngzài xiě gùshi" />,
    );

    const squares = container.querySelectorAll(".tianzige");
    expect([...squares].map((square) => square.textContent)).toEqual([
      ..."正在写故事",
    ]);
    expect(container).toHaveTextContent("zhèngzài xiě gùshi");
    expect(container.querySelector("svg")).toBeNull();
  });

  it("shows the characters without animating when one has no stroke data", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({ matches: false }),
    );
    const { container } = render(<BrushLoader text="正龙" pinyin="" />);

    expect(container.querySelector(".brush-loader-squares")).toHaveTextContent(
      "正龙",
    );
  });

  it("is hidden from screen readers", () => {
    const { container } = render(
      <BrushLoader text="排队中" pinyin="páiduì zhōng" />,
    );
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });
});
