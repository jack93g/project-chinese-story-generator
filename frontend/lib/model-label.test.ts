import { describe, expect, it } from "vitest";
import { describeModel } from "./model-label";

describe("describeModel", () => {
  it("drops the vendor prefix and names the provider", () => {
    expect(describeModel("groq", "openai/gpt-oss-120b")).toBe(
      "gpt-oss-120b via Groq",
    );
  });

  it("shows an unknown provider label as stored", () => {
    expect(describeModel("my-host", "some-model")).toBe(
      "some-model via my-host",
    );
  });

  it("shows just the model when the provider is missing", () => {
    expect(describeModel(null, "gpt-5")).toBe("gpt-5");
  });

  it("returns null when the model is missing or not sent", () => {
    expect(describeModel("groq", null)).toBeNull();
    expect(describeModel(undefined, undefined)).toBeNull();
  });
});
