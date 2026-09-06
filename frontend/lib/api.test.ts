import { afterEach, describe, expect, it, vi } from "vitest";

const ENV_KEY = "NEXT_PUBLIC_API_BASE_URL";
const originalValue = process.env[ENV_KEY];

describe("apiUrl", () => {
  afterEach(() => {
    if (originalValue === undefined) {
      delete process.env[ENV_KEY];
    } else {
      process.env[ENV_KEY] = originalValue;
    }
    vi.resetModules();
  });

  it("defaults to the local API when no env var is set", async () => {
    delete process.env[ENV_KEY];
    const { apiUrl } = await import("./api");
    expect(apiUrl("/vocabulary-lists")).toBe(
      "http://127.0.0.1:8000/vocabulary-lists",
    );
  });

  it("uses NEXT_PUBLIC_API_BASE_URL when set", async () => {
    process.env[ENV_KEY] = "https://api.example.com";
    const { apiUrl } = await import("./api");
    expect(apiUrl("stories")).toBe("https://api.example.com/stories");
  });
});
