import { describe, expect, it } from "vitest";

import { EnvError, hasSupabaseConfig, parsePublicEnv } from "@/lib/env";

describe("parsePublicEnv", () => {
  it("falls back to documented defaults in local mode", () => {
    const env = parsePublicEnv({});
    expect(env.appUrl).toBe("http://localhost:3000");
    expect(env.apiBaseUrl).toBe("http://localhost:8000");
    expect(env.supabaseUrl).toBeNull();
    expect(env.supabasePublishableKey).toBeNull();
  });

  it("trims values and ignores empty strings", () => {
    const env = parsePublicEnv({
      NEXT_PUBLIC_APP_URL: "  https://app.test  ",
      NEXT_PUBLIC_API_BASE_URL: "   ",
      NEXT_PUBLIC_SUPABASE_URL: "https://supabase.test",
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_x"
    });
    expect(env.appUrl).toBe("https://app.test");
    expect(env.apiBaseUrl).toBe("http://localhost:8000");
    expect(env.supabaseUrl).toBe("https://supabase.test");
    expect(env.supabasePublishableKey).toBe("sb_publishable_x");
  });

  it("throws with the missing variable names when required", () => {
    expect(() => parsePublicEnv({}, { required: true })).toThrowError(EnvError);
    try {
      parsePublicEnv({ NEXT_PUBLIC_APP_URL: "https://app.test" }, { required: true });
    } catch (error) {
      expect(error).toBeInstanceOf(EnvError);
      expect((error as EnvError).missing).toEqual([
        "NEXT_PUBLIC_API_BASE_URL",
        "NEXT_PUBLIC_SUPABASE_URL",
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"
      ]);
    }
  });

  it("passes strict validation when all variables are present", () => {
    const env = parsePublicEnv(
      {
        NEXT_PUBLIC_APP_URL: "https://app.test",
        NEXT_PUBLIC_API_BASE_URL: "https://api.test",
        NEXT_PUBLIC_SUPABASE_URL: "https://supabase.test",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_x"
      },
      { required: true }
    );
    expect(env.apiBaseUrl).toBe("https://api.test");
  });
});

describe("hasSupabaseConfig", () => {
  it("detects a configured publishable key", () => {
    expect(
      hasSupabaseConfig({
        NEXT_PUBLIC_SUPABASE_URL: "https://supabase.test",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_x"
      })
    ).toBe(true);
    expect(hasSupabaseConfig({})).toBe(false);
  });
});
