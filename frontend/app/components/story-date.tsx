import { formatChineseDate, formatEnglishDate } from "@/lib/dates";

// A story's date written the Chinese way (二〇二六年九月二十四日), with the
// English date on hover for anyone who can't read it yet.
export function StoryDate({ isoDate }: { isoDate: string }) {
  return (
    <time dateTime={isoDate} lang="zh" title={formatEnglishDate(isoDate)}>
      {formatChineseDate(isoDate)}
    </time>
  );
}
