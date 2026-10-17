import { createSupabaseServerClient } from "@/lib/supabase/server";
import { notFound, redirect } from "next/navigation";

import Link from "next/link";

import SupabaseNotice from "@/components/SupabaseNotice";
import MaterialsLibrary from "@/components/MaterialsLibrary";
import StudySessionPanel from "@/components/StudySessionPanel";
import StudyToolsPanel from "@/components/StudyToolsPanel";
import { ApiError } from "@/lib/api-client";
import { hasSupabaseConfig } from "@/lib/supabase/browser";
import { fetchSubject, fetchSubjectMembers, type SubjectDetail, type SubjectMember } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function SubjectDetailPage({
  params
}: {
  params: Promise<{ subjectId: string }>;
}) {
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

  const { subjectId } = await params;
  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token ?? "";

  let subject: SubjectDetail;
  let members: SubjectMember[] = [];
  try {
    subject = await fetchSubject(token, subjectId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    return (
      <main>
        <p className="error" role="alert">تعذّر تحميل المادة.</p>
      </main>
    );
  }

  try {
    members = await fetchSubjectMembers(token, subjectId);
  } catch {
    members = [];
  }

  return (
    <main>
      <p>
        <Link href="/subjects">← كل المواد</Link>
      </p>
      <h1>{subject.name}</h1>
      <p>
        الدور: <span className="badge">{subject.role === "owner" ? "مالك" : "عضو"}</span>
        {subject.archived_at ? <span className="badge archived">مؤرشفة</span> : null}
      </p>

      <StudySessionPanel subjectId={subjectId} />

      <MaterialsLibrary subjectId={subjectId} isOwner={subject.role === "owner"} />

      <StudyToolsPanel subjectId={subjectId} />

      <section className="panel">
        <h2>الأعضاء ({members.length})</h2>
        <ul className="list">
          {members.map((member) => (
            <li key={member.user_id} className="list-item">
              <span className="status">{member.user_id}</span>
              <span className="badge">{member.role === "owner" ? "مالك" : "عضو"}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
