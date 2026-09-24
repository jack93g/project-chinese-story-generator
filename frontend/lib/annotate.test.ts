import { describe, expect, it } from "vitest";
import { annotateVocabulary, groupSentences } from "./annotate";

describe("annotateVocabulary", () => {
  it("marks each occurrence of a vocabulary word with tone-marked pinyin", () => {
    expect(
      annotateVocabulary("今天天气好，明天天气也好。", [
        { writing: "天气", reading: "tian1qi4" },
      ]),
    ).toEqual([
      { kind: "text", text: "今天" },
      { kind: "word", text: "天气", reading: "tiānqì" },
      { kind: "text", text: "好，明天" },
      { kind: "word", text: "天气", reading: "tiānqì" },
      { kind: "text", text: "也好。" },
    ]);
  });

  it("prefers the longest matching word", () => {
    expect(
      annotateVocabulary("旅游景点", [
        { writing: "旅游", reading: "lv3you2" },
        { writing: "旅游景点", reading: "lv3you2jing3dian3" },
      ]),
    ).toEqual([{ kind: "word", text: "旅游景点", reading: "lǚyóujǐngdiǎn" }]);
  });

  it("skips words without a reading and grammar patterns", () => {
    expect(
      annotateVocabulary("从今天开始下雨", [
        { writing: "从...开始", reading: "cong2kai1shi3" },
        { writing: "下雨", reading: null },
      ]),
    ).toEqual([{ kind: "text", text: "从今天开始下雨" }]);
  });

  it("matches a word Skritter stores with spaces between its parts", () => {
    expect(
      annotateVocabulary("口语能力", [
        { writing: "口语 能力", reading: "kou3yu3 neng2li4" },
      ]),
    ).toEqual([{ kind: "word", text: "口语能力", reading: "kǒuyǔ nénglì" }]);
  });

  it("keeps line breaks in the surrounding text", () => {
    expect(
      annotateVocabulary("第一行。\n天气", [
        { writing: "天气", reading: "tian1qi4" },
      ]),
    ).toEqual([
      { kind: "text", text: "第一行。\n" },
      { kind: "word", text: "天气", reading: "tiānqì" },
    ]);
  });
});

describe("groupSentences", () => {
  it("splits after sentence-ending punctuation and line breaks, keeping words whole", () => {
    const segments = annotateVocabulary("今天天气好。他说：“下雨吗？”\n好！", [
      { writing: "天气", reading: "tian1qi4" },
    ]);

    expect(
      groupSentences(segments).map((sentence) =>
        sentence.map((segment) => segment.text).join(""),
      ),
    ).toEqual(["今天天气好。", "他说：“下雨吗？”\n", "好！"]);
    expect(groupSentences(segments)[0]).toContainEqual({
      kind: "word",
      text: "天气",
      reading: "tiānqì",
    });
  });

  it("keeps trailing text without end punctuation as a final sentence", () => {
    expect(
      groupSentences([{ kind: "text", text: "第一句。没有句号" }]),
    ).toEqual([
      [{ kind: "text", text: "第一句。" }],
      [{ kind: "text", text: "没有句号" }],
    ]);
  });
});
