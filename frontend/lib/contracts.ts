export type MessageType =
  | "MT540"
  | "MT541"
  | "MT542"
  | "MT543"
  | "MT544"
  | "MT545"
  | "MT546"
  | "MT547"
  | "MT548"
  | "MT530"
  | "MT537"
  | "MT564"
  | "MT565"
  | "MT566"
  | "MT567"
  | "MT568";

export type CapabilityState =
  | "PRODUCTION_CAPABLE"
  | "UAT_READY"
  | "PARTIAL"
  | "CATALOGUE_ONLY"
  | "DISABLED"
  | "UNSUPPORTED";

export interface SequenceSpecification {
  path: string;
  code: string;
  parentPath?: string;
  order: number;
  minOccurs: number;
  maxOccurs: number;
  insertAfterTag?: string;
}

export interface FieldSpecification {
  rowId: string;
  rowNumber: number;
  messageType: MessageType;
  workflowModule: WorkflowModule;
  sequencePath: string;
  sequenceCode: string;
  tag: string;
  option: string;
  qualifier?: string;
  businessPath: string;
  businessName: string;
  technicalName: string;
  presence: "MANDATORY" | "OPTIONAL" | "CONDITIONAL";
  minOccurs: number;
  maxOccurs: number;
  repeatable: boolean;
  format: string;
  allowedOptions: string[];
  allowedCodes: string[];
  conditionExpression?: string;
  conditionExplanation?: string;
  knowledgeId: string;
  source: {
    verificationStatus: string;
    sourceReference: string;
    standardsRelease: string;
  };
}

export interface MessageSpecification {
  messageType: MessageType;
  name: string;
  scope: string;
  capability: CapabilityState;
  capabilityExplanation: string;
  workflowModule: WorkflowModule;
  standardsRelease: string;
  registryVersion: string;
  authoritativeCompletenessKnown: boolean;
  sequences: SequenceSpecification[];
  fields: FieldSpecification[];
}

export interface MessageCatalogue {
  supported: MessageSpecification[];
  catalogueOnly: Array<{
    messageType: string;
    name: string;
    capability: "CATALOGUE_ONLY";
    message: string;
    sourceReference: string;
  }>;
  registryVersion: string;
}

export interface MessageCoverage {
  messageType: MessageType;
  capability: CapabilityState;
  authoritativeCompletenessKnown: boolean;
  configuredFormatRows: number;
  knowledgeRecords: CoverageMetric;
  formSupportedFields: CoverageMetric;
  composerSupportedFields: CoverageMetric;
  parserSupportedFields: CoverageMetric;
  validatorSupportedFields: CoverageMetric;
  sampleCoveredFields: CoverageMetric;
  goldenTestedFields: CoverageMetric;
  productionGatePassed: boolean;
  gaps: string[];
}

export interface CoverageMetric {
  covered: number;
  configured: number;
  percentage: number;
}

export interface SampleSummary {
  sampleId: string;
  messageType: MessageType;
  scenario: string;
  profileId: string;
  profileVersion: string;
  standardsRelease: string;
  capability: CapabilityState;
  generatedByProductionComposer: boolean;
  synthetic: boolean;
}

export interface SampleDetail extends SampleSummary {
  rawMessage: string;
  annotations: Array<{
    lineNumber: number;
    rawLine: string;
    sequencePath: string;
    sequenceOccurrence: number;
    rowId: string;
    knowledgeId: string;
    tag: string;
    qualifier?: string;
    enteredValue: string;
    businessMeaning: string;
    whyUsed: string;
    presence: "MANDATORY" | "OPTIONAL" | "CONDITIONAL";
    source: "SAMPLE_DATA";
  }>;
  coveredRowIds: string[];
  knownLimitations: string[];
}

export interface PlatformSession {
  authenticated: boolean;
  user?: {
    userId: string;
    tenantId: string;
    displayName: string;
    roles: string[];
  };
  authMode: string;
  expiresAt?: string;
}

export interface SecureDraft {
  draftId: string;
  messageType: MessageType;
  profileId: string;
  profileVersion: string;
  standardsRelease: string;
  capability: CapabilityState;
  status: string;
  revision: number;
  createdBy: string;
  sequences: Array<{
    sequenceId: string;
    sequencePath: string;
    parentSequenceId?: string;
    occurrence: number;
  }>;
  fields: Array<{
    fieldId: string;
    sequenceId: string;
    rowId: string;
    value: string;
    masked: boolean;
    source: string;
    confirmed: boolean;
    classification: string;
  }>;
  currentChecksum?: string;
  validationLevels: Record<string, string>;
  createdAt: string;
  updatedAt: string;
}

export interface SecureComposition {
  draftId: string;
  revision: number;
  messageType: MessageType;
  block4: string;
  checksum: string;
  validationLevels: Record<string, string>;
  findings: string[];
  capability: CapabilityState;
  disclaimer: string;
}

export type WorkflowModule =
  | "SETTLEMENT"
  | "SETTLEMENT_COMMAND"
  | "PENALTIES"
  | "CORPORATE_ACTIONS";

export interface TagKnowledgeRecord {
  knowledgeId: string;
  messageType: MessageType;
  workflowModule: WorkflowModule;
  sequencePath: string;
  fieldTag: string;
  qualifier?: string;
  businessPath: string;
  displayName: string;
  businessMeaning: string;
  technicalMeaning: string;
  whyUsed: string;
  businessQuestion: string;
  missingImpact: string;
  presence: "MANDATORY" | "OPTIONAL" | "CONDITIONAL";
  conditionExpression?: string;
  conditionExplanation?: string;
  supportedOptions: string[];
  allowedCodes: string[];
  formatExplanation: string;
  exampleValues: Array<{ value: string; synthetic: boolean; explanation: string }>;
  commonMistakes: string[];
  dependsOn: string[];
  requiredWith: string[];
  conflictsWith: string[];
  relatedFields: string[];
  lifecycleImpact: string;
  ruleLayer: string;
  standardsRelease: string;
  knowledgeVersion: string;
  source: {
    sourceType: string;
    sourceReference: string;
    reviewStatus: "VERIFIED" | "UNVERIFIED";
    reviewedAt: string;
    reviewedBy: string;
  };
  searchTerms: string[];
}

export interface EffectiveTagKnowledge {
  record: TagKnowledgeRecord;
  profileId: string;
  profileVersion: string;
  effectivePresence: "MANDATORY" | "OPTIONAL" | "CONDITIONAL";
  effectiveOptions: string[];
  effectiveCodes: string[];
  clientExplanation?: string;
  effectiveBusinessQuestion: string;
  profileCommonMistakes: string[];
  profileOverrideApplied: boolean;
}

export interface KnowledgeMessageSummary {
  messageType: MessageType;
  workflowModule: WorkflowModule;
  recordCount: number;
  knowledgeVersion: string;
}

export interface KnowledgeSearchResponse {
  query: string;
  results: EffectiveTagKnowledge[];
  deterministic: boolean;
  llmUsed: boolean;
}

export interface ValidationFinding {
  ruleId: string;
  severity: "ERROR" | "WARNING" | "INFO";
  fieldPath?: string;
  message: string;
  suggestion?: string;
  intentional: boolean;
}

export interface ValidationReport {
  status: "VALID" | "INVALID" | "INTENTIONALLY_INVALID";
  profileId: string;
  profileVersion: string;
  findings: ValidationFinding[];
  errorCount: number;
  warningCount: number;
}

export interface RawParsedField {
  sequence: string;
  tag: string;
  qualifier?: string;
  value: string;
  lineNumber: number;
}

export interface RawValidationResponse {
  messageType?: MessageType;
  supportedSubset: boolean;
  parsedFields: RawParsedField[];
  validation: ValidationReport;
  disclaimer: string;
}

export interface GeneratedMessage {
  messageId: string;
  resolvedMessageType: MessageType;
  rawMessage: string;
  profileId: string;
  profileVersion: string;
  validation: ValidationReport;
  disclaimer: string;
  intentionalInvalidNotice?: string;
  fieldMap: RenderedField[];
  scenario: CanonicalScenario;
}

export interface RenderedField {
  sequence: string;
  tag: string;
  qualifier?: string;
  value: string;
  businessPath: string;
  businessMeaning: string;
}

export interface CanonicalScenario {
  scenarioId: string;
  profileId: string;
  lifecycle: "INSTRUCTION" | "CONFIRMATION" | "STATUS";
  direction?: "RECEIVE" | "DELIVER";
  paymentType?: "FREE_OF_PAYMENT" | "AGAINST_PAYMENT";
  messageType?: MessageType;
  function?: "NEWM" | "CANC" | "REVR";
  senderReference?: string;
  relatedReference?: string;
  clientReference?: string;
  trade: {
    transactionType?: "BUY" | "SELL";
    tradeDate?: string;
    settlementDate?: string;
  };
  security: {
    identifierType: "ISIN";
    identifier?: string;
    quantityType: "UNIT";
    quantity?: string;
  };
  account: { safekeepingAccount?: string };
  settlement: {
    currency?: string;
    amount?: string;
    placeOfSettlement?: string;
    deliveringAgent?: string;
    receivingAgent?: string;
  };
  confirmation: { settlementResult?: string; settledQuantity?: string };
  status: { category?: string; reasonCode?: string };
  command?: {
    commandType?: "MODIFY_PRIORITY";
    originalInstructionReference?: string;
    priority?: number;
  };
  testConfiguration: {
    mode: "VALID" | "NEGATIVE_TEST";
    mutation?: string;
    expectedOutcome?: string;
  };
  syntheticData: boolean;
}

export interface AmendmentDecision {
  classification:
    | "PROCESSING_DATA_MODIFICATION"
    | "CORE_BUSINESS_DATA_CHANGE"
    | "CANCELLATION_ONLY"
    | "UNSUPPORTED_MODIFICATION"
    | "CLARIFICATION_REQUIRED";
  method: string;
  explanation: string;
  directAmendmentSupported: boolean;
  requiresCancelRebook: boolean;
  affectedFields: string[];
  sourceReference: string;
  profileId: string;
  profileVersion: string;
}

export interface CancelRebookResult {
  decision: AmendmentDecision;
  cancellation: GeneratedMessage;
  cancellationStatus: GeneratedMessage;
  replacement: GeneratedMessage;
  beforeValues: Record<string, unknown>;
  afterValues: Record<string, unknown>;
}

export interface WorkflowGeneratedMessage {
  messageId: string;
  workflowId: string;
  workflowModule: WorkflowModule;
  resolvedMessageType: MessageType;
  canonicalData: Record<string, unknown>;
  rawMessage: string;
  fieldMap: RenderedField[];
  profileId: string;
  profileVersion: string;
  validation: ValidationReport;
  disclaimer: string;
  relatedWorkflowMessageId?: string;
  relatedSettlementMessageId?: string;
  createdAt: string;
}

export interface WorkflowLifecycle {
  workflowId: string;
  entries: Array<{
    messageId: string;
    messageType: MessageType;
    workflowModule: WorkflowModule;
    businessStatus: string;
    validationStatus: string;
    createdAt: string;
  }>;
  correlationValid: boolean;
  correlationFindings: string[];
}

export interface MessageResolution {
  resolvedMessageType?: MessageType;
  explanation: string;
  missingDecisionInformation: string[];
  confidence: string;
}

export interface ScenarioInterpretation {
  scenario: CanonicalScenario;
  resolution: MessageResolution;
  detectedFields: string[];
  explanation: string;
  requiresBusinessConfirmation: boolean;
  intent?: {
    lifecycle?: "INSTRUCTION" | "CONFIRMATION" | "STATUS";
    direction?: "RECEIVE" | "DELIVER";
    paymentType?: "FREE_OF_PAYMENT" | "AGAINST_PAYMENT";
    transactionType?: "BUY" | "SELL";
    function?: "NEWM" | "CANC" | "REVR";
    responseAction?: string;
    inferredFields: string[];
  };
  extractedFields: Array<{
    fieldPath: string;
    value: string;
    source: "EXPLICIT" | "PLACEHOLDER";
  }>;
  ambiguities: string[];
  missingDecisions: string[];
  conflicts: Array<{
    fieldPath: string;
    existingValue: string;
    proposedValue: string;
    message: string;
  }>;
  confidence?: number;
  requiresClarification: boolean;
  ai: {
    used: boolean;
    provider: "openrouter" | "deterministic_non_ai" | "test_mock";
    model?: string;
    primaryModel?: string;
    escalated: boolean;
    escalationReason?: string;
    promptVersion: string;
    schemaVersion: string;
    requestId: string;
    latencyMs: number;
    attemptCount: number;
    outcomeCode: string;
    processingSource: "LIVE_API" | "CACHE" | "DETERMINISTIC" | "AI_UNAVAILABLE";
    apiCalls: number;
    cacheHit: boolean;
    cacheNamespace?: string;
    cacheAgeSeconds?: number;
    originalCachedTotalTokens: number;
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    reportedCost?: string;
    tokensAvoided: number;
    callsAvoided: number;
    costAvoided?: string;
    knowledgeVersion: string;
  };
}

export interface AiHealth {
  configured: boolean;
  mode: "required" | "optional";
  provider: string;
  primaryModel: string;
  escalationModel: string;
  escalationEnabled: boolean;
  circuitState: "CLOSED" | "OPEN" | "HALF_OPEN";
  lastSuccessfulCallAt?: string;
  privacyEnforcementEnabled: boolean;
  requireParameters: boolean;
  dataCollection: string;
  zdrRequired: boolean;
  promptVersion: string;
  schemaVersion: string;
  cacheEnabled: boolean;
  cacheKeyVersion: string;
  knowledgeVersion: string;
}

export interface AiUsageInteraction {
  interactionId: string;
  operationType: string;
  source: "LIVE_API" | "CACHE" | "DETERMINISTIC" | "AI_UNAVAILABLE";
  provider?: string;
  model?: string;
  escalated: boolean;
  cacheHit: boolean;
  cacheNamespace?: string;
  cacheEntryAgeSeconds?: number;
  liveApiCallCount: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  providerReportedCost?: string;
  latencyMs: number;
  tokensAvoided: number;
  callsAvoided: number;
  estimatedCostAvoided?: string;
  promptVersion: string;
  schemaVersion: string;
  knowledgeVersion: string;
  profileVersion?: string;
  outcomeCode: string;
  createdAt: string;
}

export interface AiUsageSummary {
  periodDays: number;
  interactions: number;
  deterministicInteractions: number;
  liveApiCalls: number;
  cacheHits: number;
  cacheHitRate: number;
  tokensConsumed: number;
  tokensAvoided: number;
  apiCallsAvoided: number;
  providerReportedCost: string;
  estimatedCostAvoided: string;
  averageLatencyMs: number;
}

export interface AiCacheStats {
  enabled: boolean;
  keyVersion: string;
  l1Entries: number;
  l1Maximum: number;
  entries: number;
  activeEntries: number;
  totalHits: number;
  privacySafe: boolean;
}

export interface MissingField {
  fieldPath: string;
  question: string;
  explanation: string;
  technicalMapping?: string;
}

export interface MissingFieldsResponse {
  messageType: MessageType;
  profileId: string;
  profileVersion: string;
  missingFields: MissingField[];
  nextQuestion?: MissingField;
  completionPercentage: number;
  scenarioWithDefaults: CanonicalScenario;
}

export interface LifecycleEntry {
  messageId: string;
  messageType: MessageType;
  relatedMessageId?: string;
  senderReference: string;
  relatedReference?: string;
  lifecycle: "INSTRUCTION" | "STATUS" | "CONFIRMATION";
  businessStatus: string;
  profileId: string;
  profileVersion: string;
  validationStatus: string;
  createdAt: string;
}

export interface LifecycleTimeline {
  rootMessageId: string;
  entries: LifecycleEntry[];
  correlationValid: boolean;
  correlationFindings: ValidationFinding[];
}

export interface BulkRowResult {
  rowNumber: number;
  scenarioId?: string;
  status: "GENERATED" | "FAILED";
  resolvedMessageType?: MessageType;
  generatedFilename?: string;
  profileId?: string;
  profileVersion?: string;
  validationStatus?: string;
  errorCount: number;
  warningCount: number;
  expectedNegativeFailure: boolean;
  findings: ValidationFinding[];
}

export interface BulkGenerateResponse {
  reportId: string;
  totalRows: number;
  generatedRows: number;
  failedRows: number;
  rowResults: BulkRowResult[];
  downloadPath: string;
  disclaimer: string;
}

export interface ReportMetadataResponse {
  reportId: string;
  reportPayload: {
    totalRows: number;
    generatedRows: number;
    failedRows: number;
    disclaimer: string;
    rows: BulkRowResult[];
  };
  downloadPath: string;
}
