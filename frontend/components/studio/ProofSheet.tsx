"use client";

/**
 * The proof sheet — the generated message, presented as the artifact it is.
 *
 * Dark ground, monospaced, line-numbered, with margin annotations naming the business
 * field each line came from. It is the most important thing on any screen it appears on,
 * because it is the thing the user came for.
 */

import { useMemo, useState } from "react";
import { Icon } from "@/components/studio/Icon";
import { Badge, Button, CopyButton, cx } from "@/components/studio/ui";
import { saveText, studioApi } from "@/lib/studio-api";
import type { GenerateResult, OutputMode } from "@/lib/studio-types";
import { ORIGIN_LABEL, OUTPUT_LABEL } from "@/lib/studio-types";

const FILE_EXTENSION: Record<OutputMode, string> = {
  BLOCK4: "block4.txt",
  FIN: "fin",
  TXT: "txt",
  CANONICAL_JSON: "canonical.json",
  XML: "xml",
  APPHDR: "apphdr.xml",
  DOCUMENT: "document.xml",
};

function outputText(result: GenerateResult, mode: OutputMode): string | null {
  const { outputs } = result;
  switch (mode) {
    case "BLOCK4":
      return outputs.block4;
    case "FIN":
      return outputs.fin;
    case "TXT":
      return outputs.txt;
    case "XML":
      return outputs.xml;
    case "APPHDR":
      return outputs.appHdr;
    case "DOCUMENT":
      return outputs.document;
    case "CANONICAL_JSON":
      return outputs.canonicalJson ? JSON.stringify(outputs.canonicalJson, null, 2) : null;
  }
}

export function ProofSheet({
  result,
  onGenerateAnother,
}: {
  result: GenerateResult;
  onGenerateAnother?: () => void;
}) {
  const available = useMemo(
    () => result.availableOutputModes.filter((mode) => outputText(result, mode) !== null),
    [result],
  );
  const [mode, setMode] = useState<OutputMode>(
    available.includes(result.format === "MT" ? "FIN" : "XML")
      ? result.format === "MT"
        ? "FIN"
        : "XML"
      : (available[0] ?? "TXT"),
  );

  const text = outputText(result, mode) ?? "";
  const lines = text.split("\n");

  /* Annotations only line up with the primary rendering, not with derived views. */
  const annotated =
    (result.format === "MT" && mode === "FIN") || (result.format === "MX" && mode === "XML");
  const annotationByLine = useMemo(() => {
    const map = new Map<number, string>();
    if (!annotated) return map;
    for (const line of result.renderedLines) {
      if (line.displayName) map.set(line.lineNumber, line.displayName);
    }
    return map;
  }, [annotated, result.renderedLines]);

  /* FIN prefixes blocks 1-3 ahead of the block 4 the renderer numbered from. */
  const lineOffset = useMemo(() => {
    if (!annotated || result.format !== "MT") return 0;
    const index = lines.findIndex((line) => line.startsWith("{4:"));
    return index > 0 ? index : 0;
  }, [annotated, lines, result.format]);

  const stem = `${result.messageType.replace(/\./g, "_")}_${
    result.scenarioId ?? result.correlationId.slice(0, 8)
  }`;

  return (
    <div className="proof animate-proof min-w-0 overflow-hidden rounded-lg border border-proof-line bg-proof shadow-[var(--shadow-3)]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-proof-line px-4 py-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="font-mono text-[0.8125rem] font-semibold text-proof-ink">
            {result.messageType}
            {result.version && (
              <span className="ml-1.5 font-normal text-proof-dim">{result.version}</span>
            )}
          </span>
          <span
            className={cx(
              "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-xs font-medium",
              result.valid
                ? "border-ok/40 bg-ok/15 text-[#7fca9f]"
                : "border-bad/40 bg-bad/15 text-[#e79a9a]",
            )}
          >
            <Icon name={result.valid ? "check" : "alert"} className="h-3.5 w-3.5" />
            {result.valid ? "Valid" : "Has errors"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <CopyButton value={text} label="Copy" onProof />
          <Button
            size="sm"
            variant="proof"
            icon="download"
            onClick={() =>
              result.messageId
                ? window.open(studioApi.downloadUrl(result.messageId, mode), "_blank")
                : saveText(`${stem}.${FILE_EXTENSION[mode]}`, text)
            }
          >
            Download
          </Button>
          {onGenerateAnother && (
            <Button
              size="sm"
              variant="proof"
              icon="refresh"
              onClick={onGenerateAnother}
            >
              Generate another
            </Button>
          )}
        </div>
      </header>

      {available.length > 1 && (
        <div
          role="tablist"
          aria-label="Output format"
          className="flex flex-wrap gap-0.5 border-b border-proof-line px-3 py-2"
        >
          {available.map((option) => (
            <button
              key={option}
              type="button"
              role="tab"
              aria-selected={option === mode}
              onClick={() => setMode(option)}
              className={cx(
                "rounded-sm px-2.5 py-1 text-xs font-medium transition-colors duration-150",
                option === mode
                  ? "bg-proof-line text-proof-ink"
                  : "text-proof-dim hover:text-proof-ink",
              )}
            >
              {OUTPUT_LABEL[option]}
            </button>
          ))}
        </div>
      )}

      <div className="scroll-slim on-proof max-h-[32rem] overflow-auto">
        <table className="w-full border-collapse font-mono text-[0.8125rem] leading-[1.55]">
          <tbody>
            {lines.map((line, index) => {
              const annotation = annotationByLine.get(index + 1 - lineOffset);
              return (
                <tr key={index} className="group">
                  <td className="w-11 select-none border-r border-proof-line/70 py-px pr-2 text-right align-top text-[0.6875rem] text-proof-dim tnum">
                    {index + 1}
                  </td>
                  <td className="whitespace-pre py-px pl-3 pr-4 align-top text-proof-ink">
                    {line || " "}
                  </td>
                  <td className="hidden w-[15rem] py-px pr-4 align-top text-[0.6875rem] leading-[1.55] text-proof-dim lg:table-cell">
                    {annotation}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <footer className="flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-proof-line px-4 py-2.5 text-[0.6875rem] text-proof-dim">
        <span>
          Profile <span className="text-proof-ink">{result.profileId}</span> v
          {result.profileVersion}
        </span>
        <span className="font-mono">
          SHA-256 <span className="text-proof-ink">{result.checksum.slice(0, 16)}</span>
        </span>
        <span className="font-mono">
          Correlation <span className="text-proof-ink">{result.correlationId.slice(0, 8)}</span>
        </span>
        <span>{lines.length} lines</span>
      </footer>
    </div>
  );
}

/**
 * Who is accountable for each envelope value. This is the screen that answers "where did
 * that number come from?" — and shows what the platform deliberately did not produce.
 */
export function EnvelopeTable({ result }: { result: GenerateResult }) {
  const [open, setOpen] = useState(false);
  if (result.envelopeFields.length === 0) return null;

  return (
    <div className="rounded-lg border border-line bg-panel shadow-[var(--shadow-1)]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 rounded-lg px-5 py-3.5 text-left transition-colors duration-150 hover:bg-rail"
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold">
            {result.format === "MT" ? "Envelope values" : "Header values"}
          </span>
          <span className="mt-0.5 block text-[0.8125rem] leading-6 text-ink-2">
            Where each value came from, and what the platform deliberately did not produce.
          </span>
        </span>
        <Icon
          name="chevron-down"
          className={cx(
            "h-5 w-5 shrink-0 text-ink-3 transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="scroll-slim overflow-x-auto border-t border-line">
          <table className="w-full min-w-[46rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line bg-rail text-left text-xs uppercase tracking-[0.04em] text-ink-3">
                <th className="px-5 py-2 font-medium">Block</th>
                <th className="px-3 py-2 font-medium">Value</th>
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium">Why</th>
              </tr>
            </thead>
            <tbody>
              {result.envelopeFields.map((field) => (
                <tr key={`${field.block}-${field.name}`} className="border-b border-line last:border-0">
                  <td className="px-5 py-2.5 align-top">
                    <span className="block text-[0.8125rem] font-medium">{field.name}</span>
                    <span className="mt-0.5 block font-mono text-[0.6875rem] text-ink-3">
                      Block {field.block}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 align-top font-mono text-[0.8125rem]">
                    {field.value ?? <span className="text-ink-3">not written</span>}
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <Badge
                      tone={
                        field.origin === "USER_ENTERED"
                          ? "accent"
                          : field.origin === "NETWORK_GENERATED" ||
                              field.origin === "INTERFACE_GENERATED"
                            ? "warn"
                            : "neutral"
                      }
                    >
                      {ORIGIN_LABEL[field.origin]}
                    </Badge>
                  </td>
                  <td className="max-w-[26rem] px-3 py-2.5 align-top text-[0.8125rem] leading-6 text-ink-2">
                    {field.explanation}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
