import { describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient } from "@/lib/api-client";

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    ...init
  });
}

describe("createApiClient", () => {
  it("returns typed JSON on success and joins the base url", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ status: "ok", service: "API" }));
    const client = createApiClient({ baseUrl: "http://localhost:8000/", fetchImpl });

    const result = await client.request<{ status: string; service: string }>("/health");
    expect(result).toEqual({ status: "ok", service: "API" });
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://localhost:8000/health",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("sends JSON bodies and bearer tokens", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ id: "1" }));
    const client = createApiClient({ baseUrl: "http://localhost:8000", fetchImpl });

    await client.request("/subjects", { body: { name: "Math" }, token: "jwt-token" });

    const init = fetchImpl.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ name: "Math" }));
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer jwt-token");
  });

  it("normalizes backend error payloads and preserves request id", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(
        { error: { type: "validation_error", message: "Bad input", request_id: "req-9" } },
        { status: 422 }
      )
    );
    const client = createApiClient({ baseUrl: "http://localhost:8000", fetchImpl });

    await expect(client.request("/subjects")).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      code: "validation_error",
      message: "Bad input",
      requestId: "req-9"
    });
  });

  it("falls back to a generic message for non-JSON errors", async () => {
    const fetchImpl = vi.fn(async () => new Response("boom", { status: 502 }));
    const client = createApiClient({ baseUrl: "http://localhost:8000", fetchImpl });

    const error = await client.request("/health").catch((caught) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("http_502");
  });

  it("reports a timeout when the request exceeds the budget", async () => {
    const fetchImpl = (input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(Object.assign(new Error("aborted"), { name: "AbortError" }));
        });
      });

    const client = createApiClient({ baseUrl: "http://localhost:8000", fetchImpl, defaultTimeoutMs: 5 });
    await expect(client.request("/slow")).rejects.toMatchObject({ code: "timeout", status: 0 });
  });

  it("reports a network error when fetch rejects", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("failed to fetch");
    });
    const client = createApiClient({ baseUrl: "http://localhost:8000", fetchImpl });
    await expect(client.request("/health")).rejects.toMatchObject({ code: "network_error" });
  });

  it("handles empty 204 responses", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    const client = createApiClient({ baseUrl: "http://localhost:8000", fetchImpl });
    await expect(client.request("/subjects/1")).resolves.toBeUndefined();
  });

  it("sends multipart form data without a JSON content type", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ok: true }));
    const client = createApiClient({ baseUrl: "http://localhost:8000", fetchImpl });
    const formData = new FormData();
    formData.append("title", "Lecture");

    await client.request("/subjects/1/materials", { formData, token: "jwt-token" });

    const init = fetchImpl.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(formData);
    const headers = init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBeUndefined();
    expect(headers.Authorization).toBe("Bearer jwt-token");
  });
});
