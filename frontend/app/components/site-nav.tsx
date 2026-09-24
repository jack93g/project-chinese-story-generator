import Link from "next/link";
import { LogoutButton } from "./logout-button";
import { Seal } from "./seal";

export function SiteNav() {
  return (
    <header className="site-header">
      <Link href="/" className="site-title">
        <Seal />{" "}
        <span>Huaben</span>
      </Link>
      <nav aria-label="Main navigation">
        <Link href="/generate">Generate</Link>
        <Link href="/stories">Saved stories</Link>
        <LogoutButton />
      </nav>
    </header>
  );
}
