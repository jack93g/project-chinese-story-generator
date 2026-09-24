// Display names for OPENAI_PROVIDER_LABEL values; anything not listed is
// shown exactly as stored.
const PROVIDER_NAMES: Record<string, string> = {
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  groq: "Groq",
  openai: "OpenAI",
};

/**
 * A short credit line for the model that wrote a story, e.g.
 * ("groq", "openai/gpt-oss-120b") -> "gpt-oss-120b via Groq". Returns null
 * when the model isn't known.
 */
export function describeModel(
  provider: string | null | undefined,
  model: string | null | undefined,
): string | null {
  if (!model) {
    return null;
  }
  // Drop the vendor prefix some providers use ("openai/gpt-oss-120b").
  const name = model.slice(model.lastIndexOf("/") + 1);
  if (!provider) {
    return name;
  }
  return `${name} via ${PROVIDER_NAMES[provider.toLowerCase()] ?? provider}`;
}
