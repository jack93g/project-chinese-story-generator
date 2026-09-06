import Link from "next/link";

export default function Home() {
  return (
    <div className="page-content">
      <h1>Chinese Story Generator</h1>
      <p>
        Pick a vocabulary list and generate a Chinese story built around it,
        then read your saved stories.
      </p>
      <p>
        <Link href="/generate">Generate a story</Link> ·{" "}
        <Link href="/stories">Browse saved stories</Link>
      </p>
    </div>
  );
}
