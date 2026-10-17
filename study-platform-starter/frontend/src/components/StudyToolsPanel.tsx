"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { useAuthedRequest } from "@/lib/authed-api";

type Material = {
  id: string;
  title: string;
  material_type: string;
  processing_status: string;
};

type MaterialList = { items: Material[]; total: number };

type TranscriptSegment = {
  id: string;
  segment_index: number;
  start_ms: number;
  end_ms: number;
  text: string;
  confidence: number | null;
};

type Transcript = { material_id: string; segment_count: number; total: number; segments: TranscriptSegment[] };

type Citation = {
  index: number;
  material_id: string;
  title: string;
  page_number: number | null;
  start_ms: number | null;
  end_ms: number | null;
  snippet: string;
};

type Artifact = {
  id: string;
  subject_id: string;
  material_id: string | null;
  artifact_type: string;
  model_id: string;
  prompt_version: string;
  payload: { data?: unknown; citations?: Citation[] } & Record<string, unknown>;
  created_at: string;
  updated_at: string;
  cached: boolean;
};

type ArtifactList = { items: Artifact[]; total: number; limit: number; offset: number };

type Feedback = { id: string; artifact_id: string; rating: string; comment: string | null };

const ARTIFACT_TYPES: { value: string; label: string }[] = [
  { value: "notes", label: "ملاحظات مفصّلة" },
  { value: "quiz", label: "اختبار" },
  { value: "quiz_explanation", label: "شرح الإجابات" },
  { value: "revision_cards", label: "بطاقات مراجعة" },
  { value: "mind_map", label: "خريطة مفاهيم" },
  { value: "code_descriptions", label: "وصف الأكواد والرسوم" },
  { value: "concept_alignment", label: "مواءمة المفاهيم" }
];

const ARTIFACT_LABELS = Object.fromEntries(ARTIFACT_TYPES.map((t) => [t.value, t.label]));

function formatTime(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export default function StudyToolsPanel({ subjectId }: { subjectId: string }) {
  const request = useAuthedRequest();
  const [materials, setMaterials] = useState<Material[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const explain = (caught: unknown): string => {
    if (caught instanceof ApiError) {
      if (caught.status === 503) return "المزوّد غير مهيّأ على الخادم (مفاتيح أو محرّك ناقص).";
      if (caught.status === 502) return "تعذّر استخدام مخرجات النموذج. أعد المحاولة.";
      if (caught.status === 422) return "اختيار غير صالح (تحقّق من المواد أو النوع).";
      if (caught.status === 429) return "عدد كبير من الطلبات. انتظر قليلًا.";
      if (caught.status === 403) return "لا تملك صلاحية لهذا الإجراء.";
      if (caught.status === 404) return "العنصر غير موجود.";
      return `فشل الطلب (${caught.status} ${caught.code}).`;
    }
    return "تعذّر الاتصال بالباك إند.";
  };

  const load = useCallback(async () => {
    setError(null);
    try {
      const materialData = await request<MaterialList>(`/subjects/${subjectId}/materials?limit=100`);
      setMaterials(materialData.items);
      const artifactData = await request<ArtifactList>(`/subjects/${subjectId}/artifacts?limit=20`);
      setArtifacts(artifactData.items);
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setLoading(false);
    }
  }, [request, subjectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (materialId: string) => {
    setSelected((current) =>
      current.includes(materialId)
        ? current.filter((id) => id !== materialId)
        : [...current, materialId]
    );
  };

  const transcribe = async (materialId: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await request<{ segment_count: number }>(
        `/subjects/${subjectId}/materials/${materialId}/transcribe`,
        { method: "POST" }
      );
      setNotice(`تم تحويل الصوت إلى ${result.segment_count} مقطعًا.`);
      const data = await request<Transcript>(
        `/subjects/${subjectId}/materials/${materialId}/transcript`
      );
      setTranscript(data);
      await load();
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const viewTranscript = async (materialId: string) => {
    setBusy(true);
    setError(null);
    try {
      const data = await request<Transcript>(
        `/subjects/${subjectId}/materials/${materialId}/transcript`
      );
      setTranscript(data);
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const generate = async (artifactType: string, force = false) => {
    if (selected.length === 0) {
      setError("اختر مادة واحدة على الأقل.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const artifact = await request<Artifact>(`/subjects/${subjectId}/artifacts`, {
        method: "POST",
        body: { artifact_type: artifactType, material_ids: selected, force }
      });
      setActiveArtifact(artifact);
      setNotice(artifact.cached ? "أُعيد استخدام نتيجة مُخزّنة دون استهلاك توكنز." : "تم توليد المنتج.");
      await load();
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async (artifactId: string) => {
    setBusy(true);
    setError(null);
    try {
      const artifact = await request<Artifact>(`/artifacts/${artifactId}/regenerate`, {
        method: "POST"
      });
      setActiveArtifact(artifact);
      setNotice("تمت إعادة التوليد.");
      await load();
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  const feedback = async (artifactId: string, rating: "up" | "down") => {
    setBusy(true);
    setError(null);
    try {
      await request<Feedback>(`/artifacts/${artifactId}/feedback`, {
        method: "POST",
        body: { rating }
      });
      setNotice("تم تسجيل تقييمك.");
    } catch (caught) {
      setError(explain(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <h2>أدوات الدراسة</h2>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? <p className="status">{notice}</p> : null}

      {loading ? (
        <p className="status">جارٍ التحميل...</p>
      ) : materials.length === 0 ? (
        <p className="status">ارفع مواد أولًا لتوليد الملاحظات والاختبارات.</p>
      ) : (
        <>
          <div>
            <h3>اختر المواد</h3>
            <ul className="list">
              {materials.map((material) => (
                <li key={material.id} className="list-item">
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.includes(material.id)}
                      onChange={() => toggle(material.id)}
                    />
                    <strong> {material.title}</strong>
                  </label>
                  <span className="badge">{material.material_type}</span>
                  {material.material_type === "audio" ? (
                    <div className="actions">
                      <button type="button" disabled={busy} onClick={() => transcribe(material.id)}>
                        تحويل إلى نص
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => viewTranscript(material.id)}
                      >
                        عرض النص
                      </button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>

          <div className="row">
            {ARTIFACT_TYPES.map((type) => (
              <button
                key={type.value}
                className="button"
                type="button"
                disabled={busy || selected.length === 0}
                onClick={() => generate(type.value)}
              >
                {type.label}
              </button>
            ))}
          </div>
        </>
      )}

      {transcript ? (
        <section className="panel">
          <h3>النص ({transcript.total} مقطعًا)</h3>
          <ul className="list">
            {transcript.segments.map((segment) => (
              <li key={segment.id} className="list-item">
                <span className="status">[{formatTime(segment.start_ms)}]</span>
                <span> {segment.text}</span>
                {segment.confidence !== null ? (
                  <span className="badge">ثقة {(segment.confidence * 100).toFixed(0)}%</span>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {activeArtifact ? (
        <section className="panel">
          <h3>
            {ARTIFACT_LABELS[activeArtifact.artifact_type] ?? activeArtifact.artifact_type}
            {activeArtifact.cached ? <span className="badge">مُخزّن</span> : null}
          </h3>
          <div className="actions">
            <button
              type="button"
              disabled={busy}
              onClick={() => regenerate(activeArtifact.id)}
            >
              إعادة توليد
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => feedback(activeArtifact.id, "up")}
            >
              👍 مفيد
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => feedback(activeArtifact.id, "down")}
            >
              👎 غير مفيد
            </button>
          </div>
          <pre className="status">{JSON.stringify(activeArtifact.payload.data, null, 2)}</pre>
          {activeArtifact.payload.citations && activeArtifact.payload.citations.length > 0 ? (
            <div>
              <h4>المصادر ({activeArtifact.payload.citations.length})</h4>
              <ul className="list">
                {activeArtifact.payload.citations.map((citation) => (
                  <li key={citation.index} className="list-item">
                    <span className="status">
                      [{citation.index}] {citation.title}
                      {citation.start_ms !== null ? ` — ${formatTime(citation.start_ms)}` : ""}
                      {citation.page_number !== null ? ` — صفحة ${citation.page_number}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      {artifacts.length > 0 ? (
        <section className="panel">
          <h3>المنتجات المحفوظة ({artifacts.length})</h3>
          <ul className="list">
            {artifacts.map((artifact) => (
              <li key={artifact.id} className="list-item">
                <span>
                  {ARTIFACT_LABELS[artifact.artifact_type] ?? artifact.artifact_type} ·{" "}
                  <span className="status">{artifact.model_id}</span>
                </span>
                <button type="button" disabled={busy} onClick={() => setActiveArtifact(artifact)}>
                  عرض
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
