import Link from "next/link";
import { LogoutButton } from "./logout-button";

export function SiteNav() {
  return (
    <header className="site-header">
      <Link href="/" className="site-title">
        Chinese Story Generator
      </Link>
      <nav aria-label="Main navigation">
        <Link href="/generate">Generate</Link>
        <Link href="/stories">Saved stories</Link>
        <LogoutButton />
      </nav>
    </header>
  );
}
