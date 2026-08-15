"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api-client";
import type { AiCacheStats, AiUsageInteraction, AiUsageSummary } from "@/lib/contracts";

export function AiEfficiencyDashboard() {
  const [summary, setSummary] = useState<AiUsageSummary>();
  const [cache, setCache] = useState<AiCacheStats>();
  const [last, setLast] = useState<AiUsageInteraction | null>();
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiRequest<AiUsageSummary>("/api/ai/usage/summary?days=30"),
      apiRequest<AiCacheStats>("/api/ai/cache/stats"),
      apiRequest<AiUsageInteraction | null>("/api/ai/usage/last-interaction"),
    ])
      .then(([usage, stats, interaction]) => {
        setSummary(usage);
        setCache(stats);
        setLast(interaction);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "AI efficiency data is unavailable."));
  }, []);

  if (error) return <p role="alert" className="rounded-xl bg-red-50 p-4 text-red-900">{error}</p>;
  if (!summary || !cache) return <p role="status">Loading content-free efficiency metrics…</p>;

  const metrics = [
    ["Guided interactions", summary.interactions.toLocaleString()],
    ["Deterministic-only", summary.deterministicInteractions.toLocaleString()],
    ["Live API calls", summary.liveApiCalls.toLocaleString()],
    ["Cache-hit interactions", summary.cacheHits.toLocaleString()],
    ["Cache-hit rate", `${(summary.cacheHitRate * 100).toFixed(1)}%`],
    ["API calls avoided", summary.apiCallsAvoided.toLocaleString()],
    ["Tokens consumed", summary.tokensConsumed.toLocaleString()],
    ["Tokens avoided", summary.tokensAvoided.toLocaleString()],
    ["Provider-reported cost", summary.providerReportedCost],
    ["Estimated cost avoided", summary.estimatedCostAvoided],
    ["Average latency", `${summary.averageLatencyMs} ms`],
    ["Active cache entries", cache.activeEntries.toLocaleString()],
  ];

  return (
    <div className="space-y-7">
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-600">{label}</p>
            <p className="mt-2 text-2xl font-semibold">{value}</p>
          </div>
        ))}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold">Cache safety and current state</h2>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <DashboardFact label="Enabled" value={cache.enabled ? "Yes" : "No"} />
          <DashboardFact label="Key version" value={cache.keyVersion} />
          <DashboardFact label="Persistent entries" value={String(cache.entries)} />
          <DashboardFact label="Recorded hits" value={String(cache.totalHits)} />
        </dl>
        <p className="mt-4 text-sm leading-6 text-slate-600">
          Savings use original provider usage from validated cache entries. They are estimates for avoided work, not current-request consumption. No prompts, cache keys, or placeholder mappings are shown.
        </p>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold">Last interaction</h2>
        {last ? (
          <p className="mt-3 leading-7 text-slate-700">
            {last.source} · {last.operationType} · {last.totalTokens} new tokens · {last.tokensAvoided} tokens avoided · {last.latencyMs} ms · {last.outcomeCode}
          </p>
        ) : (
          <p className="mt-3 text-slate-600">No interactions recorded.</p>
        )}
      </section>
    </div>
  );
}

function DashboardFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="mt-1 font-semibold">{value}</dd>
    </div>
  );
}
