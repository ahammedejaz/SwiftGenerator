"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api-client";
import type { PlatformSession, SecureDraft } from "@/lib/contracts";

interface Connector { connectorId: string; name: string; connectorType: string; environment: string; capability: string; destinationAlias: string; active: boolean }

export function OperationsConsole() {
  const [session, setSession] = useState<PlatformSession>();
  const [identity, setIdentity] = useState("reviewer");
  const [draftId, setDraftId] = useState("");
  const [draft, setDraft] = useState<SecureDraft>();
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [result, setResult] = useState<Record<string, unknown>>();
  const [error, setError] = useState("");

  const refresh = () => Promise.all([
    apiRequest<PlatformSession>("/api/auth/session").then(setSession),
    apiRequest<Connector[]>("/api/connectors").then(setConnectors).catch(() => setConnectors([])),
  ]);
  useEffect(() => { refresh().catch(() => undefined); }, []);
  const login = async () => { await apiRequest("/api/auth/development-login", { method: "POST", body: JSON.stringify({ identity }) }); await refresh(); };
  const load = async () => { setDraft(await apiRequest<SecureDraft>(`/api/messages/drafts/${draftId}`)); };
  const action = async (path: string, body?: object) => {
    setError(""); setResult(undefined);
    try { setResult(await apiRequest<Record<string, unknown>>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined })); await load(); }
    catch (reason) { setError((reason as Error).message); }
  };
  const importEvidence = () => draft && action(`/api/external-validation/results/${draft.draftId}`, { messageChecksum: draft.currentChecksum, providerType: "AUTHORISED_UPLOADED_RESULT", profileId: draft.profileId, standardsRelease: draft.standardsRelease, passed: true, validatedAt: new Date().toISOString(), safeFindings: [] });
  const submit = () => action(`/api/messages/${draftId}/submit`, { connectorId: "MOCK-UAT", idempotencyKey: crypto.randomUUID(), confirmProduction: false });

  return <div className="space-y-6"><section className="rounded-2xl border bg-white p-5"><h2 className="text-lg font-semibold">Development role switch</h2><p className="mt-1 text-sm text-slate-600">Production uses configured OIDC/SAML; this explicit selector exists only in development mode.</p><div className="mt-3 flex flex-wrap gap-3"><select value={identity} onChange={(event) => setIdentity(event.target.value)} className="rounded-lg border p-2">{["author","reviewer","approver","submitter","auditor"].map((item) => <option key={item}>{item}</option>)}</select><button onClick={login} className="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white">Sign in</button></div><p className="mt-3 text-sm"><strong>Current:</strong> {session?.authenticated ? `${session.user?.displayName} · ${session.user?.roles.join(", ")}` : "Not signed in"}</p></section><section className="rounded-2xl border bg-white p-5"><label className="font-semibold">Draft ID<input value={draftId} onChange={(event) => setDraftId(event.target.value)} className="mt-2 block w-full rounded-lg border p-2" /></label><button onClick={load} className="mt-3 rounded-lg border px-4 py-2 font-semibold">Load operational state</button>{draft && <div className="mt-4 grid gap-2 text-sm md:grid-cols-3"><p><strong>Status:</strong> {draft.status}</p><p><strong>Revision:</strong> {draft.revision}</p><p><strong>Checksum:</strong> <span className="break-all">{draft.currentChecksum ?? "Not composed"}</span></p></div>}</section><section className="rounded-2xl border bg-white p-5"><h2 className="text-lg font-semibold">Maker-checker controls</h2><div className="mt-3 flex flex-wrap gap-3"><button onClick={() => action(`/api/messages/${draftId}/review`)} className="rounded-lg border px-4 py-2 font-semibold">Request review (author)</button><button onClick={() => action(`/api/messages/${draftId}/approve`)} className="rounded-lg border px-4 py-2 font-semibold">Approve (approver)</button><button onClick={importEvidence} className="rounded-lg border px-4 py-2 font-semibold">Import passing evidence</button><button onClick={submit} className="rounded-lg bg-slate-900 px-4 py-2 font-semibold text-white">Submit to explicit mock UAT</button></div><p className="mt-3 text-sm text-amber-800">Production submission is disabled by default. The mock UAT connector is test/development-only and never represents a real ACK.</p></section><section className="rounded-2xl border bg-white p-5"><h2 className="text-lg font-semibold">Safe connector registry</h2>{connectors.map((connector) => <p key={connector.connectorId} className="mt-2 rounded-lg bg-slate-50 p-3"><strong>{connector.name}</strong> · {connector.environment} · {connector.capability} · destination alias {connector.destinationAlias}</p>)}</section>{error && <p role="alert" className="rounded-xl bg-red-50 p-4 text-red-800">{error}</p>}{result && <pre className="overflow-auto rounded-2xl bg-slate-950 p-5 text-xs text-slate-100">{JSON.stringify(result, null, 2)}</pre>}</div>;
}
