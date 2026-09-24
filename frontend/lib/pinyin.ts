const TONE_MARKS: Record<string, string> = {
  a: "āáǎà",
  e: "ēéěè",
  i: "īíǐì",
  o: "ōóǒò",
  u: "ūúǔù",
  ü: "ǖǘǚǜ",
};

// A syllable is a run of letters followed by its tone number (5 or 0 means
// neutral tone), e.g. "tian1" or the erhua "r5".
const SYLLABLE = /([a-zü]+)([0-5])/gi;

function markSyllable(letters: string, tone: number): string {
  if (tone < 1 || tone > 4) {
    return letters;
  }

  // Standard placement: a or e always takes the mark, "ou" marks the o,
  // otherwise the last vowel does.
  const lower = letters.toLowerCase();
  let index = lower.search(/[ae]/);
  if (index === -1) {
    index = lower.indexOf("ou");
  }
  if (index === -1) {
    for (let i = lower.length - 1; i >= 0; i--) {
      if (lower[i] in TONE_MARKS) {
        index = i;
        break;
      }
    }
  }
  if (index === -1) {
    return letters;
  }

  const vowel = letters[index];
  const marked = TONE_MARKS[vowel.toLowerCase()][tone - 1];
  const cased = vowel === vowel.toLowerCase() ? marked : marked.toUpperCase();
  return letters.slice(0, index) + cased + letters.slice(index + 1);
}

/**
 * Convert Skritter's numbered pinyin ("tian1qi4", "lv3xing2") to tone marks
 * ("tiānqì", "lǚxíng"). Spacing, punctuation and anything that isn't a
 * numbered syllable pass through unchanged.
 */
export function toToneMarks(reading: string): string {
  return reading
    .replace(/u:/g, "ü")
    .replace(/v/g, "ü")
    .replace(/V/g, "Ü")
    .replace(SYLLABLE, (_, letters: string, tone: string) =>
      markSyllable(letters, Number(tone)),
    );
}
