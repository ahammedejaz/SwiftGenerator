"use client";

/**
 * Recent Messages — find what you generated a few minutes ago and download it again.
 * Short-lived by design: this is a working surface, not a system of record.
 */

import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/studio/Icon";
import { ProofSheet } from "@/components/studio/ProofSheet";
import {
  Badge,
  Button,
  EmptyState,
  ErrorNotice,
  FormatBadge,
  SegmentedControl,
  Skeleton,
  cx,
} from "@/components/studio/ui";
import { apiUrl } from "@/lib/api-client";
import { StudioError, studioApi } from "@/lib/studio-api";
import type {
  GenerateResult,
  MessageFormat,
  MessageOutputs,
  RecentMessage,
} from "@/lib/studio-types";

type Filter = "ALL" | MessageFormat;

export function RecentMessages() {
  const [filter, setFilter] = useState<Filter>("ALL");
  const [messages, setMessages] = useState<RecentMessage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [opened, setOpened] = useState<GenerateResult | null>(null);
  const [openBusy, setOpenBusy] = useState(false);

  // A reload token keeps the fetch inside the effect, so refreshing is a state change
  // rather than a second path through the same code.
  const [reloadToken, setReloadToken] = useState(0);
  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    let cancelled = false;
    studioApi
      .recent(50, filter === "ALL" ? undefined : filter)
      .then((rows) => {
        if (cancelled) return;
        setMessages(rows);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(
          caught instanceof StudioError
            ? caught.message
            : "Recent messages could not be loaded.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [filter, reloadToken]);

  async function open(message: RecentMessage) {
    if (openId === message.messageId) {
      setOpenId(null);
      setOpened(null);
      return;
    }
    setOpenId(message.messageId);
    setOpened(null);
    setOpenBusy(true);
    try {
      const response = await fetch(apiUrl(`/api/v1/messages/id/${message.messageId}`));
      const body = (await response.json()) as {
        message: RecentMessage;
        outputs: MessageOutputs;
      };
      setOpened({
        messageId: message.messageId,
        correlationId: message.correlationId,
        scenarioId: message.scenarioId,
        format: message.format,
        messageType: message.messageType,
        version: null,
        profileId: message.profileId,
        profileVersion: "",
        valid: message.valid,
        validation: {
          valid: message.valid,
          summary: message.valid ? "Ready to generate" : "Has errors",
          layers: [],
          errors: [],
          warnings: [],
        },
        outputs: body.outputs,
        lane: "CONFIGURED",
        provenance: null,
        envelopeFields: [],
        renderedLines: [],
        checksum: message.checksum,
        availableOutputModes: availableModes(body.outputs),
        generatedAt: message.createdAt,
        disclaimer: "",
      });
    } catch {
      setError("That message could not be opened.");
    } finally {
      setOpenBusy(false);
    }
  }

  if (error) return <ErrorNotice message={error} onRetry={reload} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          label="Filter by standard"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "ALL", label: "Both" },
            { value: "MT", label: "MT" },
            { value: "MX", label: "MX" },
          ]}
        />
        <Button variant="secondary" icon="refresh" onClick={reload}>
          Refresh
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-[var(--shadow-1)]">
        {messages === null ? (
          <div className="space-y-2 p-5">
            {[0, 1, 2, 3, 4].map((row) => (
              <Skeleton key={row} className="h-12 w-full" />
            ))}
          </div>
        ) : messages.length === 0 ? (
          <EmptyState icon="clock" title="Nothing generated yet">
            Messages you generate — in the browser, from a spreadsheet, or from a pipeline —
            appear here so you can download them again without rebuilding the scenario.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {messages.map((message) => (
              <li key={message.messageId}>
                <button
                  type="button"
                  onClick={() => void open(message)}
                  aria-expanded={openId === message.messageId}
                  className="flex w-full items-center gap-3 px-5 py-3 text-left transition-colors duration-150 hover:bg-rail"
                >
                  <Icon
                    name="chevron-right"
                    className={cx(
                      "h-4 w-4 shrink-0 text-ink-3 transition-transform duration-200",
                      openId === message.messageId && "rotate-90",
                    )}
                  />
                  <FormatBadge format={message.format} />
                  <span className="w-24 shrink-0 font-mono text-[0.8125rem] font-semibold">
                    {message.messageType}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm text-ink-2">
                    {message.scenarioId ?? <span className="text-ink-3">no scenario label</span>}
                  </span>
                  <span className="hidden shrink-0 font-mono text-[0.6875rem] text-ink-3 lg:block">
                    {message.checksum.slice(0, 10)}
                  </span>
                  <span className="hidden w-36 shrink-0 text-xs text-ink-3 tnum sm:block">
                    {formatWhen(message.createdAt)}
                  </span>
                  <Badge tone={message.valid ? "ok" : "bad"}>
                    {message.valid ? "Valid" : `${message.errorCount} errors`}
                  </Badge>
                </button>
                {openId === message.messageId && (
                  <div className="animate-settle border-t border-line bg-sunken px-5 py-5">
                    {openBusy && !opened ? (
                      <Skeleton className="h-64 w-full" />
                    ) : opened ? (
                      <ProofSheet result={opened} />
                    ) : null}
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <a
                        href={studioApi.evidenceUrl(message.messageId)}
                        className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line-2 bg-panel px-3 text-[0.8125rem] font-medium transition-colors duration-150 hover:bg-rail"
                      >
                        <Icon name="download" className="h-4 w-4" />
                        Evidence ZIP
                      </a>
                      <span className="text-xs text-ink-3">
                        Every output plus the validation report and the inputs you supplied.
                      </span>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function availableModes(outputs: MessageOutputs) {
  const modes: GenerateResult["availableOutputModes"] = [];
  if (outputs.block4) modes.push("BLOCK4");
  if (outputs.fin) modes.push("FIN");
  if (outputs.txt) modes.push("TXT");
  if (outputs.xml) modes.push("XML");
  if (outputs.appHdr) modes.push("APPHDR");
  if (outputs.document) modes.push("DOCUMENT");
  if (outputs.canonicalJson) modes.push("CANONICAL_JSON");
  return modes;
}

function formatWhen(iso: string): string {
  const then = new Date(iso);
  const seconds = Math.round((Date.now() - then.getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
