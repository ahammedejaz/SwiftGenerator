/** Typed client for `/api/v1`. Every call here is one an automation tester can also make. */

import { apiUrl } from "@/lib/api-client";
import type {
  ExcelGenerateResponse,
  GenerateRequest,
  GenerateResult,
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
