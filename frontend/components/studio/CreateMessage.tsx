"use client";

/**
 * Create Message — the front door.
 *
 * A linear wizard: format, business area, message, how you want to enter data, the data
 * itself, then the result. One decision at a time, each with enough plain-English context
 * that a tester who has never seen ISO 15022 can make it.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/studio/Icon";
import {
  FieldEditor,
  type FieldValues,
  collapseChoices,
  fieldAddress,
  parseSlot,
  slotKey,
} from "@/components/studio/FieldEditor";
import { EnvelopeTable, ProofSheet } from "@/components/studio/ProofSheet";
import { MessageDiffPanel } from "@/components/studio/MessageDiff";
import { ValidationPanel } from "@/components/studio/ValidationPanel";
import {
  Badge,
  Button,
  ErrorNotice,
  FormatBadge,
  Labelled,
  Panel,
  Select,
  Skeleton,
  TextArea,
  TextInput,
  cx,
} from "@/components/studio/ui";
import { StudioError, studioApi } from "@/lib/studio-api";
import type {
  BusinessArea,
  CatalogueEntry,
  ElementInput,
  FieldInput,
  GenerateRequest,
  GenerateResult,
  ImportResult,
  MessageDiff,
  MessageFormat,
  MessageSpec,
  SampleMessage,
  SpecField,
  StudioCatalogue,
} from "@/lib/studio-types";

type InputMode = "GUIDED" | "EXPERT" | "SAMPLE";

const STEPS = [
  { id: 1, label: "Format" },
  { id: 2, label: "Business area" },
  { id: 3, label: "Message" },
  { id: 4, label: "How to enter data" },
  { id: 5, label: "Enter data" },
  { id: 6, label: "Generate" },
] as const;

export function CreateMessage() {
  const [catalogue, setCatalogue] = useState<StudioCatalogue | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [step, setStep] = useState(1);

  const [format, setFormat] = useState<MessageFormat | null>(null);
  const [area, setArea] = useState<BusinessArea | null>(null);
  const [messageType, setMessageType] = useState<string | null>(null);
  const [mode, setMode] = useState<InputMode>("GUIDED");
  const [profileId, setProfileId] = useState("BASE_DEMO_V1");
  const [scenarioId, setScenarioId] = useState("");

  const [spec, setSpec] = useState<MessageSpec | null>(null);
  const [samples, setSamples] = useState<SampleMessage[]>([]);
  const [specLoading, setSpecLoading] = useState(false);

  const [values, setValues] = useState<FieldValues>({});
  // Which sample the current values came from, so the form can say so and stop saying it
  // once the tester starts editing. Marking is presentational: the values themselves are
  // ordinary user-entered values and are generated through exactly the same path.
  const [sampleOrigin, setSampleOrigin] = useState<SampleMessage | null>(null);
  const [occurrences, setOccurrences] = useState<Record<string, number>>({});
  const [revealed, setRevealed] = useState<Set<string>>(new Set());

  const [result, setResult] = useState<GenerateResult | null>(null);
  const [imported, setImported] = useState<ImportResult | null>(null);
  // The text the tester actually pasted, kept so the regenerated message can be compared
  // with it. The server re-reads it to work out which values were edited, so this is the
  // only thing the browser has to remember.
  const [importedText, setImportedText] = useState<string | null>(null);
  const [diff, setDiff] = useState<MessageDiff | null>(null);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [focusedLocation, setFocusedLocation] = useState<string | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  /* ------------------------------------------------------------ catalogue */

  // A token rather than a callback, so the effect owns the fetch and "Try again" is just
  // a state change rather than a second code path.
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    studioApi
      .catalogue()
      .then((data) => {
        setCatalogue(data);
        setProfileId(data.defaultProfileId);
        setLoadError(null);
      })
      .catch((error: unknown) =>
        setLoadError(
          error instanceof StudioError ? error.message : "The catalogue could not be loaded.",
        ),
      );
  }, [reloadToken]);

  /* --------------------------------------------------- specification load */

  // Which (format, message) the loaded spec belongs to. Importing sets this before it
  // sets the spec, so the effect below knows the work is already done and does not clear
  // the values the import just placed.
  const loadedKey = useRef<string | null>(null);

  useEffect(() => {
    if (!format || !messageType) return;
    if (loadedKey.current === `${format}:${messageType}`) return;
    let cancelled = false;
    void (async () => {
      setSpecLoading(true);
      setSpec(null);
      try {
        const [loadedSpec, loadedSamples] = await Promise.all([
          studioApi.spec(format, messageType),
          studioApi.samples(format, messageType),
        ]);
        if (cancelled) return;
        loadedKey.current = `${format}:${messageType}`;
        setSpec(loadedSpec);
        setSamples(loadedSamples);
        // Start with a clean sheet: previous values belong to a different message.
        setValues({});
        setRevealed(new Set());
        setOccurrences({});
        setResult(null);
      } catch (error) {
        if (cancelled) return;
        setActionError(
          error instanceof StudioError
            ? error.message
            : "The message specification could not be loaded.",
        );
      } finally {
        if (!cancelled) setSpecLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [format, messageType]);

  /* ----------------------------------------------------------- derivation */

  const entries = useMemo(() => catalogue?.messages ?? [], [catalogue]);
  const areasForFormat = useMemo(
    () => catalogue?.formats.find((item) => item.id === format)?.businessAreas ?? [],
    [catalogue, format],
  );
  const messagesForArea = useMemo(
    () => entries.filter((item) => item.format === format && item.businessArea === area),
    [entries, format, area],
  );
  const selected = useMemo(
    () => entries.find((item) => item.format === format && item.messageType === messageType),
    [entries, format, messageType],
  );

  const filledKeys = useMemo(
    () =>
      new Set(
        Object.entries(values)
          .filter(([, value]) => value.trim())
          .map(([key]) => parseSlot(key).fieldId),
      ),
    [values],
  );
  // Counted per business value rather than per field option: a settlement party offered as
  // a BIC and as a proprietary identifier is one thing to fill in, and counting both made
  // a complete message report "10 of 11".
  const requiredFields = useMemo(
    () =>
      collapseChoices(spec?.fields ?? []).filter((row) => row.presence === "MANDATORY"),
    [spec],
  );
  const requiredFilled = requiredFields.filter((row) =>
    row.options.some((option) => filledKeys.has(option.id)),
  ).length;
  const anyFilled = filledKeys.size > 0;

  const invalidLocations = useMemo(() => {
    const set = new Set<string>();
    for (const issue of result?.validation.errors ?? []) {
      if (issue.location) set.add(issue.location);
    }
    return set;
  }, [result]);

  /* -------------------------------------------------------------- actions */

  function updateValue(key: string, value: string) {
    setSampleOrigin(null);
    setValues((current) => ({ ...current, [key]: value }));
  }

  function selectFormat(next: MessageFormat) {
    setImported(null);
    setImportedText(null);
    setDiff(null);
    setDiffError(null);
    setFormat(next);
    setArea(null);
    setMessageType(null);
    setSpec(null);
    setResult(null);
    setStep(2);
  }

  function selectArea(next: BusinessArea) {
    setArea(next);
    setMessageType(null);
    setSpec(null);
    setResult(null);
    setStep(3);
  }

  function selectMessage(next: string) {
    setMessageType(next);
    setScenarioId((current) => current || `TC-${next.replace(/\./g, "")}-001`);
    setStep(4);
  }

  function chooseMode(next: InputMode) {
    setMode(next);
    if (next === "EXPERT" && spec) {
      // Expert mode reveals every optional field at once.
      setRevealed(new Set(spec.fields.map((field) => field.id)));
    }
    if (next === "GUIDED") {
      // Guided shows fewer fields, but never fewer *values*. An optional field holding a
      // value stays visible, because clearing `revealed` used to leave the value in state
      // and in the generated message while removing it from the screen — kept, submitted
      // and unreviewable.
      setRevealed((current) => {
        const kept = new Set<string>();
        for (const key of current) if (key.startsWith("info:")) kept.add(key);
        for (const key of Object.keys(values)) {
          if (values[key]?.trim()) kept.add(parseSlot(key).fieldId);
        }
        return kept;
      });
    }
    setStep(5);
  }

  function applySample(sample: SampleMessage) {
    if (!spec) return;
    setImported(null);
    setImportedText(null);
    setDiff(null);
    setDiffError(null);
    const next: FieldValues = {};
    const revealedNext = new Set<string>();
    const byAddress = new Map<string, SpecField>();
    for (const field of spec.fields) {
      byAddress.set(field.id, field);
      if (field.tag) {
        byAddress.set(`${field.sequenceCode}|${field.tag}|${field.qualifier ?? ""}`, field);
      }
    }
    const assign = (fieldId: string | undefined, occurrence: number, value: string) => {
      if (!fieldId) return;
      next[slotKey(fieldId, occurrence)] = value;
      revealedNext.add(fieldId);
    };
    for (const input of sample.inputs) {
      const field =
        (input.id && byAddress.get(input.id)) ||
        byAddress.get(`${input.sequence}|${input.tag}|${input.qualifier ?? ""}`);
      assign(field?.id, input.occurrence ?? 1, input.value);
    }
    for (const element of sample.elements) {
      assign(byAddress.get(element.path)?.id, element.occurrence ?? 1, element.value);
    }
    setValues(next);
    setRevealed((current) => {
      const merged = new Set(revealedNext);
      for (const key of current) if (key.startsWith("info:")) merged.add(key);
      return merged;
    });
    setSampleOrigin(sample);
    setMode("GUIDED");
    setResult(null);
    setStep(5);
  }

  /**
   * Import an existing ISO 20022 message and land in the builder with its values loaded.
   *
   * The document names itself — the namespace identifies the message — so import skips the
   * first four steps rather than asking a tester to pick a message and then contradicting
   * them. The spec is fetched here rather than left to the loading effect so the values,
   * the specification and the step all change in one commit; the effect would otherwise
   * clear the values it had just been given.
   */
  async function applyImport(text: string, declaredType?: string | null) {
    setBusy(true);
    setActionError(null);
    try {
      const response = await studioApi.importMessage(text, profileId, declaredType);
      const [loadedSpec, loadedSamples] = await Promise.all([
        studioApi.spec(response.format, response.messageType),
        studioApi.samples(response.format, response.messageType),
      ]);

      // Both formats address a field by the specification's own id — an element path for
      // MX, a row id for MT — so the builder is filled the same way for either.
      const imports: { id: string; occurrence: number; value: string }[] =
        response.format === "MX"
          ? response.elements.map((element) => ({
              id: element.path,
              occurrence: element.occurrence ?? 1,
              value: element.value,
            }))
          : response.fields.map((item) => ({
              id: item.id ?? "",
              occurrence: item.occurrence ?? 1,
              value: item.value,
            }));

      const byId = new Map(loadedSpec.fields.map((field) => [field.id, field]));
      const next: FieldValues = {};
      const revealedNext = new Set<string>();
      // A repeated block has to be opened to the number of repeats that arrived, or the
      // later ones are held in state, submitted on generate, and never shown — data the
      // tester cannot see or correct.
      const occurrencesNext: Record<string, number> = {};
      const unmapped: string[] = [];
      for (const element of imports) {
        const field = byId.get(element.id);
        if (!field) {
          unmapped.push(element.id);
          continue;
        }
        next[slotKey(field.id, element.occurrence)] = element.value;
        revealedNext.add(field.id);
        if (element.occurrence > 1) {
          occurrencesNext[field.groupId] = Math.max(
            occurrencesNext[field.groupId] ?? 1,
            element.occurrence,
          );
        }
      }

      loadedKey.current = `${response.format}:${response.messageType}`;
      setFormat(response.format);
      setArea(loadedSpec.businessArea);
      setMessageType(response.messageType);
      setSpec(loadedSpec);
      setSamples(loadedSamples);
      setValues(next);
      setRevealed(revealedNext);
      setOccurrences(occurrencesNext);
      setMode("GUIDED");
      setScenarioId(
        (current) => current || `TC-${response.messageType.replace(/\./g, "")}-IMPORTED`,
      );
      setImported(response);
      setImportedText(text);
      setDiff(null);
      setDiffError(null);
      setResult(response.result);
      setStep(5);
      if (unmapped.length > 0) {
        // Cannot happen while import and the specification read the same YAML, but saying
        // so beats a silently shorter form if they ever diverge.
        setActionError(
          `${unmapped.length} imported value(s) had no matching field and were not loaded: ${unmapped
            .slice(0, 3)
            .join(", ")}.`,
        );
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      setActionError(
        error instanceof StudioError
          ? error.message
          : "That message could not be imported.",
      );
    } finally {
      setBusy(false);
    }
  }

  function buildRequest(persist: boolean): GenerateRequest | null {
    if (!spec || !format || !messageType) return null;
    const byId = new Map(spec.fields.map((field) => [field.id, field]));
    const fields: FieldInput[] = [];
    const elements: ElementInput[] = [];
    for (const [key, raw] of Object.entries(values)) {
      const value = raw.trim();
      if (!value) continue;
      const { fieldId, occurrence } = parseSlot(key);
      const field = byId.get(fieldId);
      if (!field) continue;
      if (format === "MT") {
        fields.push({
          id: field.id,
          sequence: field.sequenceCode,
          occurrence,
          tag: field.tag,
          qualifier: field.qualifier,
          option: field.option,
          value,
        });
      } else {
        elements.push({ path: field.xpath ?? field.id, occurrence, value });
      }
    }
    return {
      format,
      messageType,
      profileId,
      scenarioId: scenarioId.trim() || null,
      fields,
      elements,
      // An imported message keeps the addresses and identifiers it arrived with, so
      // regenerating it reproduces that message rather than a new one that merely looks
      // similar. Anything not carried by the import still falls back to the profile.
      envelope: imported?.envelope ?? null,
      persist,
    };
  }

  async function run(persist: boolean) {
    const request = buildRequest(persist);
    if (!request) return;
    setBusy(true);
    setActionError(null);
    try {
      const response = persist
        ? await studioApi.generate(request)
        : await studioApi.validate(request);
      setResult(response);
      // Only when there is an original to compare against. Generating from scratch has
      // nothing to diff, and showing an empty comparison would be a dead end.
      if (importedText) {
        try {
          setDiff((await studioApi.diffMessage(importedText, request)).diff);
        } catch {
          // A failed comparison must not cost the tester the message they just generated.
          // The proof sheet stands on its own; the diff says so rather than showing nothing.
          setDiff(null);
          setDiffError(
            "The regenerated message is above, but it could not be compared with the one you imported.",
          );
        }
      }
      if (persist && response.valid) {
        setStep(6);
        requestAnimationFrame(() =>
          resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
        );
      }
    } catch (error) {
      setActionError(
        error instanceof StudioError ? error.message : "The message could not be generated.",
      );
    } finally {
      setBusy(false);
    }
  }

  function focusField(location: string) {
    setFocusedLocation(location);
    const element = document.getElementById(`row-${location.replace(/[^A-Za-z0-9]/g, "-")}`);
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => setFocusedLocation(null), 2200);
  }

  function startOver() {
    setImported(null);
    setImportedText(null);
    setDiff(null);
    setDiffError(null);
    setResult(null);
    setValues({});
    setRevealed(new Set());
    setOccurrences({});
    setStep(1);
    setFormat(null);
    setArea(null);
    setMessageType(null);
    setSpec(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* ----------------------------------------------------------------- view */

  if (loadError) {
    return (
      <div className="mx-auto max-w-[1200px] px-4 py-10 sm:px-6">
        <ErrorNotice
          title="The studio could not start"
          message={loadError}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
      </div>
    );
  }


  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-20 pt-8 sm:px-6">
      <div className="pb-6">
        <h1 className="text-[2rem] font-semibold leading-[1.15] tracking-[-0.02em]">
          Create a message
        </h1>
        <p className="mt-2 max-w-[72ch] text-[0.9375rem] leading-7 text-ink-2">
          Pick a message, enter the business data, and download a complete SWIFT MT or ISO
          20022 message ready for your test system. No SWIFT knowledge required — every
          field explains itself.
        </p>
      </div>

      <StepRail current={step} onJump={setStep} reached={reachedStep(format, area, messageType, spec)} />

      <div className="mt-6 space-y-6">
        {step === 1 && catalogue && (
          <>
            <StepFormat catalogue={catalogue} onSelect={selectFormat} />
            <ImportPanel
              busy={busy}
              error={actionError}
              messages={catalogue.messages}
              onImport={applyImport}
            />
          </>
        )}

        {step === 2 && format && (
          <StepArea
            format={format}
            areas={areasForFormat}
            entries={entries}
            onSelect={selectArea}
            onBack={() => setStep(1)}
          />
        )}

        {step === 3 && area && (
          <StepMessage
            messages={messagesForArea}
            onSelect={selectMessage}
            onBack={() => setStep(2)}
          />
        )}

        {step === 4 && selected && (
          <StepMode
            entry={selected}
            samples={samples}
            onChoose={chooseMode}
            onSample={applySample}
            onBack={() => setStep(3)}
          />
        )}

        {step >= 5 && selected && (
          <>
            <SelectionBar
              entry={selected}
              mode={mode}
              onModeChange={chooseMode}
              sampleOrigin={sampleOrigin}
              profileId={profileId}
              profiles={catalogue?.profiles ?? []}
              scenarioId={scenarioId}
              onProfileChange={setProfileId}
              onScenarioChange={setScenarioId}
              onChange={() => setStep(1)}
            />

            {imported && <ImportedNotice imported={imported} />}

            {specLoading && <SpecSkeleton />}

            {spec && !specLoading && (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-ink-2">
                    <span className="font-medium text-ink tnum">{requiredFilled}</span> of{" "}
                    <span className="tnum">{requiredFields.length}</span> required fields
                    filled
                    {mode === "EXPERT" && " · showing every field"}
                  </p>
                  {samples.length > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="text-[0.8125rem] text-ink-3">Load a sample:</span>
                      {samples.map((sample) => (
                        <Button
                          key={sample.variant}
                          size="sm"
                          variant="quiet"
                          onClick={() => applySample(sample)}
                        >
                          {sample.title}
                        </Button>
                      ))}
                    </div>
                  )}
                </div>

                <FieldEditor
                  spec={spec}
                  values={values}
                  onChange={updateValue}
                  occurrences={occurrences}
                  onAddOccurrence={(groupId) =>
                    setOccurrences((current) => ({
                      ...current,
                      [groupId]: (current[groupId] ?? 1) + 1,
                    }))
                  }
                  onRemoveOccurrence={(groupId) =>
                    setOccurrences((current) => ({
                      ...current,
                      [groupId]: Math.max(1, (current[groupId] ?? 1) - 1),
                    }))
                  }
                  revealed={revealed}
                  onReveal={(id) => setRevealed((current) => new Set(current).add(id))}
                  onHide={(id) =>
                    setRevealed((current) => {
                      const next = new Set(current);
                      next.delete(id);
                      return next;
                    })
                  }
                  invalidLocations={invalidLocations}
                  focusedLocation={focusedLocation}
                />

                {actionError && <ErrorNotice message={actionError} />}

                <div className="sticky bottom-0 z-20 -mx-4 border-t border-line bg-paper/95 px-4 py-3 backdrop-blur-sm sm:-mx-6 sm:px-6">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <Button variant="quiet" icon="arrow-left" onClick={() => setStep(4)}>
                        Back
                      </Button>
                      <Button
                        variant="secondary"
                        icon="check-shield"
                        loading={busy}
                        onClick={() => void run(false)}
                      >
                        Validate
                      </Button>
                    </div>
                    <Button
                      variant="primary"
                      size="lg"
                      iconAfter="arrow-right"
                      loading={busy}
                      disabled={!anyFilled}
                      onClick={() => void run(true)}
                    >
                      Generate message
                    </Button>
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {result && (
          <div ref={resultRef} className="space-y-4 scroll-mt-24">
            <ValidationPanel validation={result.validation} onFocusField={focusField} />
            {(result.outputs.fin ||
              result.outputs.xml ||
              result.outputs.block4 ||
              result.outputs.document) && (
              <>
                <ProofSheet result={result} onGenerateAnother={startOver} />
                {diffError && <ErrorNotice message={diffError} />}
                {diff && (
                  <MessageDiffPanel
                    diff={diff}
                    regenerated={regeneratedText(result)}
                    filename={diffFilename(result)}
                    onReturnToEdit={() => {
                      setStep(5);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                  />
                )}
                <EnvelopeTable result={result} />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** The message the comparison is about — the same text the proof sheet shows first. */
function regeneratedText(result: GenerateResult): string {
  const outputs = result.outputs;
  return outputs.fin ?? outputs.xml ?? outputs.block4 ?? outputs.document ?? "";
}

function diffFilename(result: GenerateResult): string {
  const stem = (result.scenarioId || result.messageType).replace(/[^A-Za-z0-9._-]/g, "-");
  return result.format === "MT" ? `${stem}.fin` : `${stem}.xml`;
}

/* ------------------------------------------------------------------- steps */

function reachedStep(
  format: MessageFormat | null,
  area: BusinessArea | null,
  messageType: string | null,
  spec: MessageSpec | null,
): number {
  if (spec) return 5;
  if (messageType) return 4;
  if (area) return 3;
  if (format) return 2;
  return 1;
}

function StepRail({
  current,
  reached,
  onJump,
}: {
  current: number;
  reached: number;
  onJump: (step: number) => void;
}) {
  return (
    <ol className="scroll-slim flex items-center gap-1 overflow-x-auto rounded-md border border-line bg-panel px-2 py-2 shadow-[var(--shadow-1)]">
      {STEPS.map((step, index) => {
        const state =
          step.id < current ? "done" : step.id === current ? "current" : "upcoming";
        const reachable = step.id <= Math.max(reached, current);
        return (
          <li key={step.id} className="flex shrink-0 items-center">
            <button
              type="button"
              disabled={!reachable}
              onClick={() => reachable && onJump(step.id)}
              className={cx(
                "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[0.8125rem] font-medium transition-colors duration-150",
                state === "current" && "bg-accent-sk text-accent-2",
                state === "done" && "text-ink-2 hover:bg-rail",
                state === "upcoming" && "text-ink-3",
                !reachable && "cursor-default",
              )}
            >
              <span
                className={cx(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[0.6875rem] tnum",
                  state === "current" && "bg-accent text-white",
                  state === "done" && "bg-ok text-white",
                  state === "upcoming" && "border border-line-2 text-ink-3",
                )}
              >
                {state === "done" ? <Icon name="check" className="h-3 w-3" strokeWidth={2.5} /> : step.id}
              </span>
              {step.label}
            </button>
            {index < STEPS.length - 1 && (
              <Icon name="chevron-right" className="h-4 w-4 shrink-0 text-line-2" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function StepFormat({
  catalogue,
  onSelect,
}: {
  catalogue: StudioCatalogue;
  onSelect: (format: MessageFormat) => void;
}) {
  return (
    <Panel
      title="Which message standard do you need?"
      description="If your ticket says MT541 or MT548, choose MT. If it names something like sese.023, choose MX."
    >
      <div className="grid gap-4 md:grid-cols-2">
        {catalogue.formats.map((format) => (
          <button
            key={format.id}
            type="button"
            onClick={() => onSelect(format.id)}
            className="group flex flex-col items-start gap-3 rounded-lg border border-line-2 bg-panel p-5 text-left transition-all duration-150 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-[var(--shadow-2)]"
          >
            <div className="flex w-full items-center justify-between gap-3">
              <span className="font-mono text-[1.375rem] font-semibold tracking-[-0.015em] text-accent">
                {format.id}
              </span>
              <span className="text-xs text-ink-3 tnum">
                {format.messageCount} messages
              </span>
            </div>
            <span className="text-[0.9375rem] font-semibold">{format.label}</span>
            <span className="text-sm leading-6 text-ink-2">{format.description}</span>
            <span className="mt-auto inline-flex items-center gap-1.5 pt-1 text-[0.8125rem] font-medium text-accent">
              Choose {format.id}
              <Icon
                name="arrow-right"
                className="h-4 w-4 transition-transform duration-150 group-hover:translate-x-0.5"
              />
            </span>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function StepArea({
  format,
  areas,
  entries,
  onSelect,
  onBack,
}: {
  format: MessageFormat;
  areas: Array<{ id: BusinessArea; label: string; messageCount: number }>;
  entries: CatalogueEntry[];
  onSelect: (area: BusinessArea) => void;
  onBack: () => void;
}) {
  return (
    <Panel
      title="What kind of business event?"
      description="Only areas with messages you can actually generate are shown."
      action={
        <Button variant="quiet" icon="arrow-left" onClick={onBack}>
          Change format
        </Button>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {areas.map((item) => {
          const examples = entries
            .filter((entry) => entry.format === format && entry.businessArea === item.id)
            .slice(0, 4)
            .map((entry) => entry.messageType);
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              className="group flex items-start justify-between gap-4 rounded-md border border-line-2 bg-panel px-4 py-3.5 text-left transition-colors duration-150 hover:border-accent/40 hover:bg-accent-sk"
            >
              <span className="min-w-0">
                <span className="block text-[0.9375rem] font-semibold">{item.label}</span>
                <span className="mt-1 block truncate font-mono text-xs text-ink-3">
                  {examples.join(" · ")}
                  {item.messageCount > 4 && ` +${item.messageCount - 4}`}
                </span>
              </span>
              <Icon
                name="chevron-right"
                className="mt-1 h-4 w-4 shrink-0 text-ink-3 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-accent"
              />
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function StepMessage({
  messages,
  onSelect,
  onBack,
}: {
  messages: CatalogueEntry[];
  onSelect: (messageType: string) => void;
  onBack: () => void;
}) {
  return (
    <Panel
      title="Which message?"
      description="Every message listed here can be generated end to end."
      action={
        <Button variant="quiet" icon="arrow-left" onClick={onBack}>
          Change area
        </Button>
      }
      bodyClassName="px-0 py-0"
    >
      <ul className="divide-y divide-line">
        {messages.map((entry) => (
          <li key={entry.messageType}>
            <button
              type="button"
              onClick={() => onSelect(entry.messageType)}
              className="group flex w-full items-start gap-4 px-5 py-4 text-left transition-colors duration-150 hover:bg-accent-sk"
            >
              <span className="w-[7.5rem] shrink-0">
                <span className="block font-mono text-[0.9375rem] font-semibold text-accent">
                  {entry.messageType}
                </span>
                {entry.version && (
                  <span className="mt-0.5 block font-mono text-[0.6875rem] text-ink-3">
                    {entry.version}
                  </span>
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[0.9375rem] font-medium">{entry.name}</span>
                <span className="mt-0.5 block text-sm leading-6 text-ink-2">
                  {entry.shortDescription}
                </span>
              </span>
              <span className="hidden shrink-0 items-center gap-2 sm:flex">
                <Badge>
                  <span className="tnum">{entry.mandatoryFieldCount}</span> required
                </Badge>
                <Icon
                  name="chevron-right"
                  className="h-4 w-4 text-ink-3 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-accent"
                />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function StepMode({
  entry,
  samples,
  onChoose,
  onSample,
  onBack,
}: {
  entry: CatalogueEntry;
  samples: SampleMessage[];
  onChoose: (mode: InputMode) => void;
  onSample: (sample: SampleMessage) => void;
  onBack: () => void;
}) {
  const options: Array<{
    id: InputMode;
    title: string;
    body: string;
    recommended?: boolean;
  }> = [
    {
      id: "GUIDED",
      title: "Guided",
      body: "Shows only the fields this message requires, in business language. Add optional fields when you need them.",
      recommended: true,
    },
    {
      id: "EXPERT",
      title: "Expert",
      body:
        entry.format === "MT"
          ? "Shows every tag and qualifier in the configured subset at once."
          : "Shows every element path in the configured subset at once.",
    },
  ];

  // The typical sample is the fastest honest way to see a working message, so it leads.
  // It used to sit below two large cards under "Or start from a sample", where a tester
  // picked a card and never saw it.
  const typical = samples.find((item) => item.variant === "TYPICAL") ?? samples[0];
  const others = samples.filter((item) => item !== typical);

  return (
    <Panel
      title={`Start with ${entry.messageType}`}
      description="Load a working sample and edit it, or start from an empty form. You can switch at any time; nothing you have typed is lost."
      action={
        <Button variant="quiet" icon="arrow-left" onClick={onBack}>
          Change message
        </Button>
      }
    >
      {typical && (
        <div className="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => onSample(typical)}
            className="group flex flex-col items-start gap-2 rounded-md border border-accent/40 bg-accent-sk p-4 text-left transition-all duration-150 hover:-translate-y-0.5 hover:shadow-[var(--shadow-2)]"
          >
            <span className="flex flex-wrap items-center gap-2">
              <Icon name="compose" className="h-4 w-4 text-accent" />
              <span className="text-[0.9375rem] font-semibold">
                Load {typical.title.toLowerCase()} sample
              </span>
              <Badge tone="accent">Fastest start</Badge>
            </span>
            <span className="text-sm leading-6 text-ink-2">{typical.description}</span>
            <span className="text-xs text-ink-3 tnum">
              {typical.fieldCount} fields, ready to edit
            </span>
          </button>
          <button
            type="button"
            onClick={() => onChoose("GUIDED")}
            className="group flex flex-col items-start gap-2 rounded-md border border-line-2 bg-panel p-4 text-left transition-all duration-150 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-[var(--shadow-2)]"
          >
            <span className="flex items-center gap-2">
              <Icon name="plus" className="h-4 w-4 text-ink-3" />
              <span className="text-[0.9375rem] font-semibold">Empty message</span>
            </span>
            <span className="text-sm leading-6 text-ink-2">
              Start from a blank form and enter your own values.
            </span>
          </button>
        </div>
      )}

      {others.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-ink-3">Other samples:</span>
          {others.map((sample) => (
            <button
              key={sample.variant}
              type="button"
              onClick={() => onSample(sample)}
              className="rounded-md border border-line-2 bg-sunken px-3 py-1.5 text-[0.8125rem] font-medium transition-colors duration-150 hover:border-accent/40 hover:bg-accent-sk"
            >
              {sample.title}
              <span className="ml-1.5 text-xs text-ink-3 tnum">{sample.fieldCount}</span>
            </button>
          ))}
        </div>
      )}

      <p className="mt-4 text-xs leading-5 text-ink-3">
        Samples are generated by the same composer as your message and validated against the
        same rules, so they always work. Every value in one is synthetic test data.
      </p>

      <div className="mt-5 border-t border-line pt-5">
        <h3 className="text-[0.9375rem] font-semibold">How much do you want to see?</h3>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => onChoose(option.id)}
              className="group flex flex-col items-start gap-2 rounded-md border border-line-2 bg-panel p-4 text-left transition-all duration-150 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-[var(--shadow-2)]"
            >
              <span className="flex items-center gap-2">
                <span className="text-[0.9375rem] font-semibold">{option.title}</span>
                {option.recommended && <Badge tone="accent">Recommended</Badge>}
              </span>
              <span className="text-sm leading-6 text-ink-2">{option.body}</span>
            </button>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function SelectionBar({
  entry,
  mode,
  onModeChange,
  sampleOrigin,
  profileId,
  profiles,
  scenarioId,
  onProfileChange,
  onScenarioChange,
  onChange,
}: {
  entry: CatalogueEntry;
  mode: InputMode;
  onModeChange: (mode: InputMode) => void;
  sampleOrigin: SampleMessage | null;
  profileId: string;
  profiles: string[];
  scenarioId: string;
  onProfileChange: (value: string) => void;
  onScenarioChange: (value: string) => void;
  onChange: () => void;
}) {
  return (
    <div className="rounded-lg border border-line bg-panel px-5 py-4 shadow-[var(--shadow-1)]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <FormatBadge format={entry.format} />
            <span className="font-mono text-[1.0625rem] font-semibold">{entry.messageType}</span>
            <span className="text-[0.9375rem] text-ink-2">{entry.name}</span>
            {/* Switching happens here rather than only at step 4, because the moment a
                tester wants every field is the moment they are looking at the form. Values
                are held per field id and are untouched by the switch, so nothing entered in
                one mode is lost by moving to the other. */}
            <div
              className="inline-flex rounded-md border border-line-2 bg-panel p-0.5"
              role="group"
              aria-label="Detail level"
            >
              {(["GUIDED", "EXPERT"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={mode === option}
                  onClick={() => onModeChange(option)}
                  className={cx(
                    "rounded-[5px] px-2.5 py-1 text-xs font-medium transition-colors duration-150",
                    mode === option
                      ? "bg-accent text-white"
                      : "text-ink-2 hover:bg-rail hover:text-ink",
                  )}
                >
                  {option === "GUIDED" ? "Guided" : "Expert"}
                </button>
              ))}
            </div>
            {sampleOrigin && (
              <Badge tone="warn">
                Sample data — {sampleOrigin.title.toLowerCase()}
              </Badge>
            )}
          </div>
          <p className="mt-1 max-w-[74ch] text-sm leading-6 text-ink-2">
            {entry.shortDescription}
          </p>
        </div>
        <Button variant="quiet" icon="refresh" onClick={onChange}>
          Start over
        </Button>
      </div>

      <div className="mt-4 grid gap-4 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-3">
        <Labelled label="Client profile" hint="Controls allowed currencies and reference rules.">
          <Select value={profileId} onChange={(event) => onProfileChange(event.target.value)}>
            {profiles.map((profile) => (
              <option key={profile} value={profile}>
                {profile}
              </option>
            ))}
          </Select>
        </Labelled>
        <Labelled label="Scenario reference" hint="Your own label. Appears in Recent Messages.">
          <TextInput
            value={scenarioId}
            onChange={(event) => onScenarioChange(event.target.value)}
            placeholder="TC-001"
          />
        </Labelled>
        {!entry.authoritativeCompletenessKnown && (
          <div className="rounded-md border border-warn/25 bg-warn-sk px-3 py-2.5">
            <p className="flex items-start gap-2 text-xs leading-5 text-ink-2">
              <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
              <span>
                Coverage is a configured subset of the standard, not the complete
                authoritative definition.
              </span>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function SpecSkeleton() {
  return (
    <div className="space-y-4">
      {[0, 1].map((group) => (
        <div key={group} className="rounded-lg border border-line bg-panel p-5">
          <Skeleton className="h-5 w-44" />
          <div className="mt-5 space-y-4">
            {[0, 1, 2].map((row) => (
              <div key={row} className="flex gap-5">
                <Skeleton className="h-9 w-[19rem]" />
                <Skeleton className="h-9 flex-1" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export { fieldAddress };

/**
 * Import an existing ISO 20022 message.
 *
 * Deliberately on the first step rather than behind a message choice: an ISO 20022 document
 * names itself in its namespace, so asking a tester to pick sese.023 before pasting a
 * sese.025 would only set them up to be contradicted.
 */
function ImportPanel({
  busy,
  error,
  messages,
  onImport,
}: {
  busy: boolean;
  /** Reported here rather than by the wizard: the rest of the wizard's error surface only
   *  exists from the data-entry step onwards, so a failure on step one would be silent. */
  error: string | null;
  messages: CatalogueEntry[];
  onImport: (text: string, messageType?: string | null) => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [messageType, setMessageType] = useState("");

  // An MX document names itself in its namespace and a complete FIN message names itself
  // in its header, so the message type is normally none of the tester's business. A pasted
  // MT text block is the one thing that cannot name itself, so the picker appears only
  // once the studio has actually said it could not tell — asked for at the moment it is
  // needed rather than standing in everyone's way.
  const needsType =
    error !== null && /fits more than one message|could not be worked out/.test(error);
  const mtMessages = messages.filter((entry) => entry.format === "MT");

  async function readFile(file: File | undefined) {
    if (!file) return;
    setFileError(null);
    if (file.size > 1_000_000) {
      setFileError("That file is larger than 1 MB. Import one message at a time.");
      return;
    }
    try {
      setText(await file.text());
    } catch {
      setFileError("That file could not be read as text.");
    }
  }

  return (
    <Panel
      title="Already have a message?"
      description="Paste or upload an MT or ISO 20022 message and the studio reads it back into the builder, so you can change a value and generate it again."
      action={
        <Button variant="quiet" size="sm" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Hide" : "Import a message"}
        </Button>
      }
    >
      {open ? (
        <div className="space-y-3">
          <Labelled
            label="The message"
            hint="A FIN message, an MT text block, an AppHdr and Document, or a Document on its own."
          >
            <TextArea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={10}
              spellCheck={false}
              placeholder={"{1:F01…}{2:I541…}{4:  or  <Document xmlns=\"urn:iso:std:iso:20022:tech:xsd:sese.023.001.11\">…"}
              aria-label="Message to import"
            />
          </Labelled>
          {(fileError ?? error) && (
            <ErrorNotice
              title="That message could not be read"
              message={fileError ?? error ?? ""}
            />
          )}
          {needsType && (
            <Labelled
              label="Which message is it?"
              hint="A text block on its own does not say which message it belongs to."
            >
              <Select
                value={messageType}
                onChange={(event) => setMessageType(event.target.value)}
                aria-label="Message type of the pasted text block"
              >
                <option value="">Choose a message</option>
                {mtMessages.map((entry) => (
                  <option key={entry.messageType} value={entry.messageType}>
                    {entry.messageType} — {entry.name}
                  </option>
                ))}
              </Select>
            </Labelled>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              iconAfter="arrow-right"
              loading={busy}
              disabled={!text.trim() || (needsType && !messageType)}
              onClick={() => void onImport(text, messageType || null)}
            >
              Read this message
            </Button>
            <label className="cursor-pointer text-[0.8125rem] text-accent underline decoration-line-2 underline-offset-2">
              or choose a file
              <input
                type="file"
                accept=".xml,.fin,.txt,text/xml,application/xml,text/plain"
                className="sr-only"
                onChange={(event) => void readFile(event.target.files?.[0])}
              />
            </label>
          </div>
        </div>
      ) : (
        <p className="text-sm leading-6 text-ink-2">
          Useful when a message failed downstream and you want to change one value and send
          it again, or when you want to see how another system built the same message.
        </p>
      )}
    </Panel>
  );
}

/** What the imported message turned out to contain — including what did not survive. */
function ImportedNotice({ imported }: { imported: ImportResult }) {
  const problems = imported.importIssues.length;
  const notes = imported.importWarnings.length;
  const source = imported.version ?? imported.messageType;
  const header =
    imported.format === "MX"
      ? imported.appHdrPresent
        ? ", including the business application header."
        : ". The document had no business application header, so one is built from the client profile."
      : imported.finBlocks.includes("1")
        ? ", including the interface addresses from its header blocks."
        : ". The message had no header blocks, so the envelope is built from the client profile.";
  return (
    <div className="rounded-lg border border-accent/25 bg-accent-sk px-5 py-4">
      <div className="flex items-start gap-3">
        <Icon name="check-shield" className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink">
            Loaded from the message you imported
          </p>
          <p className="mt-1 text-sm leading-6 text-ink-2">
            {imported.elementCount} value{imported.elementCount === 1 ? "" : "s"} read from{" "}
            <span className="font-mono text-[0.8125rem]">{source}</span>
            {header}
            {problems > 0 &&
              ` ${problems} part${problems === 1 ? "" : "s"} of the message could not be imported — see the issues below.`}
            {problems === 0 && notes > 0 && ` ${notes} note${notes === 1 ? "" : "s"} below.`}
          </p>
          <p className="mt-1 text-[0.8125rem] leading-5 text-ink-3">
            Change any value and generate again. The message is rebuilt by the same composer
            that produced it.
          </p>
        </div>
      </div>
    </div>
  );
}
