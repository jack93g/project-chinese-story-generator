import { describe, expect, it, vi } from "vitest";
import { gtmScriptUrl } from "./gtm";

describe("gtmScriptUrl", () => {
  it("is null without a container ID", () => {
    expect(gtmScriptUrl(undefined)).toBeNull();
    expect(gtmScriptUrl("", "auth", "env-3")).toBeNull();
  });

  it("loads the Live container when no environment is set", () => {
    expect(gtmScriptUrl("GTM-TEST")).toBe(
      "https://www.googletagmanager.com/gtm.js?id=GTM-TEST",
    );
  });

  it("loads an Environment when auth and preview are both set", () => {
    expect(gtmScriptUrl("GTM-TEST", "abc", "env-3")).toBe(
      "https://www.googletagmanager.com/gtm.js?id=GTM-TEST&gtm_auth=abc&gtm_preview=env-3&gtm_cookies_win=x",
    );
  });

  it("falls back to Live, with a warning, when only one environment value is set", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    expect(gtmScriptUrl("GTM-TEST", "abc", undefined)).toBe(
      "https://www.googletagmanager.com/gtm.js?id=GTM-TEST",
    );
    expect(gtmScriptUrl("GTM-TEST", undefined, "env-3")).toBe(
      "https://www.googletagmanager.com/gtm.js?id=GTM-TEST",
    );
    expect(warn).toHaveBeenCalledTimes(2);

    warn.mockClear();
    gtmScriptUrl("GTM-TEST");
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
