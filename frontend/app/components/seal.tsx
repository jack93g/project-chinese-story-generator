// A red name seal (印章) reading 话本, the site's brand mark. Pass
// `decorative` where it's ornament rather than content (e.g. the stamp at the
// end of a story) so screen readers skip it.
export function Seal({
  className,
  decorative = false,
}: {
  className?: string;
  decorative?: boolean;
}) {
  return (
    <span
      lang="zh"
      className={className ? `seal ${className}` : "seal"}
      {...(decorative
        ? { "aria-hidden": true }
        : { role: "img", "aria-label": "话本" })}
    >
      话本
    </span>
  );
}
