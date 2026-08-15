"use client";

import { useState } from "react";
import Link from "next/link";
import { ApiError, apiRequest, apiUrl } from "@/lib/api-client";
import type { BulkGenerateResponse } from "@/lib/contracts";

export function BulkGenerator() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<BulkGenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [workbookType, setWorkbookType] = useState<"settlement" | "workflow">("settlement");

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const endpoint = workbookType === "workflow" ? "/api/bulk/workflow-generate" : "/api/bulk/generate";
      const response = await apiRequest<BulkGenerateResponse>(endpoint, {
        method: "POST",
        body,
      });
      setResult(response);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Bulk generation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-7">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold">Excel scenario workbook</h2>
            <p className="mt-2 text-slate-600">
              Only bounded `.xlsx` files are accepted. Each row is parsed and validated independently.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href={apiUrl("/api/bulk/template")} className="rounded-lg border border-teal-700 px-4 py-3 font-semibold text-teal-800">Settlement template</a>
            <a href={apiUrl("/api/bulk/workflow-template")} className="rounded-lg border border-teal-700 px-4 py-3 font-semibold text-teal-800">Workflow template</a>
          </div>
        </div>
        <label htmlFor="bulk-file" className="mt-6 block font-semibold">
          Select Excel workbook
        </label>
        <select aria-label="Workbook type" value={workbookType} onChange={(event) => setWorkbookType(event.target.value as "settlement" | "workflow")} className="mt-2 rounded-lg border border-slate-300 p-3">
          <option value="settlement">Settlement MT540–MT548</option>
          <option value="workflow">MT530, MT537, and Corporate Actions</option>
        </select>
        <input
          id="bulk-file"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="mt-2 block w-full rounded-lg border border-slate-300 bg-slate-50 p-3"
        />
        <button type="button" disabled={!file || busy} onClick={upload} className="mt-4 rounded-lg bg-teal-700 px-5 py-3 font-semibold text-white disabled:opacity-50">
          {busy ? "Processing rows…" : "Generate valid rows"}
        </button>
        {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-4 font-semibold text-red-800">{error}</p>}
      </section>

      {result && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold">Execution summary</h2>
              <p className="mt-2 text-slate-600">
                {result.generatedRows} generated · {result.failedRows} failed · {result.totalRows} total
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link href={`/reports/${result.reportId}`} className="rounded-lg border border-slate-800 px-5 py-3 font-semibold text-slate-900">
                Open execution report
              </Link>
              <a href={apiUrl(result.downloadPath)} className="rounded-lg bg-slate-900 px-5 py-3 font-semibold text-white">
                Download ZIP and report
              </a>
            </div>
          </div>
          <div className="mt-6 overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead><tr className="border-b text-slate-600"><th className="p-3">Row</th><th className="p-3">Scenario</th><th className="p-3">Message</th><th className="p-3">Result</th><th className="p-3">Findings</th></tr></thead>
              <tbody>
                {result.rowResults.map((row) => (
                  <tr key={row.rowNumber} className="border-b align-top">
                    <td className="p-3">{row.rowNumber}</td>
                    <td className="p-3 font-medium">{row.scenarioId}</td>
                    <td className="p-3">{row.resolvedMessageType ?? "—"}</td>
                    <td className="p-3"><span className={`rounded-full px-2 py-1 font-semibold ${row.status === "GENERATED" ? "bg-emerald-100 text-emerald-900" : "bg-red-100 text-red-900"}`}>{row.status}</span></td>
                    <td className="p-3 text-slate-600">{row.findings[0]?.message ?? "No findings"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
