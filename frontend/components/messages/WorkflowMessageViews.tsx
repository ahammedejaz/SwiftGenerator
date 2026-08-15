"use client";

import { useState } from "react";
import type { WorkflowGeneratedMessage } from "@/lib/contracts";
import { TagDetailsDrawer } from "@/components/knowledge/TagDetailsDrawer";

export function WorkflowMessageViews({ message }: { message: WorkflowGeneratedMessage }) {
  const [view, setView] = useState<"business" | "tags" | "raw">("business");
  const [knowledgeId, setKnowledgeId] = useState<string>();
  return (
    <section className="overflow-hidden rounded-2xl border bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b p-5">
        <div>
          <p className="text-sm font-semibold text-teal-700">{message.workflowModule}</p>
          <h2 className="text-2xl font-semibold">{message.resolvedMessageType}</h2>
        </div>
        <div className="flex rounded-lg bg-slate-100 p-1" role="tablist">
          {(["business", "tags", "raw"] as const).map((item) => (
            <button key={item} type="button" role="tab" aria-selected={view === item} onClick={() => setView(item)} className={`rounded-md px-3 py-2 text-sm font-semibold capitalize ${view === item ? "bg-white text-teal-800 shadow-sm" : "text-slate-600"}`}>
              {item === "tags" ? "Tag View" : `${item} View`}
            </button>
          ))}
        </div>
      </div>
      <div className="p-5">
        {view === "business" && (
          <pre className="max-h-96 overflow-auto rounded-xl bg-slate-50 p-4 text-sm">{JSON.stringify(message.canonicalData, null, 2)}</pre>
        )}
        {view === "tags" && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr className="border-b"><th className="p-3">Sequence</th><th className="p-3">Tag</th><th className="p-3">Value</th><th className="p-3">Meaning</th></tr></thead>
              <tbody>{message.fieldMap.map((field, index) => (
                <tr className="border-b" key={`${field.sequence}-${field.tag}-${field.qualifier}-${index}`}>
                  <td className="p-3">{field.sequence}</td>
                  <td className="p-3"><button type="button" className="font-mono font-bold text-teal-700 underline decoration-dotted" onClick={() => setKnowledgeId(`${message.resolvedMessageType}-${field.sequence}-${field.tag}-${field.qualifier ?? "NONE"}`)} aria-label={`Explain ${field.qualifier ?? field.tag}`}>{field.tag}{field.qualifier ? ` / ${field.qualifier}` : ""}</button></td>
                  <td className="p-3 font-mono">{field.value}</td><td className="p-3">{field.businessMeaning}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {view === "raw" && <pre className="overflow-x-auto rounded-xl bg-slate-950 p-5 text-sm leading-6 text-slate-100">{message.rawMessage}</pre>}
      </div>
      <div className="border-t bg-slate-50 p-4 text-sm">Profile {message.profileId} {message.profileVersion} · {message.validation.status}</div>
      <TagDetailsDrawer key={knowledgeId} knowledgeId={knowledgeId} profileId={message.profileId} onClose={() => setKnowledgeId(undefined)} />
    </section>
  );
}
