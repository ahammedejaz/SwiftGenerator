"use client";

/**
 * Validation as a manual tester needs to read it.
 *
 * The headline is plain English — "Ready to generate" or "3 issues need attention" — and
 * each issue names the field, the problem, what was expected, and what to do about it.
 * Rule ids and layer names are present but secondary; a tester should never have to read
 * one to fix their message.
 */

import { useState } from "react";
import { Icon } from "@/components/studio/Icon";
import { Badge, cx } from "@/components/studio/ui";
import type { ValidationIssue, ValidationResult } from "@/lib/studio-types";
import { LAYER_LABEL } from "@/lib/studio-types";

export function ValidationPanel({
  validation,
  onFocusField,
}: {
  validation: ValidationResult;
  onFocusField?: (location: string) => void;
}) {
  const [showLayers, setShowLayers] = useState(false);
  const { errors, warnings, valid } = validation;

  return (
    <div
      className={cx(
        "overflow-hidden rounded-lg border shadow-[var(--shadow-1)]",
        valid ? "border-ok/25 bg-ok-sk" : "border-bad/25 bg-bad-sk",
      )}
    >
      <div className="flex items-start gap-3 px-5 py-4">
        <span
          className={cx(
            "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
            valid ? "bg-ok text-white" : "bg-bad text-white",
          )}
        >
          <Icon name={valid ? "check" : "alert"} className="h-4 w-4" strokeWidth={2} />
        </span>
        <div className="min-w-0 flex-1">
          <p
            className={cx(
              "text-[1.0625rem] font-semibold tracking-[-0.01em]",
              valid ? "text-ok" : "text-bad",
            )}
          >
            {validation.summary}
          </p>
          <p className="mt-0.5 text-sm leading-6 text-ink-2">
            {valid
              ? warnings.length > 0
                ? `Everything required is present. ${
                    warnings.length === 1 ? "One note" : `${warnings.length} notes`
                  } below worth reading.`
                : "Everything required is present and every value matches its expected format."
              : "Fix the items below and the message will generate."}
          </p>
        </div>
      </div>

      {(errors.length > 0 || warnings.length > 0) && (
        <ul className="divide-y divide-line border-t border-line bg-panel">
          {errors.map((issue, index) => (
            <IssueRow key={`e${index}`} issue={issue} onFocusField={onFocusField} />
          ))}
          {warnings.map((issue, index) => (
            <IssueRow key={`w${index}`} issue={issue} onFocusField={onFocusField} />
          ))}
        </ul>
      )}

      <div className="border-t border-line bg-panel">
        <button
          type="button"
          onClick={() => setShowLayers(!showLayers)}
          aria-expanded={showLayers}
          className="flex w-full items-center justify-between gap-3 px-5 py-2.5 text-left text-[0.8125rem] text-ink-2 transition-colors duration-150 hover:bg-rail"
        >
          <span>What was checked</span>
          <Icon
            name="chevron-down"
            className={cx(
              "h-4 w-4 text-ink-3 transition-transform duration-200",
              showLayers && "rotate-180",
            )}
          />
        </button>
        {showLayers && (
          <ul className="grid gap-x-6 gap-y-1.5 border-t border-line px-5 py-3.5 sm:grid-cols-2">
            {validation.layers.map((layer) => (
              <li key={layer.layer} className="flex items-start gap-2 text-[0.8125rem]">
                <LayerMark state={layer.state} />
                <span className="min-w-0">
                  <span className="text-ink">{LAYER_LABEL[layer.layer]}</span>
                  {layer.detail && layer.state !== "PASSED" && (
                    <span className="mt-0.5 block text-xs leading-5 text-ink-3">
                      {layer.detail}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function IssueRow({
  issue,
  onFocusField,
}: {
  issue: ValidationIssue;
  onFocusField?: (location: string) => void;
}) {
  const isError = issue.severity === "ERROR";
  return (
    <li className="px-5 py-3.5">
      <div className="flex items-start gap-2.5">
        <Icon
          name={isError ? "alert" : "info"}
          className={cx("mt-0.5 h-4 w-4 shrink-0", isError ? "text-bad" : "text-warn")}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            {issue.field && (
              <span className="text-sm font-semibold text-ink">
                {issue.field} needs attention
              </span>
            )}
            <Badge tone={isError ? "bad" : "warn"}>{isError ? "Error" : "Note"}</Badge>
          </div>
          <p className="mt-1 text-sm leading-6 text-ink">{issue.message}</p>
          {issue.suggestion && (
            <p className="mt-1 text-sm leading-6 text-ink-2">
              <span className="font-medium text-ink">What to do: </span>
              {issue.suggestion}
            </p>
          )}
          {(issue.expected || issue.currentValue) && (
            <dl className="mt-1.5 flex flex-wrap gap-x-6 gap-y-0.5 text-xs leading-5">
              {issue.expected && (
                <div className="flex gap-1.5">
                  <dt className="text-ink-3">Expected</dt>
                  <dd className="font-mono text-ink-2">{issue.expected}</dd>
                </div>
              )}
              {issue.currentValue && (
                <div className="flex gap-1.5">
                  <dt className="text-ink-3">You entered</dt>
                  <dd className="font-mono text-ink-2">{issue.currentValue}</dd>
                </div>
              )}
            </dl>
          )}
          {issue.location && onFocusField && (
            <button
              type="button"
              onClick={() => onFocusField(issue.location as string)}
              className="mt-1.5 inline-flex items-center gap-1 rounded-sm text-[0.8125rem] font-medium text-accent underline decoration-accent/30 underline-offset-2 transition-colors duration-150 hover:text-accent-2"
            >
              <Icon name="arrow-left" className="h-3.5 w-3.5 rotate-180" />
              Go to this field
            </button>
          )}
          {/* The rule id and the layer stay available for an automation tester filing a
              defect, and stay out of the way of a manual tester fixing one. `ruleId` is a
              stable API value and is never the sentence a person is asked to decode.
              Where the finding came from an installed rule pack, the pack and the source
              location that established the rule sit here too — a reviewer's trail, not a
              tester's reading. Candidate rules never reach this screen: only reviewed,
              source-controlled packs are ever loaded. */}
          <details className="mt-1.5 group">
            <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-[0.6875rem] text-ink-3 transition-colors duration-150 hover:text-ink-2">
              <Icon
                name="chevron-down"
                className="h-3 w-3 transition-transform duration-200 group-open:rotate-180"
              />
              Technical details
            </summary>
            <dl className="mt-1 flex flex-wrap gap-x-5 gap-y-0.5 font-mono text-[0.6875rem] text-ink-3">
              <div className="flex gap-1.5">
                <dt>Rule</dt>
                <dd className="text-ink-2">{issue.ruleId}</dd>
              </div>
              {issue.location && (
                <div className="flex gap-1.5">
                  <dt>Field</dt>
                  <dd className="text-ink-2">{issue.location}</dd>
                </div>
              )}
              <div className="flex gap-1.5">
                <dt>Layer</dt>
                <dd className="text-ink-2">{issue.ruleLayer ?? issue.layer}</dd>
              </div>
              {issue.rulePackId && (
                <div className="flex gap-1.5">
                  <dt>Rule pack</dt>
                  <dd className="text-ink-2">{issue.rulePackId}</dd>
                </div>
              )}
              {issue.sourceReference && (
                <div className="flex gap-1.5">
                  <dt>Source</dt>
                  <dd className="text-ink-2">{issue.sourceReference}</dd>
                </div>
              )}
              {issue.reviewStatus && (
                <div className="flex gap-1.5">
                  <dt>Review</dt>
                  <dd className="text-ink-2">{issue.reviewStatus}</dd>
                </div>
              )}
            </dl>
          </details>
        </div>
      </div>
    </li>
  );
}

function LayerMark({ state }: { state: string }) {
  if (state === "PASSED") {
    return <Icon name="check" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ok" strokeWidth={2} />;
  }
  if (state === "FAILED") {
    return <Icon name="close" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-bad" strokeWidth={2} />;
  }
  return <Icon name="minus" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-3" strokeWidth={2} />;
}
