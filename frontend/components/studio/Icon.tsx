/**
 * Authored icon set. 20x20 grid, 1.5px stroke, round caps and joins, `currentColor`.
 * One consistent weight everywhere — no emoji, no glyph substitutes.
 */

export type IconName =
  | "compose"
  | "sheet"
  | "search"
  | "check-shield"
  | "terminal"
  | "clock"
  | "arrow-right"
  | "arrow-left"
  | "check"
  | "alert"
  | "info"
  | "copy"
  | "download"
  | "plus"
  | "minus"
  | "chevron-down"
  | "chevron-right"
  | "external"
  | "spark"
  | "layers"
  | "close"
  | "refresh";

const PATHS: Record<IconName, React.ReactNode> = {
  compose: (
    <>
      <path d="M3.5 16.5V13L13 3.5a1.8 1.8 0 0 1 2.5 0l1 1a1.8 1.8 0 0 1 0 2.5L7 16.5H3.5Z" />
      <path d="M11.5 5.5 14.5 8.5" />
    </>
  ),
  sheet: (
    <>
      <rect x="3" y="3" width="14" height="14" rx="1.5" />
      <path d="M3 7.5h14M7.5 7.5V17M3 12.5h14" />
    </>
  ),
  search: (
    <>
      <circle cx="9" cy="9" r="5.5" />
      <path d="m13.2 13.2 3.3 3.3" />
    </>
  ),
  "check-shield": (
    <>
      <path d="M10 2.8 16 5v4.6c0 3.5-2.4 6.4-6 7.6-3.6-1.2-6-4.1-6-7.6V5l6-2.2Z" />
      <path d="m7.4 9.8 1.9 1.9 3.5-3.6" />
    </>
  ),
  terminal: (
    <>
      <rect x="2.5" y="3.5" width="15" height="13" rx="1.5" />
      <path d="m6 8 2.4 2.2L6 12.4M10.5 12.8h3.5" />
    </>
  ),
  clock: (
    <>
      <circle cx="10" cy="10" r="7.2" />
      <path d="M10 5.8V10l2.8 1.8" />
    </>
  ),
  "arrow-right": <path d="M4 10h12m-4.5-4.5L16 10l-4.5 4.5" />,
  "arrow-left": <path d="M16 10H4m4.5-4.5L4 10l4.5 4.5" />,
  check: <path d="m4.5 10.5 3.6 3.6L15.5 6" />,
  alert: (
    <>
      <path d="M10 3.4 17.4 16H2.6L10 3.4Z" />
      <path d="M10 8v3.4M10 13.6h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="10" cy="10" r="7.2" />
      <path d="M10 9v4.4M10 6.6h.01" />
    </>
  ),
  copy: (
    <>
      <rect x="7" y="7" width="9.5" height="9.5" rx="1.5" />
      <path d="M13 4.5H5a1.5 1.5 0 0 0-1.5 1.5v8" />
    </>
  ),
  download: <path d="M10 3v9m0 0 3.5-3.5M10 12 6.5 8.5M3.5 14.5v1a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5v-1" />,
  plus: <path d="M10 4.5v11M4.5 10h11" />,
  minus: <path d="M4.5 10h11" />,
  "chevron-down": <path d="m5.5 8 4.5 4.5L14.5 8" />,
  "chevron-right": <path d="m8 5.5 4.5 4.5L8 14.5" />,
  external: (
    <>
      <path d="M11 4.5h4.5V9" />
      <path d="M15.5 4.5 9 11" />
      <path d="M15 12v3.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h3.5" />
    </>
  ),
  spark: <path d="M10 2.8v4.4M10 12.8v4.4M2.8 10h4.4M12.8 10h4.4M5.2 5.2l2.6 2.6M12.2 12.2l2.6 2.6M14.8 5.2l-2.6 2.6M7.8 12.2l-2.6 2.6" />,
  layers: (
    <>
      <path d="m10 2.8 7 3.6-7 3.6-7-3.6 7-3.6Z" />
      <path d="m3 10.4 7 3.6 7-3.6" />
    </>
  ),
  close: <path d="m5.5 5.5 9 9m0-9-9 9" />,
  refresh: (
    <>
      <path d="M16.3 8.6A6.5 6.5 0 0 0 4.6 6.3" />
      <path d="M3.7 11.4a6.5 6.5 0 0 0 11.7 2.3" />
      <path d="M4.2 3.4v3h3M15.8 16.6v-3h-3" />
    </>
  ),
};

export function Icon({
  name,
  className = "h-5 w-5",
  strokeWidth = 1.5,
}: {
  name: IconName;
  className?: string;
  strokeWidth?: number;
}) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
