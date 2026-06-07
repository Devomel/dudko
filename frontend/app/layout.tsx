import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dudko Scrapper — Моніторинг цін",
  description: "Система моніторингу цін автозапчастин",
};

const navLinks = [
  { href: "/", label: "Дашборд" },
  { href: "/products", label: "Каталог" },
  { href: "/scraping", label: "Скрапінг" },
{ href: "/analytics", label: "Аналітика" },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="uk" className="h-full">
      <body className="min-h-full flex flex-col bg-slate-50 text-slate-900">
        <header className="bg-white border-b border-slate-200 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-14">
            <Link href="/" className="font-bold text-lg text-blue-700 tracking-tight">
              AutoParts Monitor
            </Link>
            <nav className="flex gap-1">
              {navLinks.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  className="px-3 py-1.5 rounded-md text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
                >
                  {l.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children}
        </main>
        <footer className="border-t border-slate-200 bg-white text-center text-xs text-slate-400 py-3">
          Dudko Scrapper &mdash; система моніторингу цін автозапчастин
        </footer>
      </body>
    </html>
  );
}
