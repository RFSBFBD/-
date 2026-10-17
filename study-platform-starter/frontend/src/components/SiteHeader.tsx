"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

export default function SiteHeader({ supabaseEnabled }: { supabaseEnabled: boolean }) {
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!supabaseEnabled) {
      setLoading(false);
      return;
    }
    const supabase = createSupabaseBrowserClient();
    supabase.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? null);
      setLoading(false);
    });
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user?.email ?? null);
    });
    return () => subscription.subscription.unsubscribe();
  }, [supabaseEnabled]);

  async function signOut() {
    const supabase = createSupabaseBrowserClient();
    await supabase.auth.signOut();
    window.location.href = "/";
  }

  return (
    <header className="site-header">
      <Link className="brand" href="/">
        منصة المذاكرة
      </Link>
      <nav className="site-nav">
        {supabaseEnabled ? (
          loading ? (
            <span className="badge">جارٍ التحميل…</span>
          ) : email ? (
            <>
              <Link href="/subjects">موادي</Link>
              <Link href="/dashboard">لوحتي</Link>
              <span className="badge">{email}</span>
              <button type="button" onClick={signOut}>
                تسجيل الخروج
              </button>
            </>
          ) : (
            <Link href="/sign-in">تسجيل الدخول</Link>
          )
        ) : (
          <span className="badge" title="لم يتم ضبط مفاتيح Supabase محليًا">
            Supabase غير مهيأ
          </span>
        )}
      </nav>
    </header>
  );
}
