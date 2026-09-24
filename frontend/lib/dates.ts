const DIGITS = "〇一二三四五六七八九";

// 1–31 as spoken Chinese numerals: 九, 十, 十四, 二十, 二十四, 三十一.
function chineseNumber(n: number): string {
  if (n < 10) {
    return DIGITS[n];
  }
  const tens = Math.floor(n / 10);
  const ones = n % 10;
  return (tens > 1 ? DIGITS[tens] : "") + "十" + (ones ? DIGITS[ones] : "");
}

/**
 * The date in the traditional written form, in the viewer's time zone:
 * 2026-09-24 -> 二〇二六年九月二十四日. The year is read digit by digit.
 */
export function formatChineseDate(isoDate: string): string {
  const date = new Date(isoDate);
  const year = [...String(date.getFullYear())]
    .map((digit) => DIGITS[Number(digit)])
    .join("");
  return `${year}年${chineseNumber(date.getMonth() + 1)}月${chineseNumber(date.getDate())}日`;
}

export function formatEnglishDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}
