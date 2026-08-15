"use client";

import { useState } from "react";
import { ApiError, apiRequest } from "@/lib/api-client";
import type {
  AmendmentDecision,
  CancelRebookResult,
  GeneratedMessage,
  LifecycleTimeline,
} from "@/lib/contracts";
import { MessageViews } from "@/components/messages/MessageViews";

function reference(prefix: string) {
  return `${prefix}${Date.now().toString(36).toUpperCase()}`.slice(0, 16);
}

function instructionPayload(senderReference: string) {
  return {
    scenario: {
      scenarioId: `PROCESS-${senderReference}`,
      profileId: "BASE_DEMO_V1",
      lifecycle: "INSTRUCTION",
      direction: "RECEIVE",
      paymentType: "AGAINST_PAYMENT",
      function: "NEWM",
      senderReference,
      trade: {
        transactionType: "BUY",
        tradeDate: "2026-08-03",
        settlementDate: "2026-08-06",
      },
      security: {
        identifierType: "ISIN",
        identifier: "XS0000000001",
        quantityType: "UNIT",
        quantity: "1000",
      },
      account: { safekeepingAccount: "SYNTHSAFE01" },
      settlement: {
        currency: "USD",
        amount: "25000.00",
        placeOfSettlement: "SYNTHPSET01",
        deliveringAgent: "SYNTHDEAG01",
        receivingAgent: "SYNTHREAG01",
      },
      testConfiguration: { mode: "VALID" },
      syntheticData: true,
    },
  };
}

export function SettlementProcessingStudio() {
  const [original, setOriginal] = useState<GeneratedMessage>();
  const [decision, setDecision] = useState<AmendmentDecision>();
  const [generated, setGenerated] = useState<GeneratedMessage>();
  const [rebook, setRebook] = useState<CancelRebookResult>();
  const [timeline, setTimeline] = useState<LifecycleTimeline>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The processing operation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshTimeline(rootId: string) {
    setTimeline(await apiRequest<LifecycleTimeline>(`/api/workflows/${rootId}/lifecycle`));
  }

  function createOriginal() {
    run(async () => {
      const message = await apiRequest<GeneratedMessage>("/api/messages/generate", {
        method: "POST",
        body: JSON.stringify(instructionPayload(reference("ORIG"))),
      });
      setOriginal(message);
      setDecision(undefined);
      setGenerated(undefined);
      setRebook(undefined);
      await refreshTimeline(message.messageId);
    });
  }

  function decide(fieldPath: "processing.priority" | "security.quantity" | "processing.holdRelease") {
    if (!original) return;
    run(async () => {
      const result = await apiRequest<AmendmentDecision>("/api/settlement/amendment-decision", {
        method: "POST",
        body: JSON.stringify({
          originalInstructionId: original.messageId,
          changes: [{ fieldPath, proposedValue: fieldPath === "security.quantity" ? "1500" : "42" }],
        }),
      });
      setDecision(result);
    });
  }

  function createPriorityCommand() {
    if (!original) return;
    run(async () => {
      const message = await apiRequest<GeneratedMessage>("/api/settlement/commands", {
        method: "POST",
        body: JSON.stringify({
          originalInstructionId: original.messageId,
          commandReference: reference("CMD"),
          commandType: "MODIFY_PRIORITY",
          priority: 42,
        }),
      });
      setGenerated(message);
      await refreshTimeline(original.messageId);
    });
  }

  function createCancellation() {
    if (!original) return;
    run(async () => {
      const message = await apiRequest<GeneratedMessage>("/api/settlement/cancellations", {
        method: "POST",
        body: JSON.stringify({
          originalInstructionId: original.messageId,
          cancellationReference: reference("CXL"),
        }),
      });
      setGenerated(message);
      await refreshTimeline(original.messageId);
    });
  }

  function cancelAndRebook() {
    if (!original) return;
    run(async () => {
      const result = await apiRequest<CancelRebookResult>("/api/settlement/cancel-rebook", {
        method: "POST",
        body: JSON.stringify({
          originalInstructionId: original.messageId,
          cancellationReference: reference("RCXL"),
          replacementReference: reference("REPL"),
          changes: [{ fieldPath: "security.quantity", proposedValue: "1500" }],
        }),
      });
      setRebook(result);
      setGenerated(result.replacement);
      await refreshTimeline(original.messageId);
    });
  }

  return (
    <div className="space-y-7">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold">Synthetic processing workflow</h2>
            <p className="mt-2 max-w-3xl text-slate-600">
              Create a persisted MT541, inspect the deterministic decision, then take only a
              supported action. No AI decides amendability.
            </p>
          </div>
          <button className="rounded-lg bg-teal-700 px-4 py-3 font-semibold text-white disabled:opacity-50" disabled={busy} onClick={createOriginal} type="button">
            Create synthetic MT541
          </button>
        </div>
        {original && (
          <div className="mt-5 flex flex-wrap gap-3" aria-label="Settlement processing actions">
            <Action label="Decide priority change" disabled={busy} action={() => decide("processing.priority")} />
            <Action label="Decide quantity change" disabled={busy} action={() => decide("security.quantity")} />
            <Action label="Check unsupported hold/release" disabled={busy} action={() => decide("processing.holdRelease")} />
            <Action label="Generate MT530 priority" disabled={busy} action={createPriorityCommand} />
            <Action label="Request cancellation" disabled={busy} action={createCancellation} />
            <Action label="Cancel and rebook quantity" disabled={busy} action={cancelAndRebook} />
          </div>
        )}
        {error && <p role="alert" className="mt-5 rounded-lg bg-red-50 p-4 font-medium text-red-800">{error}</p>}
      </section>

      {decision && (
        <section aria-label="Amendment decision" className="rounded-2xl border border-blue-200 bg-blue-50 p-5 text-blue-950">
          <h2 className="text-lg font-semibold">Decision: {decision.classification}</h2>
          <p className="mt-2">Method: {decision.method}</p>
          <p className="mt-2">{decision.explanation}</p>
          <p className="mt-3 text-sm">Policy source: {decision.sourceReference}</p>
        </section>
      )}

      {rebook && (
        <section aria-label="Cancel and rebook comparison" className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
          <h2 className="text-lg font-semibold">Cancel-and-rebook completed</h2>
          <p className="mt-2">Original quantity: {String(rebook.beforeValues["security.quantity"])} → Replacement quantity: {String(rebook.afterValues["security.quantity"])}</p>
          <p className="mt-2 text-sm">The original instruction remains immutable and the replacement has a new sender reference.</p>
        </section>
      )}

      {timeline && (
        <section aria-labelledby="processing-timeline">
          <h2 id="processing-timeline" className="text-2xl font-semibold">Processing lifecycle</h2>
          <ol className="mt-4 grid gap-4 md:grid-cols-3">
            {timeline.entries.map((entry) => (
              <li key={entry.messageId} className="rounded-xl border bg-white p-4">
                <p className="text-xl font-semibold text-teal-800">{entry.messageType}</p>
                <p className="mt-1 text-sm text-slate-600">{entry.businessStatus}</p>
                <p className="mt-2 break-all text-xs">{entry.senderReference}</p>
              </li>
            ))}
          </ol>
        </section>
      )}
      {generated && <MessageViews message={generated} />}
    </div>
  );
}

function Action({ label, disabled, action }: { label: string; disabled: boolean; action: () => void }) {
  return (
    <button type="button" disabled={disabled} onClick={action} className="rounded-lg border border-teal-700 px-3 py-2 font-semibold text-teal-800 disabled:opacity-50">
      {label}
    </button>
  );
}
