import { describe, expect, it } from "vitest";
import { toToneMarks } from "./pinyin";

describe("toToneMarks", () => {
  it.each([
    ["tian1qi4", "tiānqì"],
    ["xia4yu3", "xiàyǔ"],
    ["ma5", "ma"],
    ["dou1", "dōu"],
    ["gui4", "guì"],
    ["liu2", "liú"],
    ["lv3xing2", "lǚxíng"],
    ["nu:3", "nǚ"],
    ["wan2r5", "wánr"],
    ["De2guo2", "Déguó"],
    ["E4", "È"],
    ["Ni3 zai4 ma5?", "Nǐ zài ma?"],
    ["xing2, hang2", "xíng, háng"],
    ["xian1... zai4...", "xiān... zài..."],
  ])("converts %s to %s", (reading, expected) => {
    expect(toToneMarks(reading)).toBe(expected);
  });
});
