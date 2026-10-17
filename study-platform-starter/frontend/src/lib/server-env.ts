import "server-only";

import { EnvError } from "@/lib/env";

export type ServerEnv = {
  supabaseUrl: string | null;
  supabaseServiceRoleKey: string | null;
  databaseUrl: string | null;
  internalApiSecret: string | null;
};

type EnvSource = Record<string, string | undefined>;

function read(source: EnvSource, key: string): string | null {
  const value = source[key];
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function parseServerEnv(
  source: EnvSource = process.env,
  options: { required?: boolean } = {}
): ServerEnv {
  const env: ServerEnv = {
    supabaseUrl: read(source, "NEXT_PUBLIC_SUPABASE_URL"),
    supabaseServiceRoleKey: read(source, "SUPABASE_SERVICE_ROLE_KEY"),
    databaseUrl: read(source, "DATABASE_URL"),
    internalApiSecret: read(source, "INTERNAL_API_SECRET")
  };

  if (options.required) {
    const missing: string[] = [];
    if (!env.supabaseServiceRoleKey) missing.push("SUPABASE_SERVICE_ROLE_KEY");
    if (missing.length > 0) throw new EnvError(missing);
  }

  return env;
}

export function getServerEnv(source: EnvSource = process.env): ServerEnv {
  return parseServerEnv(source);
}

export function assertServerEnv(source: EnvSource = process.env): ServerEnv {
  return parseServerEnv(source, { required: true });
}

export function requireServerSecret(name: keyof ServerEnv, source: EnvSource = process.env): string {
  const value = read(source, name as string);
  if (!value) throw new EnvError([name]);
  return value;
}
