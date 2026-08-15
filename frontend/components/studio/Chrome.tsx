"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "@/components/studio/Icon";
import { cx } from "@/components/studio/ui";

/**
 * Six primary destinations. Advanced workflows live one level down rather than competing
 * for the front door — the old thirteen-card home page is why nobody knew where to start.
 */
const NAV: Array<{ href: string; label: string; icon: IconName }> = [
  { href: "/", label: "Create Message", icon: "compose" },
  { href: "/excel", label: "Bulk / Excel", icon: "sheet" },
  { href: "/intelligence", label: "Message Intelligence", icon: "search" },
  { href: "/validate", label: "Validate", icon: "check-shield" },
  { href: "/automation", label: "API & Automation", icon: "terminal" },
  { href: "/recent", label: "Recent Messages", icon: "clock" },
];

export function Chrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-30 border-b border-line bg-rail/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-2 px-4 py-2.5 sm:px-6 lg:flex-row lg:items-center lg:gap-6">
          <Link
            href="/"
            className="group flex shrink-0 items-center gap-2.5 rounded-sm py-1"
          >
            <Mark />
            <span className="text-sm font-semibold tracking-[-0.01em]">
              Financial Message Studio
            </span>
          </Link>

          <nav
            aria-label="Primary"
            className="scroll-slim -mx-1 flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto px-1 pb-0.5 lg:pb-0"
          >
            {NAV.map((item) => {
              const active =
                item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cx(
                    "flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[0.8125rem] font-medium transition-colors duration-150",
                    active
                      ? "bg-panel text-ink shadow-[var(--shadow-1)]"
                      : "text-ink-2 hover:bg-panel/70 hover:text-ink",
                  )}
                >
                  <Icon
                    name={item.icon}
                    className={cx("h-4 w-4", active ? "text-accent" : "text-ink-3")}
                  />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <Link
            href="/advanced"
            className={cx(
              "hidden shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[0.8125rem] font-medium transition-colors duration-150 lg:flex",
              pathname.startsWith("/advanced")
                ? "bg-panel text-ink shadow-[var(--shadow-1)]"
                : "text-ink-3 hover:bg-panel/70 hover:text-ink-2",
            )}
          >
            <Icon name="layers" className="h-4 w-4" />
            Advanced
          </Link>
        </div>
      </header>

      <main id="main" className="flex-1">
        {children}
      </main>

      <footer className="mt-16 border-t border-line bg-rail">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-3 px-4 py-6 text-xs leading-6 text-ink-3 sm:px-6 md:flex-row md:items-start md:justify-between">
          <p className="max-w-[76ch]">
            Messages are generated against a configured client profile and a configured
            message subset. They are not transmitted through, validated by, or certified by
            the Swift network. Values allocated by a messaging interface or by the network
            are never fabricated.
          </p>
          <Link
            href="/advanced"
            className="shrink-0 rounded-sm font-medium text-ink-2 underline decoration-line-2 underline-offset-4 hover:text-ink lg:hidden"
          >
            Advanced workflows
          </Link>
        </div>
      </footer>
    </div>
  );
}

/**
 * The mark: two stacked rules crossed by a send stroke — a message leaving a ledger.
 * Drawn rather than lettered so it holds at 20px.
 */
function Mark() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden="true">
      <rect x="1" y="1" width="22" height="22" rx="5" className="fill-accent" />
      <path
        d="M6 9h8M6 13h5"
        stroke="white"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity="0.62"
      />
      <path
        d="M8 17.5 18 6.5"
        stroke="white"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle cx="18" cy="6.5" r="1.9" fill="white" />
    </svg>
  );
}

/** Standard page frame: title, one line of orientation, then the work. */
export function Page({
  title,
  lede,
  actions,
  wide = false,
  children,
}: {
  title: string;
  lede: string;
  actions?: React.ReactNode;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cx(
        "mx-auto px-4 pb-16 pt-8 sm:px-6",
        wide ? "max-w-[1400px]" : "max-w-[1200px]",
      )}
    >
      <div className="flex flex-wrap items-end justify-between gap-4 pb-7">
        <div className="min-w-0">
          <h1 className="text-[2rem] font-semibold leading-[1.15] tracking-[-0.02em]">
            {title}
          </h1>
          <p className="mt-2 max-w-[72ch] text-[0.9375rem] leading-7 text-ink-2">{lede}</p>
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}
