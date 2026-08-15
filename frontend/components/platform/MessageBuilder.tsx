"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiRequest, apiUrl } from "@/lib/api-client";
import type {
  MessageCatalogue,
  MessageSpecification,
  MessageType,
  PlatformSession,
  SampleSummary,
  SecureComposition,
  SecureDraft,
} from "@/lib/contracts";

const PROFILES = ["BASE_DEMO_V1", "BFS_CLIENT_DEMO_V1"];

export function MessageBuilder({ initialMessageType }: { initialMessageType?: string }) {
  const [session, setSession] = useState<PlatformSession>();
  const [catalogue, setCatalogue] = useState<MessageCatalogue>();
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [messageType, setMessageType] = useState<MessageType>((initialMessageType as MessageType) || "MT541");
  const [profileId, setProfileId] = useState(PROFILES[0]);
  const [specification, setSpecification] = useState<MessageSpecification>();
  const [draft, setDraft] = useState<SecureDraft>();
  const [composition, setComposition] = useState<SecureComposition>();
  const [values, setValues] = useState<Record<string, string>>({});
  const [parentChoices, setParentChoices] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refreshSession = () => apiRequest<PlatformSession>("/api/auth/session").then(setSession);
  useEffect(() => {
    Promise.all([
      refreshSession(),
      apiRequest<MessageCatalogue>("/api/specifications/messages").then(setCatalogue),
      apiRequest<SampleSummary[]>("/api/knowledge/samples").then(setSamples),
    ]).catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    apiRequest<MessageSpecification>(`/api/specifications/messages/${messageType}`)
      .then(setSpecification)
      .catch((reason: Error) => setError(reason.message));
  }, [messageType]);

  const acceptDraft = (next: SecureDraft) => {
    setDraft(next);
    setValues(
      Object.fromEntries(
        next.fields.map((field) => [`${field.sequenceId}:${field.rowId}`, field.value]),
      ),
    );
  };

  const login = async () => {
    setError("");
    await apiRequest<PlatformSession>("/api/auth/development-login", {
      method: "POST",
      body: JSON.stringify({ identity: "author" }),
    });
    await refreshSession();
  };

  const create = async () => {
    setBusy(true); setError(""); setComposition(undefined);
    try {
      acceptDraft(await apiRequest<SecureDraft>("/api/messages/drafts", {
        method: "POST",
        body: JSON.stringify({ messageType, profileId }),
      }));
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  };

  const loadSample = async () => {
    const sample = samples.find((item) => item.messageType === messageType);
    if (!sample) return;
    setBusy(true); setError(""); setComposition(undefined);
    try {
      acceptDraft(await apiRequest<SecureDraft>(`/api/knowledge/samples/${sample.sampleId}/load`, { method: "POST" }));
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  };

  const applyProfile = async () => {
    if (!draft) return;
    setBusy(true); setError(""); setComposition(undefined);
    try {
      acceptDraft(await apiRequest<SecureDraft>(`/api/messages/drafts/${draft.draftId}`, {
        method: "PATCH", body: JSON.stringify({ profileId }),
      }));
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  };

  const sequenceByPath = useMemo(() => {
    const result: Record<string, SecureDraft["sequences"]> = {};
    for (const sequence of draft?.sequences ?? []) {
      (result[sequence.sequencePath] ??= []).push(sequence);
    }
    return result;
  }, [draft]);

  const saveField = async (rowId: string, sequenceId: string) => {
    const valueKey = `${sequenceId}:${rowId}`;
    if (!draft || !values[valueKey]) return;
    setBusy(true); setError("");
    try {
      acceptDraft(await apiRequest<SecureDraft>(`/api/messages/drafts/${draft.draftId}/fields`, {
        method: "POST",
        body: JSON.stringify({ rowId, sequenceId, value: values[valueKey], source: "USER_ENTERED", confirmed: true }),
      }));
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  };

  const addSequence = async (path: string, parentPath?: string) => {
    if (!draft) return;
    const parentSequenceId = parentPath
      ? parentChoices[path] ?? sequenceByPath[parentPath]?.[0]?.sequenceId
      : undefined;
    acceptDraft(await apiRequest<SecureDraft>(`/api/messages/drafts/${draft.draftId}/sequences`, {
      method: "POST", body: JSON.stringify({ sequencePath: path, parentSequenceId }),
    }));
  };

  const removeSequence = async (sequenceId: string) => {
    if (!draft) return;
    acceptDraft(await apiRequest<SecureDraft>(`/api/messages/drafts/${draft.draftId}/sequences/${sequenceId}`, { method: "DELETE" }));
  };

  const removeField = async (fieldId: string) => {
    if (!draft) return;
    acceptDraft(await apiRequest<SecureDraft>(`/api/messages/drafts/${draft.draftId}/fields/${fieldId}`, { method: "DELETE" }));
  };

  const compose = async () => {
    if (!draft) return;
    setBusy(true); setError("");
    try {
      const result = await apiRequest<SecureComposition>(`/api/messages/${draft.draftId}/compose`, { method: "POST" });
      setComposition(result);
      acceptDraft(await apiRequest<SecureDraft>(`/api/messages/drafts/${draft.draftId}`));
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  };

  if (!session?.authenticated) return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-xl font-semibold">Authentication required</h2>
      <p className="mt-2 text-slate-600">Development login is explicit and unavailable in production OIDC/SAML mode.</p>
      <button onClick={login} className="mt-4 rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white">Sign in as development author</button>
      {error && <p role="alert" className="mt-3 text-red-700">{error}</p>}
    </section>
  );

  return (
    <div className="space-y-6">
      <section className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-6 md:grid-cols-4">
        <label className="font-semibold">Message type<select value={messageType} onChange={(event) => { setMessageType(event.target.value as MessageType); setDraft(undefined); }} className="mt-2 w-full rounded-lg border p-2 font-normal">{catalogue?.supported.map((item) => <option key={item.messageType}>{item.messageType}</option>)}</select></label>
        <label className="font-semibold">Client profile<select value={profileId} onChange={(event) => setProfileId(event.target.value)} className="mt-2 w-full rounded-lg border p-2 font-normal">{PROFILES.map((item) => <option key={item}>{item}</option>)}</select></label>
        <button disabled={busy} onClick={create} className="self-end rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-50">Create empty draft</button>
        <button disabled={busy} onClick={loadSample} className="self-end rounded-lg border border-teal-700 px-4 py-2 font-semibold text-teal-800">Load synthetic sample</button>
        {draft && draft.profileId !== profileId && <button disabled={busy} onClick={applyProfile} className="rounded-lg border border-amber-600 px-4 py-2 font-semibold text-amber-900">Apply profile to draft</button>}
      </section>
      <p className="rounded-xl bg-slate-100 p-4 text-sm"><strong>Session:</strong> {session.user?.displayName} · {session.user?.tenantId} · {session.user?.roles.join(", ")}</p>
      {error && <p role="alert" className="rounded-xl bg-red-50 p-4 text-red-800">{error}</p>}
      {draft && specification && (
        <>
          <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm">
            <strong>{draft.messageType} · {draft.capability}</strong> · revision {draft.revision} · {draft.status}. Actual values are encrypted server-side. Sample values are never inserted unless “Load synthetic sample” is selected.
          </section>
          <div className="space-y-5">
            {specification.sequences.map((sequence) => (
              <section key={sequence.path} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-lg font-semibold">Sequence {sequence.path} · {sequence.code}</h2>
                  {sequence.maxOccurs > 1 && <div className="flex gap-2">{sequence.parentPath && <select aria-label={`Parent for sequence ${sequence.path}`} value={parentChoices[sequence.path] ?? sequenceByPath[sequence.parentPath]?.[0]?.sequenceId ?? ""} onChange={(event) => setParentChoices({ ...parentChoices, [sequence.path]: event.target.value })} className="rounded-lg border px-2 text-sm">{(sequenceByPath[sequence.parentPath] ?? []).map((parent) => <option key={parent.sequenceId} value={parent.sequenceId}>Parent {sequence.parentPath} #{parent.occurrence}</option>)}</select>}<button onClick={() => addSequence(sequence.path, sequence.parentPath)} className="rounded-lg border px-3 py-1 text-sm font-semibold">Add repeat</button></div>}
                </div>
                <p className="mt-1 text-sm text-slate-500">Occurrences {sequence.minOccurs}..{sequence.maxOccurs}; active {sequenceByPath[sequence.path]?.length ?? 0}</p>
                {(sequenceByPath[sequence.path] ?? []).map((instance) => (
                  <div key={instance.sequenceId} className="mt-5 border-t border-slate-200 pt-4">
                    <div className="flex items-center justify-between"><p className="text-sm font-semibold text-slate-500">Occurrence {instance.occurrence}</p>{(sequenceByPath[sequence.path]?.length ?? 0) > sequence.minOccurs && <button onClick={() => removeSequence(instance.sequenceId)} className="text-sm font-semibold text-red-700 underline">Remove occurrence</button>}</div>
                    <div className="mt-3 grid gap-4 lg:grid-cols-2">
                      {specification.fields.filter((field) => field.sequencePath === sequence.path).map((field) => (
                        <div key={`${instance.sequenceId}-${field.rowId}`} className="rounded-xl bg-slate-50 p-4">
                          <div className="flex items-start justify-between gap-3"><label className="font-semibold" htmlFor={`${instance.sequenceId}-${field.rowId}`}>{field.businessName}<span className="ml-2 text-xs text-slate-500">{field.tag}{field.qualifier ? `/${field.qualifier}` : ""} · {field.presence}</span></label><Link className="text-sm font-semibold text-teal-800 underline" href={`/knowledge?tag=${field.tag}&messageType=${messageType}`}>Why?</Link></div>
                          <p className="mt-1 text-xs text-slate-500">{field.format}</p>
                          {field.allowedCodes.length > 0 ? <select id={`${instance.sequenceId}-${field.rowId}`} value={values[`${instance.sequenceId}:${field.rowId}`] ?? ""} onChange={(event) => setValues({ ...values, [`${instance.sequenceId}:${field.rowId}`]: event.target.value })} className="mt-2 w-full rounded-lg border bg-white p-2"><option value="">Select…</option>{field.allowedCodes.map((code) => <option key={code}>{code}</option>)}</select> : <input id={`${instance.sequenceId}-${field.rowId}`} value={values[`${instance.sequenceId}:${field.rowId}`] ?? ""} onChange={(event) => setValues({ ...values, [`${instance.sequenceId}:${field.rowId}`]: event.target.value })} className="mt-2 w-full rounded-lg border bg-white p-2" autoComplete="off" />}
                          {draft.fields.find((item) => item.sequenceId === instance.sequenceId && item.rowId === field.rowId) && <p className="mt-2 text-xs font-semibold text-slate-600">Source: {draft.fields.find((item) => item.sequenceId === instance.sequenceId && item.rowId === field.rowId)!.source} · {draft.fields.find((item) => item.sequenceId === instance.sequenceId && item.rowId === field.rowId)!.confirmed ? "confirmed" : "confirmation required"}</p>}
                          <div className="mt-2 flex gap-2"><button disabled={busy || !values[`${instance.sequenceId}:${field.rowId}`]} onClick={() => saveField(field.rowId, instance.sequenceId)} className="rounded-md bg-slate-800 px-3 py-1 text-sm font-semibold text-white disabled:opacity-40">Save field</button>{draft.fields.find((item) => item.sequenceId === instance.sequenceId && item.rowId === field.rowId) && field.presence !== "MANDATORY" && <button onClick={() => removeField(draft.fields.find((item) => item.sequenceId === instance.sequenceId && item.rowId === field.rowId)!.fieldId)} className="rounded-md border border-red-300 px-3 py-1 text-sm font-semibold text-red-700">Remove optional field</button>}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </section>
            ))}
          </div>
          <section className="flex flex-wrap gap-3 rounded-2xl bg-slate-900 p-5 text-white">
            <button disabled={busy} onClick={compose} className="rounded-lg bg-teal-400 px-4 py-2 font-semibold text-slate-950">Compose and validate</button>
            {composition && <a className="rounded-lg border border-white px-4 py-2 font-semibold" href={apiUrl(`/api/messages/${draft.draftId}/downloads/block4`)}>Download Block 4</a>}
            {composition && <a className="rounded-lg border border-white px-4 py-2 font-semibold" href={apiUrl(`/api/messages/${draft.draftId}/downloads/evidence-zip`)}>Download evidence ZIP</a>}
          </section>
        </>
      )}
      {composition && <section className="grid gap-5 lg:grid-cols-2"><div className="rounded-2xl border bg-white p-5"><h2 className="text-lg font-semibold">Separated validation levels</h2><dl className="mt-3 space-y-2">{Object.entries(composition.validationLevels).map(([key, value]) => <div key={key} className="flex justify-between gap-4 border-b py-1"><dt>{key}</dt><dd className="font-semibold">{value}</dd></div>)}</dl>{composition.findings.map((item) => <p key={item} className="mt-2 text-red-700">{item}</p>)}</div><div className="rounded-2xl bg-slate-950 p-5 text-slate-100"><h2 className="font-semibold">Deterministic Block 4</h2><pre className="mt-3 overflow-auto whitespace-pre-wrap text-xs">{composition.block4}</pre><p className="mt-3 break-all text-xs text-slate-400">SHA-256 {composition.checksum}</p></div></section>}
    </div>
  );
}
