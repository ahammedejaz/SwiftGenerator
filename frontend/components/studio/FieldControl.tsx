"use client";

/**
 * One control per field, chosen by the specification rather than by this component.
 *
 * Everything here reads `field.inputKind`, `field.allowedValues` and `field.literalPrefix`
 * from the message specification. Nothing infers a control, and no code list is written
 * down in the browser — the previous arrangement guessed from whether one of the field's
 * examples happened to appear in its code list, and a value outside the list silently
 * turned a dropdown back into a text box.
 *
 * The checks these controls run are for usability only. The server validates every value
 * again and is the only authority; nothing here can make an invalid message valid.
 */

import { useEffect, useId, useMemo, useState } from "react";
import { Icon } from "@/components/studio/Icon";
import { Select, TextArea, TextInput, cx } from "@/components/studio/ui";
import { checkIsin, isBicShaped, normaliseIsin } from "@/lib/identifiers";
import type { SpecField } from "@/lib/studio-types";

/**
 * A code list long enough to be worth filtering.
 *
 * A native select already supports type-ahead, so a filter box below fifteen options is
 * clutter — and its label sat close enough to the field's own to be ambiguous to a screen
 * reader. No list in the current configuration reaches this; the control is here so one
 * that does is handled rather than dumped into a scrolling menu.
 */
const SEARCHABLE_FROM = 15;

export function FieldControl({
  field,
  id,
  value,
  invalid,
  onChange,
}: {
  field: SpecField;
  id: string;
  value: string;
  invalid?: boolean;
  onChange: (value: string) => void;
}) {
  switch (field.inputKind) {
    case "SELECT":
      return <CodeSelect field={field} id={id} value={value} invalid={invalid} onChange={onChange} />;
    case "INDICATOR":
      return <Indicator field={field} id={id} value={value} invalid={invalid} onChange={onChange} />;
    case "IDENTIFIER":
      return <IdentifierInput field={field} id={id} value={value} invalid={invalid} onChange={onChange} />;
    case "PARTY_BIC":
      return <BicInput field={field} id={id} value={value} invalid={invalid} onChange={onChange} />;
    case "PARTY_PROPRIETARY":
      return <ProprietaryPartyInput field={field} id={id} value={value} invalid={invalid} onChange={onChange} />;
    case "QUANTITY":
      return <QuantityInput field={field} id={id} value={value} invalid={invalid} onChange={onChange} />;
    case "AMOUNT":
      return <AmountInput field={field} id={id} value={value} invalid={invalid} onChange={onChange} />;
    case "DATE":
      return <DateInput field={field} id={id} value={value} invalid={invalid} onChange={onChange} />;
    case "NARRATIVE":
      return (
        <>
          <TextArea
            id={id}
            value={value}
            maxLength={field.maxLength ?? undefined}
            onChange={(event) => onChange(event.target.value)}
          />
          <Counter length={value.length} max={field.maxLength} />
        </>
      );
    case "REFERENCE":
      return (
        <>
          <TextInput
            id={id}
            value={value}
            invalid={invalid}
            maxLength={field.maxLength ?? undefined}
            placeholder={field.examples[0]?.value}
            className="font-mono"
            onChange={(event) => onChange(event.target.value.toUpperCase())}
          />
          <Counter length={value.length} max={field.maxLength} />
        </>
      );
    default:
      return (
        <TextInput
          id={id}
          value={value}
          invalid={invalid}
          maxLength={field.maxLength ?? undefined}
          placeholder={field.examples[0]?.value ?? field.formatExplanation}
          className={field.format === "MX" || field.tag ? "font-mono" : undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      );
  }
}

/* ------------------------------------------------------------------ controlled codes */

function CodeSelect({
  field,
  id,
  value,
  invalid,
  onChange,
}: ControlProps) {
  const [query, setQuery] = useState("");
  const only = field.allowedValues.length === 1 ? field.allowedValues[0] : null;
  const searchable = field.allowedValues.length >= SEARCHABLE_FROM;
  const visible = useMemo(() => {
    if (!query.trim()) return field.allowedValues;
    const needle = query.trim().toLowerCase();
    return field.allowedValues.filter(
      (item) =>
        item.code.toLowerCase().includes(needle) ||
        item.label.toLowerCase().includes(needle) ||
        item.description.toLowerCase().includes(needle),
    );
  }, [field.allowedValues, query]);

  // Exactly one allowed value in this context: preselect it and say so, rather than asking
  // a question with one answer.
  //
  // In an effect, never during render. Calling the parent's setter while rendering makes
  // React re-render mid-commit; with a value that also clears other state it can loop, and
  // a looping remount aborts the catalogue fetch the page is waiting on — which surfaces as
  // "the studio API could not be reached" on a backend that is running perfectly well.
  useEffect(() => {
    if (only && value !== only.code) onChange(only.code);
  }, [only, value, onChange]);

  if (only) {
    return (
      <div className="flex min-h-10 items-center gap-2 rounded-md border border-line-2 bg-sunken px-3">
        <code className="font-mono text-[0.8125rem] font-semibold">{only.code}</code>
        <span className="text-sm text-ink-2">{only.label}</span>
        <span className="ml-auto text-xs text-ink-3">Only value for this message</span>
        <input type="hidden" id={id} value={only.code} readOnly />
      </div>
    );
  }

  const chosen = field.allowedValues.find((item) => item.code === value);
  return (
    <div className="space-y-1.5">
      {searchable && (
        <div className="relative">
          <Icon
            name="search"
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
          />
          <TextInput
            value={query}
            aria-label={`Search codes for ${field.displayName}`}
            placeholder={`Search ${field.allowedValues.length} codes…`}
            className="h-9 pl-8 text-[0.8125rem]"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      )}
      <Select
        id={id}
        value={value}
        invalid={invalid}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Choose a value…</option>
        {visible.map((item) => (
          <option key={item.code} value={item.code}>
            {item.label && item.label !== item.code
              ? `${item.code} — ${item.label}`
              : item.code}
          </option>
        ))}
        {/* A value the list no longer allows stays visible so it can be seen and corrected,
            rather than disappearing and leaving the control looking empty. */}
        {value && !chosen && <option value={value}>{value} — not an allowed code</option>}
      </Select>
      {chosen?.description && (
        <p className="text-xs leading-5 text-ink-2">{chosen.description}</p>
      )}
    </div>
  );
}

function Indicator({ field, id, value, invalid, onChange }: ControlProps) {
  const options = field.allowedValues.length
    ? field.allowedValues
    : [
        { code: "Y", label: "Yes", description: "" },
        { code: "N", label: "No", description: "" },
      ];
  return (
    <div className="inline-flex rounded-md border border-line-2 bg-panel p-0.5" id={id}>
      {options.map((item) => (
        <button
          key={item.code}
          type="button"
          aria-pressed={value === item.code}
          onClick={() => onChange(item.code)}
          className={cx(
            "rounded-[5px] px-3.5 py-1.5 text-[0.8125rem] font-medium transition-colors duration-150",
            value === item.code
              ? "bg-accent text-white"
              : "text-ink-2 hover:bg-rail hover:text-ink",
            invalid && "text-bad",
          )}
        >
          {item.label || item.code}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------------- identifiers */

function IdentifierInput({ field, id, value, invalid, onChange }: ControlProps) {
  const type = field.identifierTypes[0] ?? "ID";
  const length = field.maxLength ?? 12;
  const verdict = checkIsin(value);
  const hintId = useId();

  return (
    <div className="space-y-1.5">
      <div className="flex items-stretch">
        {/* The literal is shown as a fixed badge, never typed. Exactly one component writes
            it, and that component is the composer on the server. */}
        <span
          className="inline-flex select-none items-center rounded-l-md border border-r-0 border-line-2 bg-sunken px-2.5 font-mono text-[0.8125rem] font-semibold text-ink-2"
          title={`The studio writes "${field.literalPrefix?.trim() ?? type}" for you`}
        >
          {field.literalPrefix?.trim() ?? type}
        </span>
        <TextInput
          id={id}
          value={value}
          invalid={invalid || (value.length > 0 && !verdict.formatValid)}
          inputMode="text"
          autoCapitalize="characters"
          spellCheck={false}
          // Deliberately no `maxLength`. The browser applies it to the *raw* input, so
          // pasting `ISIN XS0000000009` would be cut to `ISIN XS00000` before the literal
          // could be stripped, leaving `XS00000`. The length is enforced after
          // normalisation instead, which is the only order that makes a paste work.
          aria-describedby={hintId}
          placeholder={field.examples[0]?.value ?? "XS0000000009"}
          className="rounded-l-none font-mono tracking-[0.06em]"
          // Paste-safe: `ISIN XS…` becomes `XS…` rather than `ISIN ISIN XS…`, and only
          // presentation is changed — a wrong identifier stays wrong and is reported.
          onChange={(event) => onChange(normaliseIsin(event.target.value).slice(0, length))}
        />
      </div>
      <div id={hintId} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className={cx("tnum", value.length === length ? "text-ok" : "text-ink-3")}>
          {value.length} / {length} characters
        </span>
        {/* Name the actual defect, and name the same one the server will. A value whose
            last character is a letter has no check digit to compare, so saying "check digit
            does not match" would send the tester looking at the wrong thing. */}
        {value.length === length && !verdict.formatValid && verdict.hint && (
          <span className="text-bad">{verdict.hint}</span>
        )}
        {value.length === length && verdict.formatValid && (
          <span className={verdict.checkDigitValid ? "text-ok" : "text-bad"}>
            {verdict.checkDigitValid
              ? "Check digit valid"
              : `Check digit does not match — expected ${verdict.expectedCheckDigit}`}
          </span>
        )}
        {value.length > 0 && value.length < length && verdict.hint && (
          <span className="text-ink-3">{verdict.hint}</span>
        )}
      </div>
    </div>
  );
}

function BicInput({ field, id, value, invalid, onChange }: ControlProps) {
  const shaped = isBicShaped(value);
  return (
    <div className="space-y-1.5">
      <TextInput
        id={id}
        value={value}
        invalid={invalid || (value.length > 0 && value.length >= 8 && !shaped)}
        spellCheck={false}
        autoCapitalize="characters"
        maxLength={11}
        placeholder={field.examples[0]?.value ?? "DEMOGB2LXXX"}
        className="font-mono tracking-[0.06em]"
        onChange={(event) => onChange(event.target.value.toUpperCase().replace(/\s+/g, ""))}
      />
      <p className="text-xs text-ink-3">
        <span className="tnum">{value.length}</span> characters — a BIC is 8 or 11.{" "}
        {value.length >= 8 && (
          <span className={shaped ? "text-ok" : "text-bad"}>
            {shaped ? "Format looks right." : "That is not a BIC shape."}
          </span>
        )}{" "}
        <span className="text-ink-3">
          The format is checked; whether the BIC is registered is not.
        </span>
      </p>
    </div>
  );
}

/**
 * Option R is a data source scheme and an identifier. Splitting them is what stops a BIC
 * being typed into the proprietary field — the mistake the reported message made.
 */
function ProprietaryPartyInput({ field, id, value, invalid, onChange }: ControlProps) {
  const slash = value.indexOf("/");
  const scheme = slash === -1 ? value : value.slice(0, slash);
  const identifier = slash === -1 ? "" : value.slice(slash + 1);
  const join = (nextScheme: string, nextIdentifier: string) =>
    onChange(`${nextScheme.toUpperCase()}/${nextIdentifier.toUpperCase()}`.replace(/\/$/, "/"));

  return (
    <div className="space-y-1.5">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="sm:w-40">
          <TextInput
            id={id}
            value={scheme}
            invalid={invalid && !scheme}
            maxLength={8}
            placeholder="CSD"
            aria-label={`${field.displayName} data source scheme`}
            className="font-mono"
            onChange={(event) => join(event.target.value, identifier)}
          />
          <p className="mt-1 text-xs text-ink-3">Data source scheme</p>
        </div>
        <div className="min-w-0 flex-1">
          <TextInput
            value={identifier}
            invalid={invalid && !identifier}
            maxLength={34}
            placeholder={field.examples[0]?.value?.split("/")[1] ?? "DEMOPSET01"}
            aria-label={`${field.displayName} proprietary identifier`}
            className="font-mono"
            onChange={(event) => join(scheme, event.target.value)}
          />
          <p className="mt-1 text-xs text-ink-3">Identifier within that scheme</p>
        </div>
      </div>
      <p className="text-xs text-ink-3">
        Rendered as <code className="font-mono">{scheme || "SCHEME"}/{identifier || "IDENTIFIER"}</code>.
        Use the BIC form instead if this party has a BIC.
      </p>
    </div>
  );
}

/* --------------------------------------------------------------- composite values */

/** `UNIT/1000` — a quantity type and a number, entered as the two things they are. */
function QuantityInput({ field, id, value, invalid, onChange }: ControlProps) {
  const slash = value.indexOf("/");
  const code = slash === -1 ? field.allowedValues[0]?.code ?? "" : value.slice(0, slash);
  const amount = slash === -1 ? value : value.slice(slash + 1);
  const join = (nextCode: string, nextAmount: string) => onChange(`${nextCode}/${nextAmount}`);

  return (
    <div className="flex flex-col gap-2 sm:flex-row">
      <div className="sm:w-44">
        <Select
          value={code}
          aria-label={`${field.displayName} quantity type`}
          onChange={(event) => join(event.target.value, amount)}
        >
          {field.allowedValues.map((item) => (
            <option key={item.code} value={item.code}>
              {item.label && item.label !== item.code ? `${item.code} — ${item.label}` : item.code}
            </option>
          ))}
        </Select>
      </div>
      <TextInput
        id={id}
        value={amount}
        invalid={invalid}
        inputMode="decimal"
        placeholder="1000"
        className="min-w-0 flex-1 font-mono"
        onChange={(event) => join(code, event.target.value.replace(/[^\d,.]/g, ""))}
      />
    </div>
  );
}

/** `USD25000,00` — a currency and a decimal amount. */
function AmountInput({ field, id, value, invalid, onChange }: ControlProps) {
  const match = /^([A-Z]{0,3})(.*)$/.exec(value.toUpperCase());
  const currency = match?.[1] ?? "";
  const amount = match?.[2] ?? "";
  const join = (nextCurrency: string, nextAmount: string) =>
    onChange(`${nextCurrency.toUpperCase()}${nextAmount}`);

  return (
    <div className="flex flex-col gap-2 sm:flex-row">
      <TextInput
        value={currency}
        aria-label={`${field.displayName} currency`}
        maxLength={3}
        placeholder="USD"
        className="font-mono sm:w-24"
        onChange={(event) => join(event.target.value, amount)}
      />
      <TextInput
        id={id}
        value={amount}
        invalid={invalid}
        inputMode="decimal"
        placeholder="25000,00"
        className="min-w-0 flex-1 font-mono"
        onChange={(event) => join(currency, event.target.value.replace(/[^\d,.]/g, ""))}
      />
    </div>
  );
}

/**
 * A date picker that writes the format the field carries.
 *
 * MT dates are `YYYYMMDD` and MX dates are `YYYY-MM-DD`; the picker speaks ISO either way,
 * so only the value written back differs.
 */
function DateInput({ field, id, value, invalid, onChange }: ControlProps) {
  const compact = field.format === "MT";
  const isoValue = compact
    ? /^\d{8}$/.test(value)
      ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`
      : ""
    : value;
  return (
    <TextInput
      id={id}
      type="date"
      value={isoValue}
      invalid={invalid}
      onChange={(event) => {
        const next = event.target.value;
        onChange(compact ? next.replace(/-/g, "") : next);
      }}
    />
  );
}

function Counter({ length, max }: { length: number; max: number | null }) {
  if (!max) return null;
  return (
    <p className={cx("mt-1 text-xs tnum", length > max ? "text-bad" : "text-ink-3")}>
      {length} / {max}
    </p>
  );
}

interface ControlProps {
  field: SpecField;
  id: string;
  value: string;
  invalid?: boolean;
  onChange: (value: string) => void;
}
