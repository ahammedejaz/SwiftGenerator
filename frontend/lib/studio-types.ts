/**
 * Mirrors the `/api/v1` contract in `backend/app/studio/models.py`.
 *
 * The UI has no private endpoints: every type here describes a payload an automation
 * tester can obtain with the same call.
 */

export type MessageFormat = "MT" | "MX";
export type Presence = "MANDATORY" | "CONDITIONAL" | "OPTIONAL";
export type IssueSeverity = "ERROR" | "WARNING" | "INFO";
export type SampleVariant = "MINIMAL" | "TYPICAL" | "FULL";

export type OutputMode =
  | "BLOCK4"
  | "FIN"
  | "TXT"
  | "CANONICAL_JSON"
  | "XML"
  | "APPHDR"
  | "DOCUMENT";

export type FieldOrigin =
  | "USER_ENTERED"
  | "PROFILE_CONFIGURED"
  | "APPLICATION_GENERATED"
  | "INTERFACE_GENERATED"
  | "NETWORK_GENERATED";

export type ValidationLayer =
  | "CANONICAL"
  | "STRUCTURE"
  | "FORMAT"
  | "BUSINESS_RULES"
  | "CLIENT_PROFILE"
  | "FIN_ENVELOPE"
  | "XML_WELL_FORMED"
  | "XSD"
  | "APPHDR_CONSISTENCY";

export type LayerState = "PASSED" | "FAILED" | "NOT_APPLICABLE" | "SKIPPED";

export type BusinessArea =
  | "SECURITIES_SETTLEMENT"
  | "SETTLEMENT_COMMANDS"
  | "PENALTIES"
  | "CORPORATE_ACTIONS"
  | "OTHER";

export interface CapabilityDimensions {
  structure: "CONFIGURED_SUBSET" | "COMPILED_FROM_SCHEMA" | "UNVERIFIED";
  businessRules: "NOT_CONFIGURED" | "CONFIGURED_SUBSET" | "SOURCE_DERIVED" | "REVIEWED";
  marketPractice: "NOT_CONFIGURED" | "CONFIGURED" | "VERIFIED";
  clientProfile: "NOT_CONFIGURED" | "CONFIGURED" | "VERIFIED";
  externalValidation: "NOT_RUN" | "PASSED" | "FAILED";
}

export interface CatalogueEntry {
  format: MessageFormat;
  messageType: string;
  version: string | null;
  name: string;
  shortDescription: string;
  businessArea: BusinessArea;
  businessAreaLabel: string;
  generatable: boolean;
  outputModes: OutputMode[];
  fieldCount: number;
  mandatoryFieldCount: number;
  sampleVariants: SampleVariant[];
  authoritativeCompletenessKnown: boolean;
  sourceReference: string;
  limitations: string[];
  capability: CapabilityDimensions | null;
  capabilitySummary: string;
}

export interface CatalogueBusinessArea {
  id: BusinessArea;
  label: string;
  messageCount: number;
}

export interface CatalogueFormat {
  id: MessageFormat;
  label: string;
  description: string;
  businessAreas: CatalogueBusinessArea[];
  messageCount: number;
}

export interface StudioCatalogue {
  formats: CatalogueFormat[];
  messages: CatalogueEntry[];
  profiles: string[];
  defaultProfileId: string;
}

export interface FieldExample {
  value: string;
  explanation: string;
}

/**
 * The control a field deserves, decided by the specification rather than by this component.
 *
 * The browser used to infer it from whether one of the field's examples happened to appear
 * in its code list, which got it wrong in both directions: a quantity such as `UNIT/1000`
 * became a free-text box, and any value outside the list silently downgraded a dropdown
 * back to a text input.
 */
export type InputKind =
  | "TEXT"
  | "SELECT"
  | "DATE"
  | "AMOUNT"
  | "QUANTITY"
  | "NARRATIVE"
  | "REFERENCE"
  | "IDENTIFIER"
  | "PARTY_BIC"
  | "PARTY_PROPRIETARY"
  | "INDICATOR";

/** One controlled code, with the words a person uses for it. */
export interface AllowedValue {
  code: string;
  label: string;
  description: string;
}

export interface SpecField {
  id: string;
  format: MessageFormat;
  groupId: string;
  groupLabel: string;
  groupOrder: number;
  order: number;
  presence: Presence;
  repeatable: boolean;
  maxOccurs: number;
  displayName: string;
  businessMeaning: string;
  technicalMeaning: string;
  whyUsed: string;
  businessQuestion: string;
  missingImpact: string | null;
  formatExplanation: string;
  allowedCodes: string[];
  allowedValues: AllowedValue[];
  codeList: string | null;
  inputKind: InputKind;
  /** The literal the composer writes in front of the value. The user never types it. */
  literalPrefix: string | null;
  userEntersLiteralPrefix: boolean;
  identifierTypes: string[];
  maxLength: number | null;
  examples: FieldExample[];
  commonMistakes: string[];
  dependsOn: string[];
  conditionExplanation: string | null;
  businessPath: string | null;
  sequence: string | null;
  sequenceCode: string | null;
  tag: string | null;
  qualifier: string | null;
  option: string | null;
  xpath: string | null;
  dataType: string | null;
  choiceGroup: string | null;
  sourceReference: string;
  standardsRelease: string;
}

export interface SpecGroup {
  id: string;
  label: string;
  description: string;
  order: number;
  repeatable: boolean;
  maxOccurs: number;
  parentId: string | null;
}

export interface MessageSpec {
  format: MessageFormat;
  messageType: string;
  version: string | null;
  name: string;
  businessArea: BusinessArea;
  scope: string;
  shortDescription: string;
  namespace: string | null;
  groups: SpecGroup[];
  fields: SpecField[];
  outputModes: OutputMode[];
  authoritativeCompletenessKnown: boolean;
  sourceReference: string;
  standardsRelease: string;
  limitations: string[];
  capability: CapabilityDimensions | null;
  capabilitySummary: string;
}

export interface FieldInput {
  id?: string | null;
  sequence?: string | null;
  occurrence?: number;
  tag?: string | null;
  qualifier?: string | null;
  option?: string | null;
  value: string;
}

export interface ElementInput {
  path: string;
  occurrence?: number;
  value: string;
}

export interface EnvelopeOverride {
  sender?: string | null;
  receiver?: string | null;
  sessionNumber?: string | null;
  sequenceNumber?: string | null;
  priority?: string | null;
  messageUserReference?: string | null;
  businessMessageIdentifier?: string | null;
  creationDate?: string | null;
}

export interface GenerateRequest {
  format: MessageFormat;
  messageType: string;
  profileId?: string;
  scenarioId?: string | null;
  fields?: FieldInput[];
  elements?: ElementInput[];
  outputModes?: OutputMode[] | null;
  envelope?: EnvelopeOverride | null;
  persist?: boolean;
}

export interface ValidationIssue {
  ruleId: string;
  severity: IssueSeverity;
  layer: ValidationLayer;
  field: string | null;
  location: string | null;
  message: string;
  expected: string | null;
  currentValue: string | null;
  suggestion: string | null;
}

export interface LayerResult {
  layer: ValidationLayer;
  state: LayerState;
  detail: string | null;
}

export interface ValidationResult {
  valid: boolean;
  summary: string;
  layers: LayerResult[];
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
}

export interface EnvelopeField {
  block: string;
  name: string;
  value: string | null;
  origin: FieldOrigin;
  explanation: string;
}

export interface MessageOutputs {
  block4: string | null;
  fin: string | null;
  txt: string | null;
  appHdr: string | null;
  document: string | null;
  xml: string | null;
  canonicalJson: Record<string, unknown> | null;
}

export interface RenderedLine {
  lineNumber: number;
  text: string;
  fieldId: string | null;
  displayName: string | null;
  origin: FieldOrigin;
}

export interface GenerateResult {
  messageId: string | null;
  correlationId: string;
  scenarioId: string | null;
  format: MessageFormat;
  messageType: string;
  version: string | null;
  profileId: string;
  profileVersion: string;
  valid: boolean;
  validation: ValidationResult;
  outputs: MessageOutputs;
  envelopeFields: EnvelopeField[];
  renderedLines: RenderedLine[];
  checksum: string;
  availableOutputModes: OutputMode[];
  generatedAt: string;
  disclaimer: string;
}

export interface SampleMessage {
  sampleId: string;
  format: MessageFormat;
  messageType: string;
  variant: SampleVariant;
  title: string;
  description: string;
  fieldCount: number;
  inputs: FieldInput[];
  elements: ElementInput[];
}

export interface ExcelScenarioResult {
  scenarioId: string;
  rowNumbers: number[];
  format: MessageFormat | null;
  messageType: string | null;
  status: string;
  valid: boolean;
  validation: ValidationResult | null;
  outputs: MessageOutputs | null;
  messageId: string | null;
  checksum: string | null;
}

export interface ExcelGenerateResponse {
  requestId: string;
  format: MessageFormat;
  totalScenarios: number;
  generated: number;
  failed: number;
  results: ExcelScenarioResult[];
  disclaimer: string;
}

export interface RecentMessage {
  messageId: string;
  correlationId: string;
  scenarioId: string | null;
  format: MessageFormat;
  messageType: string;
  profileId: string;
  valid: boolean;
  errorCount: number;
  warningCount: number;
  checksum: string;
  source: string;
  createdAt: string;
}

export interface IntelligenceHit {
  id: string;
  format: MessageFormat;
  messageTypes: string[];
  label: string;
  address: string;
  presence: Presence;
  summary: string;
  score: number;
}

export interface IntelligenceSearchResponse {
  query: string;
  total: number;
  results: IntelligenceHit[];
  deterministic: boolean;
  llmUsed: boolean;
}

export interface IntelligenceDetail {
  id: string;
  format: MessageFormat;
  label: string;
  address: string;
  messageTypes: string[];
  presence: Presence;
  businessMeaning: string;
  technicalMeaning: string;
  whyUsed: string;
  formatExplanation: string;
  allowedCodes: string[];
  allowedValues: AllowedValue[];
  codeList: string | null;
  inputKind: InputKind;
  /** The literal the composer writes in front of the value. The user never types it. */
  literalPrefix: string | null;
  userEntersLiteralPrefix: boolean;
  identifierTypes: string[];
  maxLength: number | null;
  examples: FieldExample[];
  commonMistakes: string[];
  dependsOn: string[];
  conditionExplanation: string | null;
  dataType: string | null;
  cardinality: string | null;
  parent: string | null;
  sourceReference: string;
  standardsRelease: string;
  sampleLines: string[];
}

export const PRESENCE_LABEL: Record<Presence, string> = {
  MANDATORY: "Required",
  CONDITIONAL: "Conditional",
  OPTIONAL: "Optional",
};

export const OUTPUT_LABEL: Record<OutputMode, string> = {
  BLOCK4: "Block 4 only",
  FIN: "FIN message",
  TXT: "Plain text",
  CANONICAL_JSON: "Canonical JSON",
  XML: "AppHdr + Document",
  APPHDR: "AppHdr only",
  DOCUMENT: "Document only",
};

export const LAYER_LABEL: Record<ValidationLayer, string> = {
  CANONICAL: "Input is addressable",
  STRUCTURE: "Message structure",
  FORMAT: "Field formats",
  BUSINESS_RULES: "Business rules",
  CLIENT_PROFILE: "Client profile",
  FIN_ENVELOPE: "FIN envelope",
  XML_WELL_FORMED: "XML is well formed",
  XSD: "Schema validation",
  APPHDR_CONSISTENCY: "Header matches document",
};

export const ORIGIN_LABEL: Record<FieldOrigin, string> = {
  USER_ENTERED: "You entered this",
  PROFILE_CONFIGURED: "From the client profile",
  APPLICATION_GENERATED: "Built by the platform",
  INTERFACE_GENERATED: "Your messaging interface adds this",
  NETWORK_GENERATED: "The network adds this",
};

export type DiffKind = "UNCHANGED" | "ADDED" | "REMOVED" | "CHANGED";

export type DiffReason =
  | "USER_EDIT"
  | "NORMALISATION"
  | "IMPORT_DROPPED"
  | "NOT_REPRODUCED"
  | "UNEXPLAINED";

export type DiffBasis = "FIN_LINES" | "CANONICAL_XML";

export interface DiffLine {
  kind: DiffKind;
  originalLine: number | null;
  regeneratedLine: number | null;
  originalText: string | null;
  regeneratedText: string | null;
  /** Absent on an unchanged line; always present otherwise. */
  reason: DiffReason | null;
  explanation: string | null;
  field: string | null;
  location: string | null;
}

export interface DiffSummary {
  identical: boolean;
  unchanged: number;
  added: number;
  removed: number;
  changed: number;
  /** Differences with a known, benign cause. Never a reason to investigate. */
  expected: number;
  /** Content the original held that the configured subset could not carry. */
  dropped: number;
  /** The only figure worth acting on. */
  unexplained: number;
  byReason: Record<string, number>;
}

export interface MessageDiff {
  format: MessageFormat;
  basis: DiffBasis;
  compared: string;
  /** False when the messages were too large, or too broken, to list the differences of. */
  comparable: boolean;
  notComparedReason: string | null;
  summary: DiffSummary;
  lines: DiffLine[];
  notes: string[];
}

export interface DiffResult {
  format: MessageFormat;
  messageType: string;
  result: GenerateResult;
  diff: MessageDiff;
  importIssues: ValidationIssue[];
  importWarnings: ValidationIssue[];
  disclaimer: string;
}

export interface ImportRequest {
  text: string;
  /** Only consulted when the message does not name itself — a pasted MT text block. */
  messageType?: string | null;
  profileId?: string;
  scenarioId?: string | null;
  outputModes?: OutputMode[] | null;
  persist?: boolean;
}

export interface ImportResult {
  format: MessageFormat;
  messageType: string;
  version: string | null;
  namespace: string | null;
  profileId: string;
  /** MX: whether the document carried a business application header. */
  appHdrPresent: boolean;
  /** MT: which FIN blocks the text carried. `["4"]` for a pasted text block. */
  finBlocks: string[];
  /** How many values were read, whichever format they came from. */
  elementCount: number;
  elements: ElementInput[];
  fields: FieldInput[];
  envelope: EnvelopeOverride | null;
  /** Anything the document held that could not be imported. Never silently dropped. */
  importIssues: ValidationIssue[];
  importWarnings: ValidationIssue[];
  result: GenerateResult;
  /** The imported message compared with the one just regenerated from it. */
  diff: MessageDiff;
  disclaimer: string;
}
