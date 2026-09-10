import Link from "next/link";

export default function Home() {
  return (
    <div className="page-content">
      <p lang="zh" className="home-title-zh">
        中文故事生成器
      </p>
      <h1>Chinese Story Generator</h1>
      <p>
        Pick a vocabulary list and generate a Chinese story built around it,
        then read your saved stories.
      </p>
      <p className="home-actions">
        <Link href="/generate">Generate a story</Link> ·{" "}
        <Link href="/stories">Browse saved stories</Link>
      </p>
    </div>
  );
}
