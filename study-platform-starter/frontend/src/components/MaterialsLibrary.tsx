"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { useAuthedRequest, useAuthedUpload } from "@/lib/authed-api";

type Material = {
  id: string;
  subject_id: string;
  title: string;
  material_type: string;
  processing_status: string;
  duplicate_status: string;
  uploader_id: string | null;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
};

type MaterialList = { items: Material[]; total: number; limit: number; offset: number };

type UploadResponse = {
  material: Material;
  created: boolean;
  duplicate: string;
  duplicate_material_id: string | null;
};

type DuplicateReview = {
  id: string;
  candidate_material_id: string;
  matched_material_id: string;
  similarity_score: number;
  status: string;
};

type ReviewList = { items: DuplicateReview[]; total: number };

const PAGE_SIZE = 10;

const MATERIAL_TYPE_LABELS: Record<string, string> = {
  document: "مستند",
  image: "صورة",
  audio: "صوت",
  video: "فيديو",
  other: "أخرى"
};

const DUPLICATE_LABELS: Record<string, string> = {
  none: "",
  exact: "مكرر مطابق",
  pending_review: "بانتظار مراجعة التشابه",
  confirmed: "تأكد التكرار",
  dismissed: "تم تجاهل التشابه"
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function MaterialsLibrary({
  subjectId,
  isOwner
}: {
  subjectId: string;
  isOwner: boolean;
}) {
  const request = useAuthedRequest();
  const uploadFile = useAuthedUpload();
  const [items, setItems] = useState<Material[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [reviews, setReviews] = useState<DuplicateReview[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const explain = (caught: unknown): string => {
    if (caught instanceof ApiError) {
      if (caught.status === 422) return "نوع الملف أو حجمه غير مسموح.";
      if (caught.status === 429) return "عدد كبير من عمليات الرفع. انتظر قليلًا.";
      if (caught.status === 403) return "لا تملك صلاحية لهذا الإجراء.";
      if (caught.status === 404) return " العنصر غير موجود.";
      return `فشل الطلب (${caught.status} ${caught.code}).`;
    }
    return "تعذّر الاتصال بالباك إند.";
  };

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await request<MaterialList>(
        `/subjects/${subjectId}/materials?limit=${PAGE_SIZE}&offset=${offset}`
      );
      setItems(data.items);
      setTotal(data.total);
      if (isOwner) {
        const reviewData = await request<ReviewList>(
          `/subjects/${subjectId}/duplicate-reviews`
        );
        setReviews(reviewData.items);
      }
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setLoading(false);
    }
  }, [request, subjectId, offset, isOwner]);

  useEffect(() => {
    void load();
  }, [load]);

  const onUpload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (title.trim()) formData.append("title", title.trim());
      const result = await uploadFile<UploadResponse>(
        `/subjects/${subjectId}/materials`,
        formData
      );
      if (result.duplicate === "exact") {
        setNotice("الملف مطابق لملف موجود في المادة؛ تم الربط به دون تخزين نسخة جديدة.");
      } else if (result.duplicate === "pending_review") {
        setNotice("تم رفع الملف وأُضيف إلى مراجعة التشابه اليدوية.");
      } else {
        setNotice("تم رفع الملف بنجاح.");
      }
      setFile(null);
      setTitle("");
      setOffset(0);
      await load();
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const download = async (material: Material) => {
    setError(null);
    try {
      const { url } = await request<{ url: string }>(`/materials/${material.id}/download`);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (caught) {
      setError(explain(caught));
    }
  };

  const remove = async (material: Material) => {
    if (!window.confirm(`حذف «${material.title}» من هذه المادة؟`)) return;
    setBusy(true);
    setError(null);
    try {
      await request(`/materials/${material.id}`, { method: "DELETE" });
      await load();
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const resolveReview = async (review: DuplicateReview, decision: "confirm" | "dismiss") => {
    setBusy(true);
    setError(null);
    try {
      await request(`/duplicate-reviews/${review.id}/resolve`, {
        method: "POST",
        body: { decision }
      });
      await load();
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <section className="panel">
      <h2>المكتبة ({total})</h2>

      <form className="row" onSubmit={onUpload}>
        <input
          aria-label="ملف المادة"
          type="file"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <input
          aria-label="عنوان المادة"
          placeholder="عنوان المادة (اختياري)"
          value={title}
          maxLength={255}
          onChange={(event) => setTitle(event.target.value)}
        />
        <button className="button" type="submit" disabled={busy || !file}>
          رفع
        </button>
      </form>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? <p className="status">{notice}</p> : null}

      {loading ? (
        <p className="status">جارٍ التحميل...</p>
      ) : items.length === 0 ? (
        <p className="status">لا توجد ملفات بعد.</p>
      ) : (
        <ul className="list">
          {items.map((material) => (
            <li key={material.id} className="list-item">
              <div>
                <strong>{material.title}</strong>
                <span className="badge">
                  {MATERIAL_TYPE_LABELS[material.material_type] ?? material.material_type}
                </span>
                {material.duplicate_status !== "none" ? (
                  <span className="badge archived">
                    {DUPLICATE_LABELS[material.duplicate_status] ?? material.duplicate_status}
                  </span>
                ) : null}
                <div className="status">
                  {material.original_filename} · {formatBytes(material.size_bytes)}
                </div>
              </div>
              <div className="actions">
                <button type="button" onClick={() => download(material)} disabled={busy}>
                  تنزيل
                </button>
                <button type="button" onClick={() => remove(material)} disabled={busy}>
                  حذف
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

      {isOwner && reviews.length > 0 ? (
        <section className="panel">
          <h3>مراجعة التشابه ({reviews.length})</h3>
          <ul className="list">
            {reviews.map((review) => (
              <li key={review.id} className="list-item">
                <div>
                  <span className="status">
                    تشابه {(review.similarity_score * 100).toFixed(0)}% مع مادة أخرى
                  </span>
                </div>
                <div className="actions">
                  <button
                    type="button"
                    onClick={() => resolveReview(review, "confirm")}
                    disabled={busy}
                  >
                    تأكيد التكرار
                  </button>
                  <button
                    type="button"
                    onClick={() => resolveReview(review, "dismiss")}
                    disabled={busy}
                  >
                    تجاهل
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
