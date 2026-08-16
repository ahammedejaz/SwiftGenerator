"use client";

/**
 * The component vocabulary. One button shape, one input shape, one panel shape, used
 * everywhere — consistency across screens is the point, not variety.
 */

import { useEffect, useId, useRef, useState } from "react";
import { Icon, type IconName } from "@/components/studio/Icon";
import type { Presence } from "@/lib/studio-types";
import { PRESENCE_LABEL } from "@/lib/studio-types";

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ buttons */

type ButtonVariant = "primary" | "secondary" | "quiet" | "danger" | "proof";
type ButtonSize = "sm" | "md" | "lg";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors " +
  "duration-150 ease-[var(--ease-out)] disabled:cursor-not-allowed disabled:opacity-45";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-white hover:bg-accent-2 active:bg-accent-2 " +
    "disabled:hover:bg-accent shadow-[var(--shadow-1)]",
  secondary:
    "bg-panel text-ink border border-line-2 hover:bg-rail hover:border-line-2 " +
    "active:bg-sunken disabled:hover:bg-panel",
  quiet: "text-ink-2 hover:text-ink hover:bg-rail active:bg-sunken",
  danger: "bg-bad text-white hover:brightness-110 active:brightness-95",
  // For the dark proof surface. A variant rather than className overrides, because two
  // utilities of equal specificity are resolved by stylesheet order, not attribute order.
  proof:
    "border border-proof-line bg-transparent text-proof-dim hover:bg-proof-line " +
    "hover:text-proof-ink active:bg-proof-line",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[0.8125rem]",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-[0.9375rem]",
};

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  iconAfter,
  loading = false,
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  iconAfter?: IconName;
  loading?: boolean;
}) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={cx(BUTTON_BASE, BUTTON_VARIANTS[variant], BUTTON_SIZES[size], className)}
    >
      {loading ? <Spinner /> : icon ? <Icon name={icon} className="h-4 w-4" /> : null}
      {children}
      {iconAfter && !loading ? <Icon name={iconAfter} className="h-4 w-4" /> : null}
    </button>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={cx("animate-spin", className)} aria-hidden="true">
      <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="2" opacity="0.25" fill="none" />
      <path
        d="M17.5 10a7.5 7.5 0 0 0-7.5-7.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

/* ------------------------------------------------------------------- panels */

export function Panel({
  title,
  description,
  action,
  className,
  bodyClassName,
  children,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className={cx(
        // min-w-0: Panel is often a grid or flex child, and those default to
        // min-width:auto — which lets a wide code block or table expand the track
        // instead of scrolling inside its own container.
        "min-w-0 rounded-lg border border-line bg-panel shadow-[var(--shadow-1)]",
        className,
      )}
    >
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-[1.0625rem] font-semibold tracking-[-0.01em]">{title}</h2>}
            {description && (
              <p className="mt-1 max-w-[68ch] text-sm leading-6 text-ink-2">{description}</p>
            )}
          </div>
          {action && <div className="max-w-full shrink-0">{action}</div>}
        </header>
      )}
      <div className={cx("px-5 py-5", bodyClassName)}>{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------- badges */

type Tone = "neutral" | "accent" | "ok" | "bad" | "warn";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-rail text-ink-2 border-line-2",
  accent: "bg-accent-sk text-accent-2 border-accent/25",
  ok: "bg-ok-sk text-ok border-ok/25",
  bad: "bg-bad-sk text-bad border-bad/25",
  warn: "bg-warn-sk text-warn border-warn/25",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-xs font-medium tracking-[0.02em]",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Presence is stated in words, so nothing depends on colour alone. */
export function PresenceBadge({ presence }: { presence: Presence }) {
  const tone: Tone =
    presence === "MANDATORY" ? "bad" : presence === "CONDITIONAL" ? "warn" : "neutral";
  return <Badge tone={tone}>{PRESENCE_LABEL[presence]}</Badge>;
}

export function FormatBadge({ format }: { format: "MT" | "MX" }) {
  return (
    <Badge tone={format === "MT" ? "neutral" : "accent"} className="font-mono">
      {format}
    </Badge>
  );
}

/* ------------------------------------------------------------------- inputs */

const CONTROL =
  "w-full rounded-md border border-line-2 bg-panel px-3 text-sm text-ink " +
  "placeholder:text-ink-3 transition-colors duration-150 hover:border-ink-3 " +
  "focus:border-accent focus:outline-none focus-visible:outline-2 focus-visible:outline-accent " +
  "focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-3";

export function TextInput({
  invalid,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      {...props}
      aria-invalid={invalid || undefined}
      className={cx(CONTROL, "h-10", invalid && "border-bad hover:border-bad", className)}
    />
  );
}

export function Select({
  invalid,
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <div className="relative">
      <select
        {...props}
        aria-invalid={invalid || undefined}
        className={cx(
          CONTROL,
          "h-10 cursor-pointer appearance-none pr-9",
          invalid && "border-bad",
          className,
        )}
      >
        {children}
      </select>
      <Icon
        name="chevron-down"
        className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
      />
    </div>
  );
}

export function TextArea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cx(CONTROL, "min-h-28 resize-y py-2 font-mono text-[0.8125rem] leading-6", className)}
    />
  );
}

/* -------------------------------------------------------------- disclosures */

export function InfoButton({
  label,
  expanded,
  onToggle,
}: {
  label: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={cx(
        "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-sm border transition-colors duration-150",
        expanded
          ? "border-accent/30 bg-accent-sk text-accent-2"
          : "border-transparent text-ink-3 hover:border-line-2 hover:bg-rail hover:text-ink-2",
      )}
    >
      <Icon name="info" className="h-4 w-4" />
      <span className="sr-only">{expanded ? "Hide" : "Explain"} {label}</span>
    </button>
  );
}

/* ------------------------------------------------------------------- states */

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: IconName;
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-md border border-line bg-rail text-ink-3">
        <Icon name={icon} />
      </span>
      <h3 className="text-[1.0625rem] font-semibold tracking-[-0.01em]">{title}</h3>
      <p className="max-w-[52ch] text-sm leading-6 text-ink-2">{children}</p>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cx("animate-pulse rounded-sm bg-line/70", className)}
      aria-hidden="true"
    />
  );
}

export function ErrorNotice({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-md border border-bad/25 bg-bad-sk px-4 py-3"
    >
      <Icon name="alert" className="mt-0.5 h-5 w-5 shrink-0 text-bad" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-bad">{title}</p>
        <p className="mt-0.5 text-sm leading-6 text-ink-2">{message}</p>
      </div>
      {onRetry && (
        <Button size="sm" variant="secondary" icon="refresh" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/* --------------------------------------------------------- copy-to-clipboard */

export function CopyButton({
  value,
  label = "Copy",
  size = "sm",
  variant = "secondary",
  onProof = false,
}: {
  value: string;
  label?: string;
  size?: ButtonSize;
  variant?: ButtonVariant;
  onProof?: boolean;
}) {
  const effectiveVariant: ButtonVariant = onProof ? "proof" : variant;
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // Clipboard access can be denied; fall back to a selectable prompt-free no-op
      // rather than throwing at the user mid-task.
      return;
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1600);
  }

  return (
    <Button
      size={size}
      variant={effectiveVariant}
      icon={copied ? "check" : "copy"}
      onClick={copy}
      className={cx(copied && !onProof && "text-ok")}
    >
      {copied ? "Copied" : label}
    </Button>
  );
}

/* ------------------------------------------------------------------ segments */

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: Array<{ value: T; label: string; hint?: string }>;
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="scroll-slim inline-flex max-w-full overflow-x-auto rounded-md border border-line-2 bg-rail p-0.5"
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            title={option.hint}
            onClick={() => onChange(option.value)}
            className={cx(
              "shrink-0 whitespace-nowrap rounded-[6px] px-3 py-1.5 text-[0.8125rem] font-medium transition-colors duration-150",
              selected
                ? "bg-panel text-ink shadow-[var(--shadow-1)]"
                : "text-ink-2 hover:text-ink",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------------------- field */

export function Labelled({
  label,
  hint,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const generated = useId();
  const id = htmlFor ?? generated;
  return (
    <div className={cx("min-w-0", className)}>
      <label htmlFor={id} className="block text-[0.8125rem] font-medium text-ink-2">
        {label}
      </label>
      <div className="mt-1.5">{children}</div>
      {hint && <p className="mt-1 text-xs leading-5 text-ink-3">{hint}</p>}
    </div>
  );
}
