"use client";

import { useState } from "react";
import { ApiError, apiRequest } from "@/lib/api-client";
import type { WorkflowGeneratedMessage, WorkflowLifecycle } from "@/lib/contracts";
import { WorkflowMessageViews } from "@/components/messages/WorkflowMessageViews";

export function PenaltyStudio() {
  const [status, setStatus] = useState("ACTIVE");
  const [direction, setDirection] = useState("PAYABLE");
  const [message, setMessage] = useState<WorkflowGeneratedMessage>();
  const [lifecycle, setLifecycle] = useState<WorkflowLifecycle>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function generate() {
    setBusy(true); setError("");
    const suffix = Date.now().toString(36).toUpperCase();
    const workflowId = `PENA-${suffix}`;
    try {
      const generated = await apiRequest<WorkflowGeneratedMessage>("/api/penalties/generate", {
        method: "POST",
        body: JSON.stringify({ statement: {
          workflowId,
          profileId: "BASE_DEMO_V1",
          statementReference: `PS${suffix}`.slice(0, 16),
          statementDate: "2026-08-05",
          safekeepingAccount: "SYNTHSAFE01",
          accountServicer: "SYNTHSERVICER",
          relatedParty: "SYNTHPARTY",
          listType: "NEW_ONLY",
          penalties: [{
            penaltyReference: `PD${suffix}`.slice(0, 16),
            commonReference: `PC${suffix}`.slice(0, 16),
            relatedInstructionReference: "SYNTHSETTLE01",
            penaltyType: "SETTLEMENT_FAIL",
            action: "NEW",
            status,
            currency: "EUR",
            amount: "25.00",
            amountDirection: direction,
            detectionDate: "2026-08-04",
            numberOfDays: 1,
          }],
          syntheticData: true,
        }}),
      });
      setMessage(generated);
      setLifecycle(await apiRequest<WorkflowLifecycle>(`/api/workflows/${workflowId}/lifecycle`));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Penalty generation failed.");
    } finally { setBusy(false); }
  }

  return <div className="space-y-7">
    <section className="rounded-2xl border bg-white p-6 shadow-sm">
      <h2 className="text-xl font-semibold">Synthetic penalty statement builder</h2>
      <p className="mt-2 text-slate-600">The amount EUR 25.00 is explicit synthetic input, not a calculated value.</p>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="font-semibold">Penalty status<select aria-label="Penalty status" value={status} onChange={(event) => setStatus(event.target.value)} className="mt-2 block w-full rounded-lg border p-3"><option value="ACTIVE">Active</option><option value="NOT_COMPUTED">Not computed</option></select></label>
        <label className="font-semibold">Amount direction<select aria-label="Amount direction" value={direction} onChange={(event) => setDirection(event.target.value)} className="mt-2 block w-full rounded-lg border p-3"><option value="PAYABLE">Payable</option><option value="RECEIVABLE">Receivable</option></select></label>
      </div>
      <button type="button" disabled={busy} onClick={generate} className="mt-5 rounded-lg bg-teal-700 px-4 py-3 font-semibold text-white disabled:opacity-50">Generate MT537</button>
      {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-4 text-red-800">{error}</p>}
    </section>
    {lifecycle && <section className="rounded-2xl border bg-white p-5"><h2 className="text-lg font-semibold">Penalty history</h2><p className="mt-2">{lifecycle.entries.length} persisted statement · Correlation {lifecycle.correlationValid ? "valid" : "invalid"}</p></section>}
    {message && <WorkflowMessageViews message={message} />}
  </div>;
}
