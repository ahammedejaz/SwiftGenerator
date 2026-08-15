"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiRequest } from "@/lib/api-client";
import type {
  EffectiveTagKnowledge,
  KnowledgeMessageSummary,
  KnowledgeSearchResponse,
  MessageType,
} from "@/lib/contracts";
import { TagDetailsDrawer } from "./TagDetailsDrawer";

export function KnowledgeCentre() {
  const [messages, setMessages] = useState<KnowledgeMessageSummary[]>([]);
  const [selectedMessage, setSelectedMessage] = useState<MessageType>("MT541");
  const [records, setRecords] = useState<EffectiveTagKnowledge[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest<KnowledgeMessageSummary[]>("/api/knowledge/messages")
      .then(setMessages)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Knowledge could not be loaded."));
  }, []);

  useEffect(() => {
    apiRequest<EffectiveTagKnowledge[]>(`/api/knowledge/messages/${selectedMessage}`)
      .then(setRecords)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Message knowledge could not be loaded."));
  }, [selectedMessage]);

  async function search(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    try {
      const response = await apiRequest<KnowledgeSearchResponse>(
        `/api/knowledge/search?q=${encodeURIComponent(query.trim())}`,
      );
      setRecords(response.results);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Search failed.");
    }
  }

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <aside className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="font-semibold">Workflow modules</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Verified settlement knowledge is active. New modules appear only after their bounded rule packs are enabled.
          </p>
          <div className="mt-5 space-y-2">
            {messages.map((message) => (
              <button
                key={message.messageType}
                type="button"
                onClick={() => {
                  setError("");
                  setRecords([]);
                  setSelectedMessage(message.messageType);
                }}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left ${
                  selectedMessage === message.messageType
                    ? "bg-teal-700 text-white"
                    : "bg-slate-100 text-slate-800"
                }`}
              >
                <span className="font-semibold">{message.messageType}</span>
                <span className="text-xs">{message.recordCount} fields</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wider text-teal-700">Tag Intelligence Centre</p>
              <h2 className="mt-1 text-2xl font-semibold">{selectedMessage} knowledge</h2>
            </div>
            <form onSubmit={search} className="flex gap-2">
              <label>
                <span className="sr-only">Search verified tag knowledge</span>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search PSET, account, date…"
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <button type="submit" className="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white">
                Search
              </button>
            </form>
          </div>

          {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-red-900">{error}</p>}

          <div className="mt-6 overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b text-slate-600">
                  <th className="p-3">Sequence</th>
                  <th className="p-3">Tag / qualifier</th>
                  <th className="p-3">Business meaning</th>
                  <th className="p-3">Presence</th>
                  <th className="p-3">Source</th>
                </tr>
              </thead>
              <tbody>
                {records.map((item) => (
                  <tr key={item.record.knowledgeId} className="border-b align-top">
                    <td className="p-3 font-medium">{item.record.sequencePath}</td>
                    <td className="p-3">
                      <button
                        type="button"
                        onClick={() => setSelectedId(item.record.knowledgeId)}
                        className="font-mono font-bold text-teal-700 underline decoration-dotted underline-offset-4"
                      >
                        {item.record.fieldTag}{item.record.qualifier ? ` / ${item.record.qualifier}` : ""}
                      </button>
                    </td>
                    <td className="max-w-xl p-3 leading-6">{item.record.businessMeaning}</td>
                    <td className="p-3">{item.effectivePresence}</td>
                    <td className="p-3 text-xs">{item.record.source.reviewStatus}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      <TagDetailsDrawer
        key={selectedId}
        knowledgeId={selectedId}
        profileId="BASE_DEMO_V1"
        onClose={() => setSelectedId(undefined)}
      />
    </>
  );
}
