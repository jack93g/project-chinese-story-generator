/**
 * A story's paragraphs: its non-blank lines, trimmed. Must match the
 * backend's split_paragraphs (story_generator/generation/validation.py),
 * because translation_en[i] is the English for paragraph i.
 */
export function splitParagraphs(content: string): string[] {
  return content
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}
