export type PublicEnv = {
  appUrl: string;
  apiBaseUrl: string;
  supabaseUrl: string | null;
  supabasePublishableKey: string | null;
};

export class EnvError extends Error {
  readonly missing: string[];
  constructor(missing: string[]) {
    super(`Missing required environment variables: ${missing.join(", ")}`);
    this.name = "EnvError";
    this.missing = missing;
  }
}

type EnvSource = Record<string, string | undefined>;

const DEFAULTS = {
  appUrl: "http://localhost:3000",
  apiBaseUrl: "http://localhost:8000"
};

function read(source: EnvSource, key: string): string | null {
  const value = source[key];
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function parsePublicEnv(
  source: EnvSource = process.env,
  options: { required?: boolean } = {}
): PublicEnv {
  const required = options.required ?? false;
  const appUrl = read(source, "NEXT_PUBLIC_APP_URL") ?? DEFAULTS.appUrl;
  const apiBaseUrl = read(source, "NEXT_PUBLIC_API_BASE_URL") ?? DEFAULTS.apiBaseUrl;
  const supabaseUrl = read(source, "NEXT_PUBLIC_SUPABASE_URL");
  const supabasePublishableKey = read(source, "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY");

  if (required) {
    const missing: string[] = [];
    if (!read(source, "NEXT_PUBLIC_APP_URL")) missing.push("NEXT_PUBLIC_APP_URL");
    if (!read(source, "NEXT_PUBLIC_API_BASE_URL")) missing.push("NEXT_PUBLIC_API_BASE_URL");
    if (!supabaseUrl) missing.push("NEXT_PUBLIC_SUPABASE_URL");
    if (!supabasePublishableKey) missing.push("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY");
    if (missing.length > 0) throw new EnvError(missing);
  }

  return { appUrl, apiBaseUrl, supabaseUrl, supabasePublishableKey };
}

export function getPublicEnv(source: EnvSource = process.env): PublicEnv {
  return parsePublicEnv(source);
}

export function assertPublicEnv(source: EnvSource = process.env): PublicEnv {
  return parsePublicEnv(source, { required: true });
}

export function hasSupabaseConfig(source: EnvSource = process.env): boolean {
  return (
    read(source, "NEXT_PUBLIC_SUPABASE_URL") !== null &&
    read(source, "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") !== null
  );
}
