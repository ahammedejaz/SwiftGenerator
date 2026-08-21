/** Typed client for `/api/v1`. Every call here is one an automation tester can also make. */

import { apiUrl } from "@/lib/api-client";
import type {
  AiAskRequest,
  AiAskResponse,
  AiCompareRequest,
  AiCompareResponse,
  AiIdentifyRequest,
  AiIdentifyResponse,
  AiPrepareRequest,
  AiPrepareResponse,
  AiPresentationRequest,
  AiPresentationResponse,
  AiSampleRequest,
  AiSampleResponse,
  AiTestDataRequest,
  AiTestDataResponse,
  ConvertRequest,
  ConversionResponse,
  ConversionTargetsResponse,
  ExcelGenerateResponse,
  DiffResult,
  GenerateRequest,
  GenerateResult,
  ImportResult,
  IntelligenceDetail,
  IntelligenceSearchResponse,
  KnowledgeMessagesResponse,
  KnowledgeSearchRequest,
  KnowledgeSearchResponse,
  KnowledgeSourcesResponse,
  KnowledgeStatus,
  KnowledgeSyncResponse,
  KnowledgeTelemetry,
  Lane,
  MessageFormat,
  MessageSpec,
  OutputMode,
  RecentMessage,
  SampleMessage,
  SampleVariant,
  StudioCatalogue,
} from "@/lib/studio-types";

/** Which registry a call addresses. Omitted entirely for the configured lane, so every
 *  existing call site — and every existing URL — is unchanged. */
export interface LaneOptions {
  lane?: Lane | null;
  release?: string | null;
}

function laneQuery(options?: LaneOptions): string {
  if (!options?.lane || options.lane === "CONFIGURED") return "";
  let query = `&lane=${options.lane}`;
  if (options.release) query += `&release=${encodeURIComponent(options.release)}`;
  return query;
}

function laneBody(options?: LaneOptions): { lane?: Lane; release?: string } {
  if (!options?.lane || options.lane === "CONFIGURED") return {};
  return { lane: options.lane, ...(options.release ? { release: options.release } : {}) };
}

export class StudioError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string = "API_ERROR",
  ) {
    super(message);
    this.name = "StudioError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(apiUrl(path), { ...init, headers, cache: "no-store" });
  } catch {
    throw new StudioError(
      "The studio API could not be reached. Check that the backend is running on port 8000.",
      0,
      "NETWORK_UNAVAILABLE",
    );
  }
  if (!response.ok) {
    if (response.status === 429) {
      // Distinct from NETWORK_UNAVAILABLE on purpose: being throttled and the backend
      // being down look identical to fetch(), and telling a tester to restart a server
      // that is running wastes their time.
      const retry = Number(response.headers.get("Retry-After"));
      throw new StudioError(
        `Too many requests were sent to the studio API. Wait ${
          Number.isFinite(retry) && retry > 0 ? `${retry} seconds` : "a minute"
        } and try again.`,
        429,
        "RATE_LIMIT_EXCEEDED",
      );
    }
    let message = `The request failed with status ${response.status}.`;
    let code = "API_ERROR";
    try {
      const payload = (await response.json()) as {
        error?: { message?: string; code?: string };
        detail?: string;
      };
      message = payload.error?.message ?? payload.detail ?? message;
      code = payload.error?.code ?? code;
    } catch {
      /* A non-JSON body leaves the default message in place. */
    }
    throw new StudioError(message, response.status, code);
  }
  return (await response.json()) as T;
}

const catalogueCache = new Map<string, StudioCatalogue>();
const catalogueInFlight = new Map<string, Promise<StudioCatalogue>>();
const CATALOGUE_SESSION_TTL_MS = 5 * 60 * 1000;

function sessionCatalogue(key: string): StudioCatalogue | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(`studio-catalogue-v1:${key}`);
    if (!raw) return null;
    const entry = JSON.parse(raw) as { storedAt: number; catalogue: StudioCatalogue };
    if (Date.now() - entry.storedAt > CATALOGUE_SESSION_TTL_MS) {
      window.sessionStorage.removeItem(`studio-catalogue-v1:${key}`);
      return null;
    }
    return entry.catalogue;
  } catch {
    return null;
  }
}

function storeSessionCatalogue(key: string, catalogue: StudioCatalogue): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      `studio-catalogue-v1:${key}`,
      JSON.stringify({ storedAt: Date.now(), catalogue }),
    );
  } catch {
    // Storage may be unavailable or full; the in-memory cache remains sufficient.
  }
}

function catalogueRequest(options?: {
  includePreview?: boolean;
  force?: boolean;
}): Promise<StudioCatalogue> {
  const includePreview = options?.includePreview ?? true;
  const key = includePreview ? "all" : "configured";
  if (!options?.force) {
    const cached = catalogueCache.get(key) ?? sessionCatalogue(key);
    if (cached) return Promise.resolve(cached);
  }
  const pending = catalogueInFlight.get(key);
  if (pending) return pending;
  const requestPromise = request<StudioCatalogue>(
    `/api/v1/catalogue${includePreview ? "" : "?includePreview=false"}`,
  )
    .then((catalogue) => {
      catalogueCache.set(key, catalogue);
      storeSessionCatalogue(key, catalogue);
      return catalogue;
    })
    .finally(() => catalogueInFlight.delete(key));
  catalogueInFlight.set(key, requestPromise);
  return requestPromise;
}

export const studioApi = {
  catalogue: catalogueRequest,

  spec: (format: MessageFormat, messageType: string, options?: LaneOptions) =>
    request<MessageSpec>(
      `/api/v1/messages/${encodeURIComponent(messageType)}/spec?format=${format}${laneQuery(options)}`,
    ),

  samples: (format: MessageFormat, messageType: string, options?: LaneOptions) =>
    request<SampleMessage[]>(
      `/api/v1/messages/${encodeURIComponent(messageType)}/samples?format=${format}${laneQuery(options)}`,
    ),

  sample: (
    format: MessageFormat,
    messageType: string,
    variant: SampleVariant,
    options?: LaneOptions,
  ) =>
    request<SampleMessage>(
      `/api/v1/messages/${encodeURIComponent(messageType)}/samples/${variant}?format=${format}${laneQuery(options)}`,
    ),

  validate: (payload: GenerateRequest) =>
    request<GenerateResult>("/api/v1/messages/validate", {
      method: "POST",
      body: JSON.stringify({ ...payload, persist: false }),
    }),

  generate: (payload: GenerateRequest) =>
    request<GenerateResult>("/api/v1/messages/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  conversionTargets: (
    source: string,
    sourceFormat: MessageFormat = "MT",
    options: { lane?: Lane; release?: string | null } = {},
  ) =>
    request<ConversionTargetsResponse>(
      `/api/v1/messages/${encodeURIComponent(source)}/conversion-targets?sourceFormat=${sourceFormat}` +
        (options.lane ? `&sourceLane=${encodeURIComponent(options.lane)}` : "") +
        (options.release ? `&sourceRelease=${encodeURIComponent(options.release)}` : ""),
    ),

  convert: (payload: ConvertRequest) =>
    request<ConversionResponse>("/api/v1/messages/convert", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Read an existing ISO 20022 message back into canonical values. */
  /** `messageType` is only read when the message cannot name itself — a pasted MT text
   *  block. An MT header that disagrees with it is a refusal, not a reconciliation. */
  importMessage: (
    text: string,
    profileId?: string,
    messageType?: string | null,
    options?: LaneOptions,
  ) =>
    request<ImportResult>("/api/v1/messages/import", {
      method: "POST",
      body: JSON.stringify({
        text,
        ...(profileId ? { profileId } : {}),
        ...(messageType ? { messageType } : {}),
        ...laneBody(options),
      }),
    }),

  /** Regenerate from these values and compare the result with a message you already have.
   *  Deterministic and server-side — the diff is part of the API, not a browser feature. */
  diffMessage: (original: string, payload: GenerateRequest) =>
    request<DiffResult>("/api/v1/messages/diff", {
      method: "POST",
      body: JSON.stringify({ ...payload, original, persist: false }),
    }),

  recent: (limit = 40, format?: MessageFormat) =>
    request<RecentMessage[]>(
      `/api/v1/messages/recent?limit=${limit}${format ? `&format=${format}` : ""}`,
    ),

  searchIntelligence: (query: string, format?: MessageFormat) =>
    request<IntelligenceSearchResponse>(
      `/api/v1/intelligence/search?q=${encodeURIComponent(query)}` +
        (format ? `&format=${format}` : ""),
    ),

  intelligenceField: (id: string) =>
    request<IntelligenceDetail>(
      `/api/v1/intelligence/field?id=${encodeURIComponent(id)}`,
    ),

  async generateFromExcel(
    file: File,
    profileId: string,
    options?: LaneOptions,
  ): Promise<ExcelGenerateResponse> {
    const body = new FormData();
    body.append("file", file);
    return request<ExcelGenerateResponse>(
      `/api/v1/messages/generate-from-excel?profileId=${encodeURIComponent(profileId)}${laneQuery(options)}`,
      { method: "POST", body },
    );
  },

  /** A template for every configured message, or for one named message in either lane. */
  templateUrl: (format: MessageFormat, messageType?: string, options?: LaneOptions) => {
    const query = messageType
      ? `?messageType=${encodeURIComponent(messageType)}${laneQuery(options)}`
      : "";
    return apiUrl(`/api/v1/templates/${format}.xlsx${query}`);
  },

  /* ---------------------------------------------------------- knowledge base */

  knowledgeStatus: () => request<KnowledgeStatus>("/api/v1/knowledge/status"),

  knowledgeMessages: () => request<KnowledgeMessagesResponse>("/api/v1/knowledge/messages"),

  knowledgeSources: () => request<KnowledgeSourcesResponse>("/api/v1/knowledge/sources"),

  knowledgeSearch: (payload: KnowledgeSearchRequest) =>
    request<KnowledgeSearchResponse>("/api/v1/knowledge/search", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  knowledgeTelemetry: () => request<KnowledgeTelemetry>("/api/v1/knowledge/telemetry"),

  /** Exists only while the backend reports `adminEnabled`; a 404 otherwise. */
  knowledgeSync: () =>
    request<KnowledgeSyncResponse>("/api/v1/knowledge/sync", { method: "POST" }),

  /* ----------------------------------------------------------- AI authoring */

  aiIdentify: (payload: AiIdentifyRequest) =>
    request<AiIdentifyResponse>("/api/v1/ai/messages/identify", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  aiPrepare: (payload: AiPrepareRequest) =>
    request<AiPrepareResponse>("/api/v1/ai/messages/prepare", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  aiSample: (payload: AiSampleRequest) =>
    request<AiSampleResponse>("/api/v1/ai/samples", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  aiTestData: (payload: AiTestDataRequest) =>
    request<AiTestDataResponse>("/api/v1/ai/test-data/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  aiAsk: (payload: AiAskRequest) =>
    request<AiAskResponse>("/api/v1/ai/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  aiPresentation: (payload: AiPresentationRequest) =>
    request<AiPresentationResponse>("/api/v1/ai/presentation", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  aiCompare: (payload: AiCompareRequest) =>
    request<AiCompareResponse>("/api/v1/ai/releases/compare", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  downloadUrl: (messageId: string, output: OutputMode) =>
    apiUrl(`/api/v1/messages/id/${messageId}/download/${output}`),

  evidenceUrl: (messageId: string) =>
    apiUrl(`/api/v1/messages/id/${messageId}/evidence.zip`),
};

/** Save text the browser already holds, without a round trip to the server. */
export function saveText(filename: string, text: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
