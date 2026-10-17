"use client";

import { useEffect, useState } from "react";

import { ApiError, getApiClient } from "@/lib/api-client";

type Health = { status?: string; service?: string };

export default function BackendStatus() {
  const [message, setMessage] = useState("جارٍ فحص الاتصال...");

  useEffect(() => {
    const controller = new AbortController();
    getApiClient()
      .request<Health>("/health", { signal: controller.signal, timeoutMs: 8000 })
      .then((data) => setMessage(`متصل — ${data.service ?? "API"} (${data.status ?? "ok"})`))
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.code === "timeout") {
          setMessage("انتهت مهلة الاتصال بالباك إند. تأكد أن FastAPI يعمل.");
          return;
        }
        setMessage("غير متصل. تأكد أن FastAPI يعمل وأن NEXT_PUBLIC_API_BASE_URL صحيح.");
      });
    return () => controller.abort();
  }, []);

  return <p className="status" aria-live="polite">{message}</p>;
}
