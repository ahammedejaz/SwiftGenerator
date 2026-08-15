"use client";

import { useEffect, useState } from "react";
import { ApiError, apiRequest, apiUrl } from "@/lib/api-client";
import type { ReportMetadataResponse } from "@/lib/contracts";

export function ReportViewer({ reportId }: { reportId: string }) {
  const [report, setReport] = useState<ReportMetadataResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiRequest<ReportMetadataResponse>(`/api/reports/${reportId}/metadata`)
      .then((value) => {
        if (active) setReport(value);
      })
      .catch((caught: unknown) => {
        if (active) {
          setError(caught instanceof ApiError ? caught.message : "Report retrieval failed.");
        }
      });
    return () => {
      active = false;
    };
  }, [reportId]);

  if (error) return <p role="alert" className="rounded-xl bg-red-50 p-4 font-semibold text-red-800">{error}</p>;
  if (!report) return <p className="text-slate-600">Loading execution report…</p>;

  const payload = report.reportPayload;
  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-3">
        <Summary label="Total rows" value={payload.totalRows} />
        <Summary label="Generated" value={payload.generatedRows} />
        <Summary label="Failed" value={payload.failedRows} />
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-2xl font-semibold">Row audit</h2>
          <a href={apiUrl(report.downloadPath)} className="rounded-lg bg-slate-900 px-5 py-3 font-semibold text-white">Download complete ZIP</a>
        </div>
        <div className="mt-5 space-y-3">
          {payload.rows.map((row) => (
            <article key={row.rowNumber} className="rounded-xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-semibold">Row {row.rowNumber}: {row.scenarioId}</h3>
                <span className="font-semibold">{row.status}</span>
              </div>
              <p className="mt-2 text-sm text-slate-600">
                {row.resolvedMessageType ?? "No message"} · {row.profileId ?? "No profile"} · {row.errorCount} errors
              </p>
              {row.findings[0] && <p className="mt-2 text-sm">{row.findings[0].ruleId}: {row.findings[0].message}</p>}
            </article>
          ))}
        </div>
      </section>
      <p className="rounded-xl bg-amber-50 p-4 text-sm leading-6 text-amber-950">{payload.disclaimer}</p>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: number }) {
  return <div className="rounded-2xl bg-slate-900 p-5 text-white"><p className="text-sm text-slate-300">{label}</p><p className="mt-2 text-3xl font-semibold">{value}</p></div>;
}
