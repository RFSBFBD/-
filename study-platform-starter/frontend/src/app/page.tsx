import Link from "next/link";

import BackendStatus from "@/components/BackendStatus";

export default function HomePage() {
  return (
    <main>
      <p>AI STUDY PLATFORM · STARTER</p>
      <h1>منصة المذاكرة الذكية</h1>
      <p>
        الهيكل الأساسي للواجهة والـ API جاهز للتطوير المرحلي. المصادقة عبر Supabase
        أصبحت مُهيّأة، وبقية الميزات (المواد، الرفع، الـ RAG) تُنفّذ في المراحل التالية.
      </p>
      <p>
        <Link className="button" href="/dashboard">الذهاب إلى لوحتي</Link>
      </p>
      <section className="panel">
        <h2>حالة اتصال الباك إند</h2>
        <BackendStatus />
      </section>
    </main>
  );
}
