import type { PublicEnv } from "@/lib/env";
import { getPublicEnv } from "@/lib/env";

export type NormalizedApiError = {
  status: number;
  code: string;
  message: string;
  requestId: string | null;
  details?: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details?: unknown;

  constructor(error: NormalizedApiError) {
    super(error.message);
    this.name = "ApiError";
    this.status = error.status;
    this.code = error.code;
    this.requestId = error.requestId;
    this.details = error.details;
  }
}

export type ApiFetch = (input: string, init?: RequestInit) => Promise<Response>;

export type ApiClientOptions = {
  baseUrl: string;
  fetchImpl?: ApiFetch;
  defaultTimeoutMs?: number;
};

export type RequestOptions = {
  method?: string;
  body?: unknown;
  formData?: FormData;
  headers?: Record<string, string>;
  token?: string | null;
  timeoutMs?: number;
  signal?: AbortSignal;
  cache?: RequestCache;
};

const DEFAULT_TIMEOUT_MS = 15_000;

export function createApiClient(options: ApiClientOptions) {
  const baseUrl = options.baseUrl.replace(/\/+$/, "");
  const doFetch: ApiFetch = options.fetchImpl ?? ((input, init) => fetch(input, init));
  const defaultTimeoutMs = options.defaultTimeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function request<T>(path: string, requestOptions: RequestOptions = {}): Promise<T> {
    const url = path.startsWith("http") ? path : `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
    const controller = new AbortController();
    const timeoutMs = requestOptions.timeoutMs ?? defaultTimeoutMs;
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    if (requestOptions.signal) {
      if (requestOptions.signal.aborted) controller.abort();
      else requestOptions.signal.addEventListener("abort", () => controller.abort(), { once: true });
    }

    const headers: Record<string, string> = {
      Accept: "application/json",
      ...requestOptions.headers
    };
    const isFormData = requestOptions.formData !== undefined;
    if (requestOptions.body !== undefined && !isFormData) {
      headers["Content-Type"] = "application/json";
    }
    if (requestOptions.token) headers.Authorization = `Bearer ${requestOptions.token}`;

    const hasBody = requestOptions.body !== undefined || isFormData;
    const requestBody = isFormData ? requestOptions.formData : requestOptions.body;

    let response: Response;
    try {
      response = await doFetch(url, {
        method: requestOptions.method ?? (hasBody ? "POST" : "GET"),
        headers,
        body: isFormData ? (requestBody as FormData) : hasBody ? JSON.stringify(requestBody) : undefined,
        signal: controller.signal,
        cache: requestOptions.cache ?? "no-store"
      });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new ApiError({
          status: 0,
          code: "timeout",
          message: `Request timed out after ${timeoutMs}ms.`,
          requestId: null
        });
      }
      throw new ApiError({
        status: 0,
        code: "network_error",
        message: "Network request failed.",
        requestId: null
      });
    } finally {
      clearTimeout(timeout);
    }

    const requestId = response.headers.get("X-Request-ID");

    if (response.status === 204) {
      return undefined as T;
    }

    const payload = await parseJson(response);

    if (!response.ok) {
      throw new ApiError(normalizeError(response.status, payload, requestId));
    }

    return payload as T;
  }

  return { request, baseUrl };
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function normalizeError(status: number, payload: unknown, requestId: string | null): NormalizedApiError {
  if (payload && typeof payload === "object" && "error" in payload) {
    const error = (payload as { error?: Record<string, unknown> }).error;
    if (error && typeof error === "object") {
      return {
        status,
        code: typeof error.type === "string" ? error.type : `http_${status}`,
        message: typeof error.message === "string" ? error.message : `Request failed with status ${status}.`,
        requestId: typeof error.request_id === "string" ? error.request_id : requestId,
        details: error.details
      };
    }
  }
  return {
    status,
    code: `http_${status}`,
    message: `Request failed with status ${status}.`,
    requestId
  };
}

export function getApiClient(env: PublicEnv = getPublicEnv()) {
  return createApiClient({ baseUrl: env.apiBaseUrl });
}
