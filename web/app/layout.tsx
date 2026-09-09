import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trading Bot Dashboard",
  description: "Read-only window on the gold breakout bot (DuckDB marts).",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/ledger", label: "Ledger" },
  { href: "/ai", label: "AI" },
  { href: "/risk", label: "Risk" },
  { href: "/news", label: "News" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-zinc-950 text-zinc-100 antialiased">
        <header className="border-b border-zinc-800">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="text-sm font-semibold text-zinc-100">
              Gold 5m Breakout Bot
            </Link>
            <nav className="flex gap-1 text-sm">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded px-3 py-1.5 text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-100"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="border-t border-zinc-800 py-4 text-center text-xs text-zinc-600">
          Read-only · loopback-bound (127.0.0.1) · no order/risk mutation from this surface
        </footer>
      </body>
    </html>
  );
}
