from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.base import AIProviderError, ChatModel, EmbeddingModel, ProviderUnavailable
from app.ai.documents import get_document_parser
from app.ai.factory import get_chat_model, get_embedding_model
from app.auth.dependencies import get_current_profile
from app.db.session import get_db
from app.models.profile import Profile
from app.schemas.rag import AskIn, AskOut, CitationOut, IngestOut
from app.services import ingestion as ingestion_service
from app.services import materials as material_service
from app.services import rag as rag_service
from app.services.ingestion import IngestionError
from app.services.materials import MaterialError
from app.services.subjects import SubjectError
from app.storage import get_storage
from app.storage.base import StorageProvider

router = APIRouter(tags=["rag"])


def get_embedding_model_dep() -> EmbeddingModel:
    try:
        return get_embedding_model()
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_chat_model_dep() -> ChatModel:
    try:
        return get_chat_model()
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/subjects/{subject_id}/materials/{material_id}/ingest",
    response_model=IngestOut,
)
def ingest_material(
    subject_id: uuid.UUID,
    material_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage),
    embedding_model: EmbeddingModel = Depends(get_embedding_model_dep),
) -> IngestOut:
    try:
        material, _ = material_service.get_material(db, profile, material_id)
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if material.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Material not found.")

    try:
        result = ingestion_service.ingest_material(
            db,
            storage,
            embedding_model,
            get_document_parser(),
            profile,
            material_id,
        )
    except (MaterialError, SubjectError, IngestionError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return IngestOut(
        material_id=result.material_id,
        processing_status=result.processing_status,
        chunk_count=result.chunk_count,
        embedded_count=result.embedded_count,
        cached_count=result.cached_count,
        inserted_count=result.inserted_count,
    )


@router.post("/subjects/{subject_id}/ask", response_model=AskOut)
def ask_subject(
    subject_id: uuid.UUID,
    payload: AskIn,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
    embedding_model: EmbeddingModel = Depends(get_embedding_model_dep),
    chat_model: ChatModel = Depends(get_chat_model_dep),
) -> AskOut:
    try:
        answer = rag_service.answer_question(
            db,
            embedding_model,
            chat_model,
            profile,
            subject_id=subject_id,
            question=payload.question,
            top_k=payload.top_k,
        )
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AskOut(
        answer=answer.answer,
        citations=[
            CitationOut(
                index=citation.index,
                material_id=citation.material_id,
                chunk_id=citation.chunk_id,
                title=citation.title,
                score=citation.score,
                snippet=citation.snippet,
                page_number=citation.page_number,
                start_ms=citation.start_ms,
                end_ms=citation.end_ms,
            )
            for citation in answer.citations
        ],
        model=answer.model,
        used_context=answer.used_context,
    )
