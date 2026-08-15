"use client";

import { useState } from "react";
import { ApiError, apiRequest } from "@/lib/api-client";
import type { WorkflowGeneratedMessage, WorkflowLifecycle } from "@/lib/contracts";
import { WorkflowMessageViews } from "@/components/messages/WorkflowMessageViews";

type Stage = "notification" | "instruction" | "status" | "confirmation" | "narrative";

export function CorporateActionStudio() {
  const [workflowId, setWorkflowId] = useState("");
  const [messages, setMessages] = useState<Partial<Record<Stage, WorkflowGeneratedMessage>>>({});
  const [selected, setSelected] = useState<Stage>("notification");
  const [lifecycle, setLifecycle] = useState<WorkflowLifecycle>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh(id: string) {
    setLifecycle(await apiRequest<WorkflowLifecycle>(`/api/workflows/${id}/lifecycle`));
  }

  async function createNotification() {
    setBusy(true); setError("");
    const suffix = Date.now().toString(36).toUpperCase();
    const id = `CA-${suffix}`;
    try {
      const message = await apiRequest<WorkflowGeneratedMessage>("/api/corporate-actions/notifications", {
        method: "POST",
        body: JSON.stringify({ notification: {
          workflowId: id,
          profileId: "BASE_DEMO_V1",
          eventReference: `CE${suffix}`.slice(0, 16),
          messageReference: `N4${suffix}`.slice(0, 16),
          eventType: "DIVIDEND_WITH_OPTIONS",
          classification: "VOLUNTARY",
          securityIdentifier: "XS0000000001",
          safekeepingAccount: "SYNTHSAFE01",
          eligibleQuantity: "1000",
          electionDeadline: "2099-08-10",
          paymentDate: "2099-08-15",
          options: [
            { optionNumber: 1, optionCode: "CASH", defaultOption: true },
            { optionNumber: 2, optionCode: "SECURITIES", defaultOption: false },
          ],
          syntheticData: true,
        }}),
      });
      setWorkflowId(id); setMessages({ notification: message }); setSelected("notification");
      await refresh(id);
    } catch (caught) { setError(messageFor(caught)); } finally { setBusy(false); }
  }

  async function createInstruction() {
    const notification = messages.notification; if (!notification) return;
    await execute("instruction", "/api/corporate-actions/instructions", {
      workflowId,
      messageReference: uniqueReference("I5"),
      notificationMessageId: notification.messageId,
      optionNumber: 1,
      instructedQuantity: "800",
    });
  }

  async function createStatus() {
    const instruction = messages.instruction; if (!instruction) return;
    await execute("status", "/api/corporate-actions/statuses", {
      workflowId,
      messageReference: uniqueReference("S7"),
      instructionMessageId: instruction.messageId,
      status: "PENDING",
    });
  }

  async function createConfirmation() {
    const instruction = messages.instruction; if (!instruction) return;
    await execute("confirmation", "/api/corporate-actions/confirmations", {
      workflowId,
      messageReference: uniqueReference("C6"),
      instructionMessageId: instruction.messageId,
      optionNumber: 1,
      confirmedQuantity: "800",
      cashCurrency: "USD",
      cashAmount: "125.50",
      paymentDate: "2099-08-15",
    });
  }

  async function createNarrative() {
    const notification = messages.notification; if (!notification) return;
    await execute("narrative", "/api/corporate-actions/narratives", {
      workflowId,
      messageReference: uniqueReference("N8"),
      notificationMessageId: notification.messageId,
      narrative: "SYNTHETIC SUPPORTING INFORMATION ONLY.",
    });
  }

  async function execute(stage: Stage, path: string, body: Record<string, unknown>) {
    setBusy(true); setError("");
    try {
      const message = await apiRequest<WorkflowGeneratedMessage>(path, {
        method: "POST", body: JSON.stringify(body),
      });
      setMessages((current) => ({ ...current, [stage]: message })); setSelected(stage);
      await refresh(workflowId);
    } catch (caught) { setError(messageFor(caught)); } finally { setBusy(false); }
  }

  const current = messages[selected];
  return <div className="mt-8 space-y-6">
    <section className="rounded-2xl border bg-white p-6 shadow-sm">
      <h2 className="text-xl font-semibold">Lifecycle controls</h2>
      <p className="mt-2 text-slate-600">All values below are synthetic. The supplied cash amount is reported, not calculated.</p>
      <div className="mt-5 flex flex-wrap gap-3">
        <Action label="Create MT564 notification" disabled={busy} onClick={createNotification} />
        <Action label="Create MT565 election" disabled={busy || !messages.notification} onClick={createInstruction} />
        <Action label="Create MT567 pending" disabled={busy || !messages.instruction} onClick={createStatus} />
        <Action label="Create MT566 confirmation" disabled={busy || !messages.instruction} onClick={createConfirmation} />
        <Action label="Create MT568 narrative" disabled={busy || !messages.notification} onClick={createNarrative} />
      </div>
      {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-4 text-red-800">{error}</p>}
    </section>
    {lifecycle && <section className="rounded-2xl border bg-white p-6">
      <h2 className="font-semibold">Notification → Election → Processing Status → Confirmation</h2>
      <ol aria-label="Corporate action lifecycle" className="mt-4 grid gap-3 md:grid-cols-5">
        {lifecycle.entries.map((entry) => <li key={entry.messageId} className="rounded-lg bg-slate-50 p-3">
          <button type="button" className="text-left" onClick={() => {
            const match = Object.entries(messages).find(([, message]) => message?.messageId === entry.messageId);
            if (match) setSelected(match[0] as Stage);
          }}><strong>{entry.messageType}</strong><span className="mt-1 block text-sm text-slate-600">{entry.businessStatus}</span></button>
        </li>)}
      </ol>
    </section>}
    {current && <WorkflowMessageViews message={current} />}
  </div>;
}

function Action({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }) {
  return <button type="button" disabled={disabled} onClick={onClick} className="rounded-lg bg-teal-700 px-4 py-3 font-semibold text-white disabled:opacity-40">{label}</button>;
}

function uniqueReference(prefix: string) {
  return `${prefix}${Date.now().toString(36).toUpperCase()}`.slice(0, 16);
}

function messageFor(error: unknown) {
  return error instanceof ApiError ? error.message : "Corporate-action operation failed.";
}
