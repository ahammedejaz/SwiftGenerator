"use client";

/**
 * Validate — check data without generating and keeping a message.
 *
 * Three ways in: paste JSON field data (what an automation tester already has), check an
 * existing MT text block, or read back an existing ISO 20022 document. All three run the
 * same layers as generation and keep nothing.
 */

import { useEffect, useState } from "react";
import { ValidationPanel } from "@/components/studio/ValidationPanel";
import {
  Button,
  EmptyState,
  ErrorNotice,
  Labelled,
  Panel,
  SegmentedControl,
  Select,
  TextArea,
} from "@/components/studio/ui";
import { StudioError, studioApi } from "@/lib/studio-api";
import { apiUrl } from "@/lib/api-client";
import type {
  GenerateRequest,
  GenerateResult,
  StudioCatalogue,
  ValidationResult,
} from "@/lib/studio-types";

type Mode = "STRUCTURED" | "RAW" | "MX";

const STARTER = `{
  "format": "MT",
  "messageType": "MT541",
  "profileId": "BASE_DEMO_V1",
  "fields": [
    { "sequence": "GENL", "tag": "20C", "qualifier": "SEME", "value": "TESTREF001" },
    { "sequence": "GENL", "tag": "23G", "value": "NEWM" }
  ]
}`;

export function ValidateStudio() {
  const [mode, setMode] = useState<Mode>("STRUCTURED");
  const [payload, setPayload] = useState(STARTER);
  const [raw, setRaw] = useState("");
  const [xml, setXml] = useState("");
  const [profileId, setProfileId] = useState("BASE_DEMO_V1");
  const [catalogue, setCatalogue] = useState<StudioCatalogue | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [rawResult, setRawResult] = useState<ValidationResult | null>(null);

  useEffect(() => {
    studioApi.catalogue().then(setCatalogue).catch(() => setCatalogue(null));
  }, []);

  async function runStructured() {
    setBusy(true);
    setError(null);
    setResult(null);
    setRawResult(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(payload);
    } catch {
      setBusy(false);
      setError("That is not valid JSON. Check for a missing comma or bracket.");
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setBusy(false);
      setError("The body must be a JSON object with format, messageType and fields.");
      return;
    }
    const body = parsed as Partial<GenerateRequest> & Record<string, unknown>;
    if (!body.format || !body.messageType) {
      setBusy(false);
      setError('The body needs a "format" ("MT" or "MX") and a "messageType".');
      return;
    }
    try {
      setResult(
        await studioApi.validate({
          ...body,
          format: body.format,
          messageType: body.messageType,
          profileId: (body.profileId as string | undefined) ?? profileId,
        }),
      );
    } catch (caught) {
      setError(caught instanceof StudioError ? caught.message : "Validation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runMx() {
    setBusy(true);
    setError(null);
    setResult(null);
    setRawResult(null);
    try {
      // The same endpoint the Create screen imports with. Validating and importing are the
      // same read; only what the caller does with the result differs.
      const imported = await studioApi.importMessage(xml, profileId);
      setResult(imported.result);
    } catch (caught) {
      setError(
        caught instanceof StudioError ? caught.message : "That document could not be read.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function runRaw() {
    setBusy(true);
    setError(null);
    setResult(null);
    setRawResult(null);
    try {
      const response = await fetch(apiUrl("/api/messages/validate-raw"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rawMessage: raw, profileId }),
      });
      const body = (await response.json()) as {
        validation?: ValidationResult;
        error?: { message?: string };
      };
      if (!response.ok) {
        setError(body.error?.message ?? "The message could not be parsed.");
        return;
      }
      setRawResult(body.validation ?? null);
    } catch {
      setError("The studio API could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          label="What do you want to validate?"
          value={mode}
          onChange={setMode}
          options={[
            { value: "STRUCTURED", label: "Field or element data" },
            { value: "RAW", label: "An existing MT message" },
            { value: "MX", label: "An existing MX message" },
          ]}
        />
        {catalogue && (
          <Labelled label="Client profile" className="w-56">
            <Select value={profileId} onChange={(event) => setProfileId(event.target.value)}>
              {catalogue.profiles.map((profile) => (
                <option key={profile} value={profile}>
                  {profile}
                </option>
              ))}
            </Select>
          </Labelled>
        )}
      </div>

      {mode === "MX" ? (
        <Panel
          title="An existing MX message"
          description="Paste an ISO 20022 document. It is read back into element values and checked against the configured subset, the client profile and the schema. Nothing is saved."
          action={
            <Button
              variant="primary"
              icon="check-shield"
              loading={busy}
              disabled={!xml.trim()}
              onClick={() => void runMx()}
            >
              Validate
            </Button>
          }
        >
          <TextArea
            value={xml}
            onChange={(event) => setXml(event.target.value)}
            rows={16}
            spellCheck={false}
            placeholder={'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:sese.023.001.11">…'}
            aria-label="Message to validate"
          />
        </Panel>
      ) : mode === "STRUCTURED" ? (
        <Panel
          title="Field or element data"
          description="Paste the same body you would send to POST /api/v1/messages/generate. Nothing is saved."
          action={
            <Button variant="primary" icon="check-shield" loading={busy} onClick={() => void runStructured()}>
              Validate
            </Button>
          }
        >
          <TextArea
            value={payload}
            onChange={(event) => setPayload(event.target.value)}
            rows={16}
            spellCheck={false}
            aria-label="Request body"
          />
        </Panel>
      ) : (
        <Panel
          title="An existing MT message"
          description="Paste a Block 4 text block or a full FIN message. It is parsed and checked against the configured subset."
          action={
            <Button
              variant="primary"
              icon="check-shield"
              loading={busy}
              disabled={!raw.trim()}
              onClick={() => void runRaw()}
            >
              Validate
            </Button>
          }
        >
          <TextArea
            value={raw}
            onChange={(event) => setRaw(event.target.value)}
            rows={16}
            spellCheck={false}
            placeholder={"{4:\n:16R:GENL\n:20C::SEME//TESTREF001\n…\n-}"}
            aria-label="Raw message"
          />
        </Panel>
      )}

      {error && <ErrorNotice message={error} />}
      {result && <ValidationPanel validation={result.validation} />}
      {rawResult && <RawValidation validation={rawResult} />}

      {!result && !rawResult && !error && (
        <Panel>
          <EmptyState icon="check-shield" title="Nothing checked yet">
            Validation runs the same layers as generation — structure, formats, business
            rules, client profile, and for MX the schema too — but keeps nothing.
          </EmptyState>
        </Panel>
      )}
    </div>
  );
}

/**
 * The legacy raw-validation endpoint returns the older finding shape, so it is mapped onto
 * the studio's validation panel rather than given a second, inconsistent presentation.
 */
function RawValidation({ validation }: { validation: ValidationResult }) {
  const legacy = validation as unknown as {
    status?: string;
    findings?: Array<Record<string, string | null>>;
    errorCount?: number;
  };
  if (!legacy.findings) return <ValidationPanel validation={validation} />;

  const errors = legacy.findings.filter((item) => item.severity === "ERROR");
  const warnings = legacy.findings.filter((item) => item.severity !== "ERROR");
  const count = errors.length;
  const mapped: ValidationResult = {
    valid: count === 0,
    summary:
      count === 0
        ? "Ready to generate"
        : count === 1
          ? "1 issue needs attention"
          : `${count} issues need attention`,
    layers: [],
    errors: errors.map((item) => ({
      ruleId: item.ruleId ?? "RULE",
      severity: "ERROR",
      layer: "BUSINESS_RULES",
      field: item.fieldPath ?? null,
      location: item.fieldPath ?? null,
      message: item.message ?? "",
      expected: item.expectedCondition ?? null,
      currentValue: item.currentValue ?? null,
      suggestion: item.suggestion ?? null,
    })),
    warnings: warnings.map((item) => ({
      ruleId: item.ruleId ?? "RULE",
      severity: "WARNING",
      layer: "BUSINESS_RULES",
      field: item.fieldPath ?? null,
      location: item.fieldPath ?? null,
      message: item.message ?? "",
      expected: item.expectedCondition ?? null,
      currentValue: item.currentValue ?? null,
      suggestion: item.suggestion ?? null,
    })),
  };
  return <ValidationPanel validation={mapped} />;
}
