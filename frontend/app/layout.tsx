import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Intelligent SWIFT Message Engineering Platform",
  description: "Source-bounded deterministic ISO 15022 message authoring and testing",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <Link href="/" className="font-semibold tracking-tight text-slate-900">
              Intelligent SWIFT Message Engineering Platform
            </Link>
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
              Source-bounded · No certification claim
            </span>
          </div>
        </header>
        {children}
        <footer className="mx-auto max-w-7xl px-6 py-8 text-sm leading-6 text-slate-600">
          Messages are authored against configured, versioned rule subsets. The platform does
          not claim SWIFT certification or universal market acceptance. Production submission
          remains disabled unless an authorised connector, approval policy, and validation gate
          are explicitly configured.
        </footer>
      </body>
    </html>
  );
}
