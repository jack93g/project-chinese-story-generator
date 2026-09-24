import { toToneMarks } from "./pinyin";

export type TextSegment =
  | { kind: "text"; text: string }
  | { kind: "word"; text: string; reading: string };

type Annotatable = { writing: string; reading: string | null };

// Only plain runs of Chinese characters can be found verbatim in a story;
// grammar patterns like "从...开始" or "先 ... 再..." are skipped.
const HAN_ONLY = /^\p{Script=Han}+$/u;

/**
 * Split story text into plain runs and vocabulary words, so each word can be
 * shown with its pinyin. Where words overlap, the longest match wins (so
 * "旅游景点" beats "旅游").
 */
export function annotateVocabulary(
  content: string,
  vocabulary: Annotatable[],
): TextSegment[] {
  const readings = new Map<string, string>();
  for (const item of vocabulary) {
    if (item.reading && HAN_ONLY.test(item.writing) && !readings.has(item.writing)) {
      readings.set(item.writing, toToneMarks(item.reading));
    }
  }
  const words = [...readings.keys()].sort((a, b) => b.length - a.length);

  const segments: TextSegment[] = [];
  let plain = "";
  let i = 0;
  while (i < content.length) {
    const word = words.find((w) => content.startsWith(w, i));
    if (word) {
      if (plain) {
        segments.push({ kind: "text", text: plain });
        plain = "";
      }
      segments.push({ kind: "word", text: word, reading: readings.get(word)! });
      i += word.length;
    } else {
      plain += content[i];
      i += 1;
    }
  }
  if (plain) {
    segments.push({ kind: "text", text: plain });
  }
  return segments;
}
