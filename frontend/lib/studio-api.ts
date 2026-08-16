/** Typed client for `/api/v1`. Every call here is one an automation tester can also make. */

import { apiUrl } from "@/lib/api-client";
import type {
  ExcelGenerateResponse,
  DiffResult,
  GenerateRequest,
  GenerateResult,
  ImportResult,
  IntelligenceDetail,
  IntelligenceSearchResponse,
  MessageFormat,
  MessageSpec,
  OutputMode,
  RecentMessage,
  SampleMessage,
  SampleVariant,
  StudioCatalogue,
} from "@/lib/studio-types";

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

export const studioApi = {
  catalogue: () => request<StudioCatalogue>("/api/v1/catalogue"),

  spec: (format: MessageFormat, messageType: string) =>
    request<MessageSpec>(
      `/api/v1/messages/${encodeURIComponent(messageType)}/spec?format=${format}`,
    ),

  samples: (format: MessageFormat, messageType: string) =>
    request<SampleMessage[]>(
      `/api/v1/messages/${encodeURIComponent(messageType)}/samples?format=${format}`,
    ),

  sample: (format: MessageFormat, messageType: string, variant: SampleVariant) =>
    request<SampleMessage>(
      `/api/v1/messages/${encodeURIComponent(messageType)}/samples/${variant}?format=${format}`,
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

  /** Read an existing ISO 20022 message back into canonical values. */
  /** `messageType` is only read when the message cannot name itself — a pasted MT text
   *  block. An MT header that disagrees with it is a refusal, not a reconciliation. */
  importMessage: (text: string, profileId?: string, messageType?: string | null) =>
    request<ImportResult>("/api/v1/messages/import", {
      method: "POST",
      body: JSON.stringify({
        text,
        ...(profileId ? { profileId } : {}),
        ...(messageType ? { messageType } : {}),
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
  ): Promise<ExcelGenerateResponse> {
    const body = new FormData();
    body.append("file", file);
    return request<ExcelGenerateResponse>(
      `/api/v1/messages/generate-from-excel?profileId=${encodeURIComponent(profileId)}`,
      { method: "POST", body },
    );
  },

  templateUrl: (format: MessageFormat) => apiUrl(`/api/v1/templates/${format}.xlsx`),

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
