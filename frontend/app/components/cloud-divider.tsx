// A section break with an auspicious-cloud (祥云) motif between two rules.
// Purely decorative, so it's hidden from screen readers.
export function CloudDivider() {
  return (
    <div className="cloud-divider" aria-hidden="true">
      <svg
        viewBox="0 0 64 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M8 19 H56" />
        <path d="M8 19 C2.5 19 2.5 11 8 11 C11.5 11 12.5 15 9.8 16.2 C8.2 16.8 7 15.6 7.6 14.4" />
        <path d="M56 19 C61.5 19 61.5 11 56 11 C52.5 11 51.5 15 54.2 16.2 C55.8 16.8 57 15.6 56.4 14.4" />
        <path d="M12.5 12.5 C13 6.5 21 5.5 24 10.5" />
        <path d="M51.5 12.5 C51 6.5 43 5.5 40 10.5" />
        <path d="M22.5 13 C22.5 3 41.5 3 41.5 13 C41.5 18 33.5 18.5 32.5 14 C32 11.5 34.5 10.5 35.8 12" />
      </svg>
    </div>
  );
}
