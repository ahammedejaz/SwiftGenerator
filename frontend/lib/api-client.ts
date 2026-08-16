// 127.0.0.1, not localhost. The backend binds 127.0.0.1, but a browser resolves `localhost`
// to ::1 first on a dual-stack machine and only then falls back — so an occasional request
// died with ECONNREFUSED ::1:8000, which reaches fetch() as a bare network error and reads
// to the tester as "the backend is down". An address needs no resolving.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details: unknown[] = [],
    public readonly code: string = "API_ERROR",
  ) {
    super(message);
  }
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const method = (init?.method ?? "GET").toUpperCase();
  if (
    typeof document !== "undefined" &&
    ["POST", "PATCH", "PUT", "DELETE"].includes(method) &&
    !headers.has("X-CSRF-Token")
  ) {
    const csrf = document.cookie
      .split("; ")
      .find((item) => item.startsWith("swift_platform_csrf="))
      ?.split("=")[1];
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    cache: "no-store",
    credentials: "include",
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const envelope = payload as {
      error?: { code?: string; message?: string; details?: unknown[] };
    };
    throw new ApiError(
      envelope.error?.message ?? "The API request failed.",
      response.status,
      envelope.error?.details,
      envelope.error?.code,
    );
  }
  return payload as T;
}
