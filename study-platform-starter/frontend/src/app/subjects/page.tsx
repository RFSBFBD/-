import { createSupabaseServerClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

import SupabaseNotice from "@/components/SupabaseNotice";
import { hasSupabaseConfig } from "@/lib/supabase/browser";

export const dynamic = "force-dynamic";

export default async function SubjectsPage() {
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

  // SubjectsManager is a client component that uses useAuthedRequest.
  const { default: SubjectsManager } = await import("@/components/SubjectsManager");
  return (
    <main>
      <p>AI STUDY PLATFORM · SUBJECTS</p>
      <h1>موادي</h1>
      <SubjectsManager />
    </main>
  );
}
