import { describe, expect, it } from "vitest";
import { formatChineseDate, formatEnglishDate, formatTimeAgo } from "./dates";

describe("formatChineseDate", () => {
  // Midday local time, so the date is the same in every time zone the
  // tests might run in.
  it.each([
    ["2026-09-24T12:00:00", "二〇二六年九月二十四日"],
    ["2026-01-01T12:00:00", "二〇二六年一月一日"],
    ["2026-10-10T12:00:00", "二〇二六年十月十日"],
    ["2030-12-31T12:00:00", "二〇三〇年十二月三十一日"],
    ["2026-11-15T12:00:00", "二〇二六年十一月十五日"],
    ["2026-02-20T12:00:00", "二〇二六年二月二十日"],
  ])("formats %s as %s", (iso, expected) => {
    expect(formatChineseDate(iso)).toBe(expected);
  });
});

describe("formatEnglishDate", () => {
  it("formats a long US-style date", () => {
    expect(formatEnglishDate("2026-09-24T12:00:00")).toBe(
      "September 24, 2026",
    );
  });
});

describe("formatTimeAgo", () => {
  const now = new Date("2026-09-24T12:00:00Z");

  it.each([
    ["2026-09-24T11:59:30Z", "this minute"],
    ["2026-09-24T11:55:00Z", "5 minutes ago"],
    ["2026-09-24T09:00:00Z", "3 hours ago"],
    ["2026-09-23T10:00:00Z", "yesterday"],
    ["2026-09-14T12:00:00Z", "10 days ago"],
    // A clock slightly ahead of the viewer's never reads as "in 1 minute".
    ["2026-09-24T12:01:00Z", "this minute"],
  ])("formats %s as %s", (iso, expected) => {
    expect(formatTimeAgo(iso, now)).toBe(expected);
  });
});
