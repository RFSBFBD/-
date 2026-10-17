"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useAuthedRequest } from "@/lib/authed-api";

type Session = {
  id: string;
  subject_id: string;
  status: string;
  ends_at: string;
  server_now: string;
};

type ActiveResponse = { active_session: Session | null; server_now: string };

function formatClock(totalSeconds: number): string {
  const safe = Math.max(0, totalSeconds);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function ActiveSessionBanner() {
  const request = useAuthedRequest();
  const [active, setActive] = useState<Session | null>(null);
  const [offsetMs, setOffsetMs] = useState(0);
  const [nowTick, setNowTick] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    request<ActiveResponse>("/study-sessions/active")
      .then((data) => {
        if (cancelled) return;
        setActive(data.active_session);
        setOffsetMs(Date.parse(data.server_now) - Date.now());
      })
      .catch(() => {
        if (!cancelled) setActive(null);
      });
    return () => {
      cancelled = true;
    };
  }, [request]);

  useEffect(() => {
    const timer = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const remainingSeconds = useMemo(() => {
    if (!active) return 0;
    return Math.max(0, Math.round((Date.parse(active.ends_at) - (nowTick + offsetMs)) / 1000));
  }, [active, nowTick, offsetMs]);

  if (!active) return null;

  return (
    <section className="panel">
      <p>
        لديك جلسة دراسة نشطة — الوقت المتبقي:{" "}
        <span className="timer" aria-live="polite">
          {formatClock(remainingSeconds)}
        </span>
      </p>
      <Link className="button" href={`/subjects/${active.subject_id}`}>
        متابعة الدراسة
      </Link>
    </section>
  );
}
