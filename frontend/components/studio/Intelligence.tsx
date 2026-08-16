"use client";

/**
 * Message Intelligence — one search across MT tags and MX elements.
 *
 * Deterministic lookup, no model call. The point is that a tester can paste anything they
 * have in front of them (a tag, a qualifier, an XML element, a business phrase) and get
 * the meaning, the format, an example, and the field shown inside a real message.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/studio/Icon";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  FormatBadge,
  PresenceBadge,
  SegmentedControl,
  Skeleton,
  TextInput,
  cx,
} from "@/components/studio/ui";
import { StudioError, studioApi } from "@/lib/studio-api";
import type {
  IntelligenceDetail,
  IntelligenceHit,
  MessageFormat,
} from "@/lib/studio-types";

const SUGGESTIONS = [
  "PSET",
  "settlement amount",
  "SttlmDt",
  "20C",
  "FinInstrmId",
  "DEAG",
  "trade date",
  "sese.023",
];

/**
 * The tail of an element path is what distinguishes two results, so keep the last few
 * segments. Trimming here rather than with dir="rtl" avoids the bidi reordering that moves
 * a leading colon to the end of the line.
 */
function shortAddress(address: string): string {
  if (!address.startsWith("/")) return address;
  const parts = address.split("/").filter(Boolean);
  if (parts.length <= 4) return address;
  return `…/${parts.slice(-4).join("/")}`;
}

type FormatFilter = "ALL" | MessageFormat;

export function Intelligence({ initialQuery = "" }: { initialQuery?: string }) {
  const [query, setQuery] = useState(initialQuery);
  const [debounced, setDebounced] = useState(initialQuery);
  const [filter, setFilter] = useState<FormatFilter>("ALL");
  const [hits, setHits] = useState<IntelligenceHit[]>([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IntelligenceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    const handle = setTimeout(() => setDebounced(query.trim()), 180);
    return () => clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!debounced) {
        setHits([]);
        setTotal(0);
        setSelectedId(null);
        setDetail(null);
        return;
      }
      setSearching(true);
      setError(null);
      try {
        const response = await studioApi.searchIntelligence(
          debounced,
          filter === "ALL" ? undefined : filter,
        );
        if (cancelled) return;
        setHits(response.results);
        setTotal(response.total);
        setSelectedId((current) =>
          current && response.results.some((hit) => hit.id === current)
            ? current
            : (response.results[0]?.id ?? null),
        );
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof StudioError ? caught.message : "The search failed.");
      } finally {
        if (!cancelled) setSearching(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [debounced, filter]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!selectedId) {
        setDetail(null);
        return;
      }
      setDetailLoading(true);
      try {
        const response = await studioApi.intelligenceField(selectedId);
        if (!cancelled) setDetail(response);
      } catch {
        if (!cancelled) setDetail(null);
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const grouped = useMemo(() => {
    const mt = hits.filter((hit) => hit.format === "MT");
    const mx = hits.filter((hit) => hit.format === "MX");
    return [
      { format: "MT" as const, items: mt },
      { format: "MX" as const, items: mx },
    ].filter((group) => group.items.length > 0);
  }, [hits]);

  const runSuggestion = useCallback((value: string) => {
    setQuery(value);
    setDebounced(value);
  }, []);

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-line bg-panel p-5 shadow-[var(--shadow-1)]">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative min-w-0 flex-1">
            <Icon
              name="search"
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
            />
            <TextInput
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search a tag, qualifier, element, XPath or business term"
              className="h-11 pl-9"
              autoFocus
              aria-label="Search message fields"
            />
          </div>
          <SegmentedControl
            label="Filter by standard"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "ALL", label: "Both" },
              { value: "MT", label: "MT" },
              { value: "MX", label: "MX" },
            ]}
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-ink-3">Try:</span>
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => runSuggestion(suggestion)}
              className="rounded-sm border border-line-2 bg-sunken px-2 py-0.5 font-mono text-xs text-ink-2 transition-colors duration-150 hover:border-accent/40 hover:bg-accent-sk hover:text-accent-2"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorNotice message={error} />}

      {!debounced && (
        <div className="rounded-lg border border-line bg-panel shadow-[var(--shadow-1)]">
          <EmptyState icon="search" title="Look anything up">
            Search by whatever you have: a tag such as <code className="font-mono">95R</code>,
            a qualifier such as <code className="font-mono">PSET</code>, an ISO 20022 element
            such as <code className="font-mono">SttlmDt</code>, or plain English such as
            &ldquo;settlement amount&rdquo;. Answers come from the platform&rsquo;s own
            configured knowledge base — no model call is made.
          </EmptyState>
        </div>
      )}

      {debounced && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <div className="rounded-lg border border-line bg-panel shadow-[var(--shadow-1)]">
            <header className="flex items-baseline justify-between gap-2 border-b border-line px-4 py-2.5">
              <span className="text-[0.8125rem] font-medium">
                {searching ? "Searching…" : `${total} ${total === 1 ? "match" : "matches"}`}
              </span>
              <span className="text-xs text-ink-3">Deterministic</span>
            </header>
            {searching && hits.length === 0 ? (
              <div className="space-y-2 p-4">
                {[0, 1, 2, 3].map((row) => (
                  <Skeleton key={row} className="h-14 w-full" />
                ))}
              </div>
            ) : hits.length === 0 ? (
              <EmptyState icon="search" title="Nothing matched">
                Try a shorter term, or switch the filter to Both.
              </EmptyState>
            ) : (
              <div className="scroll-slim max-h-[38rem] overflow-y-auto">
                {grouped.map((group) => (
                  <div key={group.format}>
                    <p className="sticky top-0 border-b border-line bg-rail px-4 py-1.5 text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-3">
                      {group.format === "MT" ? "MT — ISO 15022" : "MX — ISO 20022"}
                    </p>
                    <ul>
                      {group.items.map((hit) => (
                        <li key={hit.id}>
                          <button
                            type="button"
                            onClick={() => setSelectedId(hit.id)}
                            aria-current={hit.id === selectedId ? "true" : undefined}
                            className={cx(
                              "w-full border-b border-line px-4 py-3 text-left transition-colors duration-150",
                              hit.id === selectedId
                                ? "bg-accent-sk"
                                : "hover:bg-rail",
                            )}
                          >
                            <span className="flex items-baseline justify-between gap-2">
                              <span className="min-w-0 truncate text-[0.8125rem] font-medium">
                                {hit.label}
                              </span>
                              <PresenceBadge presence={hit.presence} />
                            </span>
                            <span className="mt-1 flex items-baseline gap-1.5 text-[0.6875rem]">
                              <span className="shrink-0 font-mono font-medium text-ink-2">
                                {hit.messageTypes.length > 2
                                  ? `${hit.messageTypes[0]} +${hit.messageTypes.length - 1}`
                                  : hit.messageTypes.join(" ")}
                              </span>
                              <span className="min-w-0 truncate font-mono text-ink-3">
                                {shortAddress(hit.address)}
                              </span>
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            {detailLoading && !detail ? (
              <div className="space-y-3 rounded-lg border border-line bg-panel p-6">
                <Skeleton className="h-6 w-64" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-28 w-full" />
              </div>
            ) : detail ? (
              <FieldDetail detail={detail} />
            ) : (
              <div className="rounded-lg border border-line bg-panel shadow-[var(--shadow-1)]">
                <EmptyState icon="info" title="Choose a result">
                  Select a match on the left to see what it means, how it is formatted, and
                  what it looks like inside a real message.
                </EmptyState>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function FieldDetail({ detail }: { detail: IntelligenceDetail }) {
  return (
    <article className="animate-settle overflow-hidden rounded-lg border border-line bg-panel shadow-[var(--shadow-1)]">
      <header className="border-b border-line px-6 py-5">
        <div className="flex flex-wrap items-center gap-2">
          <FormatBadge format={detail.format} />
          <PresenceBadge presence={detail.presence} />
          {detail.cardinality && <Badge>{detail.cardinality}</Badge>}
          {detail.dataType && <Badge>{detail.dataType}</Badge>}
        </div>
        <h2 className="mt-2 text-[1.375rem] font-semibold leading-tight tracking-[-0.015em]">
          {detail.label}
        </h2>
        <p className="mt-1.5 break-all font-mono text-[0.8125rem] text-accent">
          {detail.address}
        </p>
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
          <span>Used in</span>
          {detail.messageTypes.map((type) => (
            <code key={type} className="font-mono text-ink-2">
              {type}
            </code>
          ))}
        </p>
      </header>

      <div className="grid gap-x-10 gap-y-5 px-6 py-5 md:grid-cols-2">
        <Section title="What it means">{detail.businessMeaning}</Section>
        {detail.whyUsed && <Section title="Why it is used">{detail.whyUsed}</Section>}
        <Section title="Expected format">{detail.formatExplanation}</Section>
        {detail.technicalMeaning && (
          <Section title="Technical meaning">{detail.technicalMeaning}</Section>
        )}
        {detail.conditionExplanation && (
          <Section title="When it applies">{detail.conditionExplanation}</Section>
        )}
        {detail.parent && (
          <Section title="Sits inside">
            <code className="break-all font-mono text-[0.8125rem]">{detail.parent}</code>
          </Section>
        )}
        {detail.dependsOn.length > 0 && (
          <Section title="Depends on">{detail.dependsOn.join(", ")}</Section>
        )}
        {detail.commonMistakes.length > 0 && (
          <Section title="Common mistakes">
            <ul className="list-inside list-disc space-y-1">
              {detail.commonMistakes.map((mistake) => (
                <li key={mistake}>{mistake}</li>
              ))}
            </ul>
          </Section>
        )}
      </div>

      {detail.allowedCodes.length > 0 && (
        <div className="border-t border-line px-6 py-4">
          <h3 className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Allowed codes
          </h3>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {detail.allowedCodes.map((code) => (
              <code
                key={code}
                className="rounded-sm border border-line-2 bg-sunken px-1.5 py-0.5 font-mono text-xs"
              >
                {code}
              </code>
            ))}
          </div>
        </div>
      )}

      {detail.examples.length > 0 && (
        <div className="border-t border-line px-6 py-4">
          <h3 className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Examples
          </h3>
          <ul className="mt-2 space-y-1.5">
            {detail.examples.map((example) => (
              <li key={example.value} className="text-[0.8125rem] leading-6">
                <code className="rounded-sm bg-sunken px-1.5 py-0.5 font-mono text-ink">
                  {example.value}
                </code>
                <span className="ml-2 text-ink-2">{example.explanation}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {detail.sampleLines.length > 0 && (
        <div className="proof border-t border-proof-line bg-proof px-6 py-4">
          <h3 className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-proof-dim">
            In a real generated message
          </h3>
          <pre className="scroll-slim on-proof mt-2 overflow-x-auto font-mono text-[0.8125rem] leading-6 text-proof-ink">
            {detail.sampleLines.join("\n")}
          </pre>
        </div>
      )}

      <footer className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line bg-rail px-6 py-3 text-xs text-ink-3">
        <span>
          Source <span className="font-mono text-ink-2">{detail.sourceReference}</span>
        </span>
        <span>
          Release <span className="font-mono text-ink-2">{detail.standardsRelease}</span>
        </span>
      </footer>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <h3 className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-3">
        {title}
      </h3>
      <div className="mt-1 text-sm leading-6 text-ink">{children}</div>
    </div>
  );
}
