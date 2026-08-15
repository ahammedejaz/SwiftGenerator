"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiRequest } from "@/lib/api-client";
import type {
  MessageCatalogue as Catalogue,
  MessageCoverage,
  SampleSummary,
} from "@/lib/contracts";

export function MessageCatalogue() {
  const [catalogue, setCatalogue] = useState<Catalogue>();
  const [coverage, setCoverage] = useState<Record<string, MessageCoverage>>({});
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiRequest<Catalogue>("/api/specifications/messages"),
      apiRequest<SampleSummary[]>("/api/knowledge/samples"),
    ])
      .then(async ([nextCatalogue, nextSamples]) => {
        setCatalogue(nextCatalogue);
        setSamples(nextSamples);
        const pairs = await Promise.all(
          nextCatalogue.supported.map(async (item) => [
            item.messageType,
            await apiRequest<MessageCoverage>(
              `/api/specifications/messages/${item.messageType}/coverage`,
            ),
          ] as const),
        );
        setCoverage(Object.fromEntries(pairs));
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  if (error) return <p role="alert" className="rounded-xl bg-red-50 p-4 text-red-800">{error}</p>;
  if (!catalogue) return <p>Loading source-bounded catalogue…</p>;

  const sampleTypes = new Set(samples.map((sample) => sample.messageType));
  return (
    <div className="space-y-8">
      <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
        <strong>Coverage boundary:</strong> percentages use the 200 configured rows as the
        denominator. The complete current authoritative SR2026 format denominator is unavailable,
        so no message is marked production-capable.
      </section>
      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="bg-slate-900 text-white">
            <tr>
              <th className="p-4">Message</th><th className="p-4">Scope</th>
              <th className="p-4">Capability</th><th className="p-4">Configured rows</th>
              <th className="p-4">Knowledge</th><th className="p-4">Sample rows</th>
              <th className="p-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {catalogue.supported.map((item) => {
              const measured = coverage[item.messageType];
              return (
                <tr key={item.messageType} className="border-t border-slate-200 align-top">
                  <td className="p-4 font-semibold">{item.messageType}<span className="block font-normal text-slate-500">{item.name}</span></td>
                  <td className="max-w-sm p-4 text-slate-600">{item.scope}</td>
                  <td className="p-4"><span className="rounded-full bg-amber-100 px-2 py-1 font-semibold text-amber-900">{item.capability}</span></td>
                  <td className="p-4">{measured?.configuredFormatRows ?? "—"}</td>
                  <td className="p-4">{measured ? `${measured.knowledgeRecords.percentage}%` : "—"}</td>
                  <td className="p-4">{measured ? `${measured.sampleCoveredFields.covered}/${measured.sampleCoveredFields.configured}` : "—"}</td>
                  <td className="space-y-2 p-4">
                    <Link className="block font-semibold text-teal-800 underline" href={`/message-builder?messageType=${item.messageType}`}>Open builder</Link>
                    <Link className="block font-semibold text-teal-800 underline" href={`/knowledge?messageType=${item.messageType}`}>Tag Intelligence</Link>
                    <span className="block text-slate-500">{sampleTypes.has(item.messageType) ? "Annotated sample available" : "No sample"}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <section>
        <h2 className="text-xl font-semibold">Catalogue-only Category 5 messages</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {catalogue.catalogueOnly.map((item) => (
            <article key={item.messageType} className="rounded-xl border border-slate-200 bg-white p-5">
              <h3 className="font-semibold">{item.messageType} · {item.name}</h3>
              <p className="mt-2 text-slate-600">{item.message}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
