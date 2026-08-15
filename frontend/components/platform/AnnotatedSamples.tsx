"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiRequest } from "@/lib/api-client";
import type { SampleDetail, SampleSummary } from "@/lib/contracts";

export function AnnotatedSamples() {
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [selected, setSelected] = useState<SampleDetail>();
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest<SampleSummary[]>("/api/knowledge/samples")
      .then((items) => {
        setSamples(items);
        if (items[0]) return apiRequest<SampleDetail>(`/api/knowledge/samples/${items[0].sampleId}`);
      })
      .then((detail) => detail && setSelected(detail))
      .catch((reason: Error) => setError(reason.message));
  }, []);

  const choose = async (sampleId: string) => {
    setSelected(await apiRequest<SampleDetail>(`/api/knowledge/samples/${sampleId}`));
  };

  return <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
    <aside className="rounded-2xl border bg-white p-4"><h2 className="font-semibold">Synthetic samples</h2><div className="mt-3 space-y-2">{samples.map((sample) => <button key={sample.sampleId} onClick={() => choose(sample.sampleId)} className={`block w-full rounded-lg px-3 py-2 text-left text-sm ${selected?.sampleId === sample.sampleId ? "bg-teal-800 text-white" : "bg-slate-100"}`}>{sample.messageType}<span className="block text-xs opacity-75">{sample.capability}</span></button>)}</div></aside>
    <section>{error && <p role="alert" className="rounded-xl bg-red-50 p-4 text-red-800">{error}</p>}{!selected ? <p>Loading samples…</p> : <div className="space-y-5"><div className="rounded-2xl border bg-white p-5"><h2 className="text-xl font-semibold">{selected.messageType} annotated sample</h2><p className="mt-2 text-slate-600">{selected.scenario}</p><p className="mt-2 text-sm">{selected.standardsRelease} · {selected.profileId} v{selected.profileVersion} · {selected.capability}</p><Link href={`/message-builder?messageType=${selected.messageType}`} className="mt-4 inline-block rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white">Open builder and load sample</Link>{selected.knownLimitations.map((item) => <p key={item} className="mt-2 text-sm text-amber-800">{item}</p>)}</div><div className="overflow-hidden rounded-2xl bg-slate-950 text-slate-100"><div className="grid grid-cols-[minmax(260px,1fr)_minmax(300px,1fr)] border-b border-slate-700 p-3 text-xs font-semibold uppercase tracking-wider"><span>Raw line</span><span>Annotation</span></div>{selected.annotations.map((line) => <div key={`${line.lineNumber}-${line.rowId}`} className="grid grid-cols-[minmax(260px,1fr)_minmax(300px,1fr)] gap-4 border-b border-slate-800 p-3 text-sm"><code className="break-all text-teal-200">{line.rawLine}</code><div><p className="font-semibold">Sequence {line.sequencePath} · {line.tag}{line.qualifier ? `/${line.qualifier}` : ""} · {line.presence}</p><p className="mt-1 text-slate-300">{line.businessMeaning}</p><p className="mt-1 text-xs text-slate-400">Why: {line.whyUsed}</p><Link href={`/knowledge?tag=${line.tag}&messageType=${selected.messageType}`} className="mt-2 inline-block text-xs font-semibold text-teal-300 underline">Open Tag Intelligence</Link></div></div>)}</div></div>}</section>
  </div>;
}
