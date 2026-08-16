"use client";

/**
 * Validate — check data without generating and keeping a message.
 *
 * Two ways in: paste JSON field data (what an automation tester already has), or paste an
 * existing message and have it read back. Both run the same layers as generation and keep
 * nothing.
 *
 * There used to be a separate mode for MT and for MX. The import endpoint recognises a
 * message from its own content, so asking the tester to classify it first was a question
 * with no purpose and one more way to pick wrong.
 */

import { useEffect, useState } from "react";
import { MessageDiffPanel } from "@/components/studio/MessageDiff";
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
import type {
  GenerateRequest,
  GenerateResult,
  MessageDiff,
  StudioCatalogue,
} from "@/lib/studio-types";

type Mode = "STRUCTURED" | "EXISTING";

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
  const [text, setText] = useState("");
  const [messageType, setMessageType] = useState("");
  const [profileId, setProfileId] = useState("BASE_DEMO_V1");
  const [catalogue, setCatalogue] = useState<StudioCatalogue | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);
  // Validating an existing message and importing it are the same read, so the same
  // question applies: did anything get lost on the way in?
  const [diff, setDiff] = useState<MessageDiff | null>(null);

  useEffect(() => {
    studioApi.catalogue().then(setCatalogue).catch(() => setCatalogue(null));
  }, []);

  // Only a pasted MT text block cannot say what it is, so the picker appears once the
  // studio has said it could not tell — never as a question asked up front.
  const needsType =
    error !== null && /fits more than one message|could not be worked out/.test(error);

  async function runStructured() {
    setBusy(true);
    setError(null);
    setResult(null);
    setDiff(null);
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

  async function runExisting() {
    setBusy(true);
    setError(null);
    setResult(null);
    setDiff(null);
    try {
      // The same endpoint the Create screen imports with. Validating and importing are the
      // same read; only what the caller does with the result differs.
      const imported = await studioApi.importMessage(text, profileId, messageType || null);
      setResult(imported.result);
      setDiff(imported.diff);
    } catch (caught) {
      setError(
        caught instanceof StudioError ? caught.message : "That message could not be read.",
      );
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
            { value: "EXISTING", label: "An existing message" },
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

      {mode === "EXISTING" ? (
        <Panel
          title="An existing message"
          description="Paste an MT FIN message, an MT text block, or an ISO 20022 document. It is read back into values and checked against the configured subset, the client profile and — for MX — the schema. Nothing is saved."
          action={
            <Button
              variant="primary"
              icon="check-shield"
              loading={busy}
              disabled={!text.trim() || (needsType && !messageType)}
              onClick={() => void runExisting()}
            >
              Validate
            </Button>
          }
        >
          <TextArea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={16}
            spellCheck={false}
            placeholder={"{1:F01…}{2:I541…}{4:  or  <Document xmlns=\"urn:iso:std:iso:20022:tech:xsd:sese.023.001.11\">…"}
            aria-label="Message to validate"
          />
          {needsType && (
            <Labelled
              className="mt-3"
              label="Which message is it?"
              hint="A text block on its own does not say which message it belongs to."
            >
              <Select
                value={messageType}
                onChange={(event) => setMessageType(event.target.value)}
                aria-label="Message type of the pasted text block"
              >
                <option value="">Choose a message</option>
                {(catalogue?.messages ?? [])
                  .filter((entry) => entry.format === "MT")
                  .map((entry) => (
                    <option key={entry.messageType} value={entry.messageType}>
                      {entry.messageType} — {entry.name}
                    </option>
                  ))}
              </Select>
            </Labelled>
          )}
        </Panel>
      ) : (
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
      )}

      {error && <ErrorNotice message={error} />}
      {result && <ValidationPanel validation={result.validation} />}
      {result && diff && (
        <MessageDiffPanel
          diff={diff}
          regenerated={
            result.outputs.fin ??
            result.outputs.xml ??
            result.outputs.block4 ??
            result.outputs.document ??
            ""
          }
          filename={`${result.messageType.replace(/[^A-Za-z0-9._-]/g, "-")}.${
            result.format === "MT" ? "fin" : "xml"
          }`}
        />
      )}

      {!result && !error && (
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
