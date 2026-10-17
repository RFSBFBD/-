"use client";

import { useCallback } from "react";

import { getApiClient, type RequestOptions } from "@/lib/api-client";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

type AuthedRequest = <T>(path: string, options?: Omit<RequestOptions, "token">) => Promise<T>;

export function useAuthedRequest(): AuthedRequest {
  return useCallback(
    async <T,>(path: string, options: Omit<RequestOptions, "token"> = {}) => {
      const supabase = createSupabaseBrowserClient();
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token ?? "";
      return getApiClient().request<T>(path, { ...options, token });
    },
    []
  );
}

type AuthedUpload = <T>(path: string, formData: FormData) => Promise<T>;

export function useAuthedUpload(): AuthedUpload {
  return useCallback(
    async <T,>(path: string, formData: FormData) => {
      const supabase = createSupabaseBrowserClient();
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token ?? "";
      return getApiClient().request<T>(path, { method: "POST", formData, token });
    },
    []
  );
}
