/**
 * Thin, typed fetch client for the EventSense AI backend.
 *
 * - Reads the base URL from VITE_API_URL (falls back to localhost:8000).
 * - Attaches the bearer token from local storage on every request.
 * - Surfaces a structured ApiError so the UI can render clean error states.
 */

const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const TOKEN_KEY = "eventsense.access_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  /** Set false to send FormData / skip JSON encoding. */
  json?: boolean;
  auth?: boolean;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, json = true, auth = true, headers, ...rest } = options;

  const finalHeaders = new Headers(headers);
  if (auth) {
    const token = getToken();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    if (json) finalHeaders.set("Content-Type", "application/json");
    payload = json ? JSON.stringify(body) : (body as BodyInit);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: payload,
  });

  if (response.status === 401) {
    clearToken();
  }

  if (!response.ok) {
    let detail: unknown;
    let message = `Request failed (${response.status})`;
    try {
      detail = await response.json();
      const d = (detail as { detail?: unknown })?.detail;
      if (typeof d === "string") message = d;
      else if (Array.isArray(d) && d[0]?.msg) message = String(d[0].msg);
    } catch {
      // non-JSON error body; keep default message
    }
    throw new ApiError(response.status, message, detail);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form, json: false }),
};
