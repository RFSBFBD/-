"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { useAuthedRequest } from "@/lib/authed-api";

type Limits = { min_minutes: number; max_minutes: number };

type Session = {
  id: string;
  subject_id: string;
  status: string;
  started_at: string;
  ends_at: string;
  remaining_seconds: number;
  server_now: string;
};

type ActiveResponse = { active_session: Session | null; server_now: string };

function formatClock(totalSeconds: number): string {
  const safe = Math.max(0, totalSeconds);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function StudySessionPanel({ subjectId }: { subjectId: string }) {
  const request = useAuthedRequest();
  const router = useRouter();
  const [limits, setLimits] = useState<Limits | null>(null);
  const [active, setActive] = useState<Session | null>(null);
  const [offsetMs, setOffsetMs] = useState(0);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const [duration, setDuration] = useState(30);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [limitsData, activeData] = await Promise.all([
        request<Limits>("/study-sessions/limits"),
        request<ActiveResponse>("/study-sessions/active")
      ]);
      setLimits(limitsData);
      setDuration((current) =>
        Math.min(Math.max(current, limitsData.min_minutes), limitsData.max_minutes)
      );
      setActive(activeData.active_session);
      setOffsetMs(Date.parse(activeData.server_now) - Date.now());
    } catch (caught) {
      setError(caught instanceof ApiError ? `فشل الطلب (${caught.status} ${caught.code}).` : "تعذّر الاتصال بالباك إند.");
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const remainingSeconds = useMemo(() => {
    if (!active) return 0;
    const endsAtMs = Date.parse(active.ends_at);
    return Math.max(0, Math.round((endsAtMs - (nowTick + offsetMs)) / 1000));
  }, [active, nowTick, offsetMs]);

  useEffect(() => {
    if (active && remainingSeconds === 0) {
      void load();
    }
  }, [active, remainingSeconds, load]);

  useEffect(() => {
    if (active && active.subject_id !== subjectId) {
      router.replace(`/subjects/${active.subject_id}`);
    }
  }, [active, subjectId, router]);

  const startSession = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await request<Session>("/study-sessions", {
        body: { subject_id: subjectId, duration_minutes: duration }
      });
      setActive(created);
      setOffsetMs(Date.parse(created.server_now) - Date.now());
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        await load();
      } else if (caught instanceof ApiError && caught.status === 422) {
        setError("المدة المختارة خارج النطاق المسموح.");
      } else {
        setError(caught instanceof ApiError ? `فشل الطلب (${caught.status} ${caught.code}).` : "تعذّر الاتصال بالباك إند.");
      }
    } finally {
      setBusy(false);
    }
  };

  const endSession = async (sessionId: string, cancel: boolean) => {
    setBusy(true);
    setError(null);
    try {
      await request<Session>(`/study-sessions/${sessionId}/end${cancel ? "?cancel=true" : ""}`, {
        method: "POST"
      });
      setActive(null);
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? `فشل الطلب (${caught.status} ${caught.code}).` : "تعذّر الاتصال بالباك إند.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <section className="panel">
        <p className="status">جارٍ تحميل حالة الجلسة...</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>جلسة الدراسة</h2>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {active && active.subject_id === subjectId ? (
        <div>
          <p className="timer" aria-live="polite">
            {formatClock(remainingSeconds)}
          </p>
          <p className="status">تنتهي الجلسة تلقائيًا عند انتهاء العدّاد.</p>
          <div className="actions">
            <button type="button" onClick={() => endSession(active.id, false)} disabled={busy}>
              إنهاء الجلسة الآن
            </button>
            <button type="button" onClick={() => endSession(active.id, true)} disabled={busy}>
              إلغاء الجلسة
            </button>
          </div>
        </div>
      ) : active ? (
        <div>
          <p>لديك جلسة دراسة نشطة في مادة أخرى. لا يمكن تشغيل جلستين معًا.</p>
          <div className="actions">
            <Link className="button" href={`/subjects/${active.subject_id}`}>
              الانتقال إلى المادة النشطة
            </Link>
            <button type="button" onClick={() => endSession(active.id, true)} disabled={busy}>
              إلغاء الجلسة الحالية
            </button>
          </div>
        </div>
      ) : (
        <form className="row" onSubmit={startSession}>
          <label className="checkbox">
            مدة الجلسة (دقائق)
            <input
              type="number"
              min={limits?.min_minutes ?? 5}
              max={limits?.max_minutes ?? 180}
              value={duration}
              onChange={(event) => setDuration(Number(event.target.value))}
            />
          </label>
          <button className="button" type="submit" disabled={busy}>
            بدء جلسة دراسة
          </button>
          {limits ? (
            <span className="status">
              النطاق المسموح: {limits.min_minutes}–{limits.max_minutes} دقيقة
            </span>
          ) : null}
        </form>
      )}
    </section>
  );
}
