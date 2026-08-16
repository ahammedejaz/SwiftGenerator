"use client";

/**
 * What changed between the message you imported and the one the studio just built.
 *
 * The design problem is not showing a diff — it is stopping a tester from reading an
 * expected difference as a fault. A regenerated message almost always differs from the one
 * that was pasted, and almost always for a reason that does not matter: a value they edited,
 * a field written back in specification order, a trailer the studio refuses to invent. So
 * the verdict comes first, in one sentence, and every line carries the reason it differs.
 *
 * One number is worth acting on — unexplained differences — and it is the only one shown in
 * the alarming colour. Content dropped on import is worth knowing about and is shown next to
 * it. Everything else is counted as expected and stated plainly.
 *
 * A unified diff rather than side-by-side: FIN lines and ISO 20022 elements are long, and
 * two columns at 390px would mean reading each of them at half width.
 */

import { useState } from "react";
import { Icon } from "@/components/studio/Icon";
import { Badge, Button, CopyButton, cx, Panel } from "@/components/studio/ui";
import { saveText } from "@/lib/studio-api";
import type { DiffKind, DiffLine, DiffReason, MessageDiff as Diff } from "@/lib/studio-types";

const REASON_LABEL: Record<DiffReason, string> = {
  USER_EDIT: "You changed this",
  NORMALISATION: "Written the studio's way",
  IMPORT_DROPPED: "Could not be imported",
  NOT_REPRODUCED: "Never generated",
  UNEXPLAINED: "Unexplained",
};

const REASON_TONE: Record<DiffReason, "neutral" | "accent" | "ok" | "bad" | "warn"> = {
  USER_EDIT: "accent",
  NORMALISATION: "neutral",
  IMPORT_DROPPED: "warn",
  NOT_REPRODUCED: "neutral",
  UNEXPLAINED: "bad",
};

const KIND_MARK: Record<DiffKind, string> = {
  UNCHANGED: " ",
  ADDED: "+",
  REMOVED: "−",
  CHANGED: "~",
};

export function MessageDiffPanel({
  diff,
  regenerated,
  filename,
  onReturnToEdit,
}: {
  diff: Diff;
  /** The regenerated message text, for copy and download. */
  regenerated: string;
  filename: string;
  /** Omitted where there is no form to go back to, so the action is never a dead end. */
  onReturnToEdit?: () => void;
}) {
  const [onlyChanges, setOnlyChanges] = useState(true);
  const { summary } = diff;

  const visible = onlyChanges
    ? diff.lines.filter((line) => line.kind !== "UNCHANGED")
    : diff.lines;

  // Too large, or too broken, to list the differences of. The verdict is still worth
  // showing — and saying why there is no list beats an empty table.
  if (!diff.comparable) {
    return (
      <Panel title="Original and regenerated" bodyClassName="px-0 py-0">
        <Verdict summary={summary} comparable={false} />
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <p className="max-w-[60ch] text-sm leading-6 text-ink-2">
            {diff.notComparedReason}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <CopyButton value={regenerated} label="Copy regenerated" />
            <Button
              size="sm"
              variant="quiet"
              icon="download"
              onClick={() => saveText(filename, regenerated)}
            >
              Download regenerated
            </Button>
            {onReturnToEdit && (
              <Button size="sm" variant="quiet" icon="arrow-left" onClick={onReturnToEdit}>
                Return to edit
              </Button>
            )}
          </div>
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Original and regenerated"
      description={`Comparing ${diff.compared}. ${
        diff.basis === "CANONICAL_XML"
          ? "Layout and indentation are ignored; only structure and values are compared."
          : "Compared line by line, exactly as the message is written."
      }`}
      bodyClassName="px-0 py-0"
    >
      <Verdict summary={summary} comparable />

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <label className="inline-flex cursor-pointer items-center gap-2 text-[0.8125rem] text-ink-2">
          <input
            type="checkbox"
            checked={onlyChanges}
            onChange={(event) => setOnlyChanges(event.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          Show only changes
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <CopyButton value={regenerated} label="Copy regenerated" />
          <Button
            size="sm"
            variant="quiet"
            icon="download"
            onClick={() => saveText(filename, regenerated)}
          >
            Download regenerated
          </Button>
          {onReturnToEdit && (
            <Button size="sm" variant="quiet" icon="arrow-left" onClick={onReturnToEdit}>
              Return to edit
            </Button>
          )}
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="px-5 py-6 text-sm leading-6 text-ink-2">
          {summary.identical
            ? "The two messages are the same. Nothing was lost or rewritten."
            : "No differences to show. Clear “Show only changes” to read the whole message."}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-0 border-collapse font-mono text-[0.75rem]">
            <caption className="sr-only">
              Original message compared with the regenerated message
            </caption>
            <thead className="sr-only">
              <tr>
                <th scope="col">Original line</th>
                <th scope="col">Regenerated line</th>
                <th scope="col">Change</th>
                <th scope="col">Content</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((line, index) => (
                <DiffRow key={`${line.originalLine}-${line.regeneratedLine}-${index}`} line={line} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {diff.notes.length > 0 && (
        <div className="border-t border-line px-5 py-4">
          <p className="text-[0.8125rem] font-semibold text-ink">What the reasons mean</p>
          <ul className="mt-2 space-y-1.5">
            {diff.notes.map((note) => (
              <li key={note} className="text-[0.8125rem] leading-5 text-ink-2">
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

/** The one sentence a tester should be able to stop reading after. */
function Verdict({ summary, comparable }: { summary: Diff["summary"]; comparable: boolean }) {
  const needsAttention = summary.unexplained > 0;
  // Differences nobody accounted for are not good news, and a green tick above "these are
  // not the same" reads as reassurance the studio has not earned.
  const worthKnowing = summary.dropped > 0 || (!comparable && !summary.identical);
  const tone = needsAttention
    ? "border-bad/30 bg-bad/10"
    : worthKnowing
      ? "border-warn/30 bg-warn/10"
      : "border-ok/30 bg-ok/10";

  return (
    <div className={cx("border-b px-5 py-4", tone)}>
      <div className="flex items-start gap-3">
        <Icon
          name={needsAttention ? "alert" : worthKnowing ? "info" : "check"}
          className={cx(
            "mt-0.5 h-5 w-5 shrink-0",
            needsAttention ? "text-bad" : worthKnowing ? "text-warn" : "text-ok",
          )}
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink">{headline(summary)}</p>
          <p className="mt-1 text-sm leading-6 text-ink-2">{detail(summary)}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {summary.changed > 0 && <Badge>{summary.changed} changed</Badge>}
            {summary.added > 0 && <Badge>{summary.added} added</Badge>}
            {summary.removed > 0 && <Badge>{summary.removed} removed</Badge>}
            {summary.dropped > 0 && (
              <Badge tone="warn">{summary.dropped} could not be imported</Badge>
            )}
            {summary.unexplained > 0 && (
              <Badge tone="bad">{summary.unexplained} unexplained</Badge>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function headline(summary: Diff["summary"]): string {
  if (summary.identical) return "The regenerated message is identical";
  if (summary.changed + summary.added + summary.removed === 0) {
    return "The regenerated message is not the same as the one you imported";
  }
  if (summary.unexplained > 0) {
    return summary.unexplained === 1
      ? "One difference could not be explained"
      : `${summary.unexplained} differences could not be explained`;
  }
  if (summary.dropped > 0) {
    return summary.dropped === 1
      ? "One part of the original could not be imported"
      : `${summary.dropped} parts of the original could not be imported`;
  }
  return "Every difference is accounted for";
}

function detail(summary: Diff["summary"]): string {
  if (summary.identical) {
    return "Nothing was lost and nothing was rewritten — the studio rebuilt exactly what you pasted.";
  }
  if (summary.changed + summary.added + summary.removed === 0) {
    return "The two messages differ.";
  }
  if (summary.unexplained > 0) {
    return "Look at the lines marked Unexplained. Everything else is a value you changed, a field written the studio's way, or something the studio never generates.";
  }
  if (summary.dropped > 0) {
    return "The original held something outside the configured subset. It was reported when the message was read, and it is not in the regenerated message.";
  }
  return "The differences are values you changed, fields written in specification order, and values a messaging interface or the network supplies. None of them is a fault.";
}

function DiffRow({ line }: { line: DiffLine }) {
  const background =
    line.kind === "ADDED"
      ? "bg-ok/10"
      : line.kind === "REMOVED"
        ? "bg-bad/10"
        : line.kind === "CHANGED"
          ? "bg-warn/10"
          : undefined;

  return (
    <>
      {(line.kind === "REMOVED" || line.kind === "CHANGED") && (
        <tr className={background}>
          <Gutter number={line.originalLine} mark="−" />
          <Content text={line.originalText} line={line} strike={line.kind === "CHANGED"} />
        </tr>
      )}
      {(line.kind === "ADDED" || line.kind === "CHANGED") && (
        <tr className={background}>
          <Gutter number={line.regeneratedLine} mark="+" />
          <Content text={line.regeneratedText} line={line} showReason />
        </tr>
      )}
      {line.kind === "UNCHANGED" && (
        <tr>
          <Gutter number={line.regeneratedLine} mark={KIND_MARK.UNCHANGED} />
          <Content text={line.regeneratedText} line={line} />
        </tr>
      )}
    </>
  );
}

function Gutter({ number, mark }: { number: number | null; mark: string }) {
  return (
    <td className="w-16 select-none whitespace-nowrap border-r border-line px-2 py-0.5 text-right align-top text-ink-3 tabular-nums">
      <span aria-hidden="true">{mark}</span> {number ?? ""}
    </td>
  );
}

function Content({
  text,
  line,
  strike,
  showReason,
}: {
  text: string | null;
  line: DiffLine;
  strike?: boolean;
  showReason?: boolean;
}) {
  const reason = line.reason;
  const label =
    line.kind === "ADDED"
      ? "added"
      : line.kind === "REMOVED"
        ? "removed"
        : line.kind === "CHANGED"
          ? "changed"
          : "";
  return (
    <td className="min-w-0 px-3 py-0.5 align-top">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {/* Stated in words as well as colour, so nothing depends on being able to see it. */}
        {label && <span className="sr-only">{label}: </span>}
        <span className={cx("whitespace-pre-wrap break-all", strike && "line-through opacity-70")}>
          {text}
        </span>
        {reason && (showReason || line.kind === "REMOVED") && (
          <span className="inline-flex items-center gap-1.5 font-sans">
            <Badge tone={REASON_TONE[reason]}>{REASON_LABEL[reason]}</Badge>
            {line.field && <span className="text-[0.75rem] text-ink-3">{line.field}</span>}
          </span>
        )}
      </div>
    </td>
  );
}
