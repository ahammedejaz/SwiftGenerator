"use client";

import { useEffect, useState } from "react";
import { MessageViews } from "@/components/messages/MessageViews";
import { AiUsagePanel } from "@/components/ai/AiUsagePanel";
import { ApiError, apiRequest } from "@/lib/api-client";
import type {
  AiHealth,
  CanonicalScenario,
  GeneratedMessage,
  MessageResolution,
  MissingFieldsResponse,
  ScenarioInterpretation,
} from "@/lib/contracts";

const DEMO_PHRASE =
  "I purchased 1,000 securities and need to settle them against payment.";

type InterpretStatus =
  | "idle"
  | "interpreting"
  | "completed"
  | "clarification"
  | "unavailable"
  | "non-ai";

export function GuidedGenerator() {
  const [phrase, setPhrase] = useState(DEMO_PHRASE);
  const [interpretation, setInterpretation] = useState<ScenarioInterpretation | null>(null);
  const [scenario, setScenario] = useState<CanonicalScenario | null>(null);
  const [missing, setMissing] = useState<MissingFieldsResponse | null>(null);
  const [generated, setGenerated] = useState<GeneratedMessage | null>(null);
  const [negativeMode, setNegativeMode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiHealth, setAiHealth] = useState<AiHealth | null>(null);
  const [interpretStatus, setInterpretStatus] = useState<InterpretStatus>("idle");
  const [businessConfirmed, setBusinessConfirmed] = useState(false);
  const [confirmedFields, setConfirmedFields] = useState<string[]>([]);

  useEffect(() => {
    void apiRequest<AiHealth>("/api/ai/health")
      .then(setAiHealth)
      .catch(() => setAiHealth(null));
  }, []);

  async function interpret() {
    setBusy(true);
    setError(null);
    setInterpretStatus("interpreting");
    try {
      const result = await apiRequest<ScenarioInterpretation>("/api/agent/interpret", {
        method: "POST",
        body: JSON.stringify({
          text: phrase,
          profileId: scenario?.profileId ?? "BASE_DEMO_V1",
          currentScenario: scenario,
          confirmedFields,
        }),
      });
      await applyInterpretation(result, "completed");
    } catch (caught) {
      setInterpretStatus("unavailable");
      setError(
        caught instanceof ApiError
          ? caught.message
          : "AI interpretation is temporarily unavailable.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function useDeterministicForm() {
    await run(async () => {
      const result = await apiRequest<ScenarioInterpretation>(
        "/api/agent/interpret-deterministic",
        {
          method: "POST",
          body: JSON.stringify({
            text: phrase,
            profileId: scenario?.profileId ?? "BASE_DEMO_V1",
          }),
        },
      );
      await applyInterpretation(result, "non-ai");
    });
  }

  async function applyInterpretation(
    result: ScenarioInterpretation,
    sourceStatus: "completed" | "non-ai",
  ) {
    setInterpretation(result);
    setScenario(result.scenario);
    setBusinessConfirmed(!result.requiresBusinessConfirmation);
    const inferred = new Set(result.intent?.inferredFields ?? []);
    const explicitlyConfirmed = result.extractedFields.map((item) => item.fieldPath);
    if (result.intent?.lifecycle && !inferred.has("lifecycle")) {
      explicitlyConfirmed.push("lifecycle");
    }
    if (result.intent?.direction && !inferred.has("direction")) {
      explicitlyConfirmed.push("direction");
    }
    if (result.intent?.paymentType && !inferred.has("paymentType")) {
      explicitlyConfirmed.push("paymentType");
    }
    if (result.intent?.transactionType && !inferred.has("transactionType")) {
      explicitlyConfirmed.push("trade.transactionType");
    }
    if (!result.ai.used) {
      explicitlyConfirmed.push(
        ...result.detectedFields.filter(
          (path) => !(result.requiresBusinessConfirmation && path === "direction"),
        ),
      );
    }
    setConfirmedFields([...new Set(explicitlyConfirmed)]);
    if (result.resolution.resolvedMessageType) {
      const completion = await getMissing(result.scenario);
      setScenario(completion.scenarioWithDefaults);
      setMissing(completion);
    } else {
      setMissing(null);
    }
    setInterpretStatus(result.requiresClarification ? "clarification" : sourceStatus);
    setGenerated(null);
  }

  async function refresh(next: CanonicalScenario) {
    const resolution = await apiRequest<MessageResolution>("/api/messages/resolve", {
      method: "POST",
      body: JSON.stringify({
        lifecycle: next.lifecycle,
        direction: next.direction,
        paymentType: next.paymentType,
      }),
    });
    const resolved = { ...next, messageType: resolution.resolvedMessageType };
    setScenario(resolved);
    setInterpretation((current) => (current ? { ...current, resolution } : current));
    if (!resolution.resolvedMessageType) {
      setMissing(null);
      return;
    }
    const completion = await getMissing(resolved);
    setScenario(completion.scenarioWithDefaults);
    setMissing(completion);
  }

  function confirmAndRefresh(next: CanonicalScenario, fieldPath: string) {
    setConfirmedFields((current) => [...new Set([...current, fieldPath])]);
    void refresh(next);
  }

  async function getMissing(value: CanonicalScenario) {
    return apiRequest<MissingFieldsResponse>("/api/messages/missing-fields", {
      method: "POST",
      body: JSON.stringify({ scenario: value }),
    });
  }

  function loadSyntheticAnswers() {
    if (!scenario) return;
    const filled: CanonicalScenario = {
      ...scenario,
      direction: "RECEIVE",
      paymentType: "AGAINST_PAYMENT",
      messageType: "MT541",
      function: "NEWM",
      senderReference: "GUIDED000001",
      clientReference:
        scenario.profileId === "BFS_CLIENT_DEMO_V1"
          ? "BFSCLIENT01"
          : scenario.clientReference,
      trade: {
        ...scenario.trade,
        transactionType: "BUY",
        tradeDate: "2026-08-03",
        settlementDate: "2026-08-06",
      },
      security: {
        ...scenario.security,
        identifier: "XS0000000001",
        quantity: scenario.security.quantity ?? "1000",
      },
      account: { safekeepingAccount: "SYNTHSAFE01" },
      settlement: {
        ...scenario.settlement,
        currency: "USD",
        amount: "25000.00",
        placeOfSettlement: scenario.settlement.placeOfSettlement ?? "SYNTHPSET01",
        deliveringAgent: "SYNTHDEAG01",
        receivingAgent: "SYNTHREAG01",
      },
    };
    setBusinessConfirmed(true);
    setConfirmedFields([
      "direction",
      "paymentType",
      "function",
      "senderReference",
      "trade.transactionType",
      "trade.tradeDate",
      "trade.settlementDate",
      "security.identifier",
      "security.quantity",
      "account.safekeepingAccount",
      "settlement.currency",
      "settlement.amount",
      "settlement.placeOfSettlement",
      "settlement.deliveringAgent",
      "settlement.receivingAgent",
    ]);
    void refresh(filled);
  }

  async function generate() {
    if (!scenario) return;
    await run(async () => {
      const configured: CanonicalScenario = {
        ...scenario,
        testConfiguration: negativeMode
          ? {
              mode: "NEGATIVE_TEST",
              mutation: "MISSING_SETTLEMENT_AMOUNT",
              expectedOutcome: "MT541-SETTLEMENT-AMOUNT-REQUIRED",
            }
          : { mode: "VALID" },
      };
      const result = await apiRequest<GeneratedMessage>("/api/messages/generate", {
        method: "POST",
        body: JSON.stringify({ scenario: configured }),
      });
      setGenerated(result);
    });
  }

  async function switchProfile(profileId: string) {
    if (!scenario) return;
    await run(async () => {
      await refresh({ ...scenario, profileId });
      setGenerated(null);
    });
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The guided operation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-7">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <label htmlFor="business-scenario" className="text-lg font-semibold">
          Describe the settlement scenario
        </label>
        <p className="mt-1 text-sm text-slate-600">
          AI interprets supported business intent. Deterministic rules—not the model—resolve,
          compose, and validate the message.
        </p>
        <textarea
          id="business-scenario"
          rows={4}
          maxLength={6000}
          value={phrase}
          onChange={(event) => setPhrase(event.target.value)}
          className="mt-4 w-full rounded-xl border border-slate-300 p-4 leading-7"
        />
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            disabled={busy || !phrase.trim()}
            onClick={interpret}
            className="mt-4 rounded-lg bg-teal-700 px-5 py-3 font-semibold text-white disabled:opacity-50"
          >
            {interpretStatus === "interpreting" ? "Interpreting request…" : "Interpret scenario"}
          </button>
          <button
            type="button"
            disabled={busy || !phrase.trim()}
            onClick={useDeterministicForm}
            className="mt-4 rounded-lg border border-slate-400 px-5 py-3 font-semibold text-slate-800 disabled:opacity-50"
          >
            Use deterministic form
          </button>
        </div>
        <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold">
          <StatusBadge label={statusLabel(interpretStatus)} />
          {aiHealth && (
            <StatusBadge
              label={`AI ${aiHealth.configured ? "configured" : "not configured"} · ${aiHealth.primaryModel}`}
            />
          )}
          {aiHealth?.privacyEnforcementEnabled && (
            <StatusBadge label="ZDR + data denial enforced" />
          )}
        </div>
      </section>

      {error && (
        <p role="alert" className="rounded-xl bg-red-50 p-4 font-semibold text-red-800">
          {error}
        </p>
      )}

      {interpretation && scenario && (
        <>
          <AiUsagePanel ai={interpretation.ai} />
          <section className="grid gap-5 lg:grid-cols-[1fr_1.5fr]">
            <div className="rounded-2xl bg-slate-900 p-6 text-white">
              <p className="text-sm font-semibold uppercase tracking-widest text-teal-300">
                Deterministic resolution
              </p>
              <p className="mt-3 text-5xl font-semibold">
                {scenario.messageType ?? "More details needed"}
              </p>
              <p className="mt-4 leading-7 text-slate-300">
                {interpretation.resolution.explanation}
              </p>
              {interpretation.requiresBusinessConfirmation && (
                <label className="mt-4 flex gap-2 rounded-lg bg-amber-100 p-3 text-sm font-semibold text-amber-950">
                  <input
                    type="checkbox"
                    checked={businessConfirmed}
                    onChange={(event) => {
                      setBusinessConfirmed(event.target.checked);
                      if (event.target.checked) {
                        setConfirmedFields((current) => [
                          ...new Set([
                            ...current,
                            "lifecycle",
                            "direction",
                            "paymentType",
                          ]),
                        ]);
                      }
                    }}
                  />
                  Confirm the interpreted lifecycle, direction, and payment involvement before
                  generation.
                </label>
              )}
              <p className="mt-4 text-sm text-slate-300">
                {interpretation.ai.used
                  ? `AI interpretation: ${interpretation.ai.model}${interpretation.ai.escalated ? " (escalated)" : ""}.`
                  : "Deterministic non-AI interpretation was explicitly selected."}
              </p>
              {interpretation.conflicts.length > 0 && (
                <div className="mt-4 rounded-lg bg-red-100 p-3 text-sm text-red-950">
                  <p className="font-semibold">Confirmed values were preserved.</p>
                  <ul className="mt-2 list-disc pl-5">
                    {interpretation.conflicts.map((conflict) => (
                      <li key={conflict.fieldPath}>{conflict.message}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-6">
              <div className="flex items-center justify-between gap-4">
                <h2 className="text-xl font-semibold">Deterministic required information</h2>
                <span className="font-semibold text-teal-800">
                  {missing ? `${missing.completionPercentage}% complete` : "Decisions required"}
                </span>
              </div>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full bg-teal-600"
                  style={{ width: `${missing?.completionPercentage ?? 0}%` }}
                />
              </div>
              {missing?.nextQuestion ? (
                <div className="mt-5 rounded-xl bg-teal-50 p-4">
                  <p className="font-semibold text-teal-950">{missing.nextQuestion.question}</p>
                  <p className="mt-1 text-sm text-teal-900">
                    {missing.nextQuestion.explanation}
                  </p>
                </div>
              ) : missing ? (
                <p className="mt-5 font-semibold text-emerald-800">
                  All required business information is present.
                </p>
              ) : (
                <p className="mt-5 rounded-xl bg-amber-50 p-4 font-semibold text-amber-950">
                  Clarification required: select Receive or Deliver and whether payment is involved.
                </p>
              )}
              <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
                <BusinessFact label="Direction" value={scenario.direction} />
                <BusinessFact label="Payment" value={scenario.paymentType} />
                <BusinessFact label="Transaction" value={scenario.trade.transactionType} />
                <BusinessFact
                  label="Confidence"
                  value={
                    interpretation.confidence === undefined
                      ? undefined
                      : `${Math.round(interpretation.confidence * 100)}%`
                  }
                />
              </dl>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold">Guided normal form</h2>
                <p className="mt-1 text-sm text-slate-600">
                  Values remain authoritative only after deterministic schema and profile checks.
                  Demo answers are synthetic.
                </p>
              </div>
              <button
                type="button"
                onClick={loadSyntheticAnswers}
                className="rounded-lg border border-teal-700 px-4 py-2 font-semibold text-teal-800"
              >
                Load synthetic demo answers
              </button>
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <SelectField
                label="Client profile"
                value={scenario.profileId}
                onChange={switchProfile}
                options={["BASE_DEMO_V1", "BFS_CLIENT_DEMO_V1"]}
              />
              <SelectField
                label="Direction"
                value={scenario.direction ?? ""}
                onChange={(value) => {
                  setBusinessConfirmed(true);
                  confirmAndRefresh(
                    {
                      ...scenario,
                      direction: value as CanonicalScenario["direction"],
                    },
                    "direction",
                  );
                }}
                options={["RECEIVE", "DELIVER"]}
              />
              <SelectField
                label="Payment type"
                value={scenario.paymentType ?? ""}
                onChange={(value) => {
                  setBusinessConfirmed(true);
                  confirmAndRefresh(
                    {
                      ...scenario,
                      paymentType: value as CanonicalScenario["paymentType"],
                    },
                    "paymentType",
                  );
                }}
                options={["AGAINST_PAYMENT", "FREE_OF_PAYMENT"]}
              />
              <InputField
                label="Sender reference"
                value={scenario.senderReference ?? ""}
                onChange={(value) =>
                  confirmAndRefresh({ ...scenario, senderReference: value }, "senderReference")
                }
              />
              {scenario.profileId === "BFS_CLIENT_DEMO_V1" && (
                <InputField
                  label="Client reference (BFS required)"
                  value={scenario.clientReference ?? ""}
                  onChange={(value) =>
                    confirmAndRefresh(
                      { ...scenario, clientReference: value },
                      "clientReference",
                    )
                  }
                />
              )}
              <InputField
                label="Trade date"
                type="date"
                value={scenario.trade.tradeDate ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    { ...scenario, trade: { ...scenario.trade, tradeDate: value } },
                    "trade.tradeDate",
                  )
                }
              />
              <InputField
                label="Settlement date"
                type="date"
                value={scenario.trade.settlementDate ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    { ...scenario, trade: { ...scenario.trade, settlementDate: value } },
                    "trade.settlementDate",
                  )
                }
              />
              <InputField
                label="Synthetic ISIN"
                value={scenario.security.identifier ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    {
                      ...scenario,
                      security: { ...scenario.security, identifier: value.toUpperCase() },
                    },
                    "security.identifier",
                  )
                }
              />
              <InputField
                label="Quantity"
                type="number"
                value={scenario.security.quantity ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    {
                      ...scenario,
                      security: { ...scenario.security, quantity: value },
                    },
                    "security.quantity",
                  )
                }
              />
              <InputField
                label="Synthetic safekeeping account"
                value={scenario.account.safekeepingAccount ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    { ...scenario, account: { safekeepingAccount: value } },
                    "account.safekeepingAccount",
                  )
                }
              />
              <InputField
                label="Currency"
                value={scenario.settlement.currency ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    {
                      ...scenario,
                      settlement: { ...scenario.settlement, currency: value.toUpperCase() },
                    },
                    "settlement.currency",
                  )
                }
              />
              <InputField
                label="Settlement amount"
                type="number"
                value={scenario.settlement.amount ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    {
                      ...scenario,
                      settlement: { ...scenario.settlement, amount: value },
                    },
                    "settlement.amount",
                  )
                }
              />
              <InputField
                label="Synthetic place of settlement"
                value={scenario.settlement.placeOfSettlement ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    {
                      ...scenario,
                      settlement: { ...scenario.settlement, placeOfSettlement: value },
                    },
                    "settlement.placeOfSettlement",
                  )
                }
              />
              <InputField
                label="Synthetic delivering agent"
                value={scenario.settlement.deliveringAgent ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    {
                      ...scenario,
                      settlement: { ...scenario.settlement, deliveringAgent: value },
                    },
                    "settlement.deliveringAgent",
                  )
                }
              />
              <InputField
                label="Synthetic receiving agent"
                value={scenario.settlement.receivingAgent ?? ""}
                onChange={(value) =>
                  confirmAndRefresh(
                    {
                      ...scenario,
                      settlement: { ...scenario.settlement, receivingAgent: value },
                    },
                    "settlement.receivingAgent",
                  )
                }
              />
            </div>
            <div className="mt-6 flex flex-wrap items-center gap-4 border-t border-slate-200 pt-5">
              <label className="flex items-center gap-2 font-semibold">
                <input
                  type="checkbox"
                  checked={negativeMode}
                  onChange={(event) => setNegativeMode(event.target.checked)}
                />
                Negative test: remove MT541 settlement amount
              </label>
              <button
                type="button"
                disabled={
                  busy ||
                  !missing ||
                  missing.missingFields.length > 0 ||
                  !businessConfirmed
                }
                onClick={generate}
                className="rounded-lg bg-teal-700 px-5 py-3 font-semibold text-white disabled:opacity-50"
              >
                {negativeMode
                  ? "Generate intentional-invalid MT541"
                  : "Generate valid MT541"}
              </button>
            </div>
          </section>
        </>
      )}

      {interpretation?.ai.used && (
        <p className="rounded-xl border border-teal-200 bg-teal-50 p-4 text-sm text-teal-950">
          AI interpreted the business request. The message type, fields, validation, and final MT
          output are controlled by the deterministic rules engine.
        </p>
      )}
      {generated && <MessageViews message={generated} />}
    </div>
  );
}

function StatusBadge({ label }: { label: string }) {
  return <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{label}</span>;
}

function BusinessFact({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-semibold text-slate-900">{value?.replaceAll("_", " ") ?? "Not stated"}</dd>
    </div>
  );
}

function statusLabel(status: InterpretStatus) {
  return {
    idle: "Ready",
    interpreting: "Interpreting request",
    completed: "Interpretation completed",
    clarification: "Clarification required",
    unavailable: "AI temporarily unavailable",
    "non-ai": "Deterministic non-AI mode",
  }[status];
}

function InputField({
  label,
  value,
  type = "text",
  onChange,
}: {
  label: string;
  value: string;
  type?: string;
  onChange: (value: string) => void;
}) {
  const id = label.toLowerCase().replaceAll(" ", "-");
  return (
    <label htmlFor={id} className="text-sm font-semibold text-slate-700">
      {label}
      <input
        id={id}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal text-slate-900"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const id = label.toLowerCase().replaceAll(" ", "-");
  return (
    <label htmlFor={id} className="text-sm font-semibold text-slate-700">
      {label}
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal text-slate-900"
      >
        <option value="">Select…</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </label>
  );
}
