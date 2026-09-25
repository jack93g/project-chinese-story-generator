import { describe, expect, it } from "vitest";
import { splitParagraphs } from "./paragraphs";

describe("splitParagraphs", () => {
  it("splits on line breaks, ignoring blank lines and outer whitespace", () => {
    expect(splitParagraphs("第一段。\n\n  第二段。 \n第三段。\n\n\n")).toEqual([
      "第一段。",
      "第二段。",
      "第三段。",
    ]);
  });

  it("treats Windows line endings like any other", () => {
    expect(splitParagraphs("第一段。\r\n\r\n第二段。")).toEqual([
      "第一段。",
      "第二段。",
    ]);
  });

  it("returns nothing for blank content", () => {
    expect(splitParagraphs(" \n\n ")).toEqual([]);
  });
});
