"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api-client";
import type { EffectiveTagKnowledge } from "@/lib/contracts";

export function TagDetailsDrawer({
  knowledgeId,
  profileId,
  onClose,
}: {
  knowledgeId?: string;
  profileId: string;
  onClose: () => void;
}) {
  const [details, setDetails] = useState<EffectiveTagKnowledge>();
  const [error, setError] = useState("");

  useEffect(() => {
    if (!knowledgeId) return;
    let active = true;
    apiRequest<EffectiveTagKnowledge>(
      `/api/knowledge/tags/${encodeURIComponent(knowledgeId)}?profileId=${encodeURIComponent(profileId)}`,
    )
      .then((result) => {
        if (active) setDetails(result);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Knowledge is unavailable.");
      });
    return () => {
      active = false;
    };
  }, [knowledgeId, profileId]);

  if (!knowledgeId) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/45" role="presentation">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Close tag details"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="tag-details-title"
        className="relative z-10 h-full w-full max-w-2xl overflow-y-auto bg-white p-6 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wider text-teal-700">
              Verified Tag Intelligence
            </p>
            <h2 id="tag-details-title" className="mt-1 text-2xl font-semibold">
              {details?.record.displayName ?? "Loading field knowledge…"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-3 py-2 font-semibold"
          >
            Close
          </button>
        </div>

        {error && (
          <div role="alert" className="mt-5 rounded-xl border border-red-300 bg-red-50 p-4 text-red-900">
            {error}
          </div>
        )}

        {details && (
          <div className="space-y-6 py-6">
            <div className="flex flex-wrap gap-2 text-sm">
              <Badge>{details.record.messageType}</Badge>
              <Badge>Sequence {details.record.sequencePath}</Badge>
              <Badge>
                {details.record.fieldTag}
                {details.record.qualifier ? ` / ${details.record.qualifier}` : ""}
              </Badge>
              <Badge>{details.effectivePresence}</Badge>
            </div>

            <KnowledgeSection title="What it means" text={details.record.businessMeaning} />
            <KnowledgeSection title="Technical meaning" text={details.record.technicalMeaning} />
            <KnowledgeSection title="Why it is used" text={details.record.whyUsed} />
            <KnowledgeSection
              title="When it is required"
              text={
                details.record.conditionExplanation ??
                `This field is ${details.effectivePresence.toLowerCase()} under the selected profile.`
              }
            />
            <KnowledgeSection title="What happens if it is missing" text={details.record.missingImpact} />
            <KnowledgeSection title="Business question" text={details.effectiveBusinessQuestion} />
            <KnowledgeSection title="Technical format" text={details.record.formatExplanation} />
            <KnowledgeSection title="Lifecycle impact" text={details.record.lifecycleImpact} />

            <section>
              <h3 className="font-semibold">Related fields</h3>
              <DependencyTree details={details} />
            </section>

            <section>
              <h3 className="font-semibold">Client-specific rule</h3>
              <p className="mt-2 leading-7 text-slate-700">
                {details.clientExplanation ??
                  `No additional explanation overrides the base rule in ${details.profileId} version ${details.profileVersion}.`}
              </p>
            </section>

            {(details.record.commonMistakes.length > 0 || details.profileCommonMistakes.length > 0) && (
              <section>
                <h3 className="font-semibold">Common mistakes</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">
                  {[...details.record.commonMistakes, ...details.profileCommonMistakes].map((mistake) => (
                    <li key={mistake}>{mistake}</li>
                  ))}
                </ul>
              </section>
            )}

            {details.record.exampleValues.length > 0 && (
              <section className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <h3 className="font-semibold">Synthetic example</h3>
                {details.record.exampleValues.map((example) => (
                  <p key={example.value} className="mt-2 font-mono text-sm">
                    {example.value} — {example.explanation}
                  </p>
                ))}
              </section>
            )}

            <section className="rounded-xl bg-slate-100 p-4 text-sm leading-6">
              <h3 className="font-semibold">Source and version</h3>
              <p className="mt-2">{details.record.source.sourceType}</p>
              <p className="break-all">{details.record.source.sourceReference}</p>
              <p>
                {details.record.source.reviewStatus} · {details.record.standardsRelease} · {details.record.knowledgeVersion}
              </p>
              <p className="mt-2 text-slate-600">
                Concise derived metadata only. No certification claim is made.
              </p>
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}

function KnowledgeSection({ title, text }: { title: string; text: string }) {
  return (
    <section>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-2 leading-7 text-slate-700">{text}</p>
    </section>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-teal-50 px-3 py-1 font-semibold text-teal-800">{children}</span>;
}

function DependencyTree({ details }: { details: EffectiveTagKnowledge }) {
  const groups = [
    ["Depends on", details.record.dependsOn],
    ["Required with", details.record.requiredWith],
    ["Related to", details.record.relatedFields],
    ["Conflicts with", details.record.conflictsWith],
  ] as const;
  const hasDependencies = groups.some(([, values]) => values.length > 0);
  if (!hasDependencies) return <p className="mt-2 text-slate-600">No verified dependencies are configured.</p>;
  return (
    <div className="mt-3 rounded-xl bg-slate-950 p-4 font-mono text-sm text-slate-100">
      <p>{details.record.qualifier ?? details.record.fieldTag}</p>
      {groups.flatMap(([label, values]) =>
        values.map((value, index) => (
          <p key={`${label}-${value}`}>
            {index === values.length - 1 ? "└──" : "├──"} {label}: {value}
          </p>
        )),
      )}
    </div>
  );
}
