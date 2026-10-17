"use client";

import { hasSupabaseConfig } from "@/lib/env";

export default function SupabaseNotice() {
  if (hasSupabaseConfig()) return null;
  return (
    <section className="panel notice" role="status">
      <h2>مصادقة Supabase غير مُهيّأة محليًا</h2>
      <p>
        لتجربة تسجيل الدخول عبر Google، أضف القيم التالية إلى <code>.env.local</code> ثم أعد تشغيل
        الواجهة:
      </p>
      <ul>
        <li>
          <code>NEXT_PUBLIC_SUPABASE_URL</code>
        </li>
        <li>
          <code>NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY</code>
        </li>
      </ul>
    </section>
  );
}
