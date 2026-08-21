"use client";

import { useEffect, useState } from "react";
import { ProofSheet } from "@/components/studio/ProofSheet";
import {
  Badge,
  Button,
  ErrorNotice,
  Labelled,
  Panel,
  TextArea,
  TextInput,
} from "@/components/studio/ui";
import { StudioError, studioApi } from "@/lib/studio-api";
import type {
  ConversionResponse,
  ConversionTarget,
  ConversionTargetsResponse,
  ElementInput,
  Lane,
  MappingCitation,
  MappingEvidenceClass,
} from "@/lib/studio-types";

const TRANSFER_KEY = "studio-conversion-source";

export function ConvertMessage() {
  const [sourceType, setSourceType] = useState("MT541");
  const [rawMessage, setRawMessage] = useState("");
  const [targets, setTargets] = useState<ConversionTargetsResponse | null>(null);
  const [sourceLane, setSourceLane] = useState<Lane>("CONFIGURED");
  const [sourceRelease, setSourceRelease] = useState<string | null>(null);
  const [selected, setSelected] = useState<ConversionTarget | null>(null);
  const [allowPreview, setAllowPreview] = useState(false);
  const [targetValues, setTargetValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ConversionResponse | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let initialSource = "MT541";
    let initialLane: Lane = "CONFIGURED";
    let initialRelease: string | null = null;
    const transferred = window.sessionStorage.getItem(TRANSFER_KEY);
    if (transferred) {
      try {
        const parsed = JSON.parse(transferred) as {
          messageType?: string;
          rawMessage?: string;
          lane?: Lane;
          release?: string | null;
        };
        if (parsed.messageType) {
          initialSource = parsed.messageType;
          setSourceType(parsed.messageType);
        }
        if (parsed.lane) {
          initialLane = parsed.lane;
          setSourceLane(parsed.lane);
        }
        if (parsed.release !== undefined) {
          initialRelease = parsed.release;
          setSourceRelease(parsed.release);
        }
        if (parsed.rawMessage) setRawMessage(parsed.rawMessage);
      } finally {
        window.sessionStorage.removeItem(TRANSFER_KEY);
      }
    }
    studioApi
      .conversionTargets(initialSource, "MT", { lane: initialLane, release: initialRelease })
      .then((response) => {
        setTargets(response);
        setSelected(response.targets[0] ?? null);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof StudioError ? caught.message : "Conversion targets are unavailable.");
      })
      .finally(() => setBusy(false));
  }, []);

  async function loadTargets(source = sourceType) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await studioApi.conversionTargets(source, "MT", {
        lane: sourceLane,
        release: sourceRelease,
      });
      setTargets(response);
      setSelected(response.targets.find((item) => item.convertible) ?? response.targets[0] ?? null);
    } catch (caught) {
      setError(caught instanceof StudioError ? caught.message : "Conversion targets are unavailable.");
    } finally {
      setBusy(false);
    }
  }

  async function convert() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const supplied: ElementInput[] = Object.entries(targetValues)
        .filter(([, value]) => value.trim())
        .map(([path, value]) => ({ path, value: value.trim() }));
      const response = await studioApi.convert({
        sourceFormat: "MT",
        sourceMessage: sourceType,
        sourceLane,
        sourceRelease,
        rawMessage,
        targetFormat: "MX",
        targetMessage: selected.target.messageType,
        targetVersion: selected.target.release ?? selected.target.messageType,
        // The target's own lane, not the default. Both candidate packs target
        // KNOWLEDGE_PREVIEW, and a request that leaves this out resolves against
        // CONFIGURED and is refused with "No exact Mapping Pack matches this source and
        // target" — after the screen has just listed the pack and had the user tick the
        // preview opt-in, which reads as a dead button rather than as a refusal.
        targetLane: selected.target.lane,
        mappingPackId: selected.packId ?? undefined,
        targetValues: supplied,
        allowSyntheticPreview: allowPreview,
      });
      setResult(response);
    } catch (caught) {
      setError(caught instanceof StudioError ? caught.message : "The conversion was refused.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Panel
        title="Source message"
        description="Paste one MT FIN message or MT text block. Parsing is deterministic and uses the same import path as Create Message."
      >
        <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
          <Labelled label="Source type">
            <div className="flex gap-2">
              <TextInput value={sourceType} onChange={(event) => setSourceType(event.target.value.toUpperCase())} />
              <Button size="sm" onClick={() => void loadTargets()} loading={busy}>Find targets</Button>
            </div>
          </Labelled>
          <Labelled label="Message">
            <TextArea
              value={rawMessage}
              onChange={(event) => setRawMessage(event.target.value)}
              placeholder=":16R:GENL&#10;:20C::SEME//..."
              className="min-h-52"
            />
          </Labelled>
        </div>
      </Panel>

      {targets && (
        <Panel
          title="Target and mapping authority"
          description={targets.authorityNote}
          action={selected ? <Badge tone={selected.productionEligible ? "ok" : "warn"}>{selected.reviewState}</Badge> : undefined}
        >
          {targets.targets.length > 1 && (
            <div className="mb-4 flex flex-wrap gap-2" data-testid="conversion-target-list">
              {targets.targets.map((item) => (
                <button
                  key={`${item.target.messageType}-${item.target.release}-${item.packId ?? "relationship"}`}
                  type="button"
                  onClick={() => setSelected(item)}
                  className={`rounded-md border px-3 py-1.5 font-mono text-xs ${selected === item ? "border-accent bg-accent/10 text-ink" : "border-line text-ink-2 hover:border-ink-3"}`}
                >
                  {item.target.release ?? item.target.messageType} · {item.evidenceClass.replace(/_/g, " ").toLowerCase()}
                </button>
              ))}
            </div>
          )}
          {selected ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="font-mono font-semibold">{selected.target.release}</p>
                  <p className="mt-1 text-sm text-ink-2">
                    {selected.packId
                      ? `Mapping Pack ${selected.packId} · ${selected.packVersion}`
                      : "No Mapping Pack — the relationship is recorded, the field mapping is not."}
                  </p>
                  <p className="mt-1 text-xs text-ink-3" data-testid="evidence-class">
                    Evidence: {evidenceLabel(selected.evidenceClass)}
                  </p>
                </div>
                {selected.convertible && selected.previewOnly && (
                  <label className="flex max-w-[48ch] cursor-pointer items-start gap-2 text-sm text-ink-2">
                    <input
                      type="checkbox"
                      checked={allowPreview}
                      onChange={(event) => setAllowPreview(event.target.checked)}
                      className="mt-1 h-4 w-4 accent-accent"
                    />
                    <span>
                      {selected.reviewState === "CANDIDATE_PREVIEW"
                        ? "Run the candidate preview. I understand this is a candidate drawn from cited definitions, not an authoritative business mapping."
                        : "Run the synthetic test preview. I understand this is not an authoritative business mapping."}
                    </span>
                  </label>
                )}
              </div>
              {selected.relationship && (
                <p className="text-sm leading-6 text-ink-2">{selected.relationship.statement}</p>
              )}
              <Citations
                citations={selected.provenance?.relationshipCitations ?? selected.relationship?.citations ?? []}
              />
              {selected.relationship?.blocker && (
                <p className="text-sm text-ink-2">
                  Not convertible: <span className="font-mono">{selected.relationship.blocker}</span>
                </p>
              )}
              {selected.provenance && (
                <ul className="border-t border-line pt-3 text-sm leading-6 text-ink-2">
                  {selected.provenance.limitations.map((item) => <li key={item}>{item}</li>)}
                </ul>
              )}
            </div>
          ) : (
            <p className="text-sm text-ink-2">No Mapping Pack and no recorded relationship exists for this source.</p>
          )}
        </Panel>
      )}

      {error && <ErrorNotice message={error} />}

      <div className="flex justify-end">
        <Button
          variant="primary"
          size="lg"
          iconAfter="arrow-right"
          disabled={!rawMessage.trim() || !selected || !selected.convertible}
          loading={busy}
          onClick={() => void convert()}
        >
          Preview conversion
        </Button>
      </div>

      {result && (
        <ConversionResult
          result={result}
          values={targetValues}
          onValue={(path, value) => setTargetValues((current) => ({ ...current, [path]: value }))}
          onRetry={() => void convert()}
          busy={busy}
        />
      )}
    </div>
  );
}

function ConversionResult({
  result,
  values,
  onValue,
  onRetry,
  busy,
}: {
  result: ConversionResponse;
  values: Record<string, string>;
  onValue: (path: string, value: string) => void;
  onRetry: () => void;
  busy: boolean;
}) {
  const report = result.report;
  if (!report) {
    return <ErrorNotice message={result.message} />;
  }
  return (
    <div className="space-y-6">
      <Panel
        title="Conversion report"
        description={result.message}
        action={<Badge tone={result.status === "READY" ? "ok" : result.status === "NEEDS_INPUT" ? "warn" : "bad"}>{result.status.replace(/_/g, " ")}</Badge>}
        bodyClassName="px-0 py-0"
      >
        <dl className="grid sm:grid-cols-2 lg:grid-cols-4">
          <ReportFact label="Mapped" value={report.mappedTargetFields.length} />
          <ReportFact label="Derived" value={report.derivedTargetFields.length} />
          <ReportFact label="Missing" value={report.targetRequiredMissing.length} />
          <ReportFact label="Not represented" value={report.sourceFieldsNotRepresented.length} />
        </dl>
        <div className="border-t border-line px-5 py-4 text-sm text-ink-2" data-testid="conversion-coverage">
          <p>
            Evidence: <span className="font-medium text-ink">{evidenceLabel(report.evidenceClass)}</span>
            {" · "}review state <span className="font-mono">{report.provenance.reviewState}</span>
          </p>
          {report.coverage && (
            <p className="mt-1">
              Business mapping coverage: {report.coverage.mandatoryTargetMapped}/{report.coverage.mandatoryTargetTotal} mandatory target
              elements established by the mapping · {report.coverage.sourceRowsRepresented}/{report.coverage.sourceRowsTotal} source rows
              represented · {report.coverage.rulesCited}/{report.coverage.rulesTotal} rules cite a knowledge-base source.
            </p>
          )}
          {report.targetRequiredMissing.length > 0 && (
            <p className="mt-1">
              {report.targetRequiredMissing.length} field{report.targetRequiredMissing.length === 1 ? "" : "s"} need additional information before MX can be generated.
            </p>
          )}
        </div>
        {report.sourceFieldsNotRepresented.length > 0 && (
          <div className="border-t border-line px-5 py-4">
            <p className="text-xs font-semibold uppercase text-ink-3">Source fields not represented</p>
            <p className="mt-1 break-words font-mono text-xs leading-5 text-ink-2">{report.sourceFieldsNotRepresented.join(", ")}</p>
          </div>
        )}
      </Panel>

      {report.targetRequiredMissing.length > 0 && (
        <Panel title="Required target information" description="Supply these values before the target can be generated. The converter will not infer them.">
          <div className="space-y-4">
            {report.targetRequiredMissing.map((missing) => (
              <Labelled key={missing.fieldId} label={missing.displayName} hint={missing.question}>
                <TextInput value={values[missing.fieldId] ?? ""} onChange={(event) => onValue(missing.fieldId, event.target.value)} />
              </Labelled>
            ))}
            <div className="flex justify-end">
              <Button variant="primary" loading={busy} onClick={onRetry}>Generate target</Button>
            </div>
          </div>
        </Panel>
      )}

      <Panel title="Canonical target preview" description="Every proposed target value and whether it was mapped, transformed, or supplied by you." bodyClassName="px-0 py-0">
        <div className="scroll-slim overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-[0.8125rem]">
            <thead className="bg-rail text-xs uppercase text-ink-3"><tr><th className="px-4 py-2.5">Target field</th><th className="px-4 py-2.5">Value</th><th className="px-4 py-2.5">Source</th></tr></thead>
            <tbody className="divide-y divide-line">
              {result.targetValues.map((item) => (
                <tr key={`${item.path}-${item.occurrence ?? 1}`}>
                  <td className="max-w-[38rem] break-all px-4 py-3 font-mono text-xs">{item.path}</td>
                  <td className="px-4 py-3 font-mono">{item.value}</td>
                  <td className="px-4 py-3">{report.userSuppliedTargetFields.includes(item.path) ? "You supplied" : report.derivedTargetFields.includes(item.path) ? "Derived" : "Mapped"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {result.generation && <ProofSheet result={result.generation} />}
    </div>
  );
}

function ReportFact({ label, value }: { label: string; value: number }) {
  return <div className="border-b border-line px-5 py-4 sm:border-r"><dt className="text-xs uppercase text-ink-3">{label}</dt><dd className="tnum mt-1 text-xl font-semibold">{value}</dd></div>;
}

export function storeConversionSource(
  messageType: string,
  rawMessage: string,
  source?: { lane?: Lane; release?: string | null },
) {
  window.sessionStorage.setItem(
    TRANSFER_KEY,
    JSON.stringify({ messageType, rawMessage, lane: source?.lane, release: source?.release ?? null }),
  );
}

function evidenceLabel(value: MappingEvidenceClass): string {
  switch (value) {
    case "SOURCE_BACKED":
      return "source-backed — relationship and every rule cite a knowledge-base document";
    case "TARGET_RELATIONSHIP_ONLY":
      return "target relationship only — a guide names the ISO 20022 family; the field rules are candidates";
    case "NAME_CORRESPONDENCE":
      return "name correspondence — the two documents' titles correspond; nothing relates them";
    default:
      return "synthetic — a repository fixture, not a standards document";
  }
}

function Citations({ citations }: { citations: MappingCitation[] }) {
  if (citations.length === 0) return null;
  return (
    <ul className="space-y-1 text-xs text-ink-2" data-testid="mapping-citations">
      {citations.map((cite, index) => (
        <li key={`${cite.sourceId}-${cite.page ?? index}`}>
          <span className="font-mono">{cite.sourceId}</span>
          {cite.page ? ` · page ${cite.page}` : ""}
          {cite.section ? ` · ${cite.section}` : ""}
          {cite.note ? ` — ${cite.note}` : ""}
        </li>
      ))}
    </ul>
  );
}
