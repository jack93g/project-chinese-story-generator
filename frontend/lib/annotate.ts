import { toToneMarks } from "./pinyin";

export type TextSegment =
  | { kind: "text"; text: string }
  | { kind: "word"; text: string; reading: string };

type Annotatable = { writing: string; reading: string | null };

// Only plain runs of Chinese characters can be found verbatim in a story;
// grammar patterns like "从...开始" or "先 ... 再..." are skipped. Skritter
// sometimes puts spaces between the parts of a word ("口语 能力"), which a
// story won't, so spaces are removed before matching.
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
    const writing = item.writing.replace(/\s+/g, "");
    if (item.reading && HAN_ONLY.test(writing) && !readings.has(writing)) {
      readings.set(writing, toToneMarks(item.reading));
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

// A sentence ends at 。！？!? or a line break, plus any closing quotes and
// the line breaks after them.
const SENTENCE = /[^。！？!?\n]*(?:[。！？!?\n]+[”」』"]*\n*)?/g;
const SENTENCE_END = /[。！？!?\n][”」』"]*$/;

/**
 * Group segments into sentences (so they can be animated one at a time),
 * splitting plain text after sentence-ending punctuation. Vocabulary words
 * never contain that punctuation, so they're never split.
 */
export function groupSentences(segments: TextSegment[]): TextSegment[][] {
  const sentences: TextSegment[][] = [];
  let current: TextSegment[] = [];
  for (const segment of segments) {
    if (segment.kind === "word") {
      current.push(segment);
      continue;
    }
    for (const piece of segment.text.match(SENTENCE) ?? []) {
      if (!piece) {
        continue;
      }
      current.push({ kind: "text", text: piece });
      if (SENTENCE_END.test(piece)) {
        sentences.push(current);
        current = [];
      }
    }
  }
  if (current.length > 0) {
    sentences.push(current);
  }
  return sentences;
}
