"""Subject-scoped retrieval-augmented answering.

Security invariants:
- Identity and subject membership are verified before any retrieval.
- Retrieval filters by ``subject_id`` inside the database query (see
  ``SqlVectorStore.search``); prompt wording is never the only guard.
- If no authorized source supports an answer, the model is instructed to say so
  rather than inventing content; empty retrieval short-circuits without a call.
- Usage (embedding + chat tokens) is logged; context is budgeted by characters.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import ChatMessage, ChatModel, EmbeddingModel, RankedDocument
from app.ai.factory import get_reranker
from app.config import settings
from app.models.knowledge import UsageLog
from app.models.material import Material
from app.models.profile import Profile
from app.services import audit
from app.services import subjects as subject_service
from app.rag.vector_store import SqlVectorStore

SYSTEM_PROMPT = (
    "You are a study assistant. Answer ONLY from the numbered sources provided. "
    "Cite sources inline using their bracket numbers, for example [1] or [2][3]. "
    "If the sources do not contain the answer, or the question is outside the "
    "provided material, reply that the sources do not support an answer and do "
    "not guess. Answer in the language of the question (Arabic, English, or mixed)."
    "\n\n"
    "أنت مساعد دراسي. اعتمد في إجابتك على المصادر المرقّمة المرفقة فقط، "
    "واستشهد بأرقامها مثل [1]. إذا لم تدعم المصادر الإجابة فاذكر ذلك بوضوح دون تخمين."
)

NO_SOURCES_ANSWER = (
    "لا تحتوي مواد هذه المادة على معلومات كافية للإجابة على هذا السؤال. "
    "(No sources in this subject support an answer.)"
)


@dataclass(frozen=True)
class Citation:
    index: int
    material_id: uuid.UUID
    chunk_id: uuid.UUID
    title: str
    score: float
    snippet: str
    page_number: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    model: str = ""
    used_context: bool = False


def _titles_for(db: Session, material_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not material_ids:
        return {}
    rows = db.execute(
        select(Material.id, Material.title).where(Material.id.in_(material_ids))
    ).all()
    return {row[0]: row[1] for row in rows}


def _build_context(
    documents: list[RankedDocument], titles: dict[uuid.UUID, str]
) -> tuple[str, list[Citation]]:
    lines: list[str] = []
    citations: list[Citation] = []
    used_chars = 0
    for document in documents:
        provenance = document.provenance or {}
        page_number = provenance.get("page_number")
        location = f", page {page_number}" if page_number else ""
        title = titles.get(document.material_id, "material")
        snippet = document.content.strip()
        entry = f"[{len(citations) + 1}] ({title}{location}) {snippet}"
        if used_chars + len(entry) > settings.rag_max_context_chars and citations:
            break
        used_chars += len(entry) + 1
        lines.append(entry)
        citations.append(
            Citation(
                index=len(citations) + 1,
                material_id=document.material_id,
                chunk_id=document.chunk_id,
                title=title,
                score=document.score,
                snippet=snippet[:400],
                page_number=page_number,
                start_ms=provenance.get("start_ms"),
                end_ms=provenance.get("end_ms"),
            )
        )
    return "\n\n".join(lines), citations


def answer_question(
    db: Session,
    embedding_model: EmbeddingModel,
    chat_model: ChatModel,
    user: Profile,
    *,
    subject_id: uuid.UUID,
    question: str,
    top_k: int | None = None,
) -> RagAnswer:
    cleaned = question.strip()
    if not cleaned:
        raise ValueError("Question must not be empty.")
    access = subject_service.get_subject_access(db, subject_id, user)

    limit = top_k or settings.rag_top_k
    limit = max(1, min(limit, 20))
    search_limit = limit * 2 if get_reranker() is not None else limit

    query_result = embedding_model.embed([cleaned])
    query_vector = query_result.vectors[0]
    db.add(
        UsageLog(
            user_id=user.id,
            subject_id=subject_id,
            provider="embedding",
            model_id=query_result.model,
            input_tokens=query_result.usage.input_tokens,
            status="success",
        )
    )

    documents = SqlVectorStore(db).search(
        subject_id=subject_id, query_vector=query_vector, top_k=search_limit
    )
    if not documents:
        db.commit()
        return RagAnswer(answer=NO_SOURCES_ANSWER, citations=[], model=chat_model.model_id, used_context=False)

    titles = _titles_for(db, {document.material_id for document in documents})
    context, citations = _build_context(documents, titles)
    if not citations:
        db.commit()
        return RagAnswer(answer=NO_SOURCES_ANSWER, citations=[], model=chat_model.model_id, used_context=False)

    messages = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=f"Sources:\n{context}\n\nQuestion: {cleaned}",
        ),
    ]
    result = chat_model.generate(messages, max_tokens=settings.rag_max_output_tokens)
    db.add(
        UsageLog(
            user_id=user.id,
            subject_id=subject_id,
            provider="chat",
            model_id=result.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            estimated_cost=result.usage.estimated_cost,
            status="success",
        )
    )
    audit.record_event(
        db,
        action="rag.answered",
        user_id=user.id,
        subject_id=access.subject.id,
        metadata={"citations": len(citations)},
        commit=False,
    )
    db.commit()
    return RagAnswer(
        answer=result.content,
        citations=citations,
        model=result.model,
        used_context=True,
    )


__all__ = ["Citation", "NO_SOURCES_ANSWER", "RagAnswer", "SYSTEM_PROMPT", "answer_question"]
