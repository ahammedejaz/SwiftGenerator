"use client";

/**
 * Knowledge Base — the operator's view of what has been indexed.
 *
 * A technical page, reached from Advanced rather than the primary navigation: a tester
 * generating a message never needs it. It shows what the index holds, which sources are in
 * it and in what state, which messages that yields and how ready each is, and lets an
 * operator search the index and — in local UAT mode only — run a sync.
 *
 * Everything shown comes from the API as-is. The API never returns a credential, an
 * absolute path or a full licensed document, so this page cannot either.
 */

import { useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/studio/Icon";
import {
  Badge,
  Button,
  EmptyState,
  ErrorNotice,
  Panel,
  Skeleton,
  TextInput,
  cx,
} from "@/components/studio/ui";
import { StudioError, studioApi } from "@/lib/studio-api";
import type {
  KnowledgeCitation,
  KnowledgeMessageEntry,
  KnowledgeSearchResponse,
  KnowledgeSource,
  KnowledgeStatus,
  Readiness,
} from "@/lib/studio-types";

const NOT_INDEXED_TITLE = "Knowledge Base has not been indexed yet";
const NOT_INDEXED_HINT = "Run `make knowledge-sync` to index the configured source roots.";

/** The API's message repeats the title as its first sentence; the body keeps the rest. */
function notIndexedBody(message: string | null): string {
  const rest = (message ?? "").replace(/^Knowledge Base has not been indexed yet\.?\s*/, "").trim();
  if (!rest) return NOT_INDEXED_HINT;
  return rest.includes("knowledge-sync") ? rest : `${rest} ${NOT_INDEXED_HINT}`;
}

const READINESS_TONE: Record<Readiness, "ok" | "accent" | "warn" | "neutral"> = {
  GENERATION_READY: "ok",
  STRUCTURE_VERIFIED: "accent",
  STRUCTURE_AVAILABLE: "warn",
  KNOWLEDGE_ONLY: "neutral",
};

const READINESS_LABEL: Record<Readiness, string> = {
  GENERATION_READY: "Generation ready",
  STRUCTURE_VERIFIED: "Structure verified",
  STRUCTURE_AVAILABLE: "Structure available",
  KNOWLEDGE_ONLY: "Knowledge only",
};

export function KnowledgeBase() {
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [messages, setMessages] = useState<KnowledgeMessageEntry[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // A token rather than a callback, so the effect owns the fetch and a reload after a sync
  // is a state change rather than a second code path.
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const loadedStatus = await studioApi.knowledgeStatus();
        if (cancelled) return;
        setStatus(loadedStatus);
        if (loadedStatus.indexed) {
          const [loadedSources, loadedMessages] = await Promise.all([
            studioApi.knowledgeSources(),
            studioApi.knowledgeMessages(),
          ]);
          if (cancelled) return;
          setSources(loadedSources.sources);
          setMessages(loadedMessages.messages);
        } else {
          setSources([]);
          setMessages([]);
        }
        setLoadError(null);
      } catch (error) {
        if (cancelled) return;
        setLoadError(
          error instanceof StudioError
            ? error.message
            : "The knowledge base status could not be loaded.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  if (loadError) {
    return (
      <ErrorNotice
        title="The knowledge base could not be reached"
        message={loadError}
        onRetry={() => setReloadToken((token) => token + 1)}
      />
    );
  }

  if (loading && !status) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="space-y-6">
      <StatusPanel
        status={status}
        onSynced={() => setReloadToken((token) => token + 1)}
      />

      {!status.indexed ? (
        <Panel>
          <EmptyState icon="layers" title={NOT_INDEXED_TITLE}>
            {notIndexedBody(status.message)}
          </EmptyState>
        </Panel>
      ) : (
        <>
          <SearchPanel />
          <SourcesPanel sources={sources} />
          <MessagesPanel messages={messages} />
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------- status */

function StatusPanel({
  status,
  onSynced,
}: {
  status: KnowledgeStatus;
  onSynced: () => void;
}) {
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState<Record<string, unknown> | null>(null);

  async function sync() {
    setSyncing(true);
    setSyncError(null);
    try {
      const response = await studioApi.knowledgeSync();
      setLastSync(response.run);
      onSynced();
    } catch (error) {
      setSyncError(
        error instanceof StudioError ? error.message : "The sync could not be started.",
      );
    } finally {
      setSyncing(false);
    }
  }

  const counts = status.counts;
  const run = status.lastRun;

  return (
    <Panel
      title="Status"
      description="What the index holds and how it may be used. Provider names only — never a key, an endpoint or a path."
      action={
        status.adminEnabled ? (
          <Button variant="secondary" icon="refresh" loading={syncing} onClick={() => void sync()}>
            Sync Knowledge Base
          </Button>
        ) : undefined
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={status.indexed ? "ok" : "warn"}>
          {status.indexed ? "Indexed" : "Not indexed"}
        </Badge>
        <Badge>Mode: {status.mode}</Badge>
        <Badge tone={status.enabled ? "neutral" : "warn"}>
          {status.enabled ? "Enabled" : "Disabled"}
        </Badge>
        {status.adminEnabled && <Badge tone="accent">Sync available</Badge>}
        {status.corpusVersion && (
          <span className="font-mono text-xs text-ink-3">
            corpus {status.corpusVersion.slice(0, 12)}
          </span>
        )}
      </div>

      <dl className="mt-5 grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
        <Fact label="Sources" value={counts.sources} note={counts.sourcesDeleted ? `${counts.sourcesDeleted} deleted` : undefined} />
        <Fact label="Segments" value={counts.segments} />
        <Fact label="Embeddings" value={counts.embeddings} />
        <Fact label="Messages" value={counts.messages} />
        <Fact label="Structures compiled" value={counts.structures} />
        <Fact label="AI samples cached" value={counts.samplesCached} />
        <Fact
          label="Embedding provider"
          value={status.embeddingProvider}
          note={
            status.embeddingDeploymentConfigured
              ? `deployment configured${status.embeddingDimensions ? ` · ${status.embeddingDimensions} dimensions` : ""}`
              : "no deployment configured"
          }
        />
        <Fact label="Language model" value={status.llmProvider} />
      </dl>

      {status.embeddingPolicyStatement && (
        <p className="mt-4 text-sm leading-6 text-ink-2">{status.embeddingPolicyStatement}</p>
      )}
      <p className="mt-2 text-xs leading-5 text-ink-3">
        {status.sourcesEmbeddingAllowed} source{status.sourcesEmbeddingAllowed === 1 ? "" : "s"} may
        be embedded; {status.sourcesEmbeddingBlocked} blocked by policy.
        {status.roots.length > 0 && ` Roots: ${status.roots.join(", ")}.`}
        {status.rootsMissing.length > 0 && ` Missing roots: ${status.rootsMissing.join(", ")}.`}
      </p>

      {run && (
        <div className="mt-5 border-t border-line pt-4">
          <h3 className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Last run
          </h3>
          <p className="mt-1 text-sm text-ink-2">
            <Badge tone={run.state === "COMPLETED" ? "ok" : "warn"}>{run.state}</Badge>
            {run.finishedAt && (
              <span className="ml-2 tnum">finished {new Date(run.finishedAt).toLocaleString()}</span>
            )}
          </p>
          <RunStats stats={run.stats} />
        </div>
      )}

      {lastSync && (
        <div className="mt-5 border-t border-line pt-4" role="status">
          <h3 className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Sync just run
          </h3>
          <RunStats stats={lastSync} />
        </div>
      )}

      {syncError && <div className="mt-4"><ErrorNotice title="Sync failed" message={syncError} /></div>}

      {status.loadErrors.length > 0 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-ink-2">
            {status.loadErrors.length} structure pack{status.loadErrors.length === 1 ? "" : "s"} could not be loaded
          </summary>
          <ul className="mt-2 space-y-0.5 font-mono text-xs text-ink-3">
            {status.loadErrors.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}

const RUN_STAT_LABELS: Record<string, string> = {
  documentsDiscovered: "Documents found",
  documentsParsed: "Parsed",
  documentsUnchanged: "Unchanged",
  documentsFailed: "Failed",
  documentsUnsupported: "Unsupported",
  documentsDeleted: "Deleted",
  segmentsCreated: "Segments created",
  segmentsReused: "Segments reused",
  segmentsEmbedded: "Segments embedded",
  embeddingRequests: "Embedding requests",
  embeddingCacheHits: "Embedding cache hits",
  embeddingRequestsAvoided: "Embedding requests avoided",
  embeddingBlockedSegments: "Blocked by policy",
  embeddingTokens: "Embedding tokens",
  structuresCompiled: "Structures compiled",
  structuresReused: "Structures reused",
  structuresFailed: "Structures failed",
  elapsedMs: "Elapsed (ms)",
};

function RunStats({ stats }: { stats: Record<string, unknown> }) {
  const rows = Object.entries(RUN_STAT_LABELS)
    .filter(([key]) => typeof stats[key] === "number")
    .map(([key, label]) => [label, stats[key] as number] as const);
  if (rows.length === 0) return null;
  return (
    <dl className="mt-2 grid gap-x-6 gap-y-1 text-[0.8125rem] sm:grid-cols-3 lg:grid-cols-6">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-2 border-b border-line py-1">
          <dt className="text-ink-3">{label}</dt>
          <dd className="font-medium text-ink tnum">{value.toLocaleString()}</dd>
        </div>
      ))}
    </dl>
  );
}

function Fact({
  label,
  value,
  note,
}: {
  label: string;
  value: number | string;
  note?: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-0.5 truncate text-[1.0625rem] font-semibold tnum">
        {typeof value === "number" ? value.toLocaleString() : value}
      </dd>
      {note && <dd className="text-xs text-ink-3">{note}</dd>}
    </div>
  );
}

/* ------------------------------------------------------------------- search */

function SearchPanel() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<KnowledgeSearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    const text = query.trim();
    if (!text) return;
    setSearching(true);
    setError(null);
    try {
      setResponse(await studioApi.knowledgeSearch({ query: text, limit: 10 }));
    } catch (caught) {
      setResponse(null);
      setError(caught instanceof StudioError ? caught.message : "The search failed.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <Panel
      title="Search the index"
      description="The same retrieval the assistant uses. Results are citations — source, section, page — with an excerpt only where the source's policy allows one."
    >
      <form
        className="flex flex-col gap-3 sm:flex-row sm:items-center"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <div className="relative min-w-0 flex-1">
          <Icon
            name="search"
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
          />
          <TextInput
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="settlement amount, 22F, field 97a"
            className="h-11 pl-9"
            aria-label="Search the knowledge base"
          />
        </div>
        <Button type="submit" variant="primary" loading={searching} disabled={!query.trim()}>
          Search
        </Button>
      </form>

      {error && <div className="mt-4"><ErrorNotice message={error} /></div>}

      {response && (
        <div className="mt-5">
          <p className="text-[0.8125rem] text-ink-2">
            <span className="font-medium text-ink tnum">{response.results.length}</span> citation
            {response.results.length === 1 ? "" : "s"} · {response.lexicalCandidates} lexical and{" "}
            {response.semanticCandidates} semantic candidates ·{" "}
            {response.semanticAvailable ? "hybrid retrieval" : "lexical only"} ·{" "}
            <span className="tnum">{response.latencyMs} ms</span>
          </p>
          {response.policyStatement && (
            <p className="mt-1 text-xs leading-5 text-ink-3">{response.policyStatement}</p>
          )}
          {response.results.length === 0 ? (
            <p className="mt-3 text-sm text-ink-2">
              No indexed section is relevant to that query.
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-line rounded-md border border-line">
              {response.results.map((citation) => (
                <CitationRow key={citation.segmentId} citation={citation} />
              ))}
            </ul>
          )}
        </div>
      )}
    </Panel>
  );
}

function CitationRow({ citation }: { citation: KnowledgeCitation }) {
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-sm font-medium text-ink">{citation.documentTitle}</span>
        {citation.messageType && (
          <span className="font-mono text-xs text-ink-2">
            {citation.messageVersion ?? citation.messageType}
          </span>
        )}
        {citation.release && <Badge>{citation.release}</Badge>}
        <Badge>{citation.section.toLowerCase().replace(/_/g, " ")}</Badge>
        {citation.page !== null && <span className="text-xs text-ink-3 tnum">page {citation.page}</span>}
        <span className="ml-auto font-mono text-[0.6875rem] text-ink-3">
          {citation.method.toLowerCase()} · {citation.score.toFixed(3)}
        </span>
      </div>
      {citation.heading && <p className="mt-0.5 text-[0.8125rem] text-ink-2">{citation.heading}</p>}
      {citation.snippet && (
        <p className="mt-1 text-xs leading-5 text-ink-3">{citation.snippet}</p>
      )}
      <p className="mt-1 font-mono text-[0.6875rem] text-ink-3">{citation.segmentId}</p>
    </li>
  );
}

/* ------------------------------------------------------------------ sources */

function SourcesPanel({ sources }: { sources: KnowledgeSource[] }) {
  return (
    <Panel
      title="Sources"
      description="Every discovered document, with its identity, policy and index state. Identities are derived from the content, never from a file name."
      bodyClassName="px-0 py-0"
    >
      {sources.length === 0 ? (
        <EmptyState icon="sheet" title="No sources discovered">
          The configured roots hold no document the indexer recognises.
        </EmptyState>
      ) : (
        <div className="scroll-slim overflow-x-auto">
          <table className="w-full min-w-[64rem] text-[0.8125rem]">
            <thead>
              <tr className="border-b border-line bg-rail text-left text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-3">
                <Th>Source</Th>
                <Th>Format</Th>
                <Th>Message</Th>
                <Th>Release</Th>
                <Th>Type</Th>
                <Th className="text-right">Pages</Th>
                <Th className="text-right">Segments</Th>
                <Th className="text-right">Embedded</Th>
                <Th>Policy</Th>
                <Th>State</Th>
                <Th>Failure</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {sources.map((source) => (
                <tr key={source.sourceId} className={cx(source.deleted && "opacity-60")}>
                  <Td>
                    <span className="block font-mono text-xs text-ink">{source.sourceId}</span>
                    {source.title && <span className="block text-xs text-ink-3">{source.title}</span>}
                  </Td>
                  <Td>{source.format}</Td>
                  <Td className="font-mono text-xs">{source.messageVersion ?? source.messageType ?? "—"}</Td>
                  <Td className="font-mono text-xs">{source.release ?? "—"}</Td>
                  <Td>
                    <span className="block">{source.documentType.toLowerCase().replace(/_/g, " ")}</span>
                    <span className="block text-xs text-ink-3">{source.classification.toLowerCase().replace(/_/g, " ")}</span>
                  </Td>
                  <Td className="text-right tnum">{source.pageCount ?? "—"}</Td>
                  <Td className="text-right tnum">{source.segments}</Td>
                  <Td className="text-right tnum">{source.embedded}</Td>
                  <Td>
                    <span className="block text-xs">embed {source.embeddingPolicy.toLowerCase()}</span>
                    <span className="block text-xs text-ink-3">model {source.llmPolicy.toLowerCase()}</span>
                  </Td>
                  <Td>
                    <Badge tone={source.state === "FAILED" ? "bad" : source.state === "EMBEDDED" ? "ok" : "neutral"}>
                      {source.state.toLowerCase()}
                    </Badge>
                  </Td>
                  <Td>
                    {source.failureCode ? (
                      <>
                        <span className="block font-mono text-xs text-bad">{source.failureCode}</span>
                        {source.failureDetail && <span className="block text-xs text-ink-3">{source.failureDetail}</span>}
                      </>
                    ) : (
                      "—"
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/* ----------------------------------------------------------------- messages */

function MessagesPanel({ messages }: { messages: KnowledgeMessageEntry[] }) {
  const [filter, setFilter] = useState("");
  const shown = useMemo(() => {
    const term = filter.trim().toLowerCase();
    if (!term) return messages;
    return messages.filter((item) =>
      [item.messageType, item.messageVersion ?? "", item.release ?? "", item.title ?? "", item.readiness]
        .join(" ")
        .toLowerCase()
        .includes(term),
    );
  }, [messages, filter]);

  const summary = useMemo(() => {
    const counts: Record<Readiness, number> = {
      GENERATION_READY: 0,
      STRUCTURE_VERIFIED: 0,
      STRUCTURE_AVAILABLE: 0,
      KNOWLEDGE_ONLY: 0,
    };
    for (const item of messages) counts[item.readiness] += 1;
    return counts;
  }, [messages]);

  return (
    <Panel
      title="Messages"
      description="Every message identity the index yields, and how far each can be taken. Readiness is measured by the compile, sample, validate and round-trip gates — never declared."
      action={
        <TextInput
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter by type, release or readiness"
          aria-label="Filter messages"
          className="h-9 w-64 max-w-full"
        />
      }
      bodyClassName="px-0 py-0"
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3 text-xs text-ink-2">
        {(Object.keys(summary) as Readiness[]).map((key) => (
          <Badge key={key} tone={READINESS_TONE[key]}>
            <span className="tnum">{summary[key]}</span> {READINESS_LABEL[key].toLowerCase()}
          </Badge>
        ))}
        <span className="ml-auto tnum">{shown.length} shown</span>
      </div>
      {shown.length === 0 ? (
        <EmptyState icon="search" title="No messages match">
          Try a message type such as MT103, or a release such as SR2026.
        </EmptyState>
      ) : (
        <div className="scroll-slim max-h-[40rem] overflow-auto">
          <table className="w-full min-w-[56rem] text-[0.8125rem]">
            <thead className="sticky top-0">
              <tr className="border-b border-line bg-rail text-left text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-3">
                <Th>Message</Th>
                <Th>Release</Th>
                <Th>Readiness</Th>
                <Th>Blockers</Th>
                <Th>Structure source</Th>
                <Th className="text-right">Sources</Th>
                <Th className="text-right">Segments</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {shown.map((item) => (
                <tr key={`${item.format}|${item.messageType}|${item.messageVersion ?? ""}|${item.release ?? ""}`}>
                  <Td>
                    <span className="block font-mono text-xs font-medium text-ink">
                      {item.messageVersion ?? item.messageType}
                    </span>
                    {item.title && <span className="block text-xs text-ink-3">{item.title}</span>}
                  </Td>
                  <Td className="font-mono text-xs">{item.release ?? "—"}</Td>
                  <Td>
                    <Badge tone={READINESS_TONE[item.readiness]}>{READINESS_LABEL[item.readiness]}</Badge>
                  </Td>
                  <Td>
                    {item.blockers.length === 0 ? (
                      "—"
                    ) : (
                      <span className="font-mono text-xs text-ink-2">{item.blockers.join(", ")}</span>
                    )}
                  </Td>
                  <Td className="font-mono text-xs">{item.structureSource ?? "—"}</Td>
                  <Td className="text-right tnum">{item.sources.length}</Td>
                  <Td className="text-right tnum">{item.segments}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return <th className={cx("px-4 py-2 font-semibold", className)}>{children}</th>;
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cx("px-4 py-2 align-top", className)}>{children}</td>;
}
