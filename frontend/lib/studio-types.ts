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
  | "MARKET_PRACTICE"
  | "CLIENT_PROFILE"
  | "FIN_ENVELOPE"
  | "XML_WELL_FORMED"
  | "XSD"
  | "APPHDR_CONSISTENCY";

export type LayerState = "PASSED" | "FAILED" | "NOT_APPLICABLE" | "SKIPPED";

export type BusinessArea =
  | "PAYMENTS_CLEARING_SETTLEMENT"
  | "PAYMENT_INITIATION"
  | "CASH_MANAGEMENT"
  | "SECURITIES_SETTLEMENT"
  | "SECURITIES_MANAGEMENT"
  | "SECURITIES_EVENTS"
  | "SETTLEMENT_COMMANDS"
  | "PENALTIES"
  | "CORPORATE_ACTIONS"
  // Catalogue buckets for messages compiled from source evidence. Never a capability claim.
  | "CUSTOMER_PAYMENTS"
  | "FINANCIAL_INSTITUTION_TRANSFERS"
  | "TREASURY_MARKETS"
  | "COLLECTIONS_CASH_LETTERS"
  | "SECURITIES_MARKETS"
  | "PRECIOUS_METALS_SYNDICATIONS"
  | "DOCUMENTARY_CREDITS_GUARANTEES"
  | "TRAVELLERS_CHEQUES"
  | "SYSTEM_MESSAGES"
  | "COMMON_GROUP"
  | "OTHER";

/**
 * Which registry a message resolves from. The configured lane is the reviewed repository
 * subset; the knowledge-preview lane is compiled from indexed source evidence and is never
 * implicit — every call that touches a preview message names the lane and the release.
 */
export type Lane = "CONFIGURED" | "KNOWLEDGE_PREVIEW";

export type ReleaseLane = "CURRENT_LIVE" | "FUTURE_TEST" | "UNKNOWN";

export type Readiness =
  | "KNOWLEDGE_ONLY"
  | "STRUCTURE_AVAILABLE"
  | "STRUCTURE_VERIFIED"
  | "GENERATION_READY";

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
  /** The same messageType can appear once per lane and release. */
  lane: Lane;
  /** MT: "SR2025" / "SR2026". MX: the full version, such as "pacs.008.001.14". */
  release: string | null;
  releaseLane: ReleaseLane | null;
  readiness: Readiness;
  /** Plain language — "Configured & validated", "Knowledge available; structure not yet compilable". */
  readinessLabel: string;
  /** Why a non-generatable entry is not generatable. Empty when it is. */
  blockers: string[];
  structureSource: string | null;
  rulesStatus: string;
  knowledgeSources: number;
  /** A validated AI sample is already cached for this entry. */
  aiSampleReady: boolean;
  automationReady: boolean;
}

/** What tells two catalogue entries apart. A messageType alone no longer does. */
export function entryKey(entry: {
  format: MessageFormat;
  messageType: string;
  lane: Lane;
  release: string | null;
}): string {
  return `${entry.format}|${entry.messageType}|${entry.lane}|${entry.release ?? ""}`;
}

/**
 * The identity the API wants in a request. MX preview entries are addressed by their full
 * version and carry no release; MT preview entries by type plus release.
 */
export interface MessageRef {
  format: MessageFormat;
  messageType: string;
  lane: Lane;
  release: string | null;
}

export function messageRef(entry: CatalogueEntry): MessageRef {
  const preview = entry.lane === "KNOWLEDGE_PREVIEW";
  if (preview && entry.format === "MX") {
    return {
      format: entry.format,
      messageType: entry.version ?? entry.messageType,
      lane: entry.lane,
      release: null,
    };
  }
  return {
    format: entry.format,
    messageType: entry.messageType,
    lane: entry.lane,
    release: preview ? entry.release : null,
  };
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
  /** Every entry in this format, previews included. */
  messageCount: number;
  /** The reviewed configured entries alone. */
  configuredMessageCount: number;
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
  minOccurs: number;
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
  lane: Lane;
  release: string | null;
  /** What generation in this lane rests on, in one sentence. Null for the configured lane. */
  capabilityStatement: string | null;
  structureSource: string | null;
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
  /** Defaults to the configured lane. The preview lane is never implicit. */
  lane?: Lane;
  release?: string | null;
}

export interface ValidationOccurrence {
  sequencePath: string;
  occurrence: number;
  path: string;
  lineage: string[];
}

export interface ValidationIssue {
  ruleId: string;
  severity: IssueSeverity;
  layer: ValidationLayer;
  field: string | null;
  location: string | null;
  occurrence?: ValidationOccurrence | null;
  message: string;
  expected: string | null;
  currentValue: string | null;
  suggestion: string | null;
  /**
   * Present only when the finding came from an installed rule pack. The platform's own
   * built-in checks leave these null, which is itself the honest answer: they have no
   * external source to cite.
   */
  ruleLayer?: string | null;
  rulePackId?: string | null;
  sourceReference?: string | null;
  reviewStatus?: string | null;
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
  lane: Lane;
  provenance: LaneProvenance | null;
}

/** What a generated message in either lane rests on. Stated, never implied. */
export interface LaneProvenance {
  lane: Lane;
  release: string | null;
  releaseLane: ReleaseLane | null;
  structureSource: string;
  ruleStatus: string;
  validationLevel: string;
  capabilityStatement: string | null;
  sourceProvenance: string[];
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
  /** The lane the scenario was generated in; a failed scenario carries no provenance. */
  lane?: Lane;
  provenance?: LaneProvenance | null;
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

export interface FieldRuleSummary {
  ruleId: string;
  /** The authority layer in words — "Market practice rule". */
  layer: string;
  title: string;
  meaning: string;
  /** Source identity and location. Never licensed prose. */
  sourceReference: string;
  reviewStatus: string;
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
  rules?: FieldRuleSummary[];
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
  MARKET_PRACTICE: "Market practice",
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
  /** A preview-lane MT import needs the message type and the release as well. */
  lane?: Lane;
  release?: string | null;
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

/* -------------------------------------------------------------- conversion */

export interface MappingIdentity {
  format: MessageFormat;
  messageType: string;
  release: string | null;
  lane: Lane;
}

export interface MappingProvenance {
  sourceType: string;
  sourceReference: string;
  sourceChecksum: string;
  reviewState: string;
  reviewedBy: string | null;
  productionEligible: boolean;
  limitations: string[];
}

export interface ConversionTarget {
  packId: string;
  packVersion: string;
  target: MappingIdentity;
  reviewState: string;
  productionEligible: boolean;
  previewOnly: boolean;
  provenance: MappingProvenance;
}

export interface ConversionTargetsResponse {
  source: MappingIdentity;
  targets: ConversionTarget[];
  authorityNote: string;
}

export interface ConvertRequest {
  sourceFormat: MessageFormat;
  sourceMessage?: string | null;
  sourceRelease?: string | null;
  sourceLane?: Lane;
  rawMessage?: string | null;
  fields?: FieldInput[];
  targetFormat: MessageFormat;
  targetMessage: string;
  targetVersion: string;
  targetLane?: Lane;
  targetValues?: ElementInput[];
  profileId?: string;
  mappingPackId?: string | null;
  allowSyntheticPreview?: boolean;
}

export interface MissingTarget {
  fieldId: string;
  displayName: string;
  question: string;
  reason: string;
}

export interface AppliedMapping {
  ruleId: string;
  kind: string;
  semantic: string | null;
  sourceRefs: string[];
  targetRefs: string[];
  transform: string;
}

export interface ConversionReport {
  source: MappingIdentity;
  target: MappingIdentity;
  mappingPackId: string;
  mappingPackVersion: string;
  provenance: MappingProvenance;
  mappedSourceFields: string[];
  sourceFieldsNotRepresented: string[];
  mappedTargetFields: string[];
  derivedTargetFields: string[];
  userSuppliedTargetFields: string[];
  targetRequiredMissing: MissingTarget[];
  transformationsApplied: AppliedMapping[];
  limitations: string[];
}

export interface ConversionResponse {
  status: "BLOCKED_BY_MAPPING_EVIDENCE" | "NEEDS_INPUT" | "READY" | "INVALID_TARGET";
  targetValues: ElementInput[];
  report: ConversionReport | null;
  validation: ValidationResult | null;
  generation: GenerateResult | null;
  outputXml: string | null;
  message: string;
}

/* ------------------------------------------------------------- knowledge base */

/**
 * `/api/v1/knowledge`. Everything here is safe to show: ids, titles, counts and policies.
 * The API never returns a credential, an absolute path or a full licensed document, so
 * nothing below can either.
 */

export interface KnowledgeCounts {
  sources: number;
  sourcesDeleted: number;
  segments: number;
  embeddings: number;
  messages: number;
  structures: number;
  samplesCached: number;
}

export interface KnowledgeRun {
  runId: string;
  startedAt: string | null;
  finishedAt: string | null;
  state: string;
  stats: Record<string, number | string | unknown[]>;
}

export interface KnowledgeStatus {
  mode: string;
  enabled: boolean;
  indexed: boolean;
  adminEnabled: boolean;
  databasePresent: boolean;
  roots: string[];
  rootsMissing: string[];
  counts: KnowledgeCounts;
  lastRun: KnowledgeRun | null;
  corpusVersion: string | null;
  embeddingProvider: string;
  /** Whether a deployment is configured — never which one. */
  embeddingDeploymentConfigured: boolean;
  embeddingDimensions: number | null;
  embeddingPolicyStatement: string | null;
  llmProvider: string;
  sourcesEmbeddingBlocked: number;
  sourcesEmbeddingAllowed: number;
  loadErrors: string[];
  /** Set when the base is not indexed; says how to index it. */
  message: string | null;
}

export interface KnowledgeSourceRef {
  sourceId: string;
  documentType: string;
  pages: number | null;
  state: string;
  checksum: string;
}

export interface KnowledgeMessageEntry {
  format: MessageFormat;
  messageType: string;
  messageVersion: string | null;
  release: string | null;
  title: string | null;
  sources: KnowledgeSourceRef[];
  segments: number;
  embedded: number;
  embeddingPolicy: string | null;
  llmPolicy: string | null;
  readiness: Readiness;
  blockers: string[];
  structureSource: string | null;
  gates?: Record<string, { passed: boolean; detail: string }>;
}

export interface KnowledgeMessagesResponse {
  indexed: boolean;
  messages: KnowledgeMessageEntry[];
  message: string | null;
}

export interface KnowledgeSource {
  sourceId: string;
  checksum: string;
  relativePaths: string[];
  sourceType: string;
  format: string;
  documentType: string;
  classification: string;
  messageType: string | null;
  messageVersion: string | null;
  release: string | null;
  title: string | null;
  pageCount: number | null;
  embeddingPolicy: string;
  llmPolicy: string;
  state: string;
  segments: number;
  embedded: number;
  failureCode: string | null;
  failureDetail: string | null;
  deleted: boolean;
}

export interface KnowledgeSourcesResponse {
  indexed: boolean;
  sources: KnowledgeSource[];
  message: string | null;
}

export interface KnowledgeSearchRequest {
  query: string;
  format?: MessageFormat;
  messageType?: string;
  release?: string;
  sections?: string[];
  limit?: number;
  lexicalOnly?: boolean;
}

/** One cited section of one indexed source. A snippet is present only where policy allows. */
export interface KnowledgeCitation {
  sourceId: string;
  documentTitle: string;
  format?: string;
  messageType: string | null;
  messageVersion: string | null;
  release: string | null;
  documentType?: string;
  section: string;
  page: number | null;
  heading: string | null;
  segmentId: string;
  segmentHash: string;
  score: number;
  method: string;
  snippet: string | null;
}

export interface KnowledgeSearchResponse {
  query: string;
  queryType: string;
  indexed: boolean;
  results: KnowledgeCitation[];
  lexicalCandidates: number;
  semanticCandidates: number;
  semanticAvailable: boolean;
  semanticReason: string | null;
  latencyMs: number;
  contextChars: number;
  corpusVersion: string | null;
  policyStatement: string | null;
  message: string | null;
}

export interface KnowledgeTelemetry {
  indexed: boolean;
  llm: {
    operations: number;
    calls: number;
    promptTokens: number;
    completionTokens: number;
    cacheHits: number;
    callsAvoided: number;
    tokensAvoided: number;
    averageLatencyMs: number;
  };
  embeddings: {
    vectorsStored: number;
    segmentsEmbedded: number;
    lastRunRequests: number;
    lastRunCacheHits: number;
    lastRunRequestsAvoided: number;
    lastRunTokens: number;
    lastRunBlockedSegments: number;
    provider: string;
  };
  retrieval: {
    queries: number;
    averageLatencyMs: number;
    averageSegments: number;
    hybrid: number;
    lexical: number;
    semantic: number;
  };
  samples: { cached: number; cacheHits: number };
  overview: {
    operationsToday: number;
    aiCallsToday: number;
    tokensToday: number;
    cacheHitsToday: number;
    retentionDays: number;
  };
  knowledge: {
    sources: number;
    messages: number;
    segments: number;
    lastSync: KnowledgeRun | null;
    syncState: string;
    loadErrors: string[];
  };
  recentOperations: Array<{
    requestId: string;
    timestamp: string;
    operation: string;
    messageType: string | null;
    release: string | null;
    provider: string;
    model: string;
    llmCalls: number;
    tokens: number;
    cacheHit: boolean;
    latencyMs: number;
    ragUsed: boolean;
    ragMode: string | null;
    queryType: string | null;
    formatFilter: string | null;
    lexicalCandidates: number;
    semanticCandidates: number;
    evidenceCount: number;
    contextChars: number;
    retrievalLatencyMs: number;
    embeddingCalls: number;
    embeddingTokens: number;
    embeddingCacheHits: number;
    embeddingLatencyMs: number;
    outcome: string;
  }>;
  /** Always false unless the provider reports cost. The page never computes one. */
  costAvailable: boolean;
  costNote: string;
}

export interface KnowledgeSyncResponse {
  run: Record<string, unknown>;
  status: KnowledgeStatus;
}

/* ---------------------------------------------------------------- AI authoring */

/**
 * `/api/v1/ai`. The model prepares values and answers questions; every message that comes
 * back was composed and validated by the deterministic engine from values it accepted.
 */

export interface AiUsage {
  /** "deterministic" means no model was involved at all. */
  provider: string;
  model: string;
  requestId: string;
  llmCalls: number;
  promptTokens: number;
  completionTokens: number;
  latencyMs: number;
  attempts: number;
  cacheHit: boolean;
  callsAvoided: number;
  tokensAvoided: number;
  ragUsed: boolean;
  ragMode: string | null;
  queryType: string | null;
  evidenceCount: number;
  lexicalCandidates: number;
  semanticCandidates: number;
  contextChars: number;
  retrievalLatencyMs: number;
  embeddingCalls: number;
  costAvailable: boolean;
}

export interface RetrievalEvidence {
  segmentsUsed: number;
  semanticAvailable: boolean;
  semanticReason: string | null;
  textSentToModel: boolean;
  latencyMs: number;
  contextChars: number;
  corpusVersion: string | null;
  citations: KnowledgeCitation[];
}

export interface AiCapability {
  readiness: Readiness;
  lane: Lane;
  capabilityStatement: string | null;
  structureSource: string | null;
}

export interface AiCacheInfo {
  status: "HIT" | "MISS";
  llmCallsAvoided: number;
  tokensAvoided: number;
}

export interface CanonicalValue {
  fieldId: string;
  occurrence: number;
  value: string;
}

export interface RejectedValue {
  fieldId: string;
  code: string;
  [key: string]: unknown;
}

export interface AiIdentifyRequest {
  request: string;
  format?: MessageFormat;
  limit?: number;
}

export interface AiCandidate {
  format: MessageFormat;
  messageType: string;
  version: string | null;
  release: string | null;
  lane: Lane;
  name: string;
  readiness: Readiness;
  readinessLabel: string;
  generatable: boolean;
  confidence: number;
  reason: string;
}

export interface AiIdentifyResponse {
  request: string;
  candidates: AiCandidate[];
  explanation: string;
  missingInformation: string[];
  confidence: number;
  retrievalEvidence: RetrievalEvidence;
  aiUsage: AiUsage;
  deterministicCandidates: unknown[];
}

export interface AiPrepareRequest {
  scenario: string;
  format?: MessageFormat;
  messageType?: string;
  release?: string | null;
  lane?: Lane;
  knownValues?: CanonicalValue[];
  profileId?: string;
}

export interface AiPrepareResponse {
  format: MessageFormat;
  messageType: string;
  version: string | null;
  release: string | null;
  lane: Lane;
  scenario: string;
  /** Keyed by `SpecField.id` — MT row ids, MX element paths — so they drop onto the form. */
  canonicalValues: CanonicalValue[];
  rejectedValues: RejectedValue[];
  missingFields: string[];
  questions: string[];
  notes: string[];
  validation: ValidationResult;
  valid: boolean;
  capability: AiCapability;
  identification: AiIdentifyResponse | null;
  retrievalEvidence: RetrievalEvidence;
  aiUsage: AiUsage;
}

export interface AiSampleRequest {
  format: MessageFormat;
  messageType: string;
  release?: string | null;
  lane?: Lane;
  sampleType: SampleVariant;
  profileId?: string;
  scenario?: string;
  /** Bypass the validated-sample cache — the only way a repeat call reaches the model. */
  refresh?: boolean;
}

export interface AiSampleResponse {
  sampleId: string;
  format: MessageFormat;
  messageType: string;
  version: string | null;
  release: string | null;
  lane: Lane;
  sampleType: SampleVariant;
  title: string;
  description: string;
  canonicalValues: CanonicalValue[];
  inputs: FieldInput[];
  elements: ElementInput[];
  validation: ValidationResult;
  valid: boolean;
  outputs: MessageOutputs;
  checksum: string;
  provenance: LaneProvenance | null;
  capability: AiCapability;
  cache: AiCacheInfo;
  aiUsage: AiUsage;
  retrievalEvidence: RetrievalEvidence;
  repair: { attempts: number; log: unknown[]; outcome: string };
  roundTrip: Record<string, unknown> | null;
  synthetic: true;
}

export interface AiTestDataRequest {
  format: MessageFormat;
  messageType: string;
  release?: string | null;
  lane?: Lane;
  scenario: string;
  count: number;
  sampleType?: SampleVariant;
  testIntent?: "POSITIVE" | "NEGATIVE";
  profileId?: string;
  reviewerMode?: boolean;
  outputModes?: OutputMode[];
}

export interface AiTestScenario {
  scenarioId: string;
  title: string;
  canonicalValues: CanonicalValue[];
  rejectedValues: RejectedValue[];
  validation: ValidationResult;
  valid: boolean;
  outputs: MessageOutputs;
  checksum: string;
  expectedRuleId?: string | null;
  actualFindings?: string[];
  proven?: boolean;
  status?: string;
}

export interface AiTestDataResponse {
  requestId: string;
  format: MessageFormat;
  messageType: string;
  version: string | null;
  release: string | null;
  lane: Lane;
  testIntent: string;
  capability: AiCapability;
  scenarios: AiTestScenario[];
  generated: number;
  total: number;
  retrievalEvidence: RetrievalEvidence;
  aiUsage: AiUsage;
  cache: AiCacheInfo;
  note: string | null;
  synthetic: true;
}

export interface AiAskRequest {
  question: string;
  format?: MessageFormat;
  messageType?: string;
  release?: string | null;
  queryType?: string;
}

export type AiSupport = "SUPPORTED" | "PARTIAL" | "UNSUPPORTED_BY_EVIDENCE";

export interface AiAskResponse {
  question: string;
  answer: string;
  supported: AiSupport;
  /** Segment ids; the matching `retrievalEvidence.citations` carry title, section, page. */
  citations: string[];
  caveats: string[];
  retrievalEvidence: RetrievalEvidence;
  aiUsage: AiUsage;
}

export interface AiPresentationRequest {
  format: MessageFormat;
  messageType: string;
  release?: string | null;
  lane?: Lane;
  fieldId: string;
}

export interface AiPresentationResponse {
  fieldId: string;
  presentation: {
    displayLabel: string;
    businessMeaning: string;
    businessQuestion: string;
    example: string;
    whyNeeded: string;
    commonMistake: string;
    citations: string[];
  };
  cache: AiCacheInfo;
  /** Always "NONE": presentation text never decides validity. */
  authority: "NONE";
  source: string;
}

export interface AiCompareRequest {
  format: MessageFormat;
  messageType: string;
  releaseA: string;
  releaseB: string;
  focus?: string;
}

export interface AiCompareResponse {
  format: MessageFormat;
  messageType: string;
  releaseA: string;
  releaseB: string;
  structural: {
    comparable: boolean;
    added: string[];
    removed: string[];
    changed: string[];
    differences: Array<{ area: string; change: string }>;
  };
  summary: string;
  differences: Array<{ area: string; change: string; citations: string[] }>;
  citations: string[];
  retrievalEvidence: RetrievalEvidence;
  aiUsage: AiUsage;
}
