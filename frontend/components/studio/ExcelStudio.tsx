"use client";

/**
 * Bulk / Excel — the automation tester's spreadsheet workflow, with a UI in front of it so
 * a manual tester can drive the same thing without writing a request.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/studio/Icon";
import { ProofSheet } from "@/components/studio/ProofSheet";
import { ValidationPanel } from "@/components/studio/ValidationPanel";
import {
  Badge,
  Button,
  ErrorNotice,
  FormatBadge,
  Panel,
  cx,
} from "@/components/studio/ui";
import { StudioError, studioApi } from "@/lib/studio-api";
import type {
  CatalogueEntry,
  ExcelGenerateResponse,
  ExcelScenarioResult,
  GenerateResult,
  MessageFormat,
} from "@/lib/studio-types";
import { entryKey, messageRef } from "@/lib/studio-types";

const TEMPLATES: Array<{
  format: MessageFormat;
  title: string;
  columns: string;
  body: string;
}> = [
  {
    format: "MT",
    title: "MT template",
    columns: "ScenarioID · MessageType · Sequence · SequenceOccurrence · Tag · Qualifier · Value",
    body: "Tag-level rows for MT541, MT543 and MT548, with a Reference sheet listing every supported tag.",
  },
  {
    format: "MX",
    title: "MX template",
    columns: "ScenarioID · MessageType · XPath · Occurrence · Value",
    body: "Element-level rows for sese.023, sese.024 and sese.025, with every supported element path.",
  },
];

export function ExcelStudio() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<ExcelGenerateResponse | null>(null);
  const [openScenario, setOpenScenario] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Knowledge-preview lane: every generation-ready dynamic pack gets the same spreadsheet
  // workflow, addressed explicitly by lane and release. Nothing is implicit.
  const [previewEntries, setPreviewEntries] = useState<CatalogueEntry[]>([]);
  const [previewKey, setPreviewKey] = useState<string>("");
  const [previewFilter, setPreviewFilter] = useState("");
  const [uploadLane, setUploadLane] = useState<"CONFIGURED" | "KNOWLEDGE_PREVIEW">(
    "CONFIGURED",
  );

  useEffect(() => {
    let cancelled = false;
    studioApi
      .catalogue()
      .then((catalogue) => {
        if (cancelled) return;
        setPreviewEntries(
          catalogue.messages.filter(
            (entry) => entry.lane === "KNOWLEDGE_PREVIEW" && entry.generatable,
          ),
        );
      })
      .catch(() => {
        /* the configured templates above do not depend on the knowledge base */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredPreview = useMemo(() => {
    const needle = previewFilter.trim().toLowerCase();
    const list = needle
      ? previewEntries.filter((entry) =>
          `${entry.messageType} ${entry.name} ${entry.version ?? ""} ${entry.release ?? ""}`
            .toLowerCase()
            .includes(needle),
        )
      : previewEntries;
    return list.slice(0, 200);
  }, [previewEntries, previewFilter]);

  const previewEntry = useMemo(
    () => previewEntries.find((entry) => entryKey(entry) === previewKey) ?? null,
    [previewEntries, previewKey],
  );
  const previewRef = previewEntry ? messageRef(previewEntry) : null;

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setResponse(null);
    try {
      const laneOptions =
        uploadLane === "KNOWLEDGE_PREVIEW" && previewEntry && previewRef
          ? { lane: previewEntry.lane, release: previewRef.release }
          : undefined;
      const result = await studioApi.generateFromExcel(file, "BASE_DEMO_V1", laneOptions);
      setResponse(result);
      setOpenScenario(result.results[0]?.scenarioId ?? null);
    } catch (caught) {
      setError(
        caught instanceof StudioError
          ? caught.message
          : "The workbook could not be processed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        {TEMPLATES.map((template) => (
          <div
            key={template.format}
            className="flex min-w-0 flex-col gap-3 rounded-lg border border-line bg-panel p-5 shadow-[var(--shadow-1)]"
          >
            <div className="flex items-center gap-2">
              <FormatBadge format={template.format} />
              <h2 className="text-[1.0625rem] font-semibold tracking-[-0.01em]">
                {template.title}
              </h2>
            </div>
            <p className="text-sm leading-6 text-ink-2">{template.body}</p>
            <p className="rounded-md bg-sunken px-3 py-2 font-mono text-[0.6875rem] leading-5 text-ink-2">
              {template.columns}
            </p>
            <a
              href={studioApi.templateUrl(template.format)}
              className="mt-auto inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line-2 bg-panel px-4 text-sm font-medium transition-colors duration-150 hover:bg-rail"
            >
              <Icon name="download" className="h-4 w-4" />
              Download {template.format} template
            </a>
          </div>
        ))}
      </div>

      <Panel
        title="Knowledge-preview template"
        description="A workbook for one message the knowledge base compiled from its sources — future releases and messages outside the configured set. Generation in this lane is structure-backed; rules are not established."
      >
        {previewEntries.length === 0 ? (
          <p className="text-sm leading-6 text-ink-2" data-testid="excel-preview-empty">
            No generation-ready preview messages. Sync the knowledge base (
            <code className="font-mono text-ink">make knowledge-sync</code>) to add them.
          </p>
        ) : (
          <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] md:items-end">
            <label className="flex min-w-0 flex-col gap-1 text-sm">
              <span className="text-ink-2">Filter</span>
              <input
                type="search"
                value={previewFilter}
                onChange={(event) => setPreviewFilter(event.target.value)}
                placeholder="MT103, pacs.008, SR2026…"
                className="h-10 w-full min-w-0 rounded-md border border-line-2 bg-panel px-3 text-sm"
                data-testid="excel-preview-filter"
              />
            </label>
            <label className="flex min-w-0 flex-col gap-1 text-sm">
              <span className="text-ink-2">Message · release</span>
              <select
                value={previewKey}
                onChange={(event) => setPreviewKey(event.target.value)}
                className="h-10 w-full min-w-0 max-w-full truncate rounded-md border border-line-2 bg-panel px-3 text-sm"
                data-testid="excel-preview-select"
              >
                <option value="">Choose a preview message…</option>
                {filteredPreview.map((entry) => (
                  <option key={entryKey(entry)} value={entryKey(entry)}>
                    {entry.format} · {entry.version ?? entry.messageType} ·{" "}
                    {entry.release ?? "—"} · {entry.name}
                  </option>
                ))}
              </select>
            </label>
            {previewEntry && previewRef ? (
              <a
                href={studioApi.templateUrl(previewEntry.format, previewRef.messageType, {
                  lane: previewEntry.lane,
                  release: previewRef.release,
                })}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line-2 bg-panel px-4 text-sm font-medium transition-colors duration-150 hover:bg-rail"
                data-testid="excel-preview-download"
              >
                <Icon name="download" className="h-4 w-4" />
                Download template
              </a>
            ) : (
              <span className="inline-flex h-10 items-center px-1 text-sm text-ink-3">
                Pick a message to download
              </span>
            )}
          </div>
        )}
        {previewEntry && (
          <p className="mt-3 text-xs leading-5 text-ink-2" data-testid="excel-preview-note">
            <Badge tone="neutral">KNOWLEDGE_PREVIEW</Badge> {previewEntry.readinessLabel} ·
            structure source {previewEntry.structureSource ?? "—"}. Upload the filled workbook
            below with the lane set to knowledge preview.
          </p>
        )}
      </Panel>

      <Panel
        title="Upload a workbook"
        description="Each ScenarioID becomes one message. A scenario that fails does not stop the others."
      >
        <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
          <span className="text-ink-2">Generate in lane</span>
          <label className="inline-flex items-center gap-1.5">
            <input
              type="radio"
              name="excel-lane"
              checked={uploadLane === "CONFIGURED"}
              onChange={() => setUploadLane("CONFIGURED")}
            />
            Configured
          </label>
          <label className="inline-flex items-center gap-1.5">
            <input
              type="radio"
              name="excel-lane"
              checked={uploadLane === "KNOWLEDGE_PREVIEW"}
              disabled={!previewEntry}
              onChange={() => setUploadLane("KNOWLEDGE_PREVIEW")}
              data-testid="excel-lane-preview"
            />
            Knowledge preview
            {previewEntry
              ? ` (${previewEntry.version ?? previewEntry.messageType}${
                  previewEntry.release && previewEntry.format === "MT"
                    ? ` · ${previewEntry.release}`
                    : ""
                })`
              : " — pick a preview message first"}
          </label>
        </div>
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const file = event.dataTransfer.files[0];
            if (file) void upload(file);
          }}
          className={cx(
            "flex flex-col items-center gap-3 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors duration-150",
            dragging ? "border-accent bg-accent-sk" : "border-line-2 bg-sunken",
          )}
        >
          <span className="flex h-11 w-11 items-center justify-center rounded-md border border-line bg-panel text-ink-3">
            <Icon name="sheet" />
          </span>
          <p className="text-sm font-medium">Drop an .xlsx workbook here</p>
          <p className="max-w-[46ch] text-sm leading-6 text-ink-2">
            Or choose a file. The format is detected from the columns — a Tag column means
            MT, an XPath column means MX.
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx"
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
              event.target.value = "";
            }}
          />
          <Button
            variant="primary"
            loading={busy}
            icon="sheet"
            onClick={() => inputRef.current?.click()}
          >
            Choose a workbook
          </Button>
        </div>

        {error && (
          <div className="mt-4">
            <ErrorNotice title="The workbook could not be used" message={error} />
          </div>
        )}
      </Panel>

      {response && <ExcelResults response={response} open={openScenario} onOpen={setOpenScenario} />}

      {!response && !busy && !error && (
        <p className="flex items-start gap-2.5 rounded-md border border-line bg-sunken px-4 py-3 text-sm leading-6 text-ink-2">
          <Icon name="terminal" className="mt-0.5 h-4 w-4 shrink-0 text-ink-3" />
          <span>
            Prefer to do this from a pipeline? The same workflow is one HTTP call —{" "}
            <code className="font-mono text-ink">
              POST /api/v1/messages/generate-from-excel
            </code>
            . The API and Automation page has a working curl and REST Assured example.
          </span>
        </p>
      )}
    </div>
  );
}

function ExcelResults({
  response,
  open,
  onOpen,
}: {
  response: ExcelGenerateResponse;
  open: string | null;
  onOpen: (scenarioId: string | null) => void;
}) {
  return (
    <Panel
      title={`${response.totalScenarios} ${
        response.totalScenarios === 1 ? "scenario" : "scenarios"
      } processed`}
      description={`${response.generated} generated, ${response.failed} need attention.`}
      action={<FormatBadge format={response.format} />}
      bodyClassName="px-0 py-0"
    >
      <ul className="divide-y divide-line">
        {response.results.map((scenario) => (
          <ScenarioRow
            key={scenario.scenarioId}
            scenario={scenario}
            expanded={open === scenario.scenarioId}
            onToggle={() => onOpen(open === scenario.scenarioId ? null : scenario.scenarioId)}
          />
        ))}
      </ul>
    </Panel>
  );
}

function ScenarioRow({
  scenario,
  expanded,
  onToggle,
}: {
  scenario: ExcelScenarioResult;
  expanded: boolean;
  onToggle: () => void;
}) {
  const tone =
    scenario.status === "GENERATED" ? "ok" : scenario.status === "INVALID" ? "bad" : "warn";

  /* The proof sheet wants a full result; an Excel scenario carries everything it needs. */
  const asResult: GenerateResult | null =
    scenario.outputs && scenario.validation
      ? {
          messageId: scenario.messageId,
          correlationId: scenario.scenarioId,
          scenarioId: scenario.scenarioId,
          format: scenario.format ?? "MT",
          messageType: scenario.messageType ?? "",
          version: null,
          profileId: "BASE_DEMO_V1",
          profileVersion: "",
          valid: scenario.valid,
          validation: scenario.validation,
          outputs: scenario.outputs,
          envelopeFields: [],
          renderedLines: [],
          checksum: scenario.checksum ?? "",
          // The lane the API generated the scenario in, and what that rests on.
          lane: scenario.lane ?? "CONFIGURED",
          provenance: scenario.provenance ?? null,
          availableOutputModes: (
            ["FIN", "BLOCK4", "TXT", "XML", "APPHDR", "DOCUMENT", "CANONICAL_JSON"] as const
          ).filter((mode) => {
            const outputs = scenario.outputs!;
            return mode === "FIN"
              ? Boolean(outputs.fin)
              : mode === "BLOCK4"
                ? Boolean(outputs.block4)
                : mode === "TXT"
                  ? Boolean(outputs.txt)
                  : mode === "XML"
                    ? Boolean(outputs.xml)
                    : mode === "APPHDR"
                      ? Boolean(outputs.appHdr)
                      : mode === "DOCUMENT"
                        ? Boolean(outputs.document)
                        : Boolean(outputs.canonicalJson);
          }),
          generatedAt: new Date().toISOString(),
          disclaimer: "",
        }
      : null;

  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center gap-4 px-5 py-3.5 text-left transition-colors duration-150 hover:bg-rail"
      >
        <Icon
          name="chevron-right"
          className={cx(
            "h-4 w-4 shrink-0 text-ink-3 transition-transform duration-200",
            expanded && "rotate-90",
          )}
        />
        <span className="w-32 shrink-0 truncate font-mono text-[0.8125rem] font-semibold">
          {scenario.scenarioId}
        </span>
        <span className="w-24 shrink-0 font-mono text-[0.8125rem] text-ink-2">
          {scenario.messageType ?? "—"}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm text-ink-2">
          {scenario.validation?.summary ?? "Could not be read"}
        </span>
        <span className="hidden shrink-0 text-xs text-ink-3 tnum sm:block">
          rows {scenario.rowNumbers[0]}–{scenario.rowNumbers[scenario.rowNumbers.length - 1]}
        </span>
        <Badge tone={tone}>
          {scenario.status === "GENERATED"
            ? "Generated"
            : scenario.status === "INVALID"
              ? "Has errors"
              : "Failed"}
        </Badge>
      </button>
      {expanded && (
        <div className="animate-settle space-y-4 border-t border-line bg-sunken px-5 py-5">
          {scenario.validation && <ValidationPanel validation={scenario.validation} />}
          {asResult && <ProofSheet result={asResult} />}
        </div>
      )}
    </li>
  );
}
