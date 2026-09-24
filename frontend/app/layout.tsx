import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { LoginGate } from "./components/login-gate";
import { SiteNav } from "./components/site-nav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "话本 Huaben",
  description: "Generate and read Chinese-language learning stories.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <SiteNav />
        <main className="site-main">
          <LoginGate>{children}</LoginGate>
        </main>
      </body>
    </html>
  );
}
