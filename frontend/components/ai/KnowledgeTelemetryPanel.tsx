"use client";

/**
 * Knowledge & authoring telemetry — the model and retrieval counters behind the assistant.
 *
 * Counts only: calls, tokens, cache hits, latency. No prompt, no document text and no
 * invented cost. The provider does not report cost, and the page says exactly that rather
 * than multiplying tokens by a price nobody agreed.
 */

import { useEffect, useState } from "react";
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
        if (cancelled) return;
        setError(
          reason instanceof StudioError
            ? reason.message
            : "Knowledge telemetry is unavailable.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-xl font-semibold">Knowledge &amp; authoring</h2>
      <p className="mt-1 text-sm text-slate-600">
        The assistant&rsquo;s model calls, retrieval and caches. Counts only; no prompt or
        document content.
      </p>
      {error ? (
        <p role="alert" className="mt-4 rounded-xl bg-red-50 p-4 text-red-900">
          {error}
        </p>
      ) : !telemetry ? (
        <p role="status" className="mt-4 text-slate-600">
          Loading knowledge telemetry…
        </p>
      ) : !telemetry.indexed ? (
        <p className="mt-4 text-slate-600">
          Knowledge Base has not been indexed yet. Run <code>make knowledge-sync</code>.
        </p>
      ) : (
        <>
          <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Fact label="LLM calls" value={telemetry.llm.calls} />
            <Fact label="Input tokens" value={telemetry.llm.promptTokens} />
            <Fact label="Output tokens" value={telemetry.llm.completionTokens} />
            <Fact label="LLM cache hits" value={telemetry.llm.cacheHits} />
            <Fact label="LLM calls avoided" value={telemetry.llm.callsAvoided} />
            <Fact label="LLM tokens avoided" value={telemetry.llm.tokensAvoided} />
            <Fact label="Average model latency" value={`${telemetry.llm.averageLatencyMs} ms`} />
            <Fact label="Operations" value={telemetry.llm.operations} />
            <Fact label="Embedding calls (last run)" value={telemetry.embeddings.lastRunRequests} />
            <Fact label="Embedding tokens (last run)" value={telemetry.embeddings.lastRunTokens} />
            <Fact label="Embedding cache hits (last run)" value={telemetry.embeddings.lastRunCacheHits} />
            <Fact label="Vectors stored" value={telemetry.embeddings.vectorsStored} />
            <Fact label="Retrieval queries" value={telemetry.retrieval.queries} />
            <Fact label="Retrieval latency" value={`${telemetry.retrieval.averageLatencyMs} ms`} />
            <Fact label="Average segments per query" value={telemetry.retrieval.averageSegments} />
            <Fact label="Sample cache hits" value={`${telemetry.samples.cacheHits} of ${telemetry.samples.cached} cached`} />
          </dl>
          <p className="mt-4 text-sm leading-6 text-slate-600">
            Embedding provider: {telemetry.embeddings.provider}. Retrieval: {telemetry.retrieval.hybrid} hybrid,{" "}
            {telemetry.retrieval.lexical} lexical, {telemetry.retrieval.semantic} semantic.
          </p>
          <p className="mt-1 text-sm leading-6 text-slate-600">{telemetry.costNote}</p>
        </>
      )}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="mt-1 font-semibold">
        {typeof value === "number" ? value.toLocaleString() : value}
      </dd>
    </div>
  );
}
