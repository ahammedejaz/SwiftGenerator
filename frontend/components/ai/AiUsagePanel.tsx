"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api-client";
import type { AiUsageInteraction, ScenarioInterpretation } from "@/lib/contracts";

export function AiUsagePanel({ ai }: { ai: ScenarioInterpretation["ai"] }) {
  const [lastProvider, setLastProvider] = useState<AiUsageInteraction | null>();

  useEffect(() => {
    apiRequest<AiUsageInteraction | null>("/api/ai/usage/last-provider-call")
      .then(setLastProvider)
      .catch(() => setLastProvider(null));
  }, [ai.requestId]);

  return (
    <details className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <summary className="cursor-pointer px-5 py-4 font-semibold">
        AI usage · {sourceLabel(ai.processingSource)} · {ai.totalTokens} new tokens
      </summary>
      <div className="grid gap-5 border-t border-slate-200 p-5 lg:grid-cols-2">
        <section>
          <h3 className="font-semibold">Last interaction</h3>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <Metric label="Result source" value={sourceLabel(ai.processingSource)} />
            <Metric label="Provider" value={ai.provider} />
            <Metric label="Model" value={ai.model ?? "No model call"} />
            <Metric label="Escalated" value={ai.escalated ? "Yes" : "No"} />
            <Metric label="New API calls" value={String(ai.apiCalls)} />
            <Metric label="Prompt tokens used now" value={String(ai.promptTokens)} />
            <Metric label="Completion tokens used now" value={String(ai.completionTokens)} />
            <Metric label="Total tokens used now" value={String(ai.totalTokens)} />
            <Metric label="Provider cost used now" value={ai.reportedCost ?? "0"} />
            <Metric label="Latency" value={`${ai.latencyMs} ms`} />
            <Metric label="Cache" value={ai.cacheHit ? "HIT" : "MISS / not used"} />
            <Metric label="Cache namespace" value={ai.cacheNamespace ?? "None"} />
            <Metric label="Tokens avoided" value={String(ai.tokensAvoided)} />
            <Metric label="API calls avoided" value={String(ai.callsAvoided)} />
            <Metric label="Estimated cost avoided" value={ai.costAvoided ?? "0"} />
            <Metric label="Prompt / schema" value={`${ai.promptVersion} / ${ai.schemaVersion}`} />
          </dl>
          {ai.cacheHit && (
            <p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-950">
              Result source: Cache. New API calls: 0. New tokens used: 0. Original cached response size: {ai.originalCachedTotalTokens.toLocaleString()} tokens. Estimated tokens avoided: {ai.tokensAvoided.toLocaleString()}.
            </p>
          )}
        </section>

        <section>
          <h3 className="font-semibold">Last real provider call</h3>
          {lastProvider ? (
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <Metric label="Timestamp" value={new Date(lastProvider.createdAt).toLocaleString()} />
              <Metric label="Provider" value={lastProvider.provider ?? "Unknown"} />
              <Metric label="Model" value={lastProvider.model ?? "Unknown"} />
              <Metric label="Prompt tokens" value={String(lastProvider.promptTokens)} />
              <Metric label="Completion tokens" value={String(lastProvider.completionTokens)} />
              <Metric label="Total tokens" value={String(lastProvider.totalTokens)} />
              <Metric label="Cost" value={lastProvider.providerReportedCost ?? "Not reported"} />
              <Metric label="Latency" value={`${lastProvider.latencyMs} ms`} />
              <Metric label="Outcome" value={lastProvider.outcomeCode} />
            </dl>
          ) : (
            <p className="mt-3 text-sm leading-6 text-slate-600">No real provider call is recorded in this environment.</p>
          )}
        </section>
      </div>
    </details>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="mt-1 break-words font-semibold text-slate-900">{value}</dd>
    </div>
  );
}

function sourceLabel(source: ScenarioInterpretation["ai"]["processingSource"]): string {
  return {
    LIVE_API: "Live API",
    CACHE: "Cache",
    DETERMINISTIC: "Deterministic",
    AI_UNAVAILABLE: "AI unavailable",
  }[source];
}
