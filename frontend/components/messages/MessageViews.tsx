"use client";

import { useState } from "react";
import { apiRequest } from "@/lib/api-client";
import type { GeneratedMessage, RawValidationResponse, RenderedField } from "@/lib/contracts";
import { TagDetailsDrawer } from "@/components/knowledge/TagDetailsDrawer";

type View = "business" | "tags" | "raw";

export function MessageViews({ message }: { message: GeneratedMessage }) {
  const [view, setView] = useState<View>("business");
  const [rawMessage, setRawMessage] = useState(message.rawMessage);
  const [rawResult, setRawResult] = useState<RawValidationResponse>();
  const [rawError, setRawError] = useState("");
  const [validatingRaw, setValidatingRaw] = useState(false);
  const [selectedKnowledgeId, setSelectedKnowledgeId] = useState<string>();

  async function validateRaw() {
    setValidatingRaw(true);
    setRawError("");
    try {
      const result = await apiRequest<RawValidationResponse>("/api/messages/validate-raw", {
        method: "POST",
        body: JSON.stringify({ rawMessage, profileId: message.profileId }),
      });
      setRawResult(result);
    } catch (error) {
      setRawResult(undefined);
      setRawError(error instanceof Error ? error.message : "Raw validation failed.");
    } finally {
      setValidatingRaw(false);
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div>
          <p className="text-sm font-semibold text-teal-700">Generated message</p>
          <h2 className="text-2xl font-semibold">{message.resolvedMessageType}</h2>
        </div>
        <div className="flex rounded-lg bg-slate-100 p-1" role="tablist" aria-label="Message views">
          {(["business", "tags", "raw"] as const).map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={view === item}
              onClick={() => setView(item)}
              className={`rounded-md px-3 py-2 text-sm font-semibold capitalize ${
                view === item ? "bg-white text-teal-800 shadow-sm" : "text-slate-600"
              }`}
            >
              {item === "tags" ? "Tag View" : `${item} View`}
            </button>
          ))}
        </div>
      </div>

      {message.intentionalInvalidNotice && (
        <div role="alert" className="border-b border-amber-300 bg-amber-100 px-5 py-4 font-bold text-amber-950">
          {message.intentionalInvalidNotice}
        </div>
      )}

      <div className="p-5">
        {view === "business" && (
          <div className="space-y-5">
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <BusinessItem label="Direction" value={message.scenario.direction} />
              <BusinessItem label="Payment type" value={message.scenario.paymentType} />
              <BusinessItem label="Sender reference" value={message.scenario.senderReference} />
              <BusinessItem label="Trade date" value={message.scenario.trade.tradeDate} />
              <BusinessItem label="Settlement date" value={message.scenario.trade.settlementDate} />
              <BusinessItem label="Security" value={message.scenario.security.identifier} />
              <BusinessItem label="Quantity" value={message.scenario.security.quantity} />
              <BusinessItem label="Currency" value={message.scenario.settlement.currency} />
              <BusinessItem label="Amount" value={message.scenario.settlement.amount ?? "Omitted"} />
            </dl>
            <FieldKnowledgeButtons
              fields={message.fieldMap}
              onSelect={setSelectedKnowledgeId}
              messageType={message.resolvedMessageType}
              label="Explain the business fields"
            />
          </div>
        )}
        {view === "tags" && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b text-slate-600">
                  <th className="p-3">Sequence</th>
                  <th className="p-3">Tag / qualifier</th>
                  <th className="p-3">Value</th>
                  <th className="p-3">Business meaning</th>
                </tr>
              </thead>
              <tbody>
                {message.fieldMap.map((field, index) => (
                  <tr key={`${field.tag}-${field.qualifier}-${index}`} className="border-b">
                    <td className="p-3 font-medium">{field.sequence}</td>
                    <td className="p-3 font-mono">
                      <button
                        type="button"
                        onClick={() =>
                          setSelectedKnowledgeId(knowledgeId(message.resolvedMessageType, field))
                        }
                        className="font-bold text-teal-700 underline decoration-dotted underline-offset-4"
                        aria-label={`Explain ${field.qualifier ?? field.tag}`}
                      >
                        {field.tag}
                        {field.qualifier ? ` / ${field.qualifier}` : ""}
                      </button>
                    </td>
                    <td className="p-3 font-mono">{field.value}</td>
                    <td className="p-3">{field.businessMeaning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {view === "raw" && (
          <div className="space-y-4">
            <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
              Raw editing and parsing cover only fields generated by this demonstration. Content is
              treated as data and is never executed or sent to an AI provider.
            </div>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold">Supported-subset raw message</span>
              <textarea
                value={rawMessage}
                onChange={(event) => {
                  setRawMessage(event.target.value);
                  setRawResult(undefined);
                }}
                rows={22}
                spellCheck={false}
                className="w-full rounded-xl bg-slate-950 p-5 font-mono text-sm leading-6 text-slate-100"
              />
            </label>
            <FieldKnowledgeButtons
              fields={message.fieldMap}
              onSelect={setSelectedKnowledgeId}
              messageType={message.resolvedMessageType}
              label="Verified knowledge for generated raw fields"
            />
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={validateRaw}
                disabled={validatingRaw}
                className="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-60"
              >
                {validatingRaw ? "Validating…" : "Validate raw subset"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setRawMessage(message.rawMessage);
                  setRawResult(undefined);
                  setRawError("");
                }}
                className="rounded-lg border border-slate-300 px-4 py-2 font-semibold"
              >
                Restore generated message
              </button>
            </div>
            {rawError && (
              <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-900">
                {rawError}
              </div>
            )}
            {rawResult && (
              <div
                role="status"
                className={`rounded-lg border p-4 ${
                  rawResult.validation.status === "VALID"
                    ? "border-emerald-300 bg-emerald-50 text-emerald-950"
                    : "border-red-300 bg-red-50 text-red-950"
                }`}
              >
                <p className="font-bold">
                  Raw subset validation: {rawResult.validation.status} · {rawResult.parsedFields.length} fields parsed
                </p>
                {rawResult.validation.findings.length > 0 && (
                  <ul className="mt-3 list-disc space-y-1 pl-5">
                    {rawResult.validation.findings.map((finding) => (
                      <li key={`${finding.ruleId}-${finding.fieldPath ?? "message"}`}>
                        {finding.ruleId}: {finding.message}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-slate-200 bg-slate-50 px-5 py-4 text-sm text-slate-700">
        Profile {message.profileId} version {message.profileVersion} · Validation {message.validation.status}
      </div>
      <TagDetailsDrawer
        key={selectedKnowledgeId}
        knowledgeId={selectedKnowledgeId}
        profileId={message.profileId}
        onClose={() => setSelectedKnowledgeId(undefined)}
      />
    </section>
  );
}

function FieldKnowledgeButtons({
  fields,
  onSelect,
  messageType,
  label,
}: {
  fields: RenderedField[];
  onSelect: (knowledgeId: string) => void;
  messageType: string;
  label: string;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <h3 className="text-sm font-semibold text-slate-700">{label}</h3>
      <div className="mt-3 flex flex-wrap gap-2">
        {fields.map((field, index) => (
          <button
            key={`${field.sequence}-${field.tag}-${field.qualifier}-${index}`}
            type="button"
            onClick={() => onSelect(knowledgeId(messageType, field))}
            className="rounded-full border border-teal-200 bg-white px-3 py-1 font-mono text-sm font-semibold text-teal-800"
            aria-label={`Explain ${field.qualifier ?? field.tag}`}
          >
            {field.tag}{field.qualifier ? ` / ${field.qualifier}` : ""}
          </button>
        ))}
      </div>
    </section>
  );
}

function knowledgeId(messageType: string, field: RenderedField): string {
  return `${messageType}-${field.sequence.replaceAll("/", "-")}-${field.tag}-${field.qualifier ?? "NONE"}`;
}

function BusinessItem({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <dt className="text-sm font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 break-words font-semibold text-slate-900">{value ?? "Not supplied"}</dd>
    </div>
  );
}
