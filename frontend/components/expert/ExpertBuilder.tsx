"use client";

import { useState } from "react";
import { ApiError, apiRequest } from "@/lib/api-client";
import type { CanonicalScenario, GeneratedMessage } from "@/lib/contracts";
import { MessageViews } from "@/components/messages/MessageViews";

function sampleScenario(profileId: string): CanonicalScenario {
  return {
    scenarioId: "EXPERT-DEMO-001",
    profileId,
    lifecycle: "INSTRUCTION",
    direction: "RECEIVE",
    paymentType: "AGAINST_PAYMENT",
    messageType: "MT541",
    function: "NEWM",
    senderReference: "EXPERT000001",
    clientReference: profileId === "BFS_CLIENT_DEMO_V1" ? "BFSCLIENT01" : undefined,
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
    confirmation: {},
    status: {},
    testConfiguration: { mode: "VALID" },
    syntheticData: true,
  };
}

export function ExpertBuilder() {
  const [profileId, setProfileId] = useState("BASE_DEMO_V1");
  const [message, setMessage] = useState<GeneratedMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const generated = await apiRequest<GeneratedMessage>("/api/messages/generate", {
        method: "POST",
        body: JSON.stringify({ scenario: sampleScenario(profileId) }),
      });
      setMessage(generated);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Expert generation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="grid items-end gap-4 md:grid-cols-[1fr_auto]">
          <label className="font-semibold" htmlFor="expert-profile">
            Client profile
            <select
              id="expert-profile"
              value={profileId}
              onChange={(event) => {
                setProfileId(event.target.value);
                setMessage(null);
              }}
              className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-3 font-normal"
            >
              <option value="BASE_DEMO_V1">Base Demo Profile</option>
              <option value="BFS_CLIENT_DEMO_V1">BFS Client Demo Profile</option>
            </select>
          </label>
          <button type="button" disabled={busy} onClick={generate} className="rounded-lg bg-teal-700 px-5 py-3 font-semibold text-white disabled:opacity-50">
            Generate and validate synthetic MT541
          </button>
        </div>
        <p className="mt-4 text-sm text-slate-600">
          The BFS profile adds a required client reference, supplies a synthetic PSET default,
          restricts currencies, and shortens the sender-reference limit.
        </p>
      </section>
      {error && <p role="alert" className="rounded-xl bg-red-50 p-4 font-semibold text-red-800">{error}</p>}
      {message && <MessageViews message={message} />}
    </div>
  );
}
