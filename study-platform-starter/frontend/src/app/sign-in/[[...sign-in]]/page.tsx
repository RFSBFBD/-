"use client";

import { useState } from "react";

import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

export default function SignInPage() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signInWithGoogle() {
    setBusy(true);
    setError(null);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` }
    });
    if (error) {
      setError(error.message);
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <h1>تسجيل الدخول</h1>
      <button type="button" onClick={signInWithGoogle} disabled={busy}>
        {busy ? "جارٍ التوجيه…" : "تسجيل الدخول عبر Google"}
      </button>
      {error ? <p className="error">{error}</p> : null}
    </main>
  );
}
