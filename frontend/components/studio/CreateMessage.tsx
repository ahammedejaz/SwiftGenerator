"use client";

/**
 * Create Message — the front door.
 *
 * A linear wizard: format, business area, message, how you want to enter data, the data
 * itself, then the result. One decision at a time, each with enough plain-English context
 * that a tester who has never seen ISO 15022 can make it.
 *
 * A message is identified by format, type, lane and release together. The same MT541 can
 * be the reviewed configured entry and a knowledge-preview entry for a later release, and
 * every call the wizard makes names which one it means — the preview lane is never implicit.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
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
import { storeConversionSource } from "@/components/studio/ConvertMessage";
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
  AiCandidate,
  AiPrepareResponse,
  AiSampleResponse,
  AiUsage,
  BusinessArea,
  CatalogueEntry,
  CatalogueFormat,
  ElementInput,
  FieldInput,
  GenerateRequest,
  GenerateResult,
  ImportResult,
  KnowledgeCitation,
  LaneProvenance,
  MessageDiff,
  MessageFormat,
  MessageRef,
  MessageSpec,
  SampleMessage,
  SampleVariant,
  SpecField,
  StudioCatalogue,
} from "@/lib/studio-types";
import { entryKey, messageRef } from "@/lib/studio-types";

type InputMode = "GUIDED" | "EXPERT" | "SAMPLE";

const STEPS = [
  { id: 1, label: "Format" },
  { id: 2, label: "Business area" },
  { id: 3, label: "Message" },
  { id: 4, label: "How to enter data" },
  { id: 5, label: "Enter data" },
  { id: 6, label: "Generate" },
] as const;

/**
 * What the assistant contributed to the values on the form, kept so the form can say so.
 * Presentational only: the values themselves went through the deterministic validator
 * before they arrived, and are generated through exactly the same path as typed ones.
 */
interface AiContribution {
  kind: "SAMPLE" | "PREPARE";
  title: string;
  sampleType: SampleVariant | null;
  segmentsUsed: number;
  citations: KnowledgeCitation[];
  cache: { status: "HIT" | "MISS"; llmCallsAvoided: number } | null;
  usage: AiUsage;
  questions: string[];
  missingFields: string[];
  notes: string[];
}

const AI_UNAVAILABLE = "AI assistant unavailable; deterministic sample used.";

export function CreateMessage() {
  const router = useRouter();
  const [catalogue, setCatalogue] = useState<StudioCatalogue | null>(null);
  const [previewLoadError, setPreviewLoadError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [step, setStep] = useState(1);

  const [format, setFormat] = useState<MessageFormat | null>(null);
  const [area, setArea] = useState<BusinessArea | null>(null);
  // The four-part key of the chosen catalogue entry. A message type alone is ambiguous now
  // that the same type can be listed once per lane and release.
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
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
  const [aiContribution, setAiContribution] = useState<AiContribution | null>(null);
  const [aiNotice, setAiNotice] = useState<string | null>(null);
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
    let cancelled = false;
    async function loadCatalogue() {
      try {
        const configured = await studioApi.catalogue({
          includePreview: false,
          force: reloadToken > 0,
        });
        if (cancelled) return;
        setCatalogue(configured);
        setProfileId(configured.defaultProfileId);
        setLoadError(null);
      } catch (error: unknown) {
        if (cancelled) return;
        setLoadError(
          error instanceof StudioError ? error.message : "The catalogue could not be loaded.",
        );
        return;
      }

      try {
        const complete = await studioApi.catalogue({ force: reloadToken > 0 });
        if (cancelled) return;
        setCatalogue(complete);
        setProfileId(complete.defaultProfileId);
        setPreviewLoadError(null);
      } catch {
        if (!cancelled) {
          setPreviewLoadError(
            "Configured messages are available. Knowledge-preview messages could not be loaded.",
          );
        }
      }
    }
    void loadCatalogue();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  /* ----------------------------------------------------------- derivation */

  const entries = useMemo(() => catalogue?.messages ?? [], [catalogue]);
  const areasForFormat = useMemo(
    () => catalogue?.formats.find((item) => item.id === format)?.businessAreas ?? [],
    [catalogue, format],
  );
  const messagesForArea = useMemo(
    () =>
      sortEntries(
        entries.filter((item) => item.format === format && item.businessArea === area),
      ),
    [entries, format, area],
  );
  const selected = useMemo(
    () => (selectedKey ? entries.find((item) => entryKey(item) === selectedKey) : undefined),
    [entries, selectedKey],
  );
  // The identity every request carries. Null until a message is chosen.
  const ref = useMemo(() => (selected ? messageRef(selected) : null), [selected]);

  /* --------------------------------------------------- specification load */

  // Which entry the loaded spec belongs to. Importing sets this before it sets the spec,
  // so the effect below knows the work is already done and does not clear the values the
  // import just placed.
  const loadedKey = useRef<string | null>(null);

  useEffect(() => {
    if (!ref || !selectedKey) return;
    if (loadedKey.current === selectedKey) return;
    let cancelled = false;
    void (async () => {
      setSpecLoading(true);
      setSpec(null);
      try {
        const [loadedSpec, loadedSamples] = await Promise.all([
          studioApi.spec(ref.format, ref.messageType, ref),
          studioApi.samples(ref.format, ref.messageType, ref),
        ]);
        if (cancelled) return;
        loadedKey.current = selectedKey;
        setSpec(loadedSpec);
        setSamples(loadedSamples);
        // Start with a clean sheet: previous values belong to a different message.
        setValues({});
        setRevealed(new Set());
        setOccurrences({});
        setResult(null);
        setAiContribution(null);
        setAiNotice(null);
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
  }, [ref, selectedKey]);

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
    setSelectedKey(null);
    setSpec(null);
    setResult(null);
    setStep(2);
  }

  function selectArea(next: BusinessArea) {
    setArea(next);
    setSelectedKey(null);
    setSpec(null);
    setResult(null);
    setStep(3);
  }

  /** Pick an entry. Search can offer one from another format or area, so both follow it. */
  function selectMessage(entry: CatalogueEntry) {
    setFormat(entry.format);
    setArea(entry.businessArea);
    setSelectedKey(entryKey(entry));
    setScenarioId((current) => current || `TC-${entry.messageType.replace(/\./g, "")}-001`);
    setActionError(null);
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

  /**
   * Put a set of addressed values on the form. Deterministic samples, AI samples and
   * prepared scenarios all arrive as field ids (or MT addresses) plus values, so they all
   * land the same way — and generate through the same path as typed values.
   */
  function placeValues(
    inputs: FieldInput[],
    elements: ElementInput[],
    loadedSpec: MessageSpec,
  ): { unmapped: string[] } {
    const next: FieldValues = {};
    const revealedNext = new Set<string>();
    const occurrencesNext: Record<string, number> = {};
    const unmapped: string[] = [];
    const byAddress = new Map<string, SpecField>();
    for (const field of loadedSpec.fields) {
      byAddress.set(field.id, field);
      if (field.tag) {
        byAddress.set(`${field.sequenceCode}|${field.tag}|${field.qualifier ?? ""}`, field);
      }
    }
    const assign = (field: SpecField | undefined, occurrence: number, value: string, id: string) => {
      if (!field) {
        unmapped.push(id);
        return;
      }
      next[slotKey(field.id, occurrence)] = value;
      revealedNext.add(field.id);
      // A repeated block has to be opened to the number of repeats that arrived, or the
      // later ones are held in state, submitted on generate, and never shown.
      if (occurrence > 1) {
        occurrencesNext[field.groupId] = Math.max(occurrencesNext[field.groupId] ?? 1, occurrence);
      }
    };
    for (const input of inputs) {
      const field =
        (input.id && byAddress.get(input.id)) ||
        byAddress.get(`${input.sequence}|${input.tag}|${input.qualifier ?? ""}`);
      assign(field, input.occurrence ?? 1, input.value, input.id ?? `${input.tag}`);
    }
    for (const element of elements) {
      assign(byAddress.get(element.path), element.occurrence ?? 1, element.value, element.path);
    }
    setValues(next);
    setRevealed((current) => {
      const merged = new Set(revealedNext);
      for (const key of current) if (key.startsWith("info:")) merged.add(key);
      return merged;
    });
    setOccurrences(occurrencesNext);
    return { unmapped };
  }

  function applySample(sample: SampleMessage) {
    if (!spec) return;
    setImported(null);
    setImportedText(null);
    setDiff(null);
    setDiffError(null);
    placeValues(sample.inputs, sample.elements, spec);
    setSampleOrigin(sample);
    setAiContribution(null);
    setAiNotice(null);
    setMode("GUIDED");
    setResult(null);
    setStep(5);
  }

  /**
   * An AI-prepared sample. The assistant proposes values from indexed evidence; the
   * deterministic engine validated them before they were returned, so what lands on the
   * form is exactly as trustworthy as a deterministic sample — and is marked as synthetic
   * in the same way. If the assistant is unavailable the deterministic sample stands in,
   * and the form says so rather than pretending.
   */
  async function applyAiSample(sampleType: SampleVariant, refresh = false) {
    if (!spec || !ref) return;
    setBusy(true);
    setActionError(null);
    try {
      const response = await studioApi.aiSample({
        ...ref,
        sampleType,
        profileId,
        ...(refresh ? { refresh: true } : {}),
      });
      applySample(aiSampleAsSample(response));
      setAiContribution({
        kind: "SAMPLE",
        title: response.title,
        sampleType: response.sampleType,
        segmentsUsed: response.retrievalEvidence?.segmentsUsed ?? 0,
        citations: response.retrievalEvidence?.citations ?? [],
        cache: response.cache,
        usage: response.aiUsage,
        questions: [],
        missingFields: [],
        notes: [],
      });
      setAiNotice(response.aiUsage.provider === "deterministic" ? AI_UNAVAILABLE : null);
    } catch {
      const fallback =
        samples.find((item) => item.variant === sampleType) ??
        samples.find((item) => item.variant === "TYPICAL") ??
        samples[0];
      if (fallback) {
        applySample(fallback);
        setAiNotice(AI_UNAVAILABLE);
      } else {
        setActionError("AI assistant unavailable, and this message has no deterministic sample to fall back to.");
      }
    } finally {
      setBusy(false);
    }
  }

  /** A described scenario, prepared into values for the chosen message. */
  async function applyPrepared(scenario: string) {
    if (!spec || !ref) return;
    setBusy(true);
    setActionError(null);
    try {
      const response = await studioApi.aiPrepare({
        scenario,
        format: ref.format,
        messageType: ref.messageType,
        lane: ref.lane,
        ...(ref.release ? { release: ref.release } : {}),
        profileId,
      });
      applySample(preparedAsSample(response, spec));
      setAiContribution({
        kind: "PREPARE",
        title: "Prepared from your description",
        sampleType: null,
        segmentsUsed: response.retrievalEvidence?.segmentsUsed ?? 0,
        citations: response.retrievalEvidence?.citations ?? [],
        cache: null,
        usage: response.aiUsage,
        questions: response.questions,
        missingFields: response.missingFields,
        notes: response.notes,
      });
      setAiNotice(
        response.aiUsage.provider === "deterministic"
          ? "AI assistant unavailable; deterministic seed values used."
          : null,
      );
    } catch (error) {
      setActionError(
        error instanceof StudioError
          ? `The scenario could not be prepared. ${error.message}`
          : "The scenario could not be prepared.",
      );
    } finally {
      setBusy(false);
    }
  }

  /**
   * Import an existing message and land in the builder with its values loaded.
   *
   * The document names itself — the namespace identifies the message — so import skips the
   * first four steps rather than asking a tester to pick a message and then contradicting
   * them. The spec is fetched here rather than left to the loading effect so the values,
   * the specification and the step all change in one commit; the effect would otherwise
   * clear the values it had just been given.
   */
  async function applyImport(text: string, declared?: MessageRef | null) {
    setBusy(true);
    setActionError(null);
    try {
      const response = await studioApi.importMessage(
        text,
        profileId,
        declared?.messageType ?? null,
        declared ?? undefined,
      );
      const entry = findEntry(entries, {
        format: response.format,
        messageType: response.messageType,
        version: response.version,
        lane: response.result.lane,
        release: response.result.provenance?.release ?? null,
      });
      const importedRef: MessageRef = entry
        ? messageRef(entry)
        : { format: response.format, messageType: response.messageType, lane: "CONFIGURED", release: null };
      const [loadedSpec, loadedSamples] = await Promise.all([
        studioApi.spec(importedRef.format, importedRef.messageType, importedRef),
        studioApi.samples(importedRef.format, importedRef.messageType, importedRef),
      ]);

      // Both formats address a field by the specification's own id — an element path for
      // MX, a row id for MT — so the builder is filled the same way for either.
      const inputs: FieldInput[] =
        response.format === "MX"
          ? []
          : response.fields.map((item) => ({
              id: item.id ?? "",
              occurrence: item.occurrence ?? 1,
              value: item.value,
            }));
      const elementInputs: ElementInput[] =
        response.format === "MX"
          ? response.elements.map((element) => ({
              path: element.path,
              occurrence: element.occurrence ?? 1,
              value: element.value,
            }))
          : [];

      const key = entry ? entryKey(entry) : entryKey({ ...importedRef });
      loadedKey.current = key;
      setFormat(response.format);
      setArea(loadedSpec.businessArea);
      setSelectedKey(key);
      setSpec(loadedSpec);
      setSamples(loadedSamples);
      const { unmapped } = placeValues(inputs, elementInputs, loadedSpec);
      setMode("GUIDED");
      setScenarioId(
        (current) => current || `TC-${response.messageType.replace(/\./g, "")}-IMPORTED`,
      );
      setImported(response);
      setImportedText(text);
      setDiff(null);
      setDiffError(null);
      setAiContribution(null);
      setAiNotice(null);
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
    if (!spec || !ref) return null;
    const byId = new Map(spec.fields.map((field) => [field.id, field]));
    const fields: FieldInput[] = [];
    const elements: ElementInput[] = [];
    for (const [key, raw] of Object.entries(values)) {
      const value = raw.trim();
      if (!value) continue;
      const { fieldId, occurrence } = parseSlot(key);
      const field = byId.get(fieldId);
      if (!field) continue;
      if (ref.format === "MT") {
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
      format: ref.format,
      messageType: ref.messageType,
      profileId,
      scenarioId: scenarioId.trim() || null,
      fields,
      elements,
      // An imported message keeps the addresses and identifiers it arrived with, so
      // regenerating it reproduces that message rather than a new one that merely looks
      // similar. Anything not carried by the import still falls back to the profile.
      envelope: imported?.envelope ?? null,
      persist,
      // Named on every request: the preview lane is never implied by the message type.
      ...(ref.lane === "KNOWLEDGE_PREVIEW"
        ? { lane: ref.lane, ...(ref.release ? { release: ref.release } : {}) }
        : {}),
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
    setAiContribution(null);
    setAiNotice(null);
    setStep(1);
    setFormat(null);
    setArea(null);
    setSelectedKey(null);
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
        {!catalogue && (
          <p role="status" className="mt-3 text-sm text-ink-3">
            Loading configured messages…
          </p>
        )}
        {previewLoadError && (
          <p role="status" className="mt-3 text-sm text-ink-3">
            {previewLoadError}
          </p>
        )}
      </div>

      <StepRail current={step} onJump={setStep} reached={reachedStep(format, area, selectedKey, spec)} />

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
            onSelectMessage={selectMessage}
            onBack={() => setStep(1)}
          />
        )}

        {step === 3 && area && (
          <StepMessage
            messages={messagesForArea}
            entries={entries}
            onSelect={selectMessage}
            onBack={() => setStep(2)}
          />
        )}

        {step === 4 && selected && (
          <StepMode
            entry={selected}
            spec={spec}
            samples={samples}
            busy={busy}
            error={actionError}
            onChoose={chooseMode}
            onSample={applySample}
            onAiSample={(variant) => void applyAiSample(variant)}
            onPrepare={(scenario) => void applyPrepared(scenario)}
            onBack={() => setStep(3)}
          />
        )}

        {step >= 5 && selected && (
          <>
            <SelectionBar
              entry={selected}
              spec={spec}
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

            {aiNotice && <AiUnavailableNotice message={aiNotice} />}

            {aiContribution && (
              <AiContributionNote
                contribution={aiContribution}
                busy={busy}
                onRefresh={
                  aiContribution.kind === "SAMPLE" && aiContribution.sampleType
                    ? () => void applyAiSample(aiContribution.sampleType as SampleVariant, true)
                    : undefined
                }
              />
            )}

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
                    <div className="flex flex-wrap items-center gap-2">
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
            {result.provenance && result.lane === "KNOWLEDGE_PREVIEW" && (
              <ProvenanceLine provenance={result.provenance} />
            )}
            {(result.outputs.fin ||
              result.outputs.xml ||
              result.outputs.block4 ||
              result.outputs.document) && (
              <>
                <ProofSheet result={result} onGenerateAnother={startOver} />
                {result.format === "MT" && (
                  <div className="flex justify-end">
                    <Button
                      variant="secondary"
                      icon="refresh"
                      onClick={() => {
                        storeConversionSource(result.messageType, regeneratedText(result));
                        router.push("/convert");
                      }}
                    >
                      Convert to MX
                    </Button>
                  </div>
                )}
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

/* ------------------------------------------------------------- entry helpers */

/** "23 configured · 267 previews", or a plain total when there are no previews. */
function formatCount(format: CatalogueFormat): string {
  const configured = format.configuredMessageCount;
  if (configured === format.messageCount) return `${format.messageCount} messages`;
  return `${configured} configured · ${format.messageCount - configured} previews`;
}

/** Configured entries first, then preview entries, each in type and release order. */
function sortEntries(items: CatalogueEntry[]): CatalogueEntry[] {
  return [...items].sort((left, right) => {
    const laneOrder = Number(left.lane !== "CONFIGURED") - Number(right.lane !== "CONFIGURED");
    if (laneOrder !== 0) return laneOrder;
    const type = left.messageType.localeCompare(right.messageType);
    if (type !== 0) return type;
    return (left.release ?? "").localeCompare(right.release ?? "");
  });
}

/**
 * Matches on type, name, release and version, so "MT103", "pacs.008", "SR2026" and
 * "credit transfer" all work. A search is across every format and area: the point of it is
 * that the tester need not know where the catalogue filed the message.
 */
function searchEntries(items: CatalogueEntry[], query: string): CatalogueEntry[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return [];
  return sortEntries(
    items.filter((entry) => {
      const haystack = [
        entry.messageType,
        entry.version ?? "",
        entry.name,
        entry.release ?? "",
        entry.lane === "KNOWLEDGE_PREVIEW" ? "preview" : "configured",
      ]
        .join(" ")
        .toLowerCase();
      return terms.every((term) => haystack.includes(term));
    }),
  );
}

/** The catalogue entry an API response refers to, across lanes and releases. */
function findEntry(
  items: CatalogueEntry[],
  identity: {
    format: MessageFormat;
    messageType: string;
    version: string | null;
    lane: CatalogueEntry["lane"];
    release: string | null;
  },
): CatalogueEntry | undefined {
  return items.find((entry) => {
    if (entry.format !== identity.format || entry.lane !== identity.lane) return false;
    if (entry.messageType !== identity.messageType && entry.version !== identity.messageType) {
      return false;
    }
    if (entry.lane === "CONFIGURED") return true;
    if (entry.format === "MX") {
      return (entry.version ?? entry.release) === (identity.version ?? identity.release);
    }
    return (entry.release ?? "") === (identity.release ?? "");
  });
}

/** What a preview entry's chip says. The release lane is stated; it is never derived from the clock. */
function laneChip(entry: CatalogueEntry): string | null {
  if (entry.lane !== "KNOWLEDGE_PREVIEW") return null;
  if (entry.format === "MX") {
    // An XSD-compiled preview is identified by its schema version, not a SWIFT release name.
    const version = entry.version ?? entry.release;
    return version ? `${version} · XSD-backed test preview` : null;
  }
  const release = entry.release;
  if (release && entry.releaseLane === "FUTURE_TEST") return `${release} · future release, test preview`;
  if (release && entry.releaseLane === "CURRENT_LIVE") return `${release} · current release, test preview`;
  if (release) return `${release} · test preview`;
  return null;
}

const BLOCKER_LABELS: Record<string, string> = {
  STRUCTURE_SOURCE_MISSING: "No structure source has been indexed, so there is nothing to compile a message from.",
  QUALIFIER_EVIDENCE_MISSING: "The evidence does not establish which qualifiers each field allows.",
  FORMAT_FIDELITY_PARTIAL: "Field formats are only partly established by the evidence.",
  DUPLICATE_TAG_IN_SEQUENCE: "A tag appears more than once in one sequence, which the composer cannot address.",
};

function blockerLabel(code: string): string {
  return BLOCKER_LABELS[code] ?? code.toLowerCase().replace(/_/g, " ");
}

/** "SWIFT_MRG_SR2026_PROWIDE_SR2025_CORROBORATED" → "SWIFT MRG SR2026, Prowide SR2025 corroborated". */
function describeStructureSource(source: string | null): string | null {
  if (!source) return null;
  const WORDS: Record<string, string> = {
    PROWIDE: "Prowide",
    CORROBORATED: "corroborated",
    OPERATOR: "operator-supplied",
    SUPPLIED: "",
    CONFIGURED: "configured",
    REPOSITORY: "repository",
    SUBSET: "subset",
  };
  const parts = source
    .split("_")
    .map((part) => (part in WORDS ? WORDS[part] : part))
    .filter(Boolean);
  return parts.join(" ").replace(/ Prowide/g, ", Prowide");
}

/** "AI Minimal sample" keeps its initials; "Minimal valid" reads better in lower case. */
function sampleTitle(title: string): string {
  return title.startsWith("AI ") ? `AI ${title.slice(3).toLowerCase()}` : title.toLowerCase();
}

/** An AI sample carries the same inputs and elements a deterministic sample does. */
function aiSampleAsSample(response: AiSampleResponse): SampleMessage {
  return {
    sampleId: response.sampleId,
    format: response.format,
    messageType: response.messageType,
    variant: response.sampleType,
    title: response.title,
    description: response.description,
    fieldCount: response.inputs.length + response.elements.length,
    inputs: response.inputs,
    elements: response.elements,
  };
}

/** Prepared canonical values are keyed by field id, which is all the form needs. */
function preparedAsSample(response: AiPrepareResponse, spec: MessageSpec): SampleMessage {
  const isMx = response.format === "MX";
  return {
    sampleId: `${response.messageType}-PREPARED`,
    format: response.format,
    messageType: response.messageType,
    variant: "TYPICAL",
    title: "Prepared from your description",
    description: response.scenario,
    fieldCount: response.canonicalValues.length,
    inputs: isMx
      ? []
      : response.canonicalValues.map((item) => ({
          id: item.fieldId,
          occurrence: item.occurrence,
          value: item.value,
        })),
    elements: isMx
      ? response.canonicalValues.map((item) => ({
          path: spec.fields.find((field) => field.id === item.fieldId)?.id ?? item.fieldId,
          occurrence: item.occurrence,
          value: item.value,
        }))
      : [],
  };
}

/* ------------------------------------------------------------------- steps */

function reachedStep(
  format: MessageFormat | null,
  area: BusinessArea | null,
  selectedKey: string | null,
  spec: MessageSpec | null,
): number {
  if (spec) return 5;
  if (selectedKey) return 4;
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
                {formatCount(format)}
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
  onSelectMessage,
  onBack,
}: {
  format: MessageFormat;
  areas: Array<{ id: BusinessArea; label: string; messageCount: number }>;
  entries: CatalogueEntry[];
  onSelect: (area: BusinessArea) => void;
  onSelectMessage: (entry: CatalogueEntry) => void;
  onBack: () => void;
}) {
  const [query, setQuery] = useState("");
  const matches = useMemo(() => searchEntries(entries, query), [entries, query]);

  return (
    <>
      <Panel
        title="Know the message already?"
        description="Search by message type, name or release — MT103, pacs.008, SR2026. Every message the catalogue knows is listed, including ones that cannot be generated yet."
      >
        <MessageSearchBox value={query} onChange={setQuery} />
        {query.trim() && (
          <div className="mt-4 -mx-5 -mb-5 border-t border-line">
            <MessageRows
              messages={matches}
              onSelect={onSelectMessage}
              emptyText="Nothing matched. Try the message type on its own, or a release such as SR2026."
            />
          </div>
        )}
        {!query.trim() && (
          <DescribeBox
            mode="IDENTIFY"
            entries={entries}
            format={format}
            onSelectEntry={onSelectMessage}
          />
        )}
      </Panel>

      <Panel
        title="What kind of business event?"
        description="Areas follow the catalogue. An entry that cannot be generated yet is still listed, and says why."
        action={
          <Button variant="quiet" icon="arrow-left" onClick={onBack}>
            Change format
          </Button>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {areas.map((item) => {
            const inArea = entries.filter(
              (entry) => entry.format === format && entry.businessArea === item.id,
            );
            const examples = Array.from(new Set(inArea.map((entry) => entry.messageType))).slice(0, 4);
            const ready = inArea.filter((entry) => entry.generatable).length;
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
                  {ready < inArea.length && (
                    <span className="mt-1 block text-xs text-ink-3 tnum">
                      {ready} of {inArea.length} ready to generate
                    </span>
                  )}
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
    </>
  );
}

function MessageSearchBox({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="relative">
      <Icon
        name="search"
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
      />
      <TextInput
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Message type, name or release"
        className="h-11 pl-9"
        aria-label="Search messages"
        autoComplete="off"
      />
    </div>
  );
}

function StepMessage({
  messages,
  entries,
  onSelect,
  onBack,
}: {
  messages: CatalogueEntry[];
  entries: CatalogueEntry[];
  onSelect: (entry: CatalogueEntry) => void;
  onBack: () => void;
}) {
  const [query, setQuery] = useState("");
  const searching = query.trim().length > 0;
  const shown = useMemo(
    () => (searching ? searchEntries(entries, query) : messages),
    [searching, entries, query, messages],
  );

  return (
    <Panel
      title="Which message?"
      description={
        searching
          ? "Showing matches from every area and both standards."
          : "Configured messages first, then knowledge previews. An entry that cannot be generated yet says why."
      }
      action={
        <Button variant="quiet" icon="arrow-left" onClick={onBack}>
          Change area
        </Button>
      }
      bodyClassName="px-0 py-0"
    >
      <div className="border-b border-line px-5 py-3">
        <MessageSearchBox value={query} onChange={setQuery} />
      </div>
      <MessageRows
        messages={shown}
        onSelect={onSelect}
        emptyText={searching ? "Nothing matched." : "This area has no messages."}
      />
    </Panel>
  );
}

/**
 * The catalogue rows. A generatable entry is chosen with one click; an entry that cannot
 * be generated yet opens to say why instead — it is never hidden, and never offered a
 * generate button it could not honour.
 */
function MessageRows({
  messages,
  onSelect,
  emptyText,
}: {
  messages: CatalogueEntry[];
  onSelect: (entry: CatalogueEntry) => void;
  emptyText: string;
}) {
  const [openKey, setOpenKey] = useState<string | null>(null);

  if (messages.length === 0) {
    return <p className="px-5 py-6 text-sm text-ink-2">{emptyText}</p>;
  }

  return (
    <ul className="divide-y divide-line">
      {messages.map((entry) => {
        const key = entryKey(entry);
        const chip = laneChip(entry);
        const open = openKey === key;
        return (
          <li key={key}>
            <button
              type="button"
              onClick={() => (entry.generatable ? onSelect(entry) : setOpenKey(open ? null : key))}
              aria-expanded={entry.generatable ? undefined : open}
              className={cx(
                "group flex w-full items-start gap-4 px-5 py-4 text-left transition-colors duration-150 hover:bg-accent-sk",
                !entry.generatable && "bg-sunken/40",
              )}
            >
              <span className="w-[7.5rem] shrink-0">
                <span
                  className={cx(
                    "block font-mono text-[0.9375rem] font-semibold",
                    entry.generatable ? "text-accent" : "text-ink-3",
                  )}
                >
                  {entry.messageType}
                </span>
                {entry.version && (
                  <span className="mt-0.5 block font-mono text-[0.6875rem] text-ink-3">
                    {entry.version}
                  </span>
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-[0.9375rem] font-medium">{entry.name}</span>
                  <ReadinessBadge entry={entry} />
                  {chip && <Badge tone="accent">{chip}</Badge>}
                </span>
                <span className="mt-0.5 block text-sm leading-6 text-ink-2">
                  {entry.shortDescription}
                </span>
                {entry.lane === "KNOWLEDGE_PREVIEW" && entry.generatable && (
                  <span className="mt-0.5 block text-xs leading-5 text-ink-3">
                    {entry.readinessLabel}
                  </span>
                )}
              </span>
              <span className="hidden shrink-0 items-center gap-2 sm:flex">
                {entry.generatable && (
                  <Badge>
                    <span className="tnum">{entry.mandatoryFieldCount}</span> required
                  </Badge>
                )}
                <Icon
                  name={entry.generatable ? "chevron-right" : open ? "chevron-down" : "info"}
                  className="h-4 w-4 text-ink-3 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-accent"
                />
              </span>
            </button>
            {open && !entry.generatable && <NotGeneratableExplanation entry={entry} />}
          </li>
        );
      })}
    </ul>
  );
}

function ReadinessBadge({ entry }: { entry: CatalogueEntry }) {
  if (entry.lane === "CONFIGURED") return <Badge tone="ok">Configured &amp; validated</Badge>;
  if (entry.generatable) return <Badge tone="accent">Knowledge preview</Badge>;
  return <Badge tone="warn">Not generatable yet</Badge>;
}

function NotGeneratableExplanation({ entry }: { entry: CatalogueEntry }) {
  const source = describeStructureSource(entry.structureSource);
  return (
    <div className="border-t border-line bg-sunken/60 px-5 py-4 sm:pl-[9.75rem]">
      <p className="text-sm font-medium text-ink">{entry.readinessLabel}</p>
      {entry.blockers.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm leading-6 text-ink-2">
          {entry.blockers.map((code) => (
            <li key={code} className="flex flex-wrap items-baseline gap-x-2">
              <span>{blockerLabel(code)}</span>
              <code className="font-mono text-[0.6875rem] text-ink-3">{code}</code>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs leading-5 text-ink-3">
        {source ? `Structure evidence: ${source}. ` : ""}
        {entry.knowledgeSources > 0
          ? `${entry.knowledgeSources} indexed source${entry.knowledgeSources === 1 ? "" : "s"}. `
          : ""}
        Generation and samples are not offered for this entry. It is listed so you know it
        exists and what is still missing.
      </p>
    </div>
  );
}

/**
 * "Describe what you want to test." Before a message is chosen the description identifies
 * one; after, it is prepared into values for the chosen message. The assistant proposes;
 * the catalogue and the validator decide — a candidate it cannot name does not appear,
 * and a value the validator rejects does not land on the form.
 */
function DescribeBox(
  props:
    | {
        mode: "IDENTIFY";
        entries: CatalogueEntry[];
        format: MessageFormat | null;
        onSelectEntry: (entry: CatalogueEntry) => void;
      }
    | {
        mode: "PREPARE";
        busy: boolean;
        /** Until the specification has loaded there is nothing to prepare values against. */
        disabled?: boolean;
        onPrepare: (scenario: string) => void;
      },
) {
  const [text, setText] = useState("");
  const [candidates, setCandidates] = useState<AiCandidate[] | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const [identifying, setIdentifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function identify() {
    if (props.mode !== "IDENTIFY") return;
    setIdentifying(true);
    setError(null);
    try {
      const response = await studioApi.aiIdentify({
        request: text.trim(),
        ...(props.format ? { format: props.format } : {}),
        limit: 5,
      });
      setCandidates(response.candidates);
      setExplanation(response.explanation);
      setMissing(response.missingInformation);
    } catch (caught) {
      setCandidates(null);
      setError(
        caught instanceof StudioError
          ? `The assistant could not identify a message. ${caught.message}`
          : "The assistant could not identify a message.",
      );
    } finally {
      setIdentifying(false);
    }
  }

  const busy = props.mode === "PREPARE" ? props.busy : identifying;
  const ready = text.trim().length >= 3 && !(props.mode === "PREPARE" && props.disabled);

  return (
    <div className="mt-5 border-t border-line pt-5">
      <div className="flex items-center gap-2">
        <Icon name="spark" className="h-4 w-4 text-accent" />
        <h3 className="text-[0.9375rem] font-semibold">Describe what you want to test</h3>
      </div>
      <p className="mt-1 text-sm leading-6 text-ink-2">
        {props.mode === "IDENTIFY"
          ? "Say it in your own words and the assistant suggests a message from the catalogue."
          : "Say it in your own words. The assistant proposes values; the deterministic validator checks every one before it reaches the form."}
      </p>
      <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-start">
        <TextArea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={2}
          className="min-h-[4.5rem] font-sans"
          placeholder={
            props.mode === "IDENTIFY"
              ? "Receive securities against payment for a client in Frankfurt"
              : "Receive securities against payment, settling in two days, EUR 250,000"
          }
          aria-label="Describe what you want to test"
        />
        <Button
          variant="secondary"
          icon="spark"
          loading={busy}
          disabled={!ready}
          className="shrink-0"
          onClick={() =>
            props.mode === "PREPARE" ? props.onPrepare(text.trim()) : void identify()
          }
        >
          {props.mode === "IDENTIFY" ? "Find the message" : "Prepare values"}
        </Button>
      </div>

      {error && <div className="mt-3"><ErrorNotice title="Assistant unavailable" message={error} /></div>}

      {props.mode === "IDENTIFY" && candidates && (
        <div className="mt-4">
          {explanation && <p className="text-sm text-ink-2">{explanation}</p>}
          {missing.length > 0 && (
            <p className="mt-1 text-xs leading-5 text-ink-3">
              Still needed: {missing.join("; ")}
            </p>
          )}
          {candidates.length === 0 ? (
            <p className="mt-2 text-sm text-ink-2">No catalogue message matched that description.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line rounded-md border border-line">
              {candidates.map((candidate) => {
                const entry = props.entries.find(
                  (item) =>
                    item.format === candidate.format &&
                    item.lane === candidate.lane &&
                    item.messageType === candidate.messageType &&
                    (item.lane === "CONFIGURED" ||
                      (item.release ?? "") === (candidate.release ?? "")),
                );
                const selectable = candidate.generatable && entry;
                return (
                  <li key={`${candidate.format}|${candidate.messageType}|${candidate.lane}|${candidate.release ?? ""}`}>
                    <button
                      type="button"
                      disabled={!selectable}
                      onClick={() => entry && props.onSelectEntry(entry)}
                      className={cx(
                        "flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-left text-sm transition-colors duration-150",
                        selectable ? "hover:bg-accent-sk" : "cursor-default opacity-70",
                      )}
                    >
                      <span className="font-mono font-semibold text-accent">{candidate.messageType}</span>
                      <span className="font-medium">{candidate.name}</span>
                      <span className="text-xs text-ink-3">{candidate.readinessLabel}</span>
                      {candidate.release && <Badge>{candidate.release}</Badge>}
                      <span className="ml-auto text-xs text-ink-3 tnum">
                        {Math.round(candidate.confidence * 100)}% match
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function StepMode({
  entry,
  spec,
  samples,
  busy,
  error,
  onChoose,
  onSample,
  onAiSample,
  onPrepare,
  onBack,
}: {
  entry: CatalogueEntry;
  spec: MessageSpec | null;
  samples: SampleMessage[];
  busy: boolean;
  error: string | null;
  onChoose: (mode: InputMode) => void;
  onSample: (sample: SampleMessage) => void;
  onAiSample: (variant: SampleVariant) => void;
  onPrepare: (scenario: string) => void;
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
  const preview = entry.lane === "KNOWLEDGE_PREVIEW";
  const chip = laneChip(entry);

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
      {preview && (
        <div className="mb-4 rounded-md border border-accent/25 bg-accent-sk px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="accent">Knowledge preview</Badge>
            {chip && <Badge>{chip}</Badge>}
          </div>
          <p className="mt-2 text-sm leading-6 text-ink-2">
            {spec?.capabilityStatement ?? entry.readinessLabel}
          </p>
          {describeStructureSource(entry.structureSource) && (
            <p className="mt-1 text-xs leading-5 text-ink-3">
              Structure from {describeStructureSource(entry.structureSource)}.
            </p>
          )}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {typical && (
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
        )}
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

      {entry.generatable && (
        <div className="mt-5 border-t border-line pt-5">
          <div className="flex items-center gap-2">
            <Icon name="spark" className="h-4 w-4 text-accent" />
            <h3 className="text-[0.9375rem] font-semibold">AI-prepared samples</h3>
          </div>
          <p className="mt-1 text-sm leading-6 text-ink-2">
            The assistant proposes values from the indexed source material; the deterministic
            engine validates every one before it reaches the form. A repeat request is served
            from the validated-sample cache with no model call.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {(["TYPICAL", "MINIMAL", "FULL"] as const).map((variant) => (
              <Button
                key={variant}
                variant="secondary"
                size="sm"
                loading={busy}
                disabled={!spec}
                onClick={() => onAiSample(variant)}
              >
                AI {variant === "TYPICAL" ? "Typical sample" : variant === "MINIMAL" ? "Minimal" : "Full"}
              </Button>
            ))}
            {!spec && <span className="text-xs text-ink-3">Loading the specification…</span>}
          </div>
          <DescribeBox mode="PREPARE" busy={busy} disabled={!spec} onPrepare={onPrepare} />
          {error && <div className="mt-3"><ErrorNotice message={error} /></div>}
        </div>
      )}

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
  spec,
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
  spec: MessageSpec | null;
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
  const chip = laneChip(entry);
  const preview = entry.lane === "KNOWLEDGE_PREVIEW";
  return (
    <div className="rounded-lg border border-line bg-panel px-5 py-4 shadow-[var(--shadow-1)]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <FormatBadge format={entry.format} />
            <span className="font-mono text-[1.0625rem] font-semibold">{entry.messageType}</span>
            <span className="text-[0.9375rem] text-ink-2">{entry.name}</span>
            {chip && <Badge tone="accent">{chip}</Badge>}
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
                Sample data — {sampleTitle(sampleOrigin.title)}
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
        <Labelled
          label="Client profile"
          hint="Controls allowed currencies, reference rules and any installed rule packs."
        >
          {/* `Labelled` renders a label whose `for` nothing claims, so a control it wraps
              is named by its own aria-label — the same arrangement the import textarea
              uses. Without this the profile selector has no accessible name at all. */}
          <Select
            aria-label="Client profile"
            value={profileId}
            onChange={(event) => onProfileChange(event.target.value)}
          >
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
        {(preview || !entry.authoritativeCompletenessKnown) && (
          <div className="rounded-md border border-warn/25 bg-warn-sk px-3 py-2.5">
            <p className="flex items-start gap-2 text-xs leading-5 text-ink-2">
              <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
              <span>
                {(preview && spec?.capabilityStatement) ||
                  entry.capabilitySummary ||
                  "Coverage is a configured subset of the standard, not the complete " +
                    "authoritative definition."}
              </span>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ AI notices */

function AiUnavailableNotice({ message }: { message: string }) {
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-md border border-warn/25 bg-warn-sk px-4 py-3"
    >
      <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
      <p className="text-sm leading-6 text-ink-2">{message}</p>
    </div>
  );
}

/**
 * What the assistant contributed, stated once and quietly. Enough for a reviewer to see
 * which sections of which documents were consulted and whether a model was called at all;
 * nothing about how retrieval works.
 */
function AiContributionNote({
  contribution,
  busy,
  onRefresh,
}: {
  contribution: AiContribution;
  busy: boolean;
  onRefresh?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const calls = contribution.usage.llmCalls;
  const cacheLine = contribution.cache
    ? contribution.cache.status === "HIT"
      ? `Cache: HIT — 0 model calls`
      : `Cache: MISS — ${calls} model call${calls === 1 ? "" : "s"}`
    : `${calls} model call${calls === 1 ? "" : "s"}`;
  const sections = contribution.segmentsUsed;
  const questions = [...contribution.missingFields, ...contribution.questions];
  const deterministic = contribution.usage.provider === "deterministic";
  const cached = contribution.cache?.status === "HIT";
  const totalTokens = contribution.usage.promptTokens + contribution.usage.completionTokens;

  return (
    <div className="rounded-lg border border-accent/25 bg-accent-sk px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-x-2 text-sm font-semibold text-ink">
            <Icon name="spark" className="h-4 w-4 text-accent" />
            {deterministic
              ? "Deterministic fallback"
              : cached
                ? "AI sample — cached"
                : contribution.kind === "SAMPLE"
                  ? "AI-assisted synthetic sample"
                  : "AI-assisted values"}
            <span className="font-normal text-ink-2">· validated by the deterministic engine</span>
          </p>
          <p className="mt-1 text-[0.8125rem] leading-5 text-ink-2">
            AI used {sections} source section{sections === 1 ? "" : "s"} · {cacheLine}
          </p>
          {contribution.notes.length > 0 && (
            <p className="mt-1 text-xs leading-5 text-ink-3">{contribution.notes.join(" ")}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" variant="quiet" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Hide details" : "Show details"}
          </Button>
          {onRefresh && (
            <Button size="sm" variant="quiet" icon="refresh" loading={busy} onClick={onRefresh}>
              Refresh with AI
            </Button>
          )}
        </div>
      </div>

      {questions.length > 0 && (
        <div className="mt-3 border-t border-accent/20 pt-3">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">
            Still to decide
          </p>
          <ul className="mt-1 list-inside list-disc text-sm leading-6 text-ink-2">
            {questions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {open && (
        <div className="mt-3 border-t border-accent/20 pt-3">
          <dl className="grid gap-x-5 gap-y-2 text-[0.8125rem] sm:grid-cols-2 lg:grid-cols-5">
            <UsageFact label="AI" value={deterministic ? "Not called" : `${contribution.usage.model || "Configured model"} via ${contribution.usage.provider}`} />
            <UsageFact label="RAG" value={`${sections} source section${sections === 1 ? "" : "s"}`} />
            <UsageFact label="Tokens" value={totalTokens.toLocaleString()} />
            <UsageFact label="Response" value={`${contribution.usage.latencyMs} ms`} />
            <UsageFact label="Cache" value={cached ? "Hit · 0 live calls" : "Miss"} />
          </dl>
          {contribution.citations.length > 0 && (
            <ul className="mt-3 space-y-2 border-t border-accent/20 pt-3">
              {contribution.citations.map((citation) => (
                <li key={citation.segmentId} className="text-[0.8125rem] leading-5">
                  <span className="font-medium text-ink">{citation.documentTitle}</span>
                  <span className="text-ink-2">
                    {" "}
                    · {citation.section.toLowerCase().replace(/_/g, " ")}
                    {citation.page !== null ? ` · page ${citation.page}` : ""}
                    {citation.heading ? ` · ${citation.heading}` : ""}
                  </span>
                  {citation.snippet && (
                    <p className="mt-0.5 text-xs leading-5 text-ink-3">{citation.snippet}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function UsageFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="truncate font-medium text-ink" title={value}>{value}</dd>
    </div>
  );
}

/** What a preview-lane message rests on, in one line under the validation result. */
function ProvenanceLine({ provenance }: { provenance: LaneProvenance }) {
  const parts = [
    "Knowledge preview",
    provenance.release
      ? `${provenance.release}${provenance.releaseLane === "FUTURE_TEST" ? " · future release, test preview" : ""}`
      : null,
    provenance.structureSource
      ? `structure from ${describeStructureSource(provenance.structureSource)}`
      : null,
    provenance.capabilityStatement
      ? provenance.capabilityStatement.replace(/\.$/, "")
      : provenance.ruleStatus === "NOT_ESTABLISHED"
        ? "semantic rules not established"
        : null,
  ].filter(Boolean);
  return (
    <p
      data-testid="provenance"
      className="flex items-start gap-2 rounded-md border border-accent/25 bg-accent-sk px-4 py-2.5 text-[0.8125rem] leading-5 text-ink-2"
    >
      <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
      <span>{parts.join(" · ")}</span>
    </p>
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
  onImport: (text: string, declared?: MessageRef | null) => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [declaredKey, setDeclaredKey] = useState("");

  // An MX document names itself in its namespace and a complete FIN message names itself
  // in its header, so the message type is normally none of the tester's business. A pasted
  // MT text block is the one thing that cannot name itself, so the picker appears only
  // once the studio has actually said it could not tell — asked for at the moment it is
  // needed rather than standing in everyone's way.
  const needsType =
    error !== null && /fits more than one message|could not be worked out/.test(error);
  // Generatable MT entries in either lane. A preview entry is named with its release, so a
  // text block for a future-release message is read against that release and no other.
  const mtMessages = sortEntries(
    messages.filter((entry) => entry.format === "MT" && entry.generatable),
  );
  // A configured entry is still chosen by its message type alone, as it always was; only a
  // preview entry needs the lane and release in its value to be told apart.
  const optionValue = (entry: CatalogueEntry) =>
    entry.lane === "CONFIGURED" ? entry.messageType : entryKey(entry);
  const declared = mtMessages.find((entry) => optionValue(entry) === declaredKey);

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
                value={declaredKey}
                onChange={(event) => setDeclaredKey(event.target.value)}
                aria-label="Message type of the pasted text block"
              >
                <option value="">Choose a message</option>
                {mtMessages.map((entry) => (
                  <option key={entryKey(entry)} value={optionValue(entry)}>
                    {entry.messageType} — {entry.name}
                    {entry.lane === "KNOWLEDGE_PREVIEW" ? ` (${entry.release ?? "preview"}, knowledge preview)` : ""}
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
              disabled={!text.trim() || (needsType && !declared)}
              onClick={() => void onImport(text, declared ? messageRef(declared) : null)}
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
