"use client";

/**
 * The field editor for step 5 of the wizard.
 *
 * Progressive disclosure is the whole design: required fields are visible, optional fields
 * are behind "Add optional field", and repeatable groups grow with "Add another". A manual
 * tester should never face eighty empty inputs.
 *
 * Every field can explain itself inline — never in a modal, never with a model call.
 */

import { useMemo, useState } from "react";
import { Icon } from "@/components/studio/Icon";
import {
  Badge,
  Button,
  InfoButton,
  PresenceBadge,
  Select,
  TextInput,
  cx,
} from "@/components/studio/ui";
import type { MessageSpec, SpecField } from "@/lib/studio-types";

export type FieldValues = Record<string, string>;

/** Composite key so one spec field can hold a value per repeated-group occurrence. */
export function slotKey(fieldId: string, occurrence: number) {
  return occurrence === 1 ? fieldId : `${fieldId}#${occurrence}`;
}

export function parseSlot(key: string): { fieldId: string; occurrence: number } {
  const hash = key.lastIndexOf("#");
  if (hash === -1) return { fieldId: key, occurrence: 1 };
  return { fieldId: key.slice(0, hash), occurrence: Number(key.slice(hash + 1)) || 1 };
}

export function FieldEditor({
  spec,
  values,
  onChange,
  occurrences,
  onAddOccurrence,
  onRemoveOccurrence,
  revealed,
  onReveal,
  onHide,
  invalidLocations,
  focusedLocation,
}: {
  spec: MessageSpec;
  values: FieldValues;
  onChange: (key: string, value: string) => void;
  occurrences: Record<string, number>;
  onAddOccurrence: (groupId: string) => void;
  onRemoveOccurrence: (groupId: string) => void;
  revealed: Set<string>;
  onReveal: (fieldId: string) => void;
  onHide: (fieldId: string) => void;
  invalidLocations: Set<string>;
  focusedLocation: string | null;
}) {
  const groups = useMemo(() => {
    const byGroup = new Map<string, SpecField[]>();
    for (const field of spec.fields) {
      const list = byGroup.get(field.groupId) ?? [];
      list.push(field);
      byGroup.set(field.groupId, list);
    }
    return spec.groups
      .filter((group) => (byGroup.get(group.id) ?? []).length > 0)
      .sort((a, b) => a.order - b.order)
      .map((group) => ({
        group,
        fields: (byGroup.get(group.id) ?? []).sort((a, b) => a.order - b.order),
      }));
  }, [spec]);

  return (
    <div className="space-y-4">
      {groups.map(({ group, fields }) => {
        const count = occurrences[group.id] ?? 1;
        const required = fields.filter((f) => f.presence !== "OPTIONAL");
        const optional = fields.filter((f) => f.presence === "OPTIONAL");
        const hiddenOptional = optional.filter((f) => !revealed.has(f.id));

        return (
          <section
            key={group.id}
            className="overflow-hidden rounded-lg border border-line bg-panel shadow-[var(--shadow-1)]"
          >
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-rail px-5 py-3">
              <div className="min-w-0">
                <h3 className="text-[0.9375rem] font-semibold tracking-[-0.01em]">
                  {group.label}
                </h3>
                {group.description && group.description !== group.label && (
                  <p className="mt-0.5 max-w-[70ch] text-[0.8125rem] leading-6 text-ink-2">
                    {group.description}
                  </p>
                )}
              </div>
              {group.repeatable && (
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-xs text-ink-3 tnum">
                    {count} of up to {group.maxOccurs}
                  </span>
                  {count > 1 && (
                    <Button
                      size="sm"
                      variant="quiet"
                      icon="minus"
                      onClick={() => onRemoveOccurrence(group.id)}
                    >
                      Remove last
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="secondary"
                    icon="plus"
                    disabled={count >= group.maxOccurs}
                    onClick={() => onAddOccurrence(group.id)}
                  >
                    Add another
                  </Button>
                </div>
              )}
            </header>

            <div className="divide-y divide-line">
              {Array.from({ length: count }, (_, index) => index + 1).map((occurrence) => (
                <div key={occurrence}>
                  {count > 1 && (
                    <p className="bg-sunken px-5 py-1.5 text-xs font-medium tracking-[0.02em] text-ink-2">
                      Occurrence {occurrence}
                    </p>
                  )}
                  <div className="divide-y divide-line">
                    {required.map((field) => (
                      <FieldRow
                        key={slotKey(field.id, occurrence)}
                        field={field}
                        occurrence={occurrence}
                        value={values[slotKey(field.id, occurrence)] ?? ""}
                        onChange={(value) => onChange(slotKey(field.id, occurrence), value)}
                        expanded={revealed.has(`info:${field.id}`)}
                        onToggleInfo={() =>
                          revealed.has(`info:${field.id}`)
                            ? onHide(`info:${field.id}`)
                            : onReveal(`info:${field.id}`)
                        }
                        invalid={invalidLocations.has(field.id)}
                        focused={focusedLocation === field.id}
                      />
                    ))}
                    {optional
                      .filter((field) => revealed.has(field.id))
                      .map((field) => (
                        <FieldRow
                          key={slotKey(field.id, occurrence)}
                          field={field}
                          occurrence={occurrence}
                          value={values[slotKey(field.id, occurrence)] ?? ""}
                          onChange={(value) => onChange(slotKey(field.id, occurrence), value)}
                          expanded={revealed.has(`info:${field.id}`)}
                          onToggleInfo={() =>
                            revealed.has(`info:${field.id}`)
                              ? onHide(`info:${field.id}`)
                              : onReveal(`info:${field.id}`)
                          }
                          onRemove={() => onHide(field.id)}
                          invalid={invalidLocations.has(field.id)}
                          focused={focusedLocation === field.id}
                        />
                      ))}
                  </div>
                </div>
              ))}
            </div>

            {hiddenOptional.length > 0 && (
              <div className="border-t border-line bg-sunken px-5 py-3">
                <OptionalPicker fields={hiddenOptional} onAdd={onReveal} />
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function OptionalPicker({
  fields,
  onAdd,
}: {
  fields: SpecField[];
  onAdd: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-sm text-[0.8125rem] font-medium text-accent transition-colors duration-150 hover:text-accent-2"
      >
        <Icon name={open ? "minus" : "plus"} className="h-4 w-4" />
        Add optional field
        <span className="text-ink-3">({fields.length} available)</span>
      </button>
      {open && (
        <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
          {fields.map((field) => (
            <li key={field.id}>
              <button
                type="button"
                onClick={() => {
                  onAdd(field.id);
                  if (fields.length === 1) setOpen(false);
                }}
                className="flex w-full items-start gap-2 rounded-md border border-line-2 bg-panel px-3 py-2 text-left transition-colors duration-150 hover:border-accent/40 hover:bg-accent-sk"
              >
                <Icon name="plus" className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <span className="min-w-0">
                  <span className="block text-[0.8125rem] font-medium">{field.displayName}</span>
                  <span className="mt-0.5 block truncate font-mono text-[0.6875rem] text-ink-3">
                    {fieldAddress(field)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function fieldAddress(field: SpecField): string {
  if (field.format === "MT") {
    return field.qualifier ? `:${field.tag}::${field.qualifier}//` : `:${field.tag}:`;
  }
  return field.xpath ?? field.id;
}

function FieldRow({
  field,
  occurrence,
  value,
  onChange,
  expanded,
  onToggleInfo,
  onRemove,
  invalid,
  focused,
}: {
  field: SpecField;
  occurrence: number;
  value: string;
  onChange: (value: string) => void;
  expanded: boolean;
  onToggleInfo: () => void;
  onRemove?: () => void;
  invalid?: boolean;
  focused?: boolean;
}) {
  const inputId = `f-${field.id.replace(/[^A-Za-z0-9]/g, "-")}-${occurrence}`;
  // A dropdown is right only when the allowed codes are the complete value. Fields such as
  // 36B carry a code as a prefix ("UNIT/1000"), so a select would silently drop the rest.
  const codesAreWholeValue =
    field.allowedCodes.length > 0 &&
    field.allowedCodes.length <= 24 &&
    (field.examples.length === 0 ||
      field.examples.some((example) => field.allowedCodes.includes(example.value)));
  const hasCodes = codesAreWholeValue && (!value || field.allowedCodes.includes(value));

  return (
    <div
      id={`row-${field.id.replace(/[^A-Za-z0-9]/g, "-")}`}
      className={cx(
        "px-5 py-3.5 transition-colors duration-200",
        focused && "bg-accent-sk",
      )}
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:gap-5">
        <div className="min-w-0 md:w-[19rem] md:shrink-0">
          <div className="flex items-start gap-1.5">
            <label htmlFor={inputId} className="min-w-0 flex-1 text-sm font-medium leading-6">
              {field.displayName}
            </label>
            <InfoButton label={field.displayName} expanded={expanded} onToggle={onToggleInfo} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <PresenceBadge presence={field.presence} />
            <code className="truncate font-mono text-[0.6875rem] text-ink-3">
              {fieldAddress(field)}
            </code>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          {hasCodes ? (
            <Select
              id={inputId}
              value={value}
              invalid={invalid}
              onChange={(event) => onChange(event.target.value)}
            >
              <option value="">Choose a value…</option>
              {field.allowedCodes.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </Select>
          ) : (
            <TextInput
              id={inputId}
              value={value}
              invalid={invalid}
              placeholder={field.examples[0]?.value ?? field.formatExplanation}
              onChange={(event) => onChange(event.target.value)}
              className={field.format === "MX" || field.tag ? "font-mono" : undefined}
            />
          )}
          <p className="mt-1.5 text-xs leading-5 text-ink-3">{field.formatExplanation}</p>
        </div>

        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            className="self-start rounded-sm p-1 text-ink-3 transition-colors duration-150 hover:bg-rail hover:text-bad md:mt-1"
          >
            <Icon name="close" className="h-4 w-4" />
            <span className="sr-only">Remove {field.displayName}</span>
          </button>
        )}
      </div>

      {expanded && <FieldExplanation field={field} />}
    </div>
  );
}

/** Everything a tester needs to fill this field in, from the knowledge base. No model call. */
function FieldExplanation({ field }: { field: SpecField }) {
  return (
    <div className="animate-settle mt-3 rounded-md border border-accent/20 bg-accent-sk/60 px-4 py-3.5">
      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
        <Explain term="What it means">{field.businessMeaning || field.technicalMeaning}</Explain>
        {field.whyUsed && <Explain term="Why it is needed">{field.whyUsed}</Explain>}
        <Explain term="Expected format">{field.formatExplanation}</Explain>
        {field.examples.length > 0 && (
          <Explain term="Example">
            <code className="font-mono text-ink">{field.examples[0].value}</code>
            {field.examples[0].explanation && (
              <span className="mt-0.5 block text-ink-2">{field.examples[0].explanation}</span>
            )}
          </Explain>
        )}
        {field.conditionExplanation && (
          <Explain term="When it applies">{field.conditionExplanation}</Explain>
        )}
        {field.missingImpact && (
          <Explain term="If it is missing">{field.missingImpact}</Explain>
        )}
        {field.commonMistakes.length > 0 && (
          <Explain term="Common mistakes">
            <ul className="list-inside list-disc space-y-0.5">
              {field.commonMistakes.map((mistake) => (
                <li key={mistake}>{mistake}</li>
              ))}
            </ul>
          </Explain>
        )}
        {field.dependsOn.length > 0 && (
          <Explain term="Depends on">{field.dependsOn.join(", ")}</Explain>
        )}
      </dl>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-accent/15 pt-2.5">
        {field.allowedCodes.length > 0 && (
          <span className="text-xs text-ink-2">
            <span className="text-ink-3">Codes: </span>
            <code className="font-mono">{field.allowedCodes.join(", ")}</code>
          </span>
        )}
        <Badge className="ml-auto">{field.standardsRelease}</Badge>
      </div>
    </div>
  );
}

function Explain({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-accent-2">
        {term}
      </dt>
      <dd className="mt-0.5 text-[0.8125rem] leading-6 text-ink">{children}</dd>
    </div>
  );
}
