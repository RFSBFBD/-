import { createSupabaseServerClient } from "@/lib/supabase/server";
import Link from "next/link";
import { redirect } from "next/navigation";

import ActiveSessionBanner from "@/components/ActiveSessionBanner";
import SupabaseNotice from "@/components/SupabaseNotice";
import { ApiError } from "@/lib/api-client";
import { fetchProfile, type Profile } from "@/lib/server-api";
import { hasSupabaseConfig } from "@/lib/supabase/browser";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  if (!hasSupabaseConfig()) {
    return (
      <main>
        <SupabaseNotice />
      </main>
    );
  }

  const supabase = await createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    redirect("/sign-in");
  }

  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token ?? "";

  let profile: Profile | null = null;
  let errorMessage: string | null = null;

  try {
    profile = await fetchProfile(token);
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage = `تعذّر تحميل الملف الشخصي (${error.status} ${error.code}).`;
    } else {
      errorMessage = "تعذّر الاتصال بالباك إند.";
    }
  }

  return (
    <main>
      <p>AI STUDY PLATFORM · DASHBOARD</p>
      <h1>لوحتي</h1>
      <p>
        <Link className="button" href="/subjects">إدارة المواد</Link>
      </p>
      <ActiveSessionBanner />
      {profile ? (
        <section className="panel">
          <p>
            <strong>الاسم:</strong> {profile.display_name ?? "غير محدد"}
          </p>
          <p>
            <strong>الدور:</strong> {profile.role === "admin" ? "مشرف" : "طالب"}
          </p>
          <p className="status">المعرّف: {profile.id}</p>
        </section>
      ) : (
        <section className="panel">
          <p>{errorMessage ?? "لا توجد بيانات."}</p>
        </section>
      )}
    </main>
  );
}
