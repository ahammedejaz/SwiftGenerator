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
import { FieldControl } from "@/components/studio/FieldControl";
import { Icon } from "@/components/studio/Icon";
import {
  Badge,
  Button,
  InfoButton,
  PresenceBadge,
  cx,
} from "@/components/studio/ui";
import type { MessageSpec, SpecField } from "@/lib/studio-types";

/**
 * Two field options carrying the same business value — a party identified by its BIC and
 * the same party identified by a proprietary scheme code — belong to one choice group.
 * Exactly one of them is needed, which is why the form asks *how* to identify the party
 * rather than presenting `95P` and `95R` as two separate required fields.
 */
export function choiceKey(field: SpecField): string | null {
  if (!field.choiceGroup) return null;
  const cut = field.choiceGroup.lastIndexOf("/");
  return cut === -1 ? field.choiceGroup : field.choiceGroup.slice(0, cut);
}

/**
 * Controls that already state their own rule inline — a character counter, a check-digit
 * verdict, a BIC length hint. Repeating `formatExplanation` underneath them says the same
 * sentence twice.
 */
const SELF_EXPLAINING = new Set<SpecField["inputKind"]>([
  "IDENTIFIER",
  "PARTY_BIC",
  "PARTY_PROPRIETARY",
  "SELECT",
]);

/** How a party is identified, in the words the question is asked in. */
function optionLabel(field: SpecField): string {
  if (field.tag === "95P") return "BIC";
  if (field.tag === "95R") return "Proprietary identifier";
  return `Option ${field.option ?? ""}`.trim();
}

function optionHint(field: SpecField): string {
  if (field.tag === "95P") return "The party has a Business Identifier Code.";
  if (field.tag === "95R") return "A code from a named scheme, with the scheme stated.";
  return field.formatExplanation;
}

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
        // Field options for one business value collapse into a single row that asks how to
        // identify the party, rather than two rows both claiming to be required.
        const rows = collapseChoices(fields);
        const required = rows.filter((row) => row.presence !== "OPTIONAL");
        const optional = rows.filter((row) => row.presence === "OPTIONAL");
        const hiddenOptional = optional.filter((row) => !revealed.has(row.id));

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
                    {required.map((row) => (
                      <FieldRow
                        key={slotKey(row.id, occurrence)}
                        row={row}
                        occurrence={occurrence}
                        values={values}
                        onChange={onChange}
                        expanded={revealed.has(`info:${row.id}`)}
                        onToggleInfo={() =>
                          revealed.has(`info:${row.id}`)
                            ? onHide(`info:${row.id}`)
                            : onReveal(`info:${row.id}`)
                        }
                        invalidLocations={invalidLocations}
                        focusedLocation={focusedLocation}
                      />
                    ))}
                    {optional
                      .filter((row) => revealed.has(row.id))
                      .map((row) => (
                        <FieldRow
                          key={slotKey(row.id, occurrence)}
                          row={row}
                          occurrence={occurrence}
                          values={values}
                          onChange={onChange}
                          expanded={revealed.has(`info:${row.id}`)}
                          onToggleInfo={() =>
                            revealed.has(`info:${row.id}`)
                              ? onHide(`info:${row.id}`)
                              : onReveal(`info:${row.id}`)
                          }
                          onRemove={() => onHide(row.id)}
                          invalidLocations={invalidLocations}
                          focusedLocation={focusedLocation}
                        />
                      ))}
                  </div>
                </div>
              ))}
            </div>

            {hiddenOptional.length > 0 && (
              <div className="border-t border-line bg-sunken px-5 py-3">
                <OptionalPicker rows={hiddenOptional} onAdd={onReveal} />
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function OptionalPicker({
  rows,
  onAdd,
}: {
  rows: FieldRowModel[];
  onAdd: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const partyRows = rows.filter((row) => row.options.length > 1);
  const label = partyRows.length === rows.length && rows.length > 0
    ? "Add settlement party"
    : "Add optional field";
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-sm text-[0.8125rem] font-medium text-accent transition-colors duration-150 hover:text-accent-2"
      >
        <Icon name={open ? "minus" : "plus"} className="h-4 w-4" />
        {label}
        <span className="text-ink-3">({rows.length} available)</span>
      </button>
      {open && (
        <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
          {rows.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                onClick={() => {
                  onAdd(row.id);
                  if (rows.length === 1) setOpen(false);
                }}
                className="flex w-full items-start gap-2 rounded-md border border-line-2 bg-panel px-3 py-2 text-left transition-colors duration-150 hover:border-accent/40 hover:bg-accent-sk"
              >
                <Icon name="plus" className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <span className="min-w-0">
                  <span className="block text-[0.8125rem] font-medium">{row.displayName}</span>
                  <span className="mt-0.5 block truncate text-[0.6875rem] text-ink-3">
                    {row.options.length > 1
                      ? row.options.map(optionLabel).join(" or ")
                      : fieldAddress(row.options[0])}
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

/**
 * One thing a tester fills in, which may be expressible through more than one field option.
 *
 * `id` is the first option's field id, so revealing, hiding and explaining all keep working
 * unchanged for the ordinary single-option case.
 */
export interface FieldRowModel {
  id: string;
  displayName: string;
  presence: SpecField["presence"];
  options: SpecField[];
}

export function collapseChoices(fields: SpecField[]): FieldRowModel[] {
  const rows: FieldRowModel[] = [];
  const byGroup = new Map<string, FieldRowModel>();
  for (const field of fields) {
    const group = choiceKey(field);
    if (!group) {
      rows.push({
        id: field.id,
        displayName: field.displayName,
        presence: field.presence,
        options: [field],
      });
      continue;
    }
    const existing = byGroup.get(group);
    if (existing) {
      existing.options.push(field);
      // Required in either form means required, whichever option happens to be listed first.
      if (field.presence === "MANDATORY") existing.presence = "MANDATORY";
      continue;
    }
    const row: FieldRowModel = {
      id: field.id,
      displayName: field.displayName,
      presence: field.presence,
      options: [field],
    };
    byGroup.set(group, row);
    rows.push(row);
  }
  return rows;
}

function FieldRow({
  row,
  occurrence,
  values,
  onChange,
  expanded,
  onToggleInfo,
  onRemove,
  invalidLocations,
  focusedLocation,
}: {
  row: FieldRowModel;
  occurrence: number;
  values: FieldValues;
  onChange: (key: string, value: string) => void;
  expanded: boolean;
  onToggleInfo: () => void;
  onRemove?: () => void;
  invalidLocations: Set<string>;
  focusedLocation: string | null;
}) {
  // Which field option is in use is derived from where the value is, so a value entered in
  // one form is never silently lost by switching to the other.
  const filled = row.options.find((option) => values[slotKey(option.id, occurrence)]?.trim());
  const [preferred, setPreferred] = useState<string | null>(null);
  const active =
    row.options.find((option) => option.id === preferred) ?? filled ?? row.options[0];
  const slot = slotKey(active.id, occurrence);
  const value = values[slot] ?? "";
  const inputId = `f-${active.id.replace(/[^A-Za-z0-9]/g, "-")}-${occurrence}`;
  const invalid = row.options.some((option) => invalidLocations.has(option.id));
  const focused = row.options.some((option) => option.id === focusedLocation);

  function chooseOption(next: SpecField) {
    if (next.id === active.id) return;
    // Moving between forms of the same party clears the other one, because the message may
    // carry the party once. The server refuses both together; the form never gets there.
    for (const option of row.options) {
      if (values[slotKey(option.id, occurrence)]) {
        onChange(slotKey(option.id, occurrence), "");
      }
    }
    setPreferred(next.id);
  }

  return (
    <div
      id={`row-${row.id.replace(/[^A-Za-z0-9]/g, "-")}`}
      className={cx("px-5 py-3.5 transition-colors duration-200", focused && "bg-accent-sk")}
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:gap-5">
        <div className="min-w-0 md:w-[19rem] md:shrink-0">
          <div className="flex items-start gap-1.5">
            <label htmlFor={inputId} className="min-w-0 flex-1 text-sm font-medium leading-6">
              {row.displayName}
            </label>
            <InfoButton label={row.displayName} expanded={expanded} onToggle={onToggleInfo} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <PresenceBadge presence={row.presence} />
            <code className="truncate font-mono text-[0.6875rem] text-ink-3">
              {fieldAddress(active)}
            </code>
          </div>
          {active.conditionExplanation && row.presence !== "OPTIONAL" && (
            <p className="mt-1.5 max-w-[34ch] text-xs leading-5 text-ink-2">
              {active.conditionExplanation}
            </p>
          )}
        </div>

        <div className="min-w-0 flex-1">
          {row.options.length > 1 && (
            <fieldset className="mb-2.5">
              <legend className="mb-1.5 text-xs font-medium text-ink-2">
                How do you want to identify this party?
              </legend>
              <div className="inline-flex flex-wrap rounded-md border border-line-2 bg-panel p-0.5">
                {row.options.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    aria-pressed={option.id === active.id}
                    title={optionHint(option)}
                    onClick={() => chooseOption(option)}
                    className={cx(
                      "rounded-[5px] px-3 py-1.5 text-[0.8125rem] font-medium transition-colors duration-150",
                      option.id === active.id
                        ? "bg-accent text-white"
                        : "text-ink-2 hover:bg-rail hover:text-ink",
                    )}
                  >
                    {optionLabel(option)}
                  </button>
                ))}
              </div>
            </fieldset>
          )}
          <FieldControl
            field={active}
            id={inputId}
            value={value}
            invalid={invalid}
            onChange={(next) => onChange(slot, next)}
          />
          {!SELF_EXPLAINING.has(active.inputKind) && (
            <p className="mt-1.5 text-xs leading-5 text-ink-3">{active.formatExplanation}</p>
          )}
        </div>

        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            className="self-start rounded-sm p-1 text-ink-3 transition-colors duration-150 hover:bg-rail hover:text-bad md:mt-1"
          >
            <Icon name="close" className="h-4 w-4" />
            <span className="sr-only">Remove {row.displayName}</span>
          </button>
        )}
      </div>

      {expanded && <FieldExplanation field={active} />}
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
      {field.allowedValues.length > 0 && (
        <div className="mt-3 border-t border-accent/15 pt-2.5">
          <dt className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-accent-2">
            Allowed values
          </dt>
          <ul className="mt-1 space-y-0.5">
            {field.allowedValues.map((item) => (
              <li key={item.code} className="text-[0.8125rem] leading-6">
                <code className="font-mono font-semibold">{item.code}</code>
                {item.label && item.label !== item.code && (
                  <span className="text-ink"> — {item.label}</span>
                )}
                {item.description && (
                  <span className="text-ink-2"> {item.description}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-accent/15 pt-2.5">
        {field.literalPrefix && (
          <span className="text-xs text-ink-2">
            The studio writes{" "}
            <code className="font-mono">{field.literalPrefix.trim()}</code> for you — you do
            not type it.
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
