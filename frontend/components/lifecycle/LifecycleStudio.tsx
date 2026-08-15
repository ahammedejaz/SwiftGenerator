"use client";

import { useState } from "react";
import { apiRequest, ApiError } from "@/lib/api-client";
import type { GeneratedMessage, LifecycleTimeline } from "@/lib/contracts";

const SYNTHETIC_MT541 = {
  scenarioId: "DEMO-LIFECYCLE-001",
  profileId: "BASE_DEMO_V1",
  lifecycle: "INSTRUCTION",
  direction: "RECEIVE",
  paymentType: "AGAINST_PAYMENT",
  function: "NEWM",
  senderReference: "DEMOLIFE0001",
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
};

export function LifecycleStudio() {
  const [instruction, setInstruction] = useState<GeneratedMessage | null>(null);
  const [messages, setMessages] = useState<GeneratedMessage[]>([]);
  const [timeline, setTimeline] = useState<LifecycleTimeline | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createInstruction() {
    await run(async () => {
      const generated = await apiRequest<GeneratedMessage>("/api/messages/generate", {
        method: "POST",
        body: JSON.stringify({ scenario: SYNTHETIC_MT541 }),
      });
      setInstruction(generated);
      setMessages([generated]);
      await refreshTimeline(generated.messageId);
    });
  }

  async function createResponse(body: Record<string, string>) {
    if (!instruction) return;
    await run(async () => {
      const generated = await apiRequest<GeneratedMessage>(
        `/api/messages/${instruction.messageId}/responses`,
        { method: "POST", body: JSON.stringify(body) },
      );
      setMessages((current) => [...current, generated]);
      await refreshTimeline(instruction.messageId);
    });
  }

  async function refreshTimeline(messageId: string) {
    const value = await apiRequest<LifecycleTimeline>(`/api/messages/${messageId}/lifecycle`);
    setTimeline(value);
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The lifecycle operation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold">Synthetic lifecycle controls</h2>
            <p className="mt-2 text-slate-600">
              Build the minimum complete deterministic lifecycle without an AI provider.
            </p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={createInstruction}
            className="rounded-lg bg-teal-700 px-4 py-3 font-semibold text-white disabled:opacity-50"
          >
            {instruction ? "Create another MT541" : "Create synthetic MT541"}
          </button>
        </div>

        {instruction && (
          <div className="mt-6 flex flex-wrap gap-3" aria-label="Lifecycle response actions">
            <ActionButton
              label="Generate MT548 Pending"
              disabled={busy}
              onClick={() =>
                createResponse({ action: "PENDING_STATUS", reasonCode: "AWAITING_CASH" })
              }
            />
            <ActionButton
              label="Generate MT548 Rejected"
              disabled={busy}
              onClick={() =>
                createResponse({ action: "REJECTED_STATUS", reasonCode: "INVALID_REFERENCE" })
              }
            />
            <ActionButton
              label="Generate MT548 Matched"
              disabled={busy}
              onClick={() =>
                createResponse({ action: "MATCHED_STATUS", reasonCode: "DETAILS_MATCHED" })
              }
            />
            <ActionButton
              label="Generate MT548 Unmatched"
              disabled={busy}
              onClick={() =>
                createResponse({
                  action: "UNMATCHED_STATUS",
                  reasonCode: "COUNTERPARTY_MISMATCH",
                })
              }
            />
            <ActionButton
              label="Generate cancellation accepted"
              disabled={busy}
              onClick={() =>
                createResponse({
                  action: "CANCELLATION_ACCEPTED_STATUS",
                  reasonCode: "CANCELLATION_PROCESSED",
                })
              }
            />
            <ActionButton
              label="Generate cancellation rejected"
              disabled={busy}
              onClick={() =>
                createResponse({
                  action: "CANCELLATION_REJECTED_STATUS",
                  reasonCode: "SETTLEMENT_ALREADY_FINAL",
                })
              }
            />
            <ActionButton
              label="Generate MT545 Full"
              disabled={busy}
              onClick={() =>
                createResponse({
                  action: "FULL_CONFIRMATION",
                  actualSettlementDate: "2026-08-06",
                })
              }
            />
            <ActionButton
              label="Generate MT545 Partial"
              disabled={busy}
              onClick={() =>
                createResponse({
                  action: "PARTIAL_CONFIRMATION",
                  actualSettlementDate: "2026-08-06",
                  settledQuantity: "400",
                  settledAmount: "10000.00",
                })
              }
            />
          </div>
        )}
        {error && (
          <p role="alert" className="mt-5 rounded-lg bg-red-50 p-4 font-medium text-red-800">
            {error}
          </p>
        )}
      </section>

      {timeline && (
        <section aria-labelledby="timeline-heading">
          <div className="flex items-center justify-between">
            <h2 id="timeline-heading" className="text-2xl font-semibold">
              Lifecycle timeline
            </h2>
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-sm font-semibold text-emerald-900">
              {timeline.correlationValid ? "Correlation valid" : "Correlation errors"}
            </span>
          </div>
          <ol className="mt-5 grid gap-4 md:grid-cols-3">
            {timeline.entries.map((entry, index) => (
              <li key={entry.messageId} className="rounded-2xl border bg-white p-5 shadow-sm">
                <p className="text-sm font-semibold text-slate-500">Step {index + 1}</p>
                <p className="mt-2 text-2xl font-semibold text-teal-800">{entry.messageType}</p>
                <p className="mt-1 text-sm text-slate-600">{entry.businessStatus}</p>
                <dl className="mt-4 space-y-2 text-sm">
                  <div>
                    <dt className="font-medium">Reference</dt>
                    <dd className="break-all text-slate-600">{entry.senderReference}</dd>
                  </div>
                  <div>
                    <dt className="font-medium">Validation</dt>
                    <dd className="text-slate-600">{entry.validationStatus}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ol>
        </section>
      )}

      {messages.length > 0 && (
        <section aria-labelledby="messages-heading">
          <h2 id="messages-heading" className="text-2xl font-semibold">
            Generated demonstration messages
          </h2>
          <div className="mt-5 space-y-5">
            {messages.map((message) => (
              <article key={message.messageId} className="overflow-hidden rounded-2xl bg-slate-950">
                <div className="flex items-center justify-between border-b border-slate-700 px-5 py-3 text-white">
                  <h3 className="font-semibold">{message.resolvedMessageType}</h3>
                  <span className="text-sm text-emerald-300">{message.validation.status}</span>
                </div>
                <pre className="overflow-x-auto p-5 text-sm leading-6 text-slate-200">
                  {message.rawMessage}
                </pre>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function ActionButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="rounded-lg border border-teal-700 px-4 py-2.5 font-semibold text-teal-800 hover:bg-teal-50 disabled:opacity-50"
    >
      {label}
    </button>
  );
}
