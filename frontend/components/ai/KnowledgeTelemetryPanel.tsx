"use client";

/** Content-free operational telemetry for AI authoring and the local knowledge runtime. */

import { useEffect, useState } from "react";
import { Badge, Panel } from "@/components/studio/ui";
import { StudioError, studioApi } from "@/lib/studio-api";
import type { KnowledgeTelemetry } from "@/lib/studio-types";

export function KnowledgeTelemetryPanel() {
  const [telemetry, setTelemetry] = useState<KnowledgeTelemetry | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    studioApi
      .knowledgeTelemetry()
      .then((data) => {
        if (!cancelled) setTelemetry(data);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(
            reason instanceof StudioError
              ? reason.message
              : "Knowledge telemetry is unavailable.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <p role="alert" className="rounded-md border border-bad/25 bg-bad-sk px-4 py-3 text-bad">
        {error}
      </p>
    );
  }
  if (!telemetry) {
    return <p role="status" className="text-sm text-ink-2">Loading usage telemetry...</p>;
  }

  const totalTokens = telemetry.llm.promptTokens + telemetry.llm.completionTokens;
  const cacheRate = telemetry.llm.operations
    ? `${Math.round((telemetry.llm.cacheHits / telemetry.llm.operations) * 100)}%`
    : "0%";

  return (
    <div className="space-y-6">
      {!telemetry.indexed && (
        <div className="rounded-md border border-warn/25 bg-warn-sk px-4 py-3 text-sm text-ink-2">
          Knowledge Base is not indexed. Configured messages remain available; run <code>make knowledge-sync</code> to enable source-backed retrieval.
        </div>
      )}

      <Panel
        title="Overview"
        description={`Content-free counters retained for ${telemetry.overview.retentionDays} days. No prompts, message values or source text are stored.`}
        bodyClassName="px-0 py-0"
      >
        <FactGrid
          facts={[
            ["Operations today", telemetry.overview.operationsToday],
            ["AI calls today", telemetry.overview.aiCallsToday],
            ["Tokens today", telemetry.overview.tokensToday],
            ["Cache hits today", telemetry.overview.cacheHitsToday],
            ["Average response", `${telemetry.llm.averageLatencyMs} ms`],
            ["Cache hit rate", cacheRate],
          ]}
        />
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="RAG" description="Retrieval activity across indexed evidence." bodyClassName="px-0 py-0">
          <FactGrid
            columns={2}
            facts={[
              ["Queries", telemetry.retrieval.queries],
              ["Average sections", telemetry.retrieval.averageSegments],
              ["Average retrieval", `${telemetry.retrieval.averageLatencyMs} ms`],
              ["Hybrid", telemetry.retrieval.hybrid],
              ["Lexical", telemetry.retrieval.lexical],
              ["Semantic", telemetry.retrieval.semantic],
            ]}
          />
        </Panel>
        <Panel title="Embeddings" description={`Provider: ${telemetry.embeddings.provider}`} bodyClassName="px-0 py-0">
          <FactGrid
            columns={2}
            facts={[
              ["Indexed segments", telemetry.embeddings.segmentsEmbedded],
              ["Vectors stored", telemetry.embeddings.vectorsStored],
              ["Calls, last sync", telemetry.embeddings.lastRunRequests],
              ["Cache hits, last sync", telemetry.embeddings.lastRunCacheHits],
              ["Calls avoided", telemetry.embeddings.lastRunRequestsAvoided],
              ["Tokens, last sync", telemetry.embeddings.lastRunTokens],
            ]}
          />
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Knowledge"
          description="Indexed source health and the most recent synchronization."
          action={<Badge tone={telemetry.knowledge.loadErrors.length ? "bad" : telemetry.indexed ? "ok" : "warn"}>{telemetry.knowledge.syncState}</Badge>}
          bodyClassName="px-0 py-0"
        >
          <FactGrid
            columns={2}
            facts={[
              ["Sources", telemetry.knowledge.sources],
              ["Messages", telemetry.knowledge.messages],
              ["Segments", telemetry.knowledge.segments],
              ["Last sync", formatTimestamp(telemetry.knowledge.lastSync?.finishedAt ?? null)],
            ]}
          />
          {telemetry.knowledge.loadErrors.length > 0 && (
            <ul className="border-t border-line px-5 py-3 text-sm text-bad">
              {telemetry.knowledge.loadErrors.map((item) => <li key={item}>{item}</li>)}
            </ul>
          )}
        </Panel>
        <Panel title="Cache" description="Validated reuse and work avoided." bodyClassName="px-0 py-0">
          <FactGrid
            columns={2}
            facts={[
              ["AI cache hits", telemetry.llm.cacheHits],
              ["Sample cache hits", telemetry.samples.cacheHits],
              ["Cached samples", telemetry.samples.cached],
              ["Model calls avoided", telemetry.llm.callsAvoided],
              ["Tokens avoided", telemetry.llm.tokensAvoided],
              ["Total model tokens", totalTokens],
            ]}
          />
          <p className="border-t border-line px-5 py-3 text-xs leading-5 text-ink-3">{telemetry.costNote}</p>
        </Panel>
      </div>

      <Panel
        title="Recent operations"
        description="Bounded request metadata only. Source text, prompts and message values are never recorded here."
        bodyClassName="px-0 py-0"
      >
        {telemetry.recentOperations.length === 0 ? (
          <p className="px-5 py-8 text-sm text-ink-2">No AI-assisted operations recorded.</p>
        ) : (
          <div className="scroll-slim overflow-x-auto">
            <table className="w-full min-w-[960px] border-collapse text-left text-[0.8125rem]">
              <thead className="bg-rail text-xs font-semibold uppercase text-ink-3">
                <tr>
                  {["Time", "Operation", "Message", "Model", "Calls", "Tokens", "RAG", "Evidence", "Latency", "Outcome"].map((label) => (
                    <th key={label} className="border-b border-line px-4 py-2.5">{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {telemetry.recentOperations.map((item) => (
                  <tr key={item.requestId} title={`Request ${item.requestId}`} className="hover:bg-rail/50">
                    <td className="whitespace-nowrap px-4 py-3 text-ink-2">{formatTimestamp(item.timestamp)}</td>
                    <td className="px-4 py-3 font-medium">{item.operation}</td>
                    <td className="whitespace-nowrap px-4 py-3 font-mono">{[item.formatFilter, item.messageType, item.release].filter(Boolean).join(" · ") || "-"}</td>
                    <td className="max-w-48 truncate px-4 py-3" title={`${item.provider} / ${item.model}`}>{item.model || item.provider}</td>
                    <td className="tnum px-4 py-3">{item.llmCalls}</td>
                    <td className="tnum px-4 py-3">{item.tokens.toLocaleString()}</td>
                    <td className="px-4 py-3">{item.ragUsed ? item.ragMode : "No"}</td>
                    <td className="tnum px-4 py-3" title={`${item.lexicalCandidates} lexical, ${item.semanticCandidates} semantic candidates`}>{item.evidenceCount}</td>
                    <td className="tnum whitespace-nowrap px-4 py-3">{item.latencyMs} ms</td>
                    <td className="px-4 py-3"><Badge tone={item.outcome === "OK" || item.outcome === "CACHE_HIT" ? "ok" : "neutral"}>{item.outcome}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function FactGrid({ facts, columns = 3 }: { facts: Array<[string, number | string | null]>; columns?: 2 | 3 }) {
  return (
    <dl className={`grid sm:grid-cols-2 ${columns === 3 ? "lg:grid-cols-3" : ""}`}>
      {facts.map(([label, value]) => (
        <div key={label} className="min-w-0 border-b border-line px-5 py-4 last:border-b-0 sm:border-r sm:[&:nth-last-child(-n+2)]:border-b-0 sm:[&:nth-child(2n)]:border-r-0 lg:[&:nth-child(2n)]:border-r">
          <dt className="text-xs font-medium uppercase text-ink-3">{label}</dt>
          <dd className="tnum mt-1 truncate text-lg font-semibold" title={String(value ?? "-")}>{typeof value === "number" ? value.toLocaleString() : value ?? "-"}</dd>
        </div>
      ))}
    </dl>
  );
}

function formatTimestamp(value: string | null) {
  if (!value) return "Not run";
  const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
