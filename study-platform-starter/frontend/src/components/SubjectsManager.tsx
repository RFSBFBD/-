"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { useAuthedRequest } from "@/lib/authed-api";

export type Subject = {
  id: string;
  name: string;
  role: string;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

type SubjectList = { items: Subject[]; total: number; limit: number; offset: number };

const PAGE_SIZE = 10;

export default function SubjectsManager() {
  const request = useAuthedRequest();
  const [items, setItems] = useState<Subject[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const explain = (caught: unknown): string => {
    if (caught instanceof ApiError) {
      if (caught.status === 409) return "يوجد مادة نشطة بنفس الاسم.";
      if (caught.status === 403) return "لا تملك صلاحية لهذا الإجراء.";
      if (caught.status === 404) return "المادة غير موجودة.";
      return `فشل الطلب (${caught.status} ${caught.code}).`;
    }
    return "تعذّر الاتصال بالباك إند.";
  };

  useEffect(() => {
    const query = `?include_archived=${includeArchived ? "true" : "false"}&limit=${PAGE_SIZE}&offset=${offset}`;
    let cancelled = false;
    setLoading(true);
    setError(null);
    request<SubjectList>(`/subjects${query}`)
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((caught) => {
        if (!cancelled) setError(explain(caught));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request, offset, includeArchived]);

  const createSubject = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await request<Subject>("/subjects", { body: { name: name.trim() } });
      setName("");
      setOffset(0);
      if (offset === 0) await reload();
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const reload = async () => {
    const query = `?include_archived=${includeArchived ? "true" : "false"}&limit=${PAGE_SIZE}&offset=${offset}`;
    const data = await request<SubjectList>(`/subjects${query}`);
    setItems(data.items);
    setTotal(data.total);
  };

  const renameSubject = async (subject: Subject) => {
    const nextName = window.prompt("الاسم الجديد للمادة:", subject.name);
    if (!nextName || !nextName.trim() || nextName.trim() === subject.name) return;
    setBusy(true);
    setError(null);
    try {
      await request<Subject>(`/subjects/${subject.id}`, {
        method: "PATCH",
        body: { name: nextName.trim() }
      });
      await reload();
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const toggleArchive = async (subject: Subject) => {
    setBusy(true);
    setError(null);
    try {
      const action = subject.archived_at ? "unarchive" : "archive";
      await request<Subject>(`/subjects/${subject.id}/${action}`, { method: "POST" });
      await reload();
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div>
      <form className="panel row" onSubmit={createSubject}>
        <input
          aria-label="اسم المادة"
          placeholder="اسم المادة الجديدة"
          value={name}
          maxLength={120}
          onChange={(event) => setName(event.target.value)}
        />
        <button className="button" type="submit" disabled={busy || !name.trim()}>
          إنشاء مادة
        </button>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => {
              setIncludeArchived(event.target.checked);
              setOffset(0);
            }}
          />
          إظهار المؤرشفة
        </label>
      </form>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="status">جارٍ التحميل...</p>
      ) : items.length === 0 ? (
        <p className="status">لا توجد مواد بعد. أنشئ مادتك الأولى.</p>
      ) : (
        <ul className="list">
          {items.map((subject) => (
            <li key={subject.id} className="list-item">
              <div>
                <Link href={`/subjects/${subject.id}`} className="subject-name">
                  {subject.name}
                </Link>
                <span className="badge">{subject.role === "owner" ? "مالك" : "عضو"}</span>
                {subject.archived_at ? <span className="badge archived">مؤرشفة</span> : null}
              </div>
              <div className="actions">
                <button type="button" onClick={() => renameSubject(subject)} disabled={busy}>
                  إعادة تسمية
                </button>
                <button type="button" onClick={() => toggleArchive(subject)} disabled={busy}>
                  {subject.archived_at ? "استعادة" : "أرشفة"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {total > PAGE_SIZE ? (
        <div className="pager">
          <button
            type="button"
            disabled={offset === 0 || busy}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            السابق
          </button>
          <span>
            صفحة {currentPage} من {totalPages}
          </span>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= total || busy}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            التالي
          </button>
        </div>
      ) : null}
    </div>
  );
}
