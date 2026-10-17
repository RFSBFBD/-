"""Private material storage and library services.

Security invariants:
- Every operation resolves subject membership server-side; inaccessible subjects
  and materials are reported as not found (never confirming existence).
- File content type and size are validated from bytes, not client metadata.
- SHA-256 is computed server-side; browser-supplied hashes are never trusted.
- Exact duplicates are detected per subject and linked instead of re-stored.
- Similar-but-not-identical content enters manual review; nothing is auto-deleted.
- Cross-subject matches and metadata are never disclosed.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.material import (
    DUPLICATE_CONFIRMED,
    DUPLICATE_DISMISSED,
    DUPLICATE_EXACT,
    DUPLICATE_NONE,
    DUPLICATE_PENDING_REVIEW,
    REVIEW_CONFIRMED,
    REVIEW_DISMISSED,
    REVIEW_PENDING,
    DuplicateReview,
    Material,
    StoredFile,
)
from app.models.profile import Profile
from app.services import audit
from app.services import subjects as subject_service
from app.services.subjects import SubjectArchived, SubjectAccess
from app.services.upload_validation import (
    UploadValidationError,
    get_malware_scanner,
    validate_upload,
)
from app.storage.base import StorageProvider

_WHITESPACE = re.compile(r"\s+")


class MaterialError(Exception):
    status_code = 400


class MaterialNotFound(MaterialError):
    status_code = 404


class MaterialForbidden(MaterialError):
    status_code = 403


class MaterialValidationError(MaterialError):
    status_code = 422


@dataclass(frozen=True)
class UploadOutcome:
    material: Material
    stored_file: StoredFile
    created: bool
    duplicate: str
    duplicate_material_id: uuid.UUID | None


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip()).casefold()


def _storage_key(sha256: str) -> str:
    return f"blobs/{sha256[:2]}/{sha256}"


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip() or filename.strip() or "مادة"
    return stem[:255]


def _access_for_subject(db: Session, subject_id: uuid.UUID, user: Profile) -> SubjectAccess:
    return subject_service.get_subject_access(db, subject_id, user)


def create_material(
    db: Session,
    storage: StorageProvider,
    user: Profile,
    *,
    subject_id: uuid.UUID,
    filename: str,
    declared_content_type: str | None,
    data: bytes,
    title: str | None = None,
) -> UploadOutcome:
    access = _access_for_subject(db, subject_id, user)
    if access.subject.archived_at is not None:
        raise SubjectArchived("Archived subjects cannot receive uploads.")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    try:
        mime_type, material_type = validate_upload(
            data,
            filename=filename,
            declared_content_type=declared_content_type,
            max_bytes=max_bytes,
        )
    except UploadValidationError as exc:
        raise MaterialValidationError(str(exc)) from exc

    scan = get_malware_scanner().scan(data, filename)
    if not scan.clean:
        audit.record_event(
            db,
            action="material.upload_rejected",
            user_id=user.id,
            subject_id=subject_id,
            metadata={"reason": scan.reason or "malware"},
        )
        raise MaterialValidationError(
            f"Upload rejected: {scan.reason or 'failed content scan'}."
        )

    sha256 = hashlib.sha256(data).hexdigest()
    display_title = (title or "").strip()[:255] or _title_from_filename(filename)

    exact = _find_exact_duplicate(db, subject_id, sha256)
    if exact is not None:
        existing, stored = exact
        audit.record_event(
            db,
            action="material.duplicate_linked",
            user_id=user.id,
            subject_id=subject_id,
            metadata={"material_id": str(existing.id), "sha256": sha256},
        )
        return UploadOutcome(
            material=existing,
            stored_file=stored,
            created=False,
            duplicate=DUPLICATE_EXACT,
            duplicate_material_id=existing.id,
        )

    stored = db.execute(
        select(StoredFile).where(StoredFile.sha256 == sha256)
    ).scalars().first()
    if stored is None:
        key = _storage_key(sha256)
        storage.put_object(key, data, content_type=mime_type)
        stored = StoredFile(
            uploader_id=user.id,
            storage_key=key,
            sha256=sha256,
            mime_type=mime_type,
            size_bytes=len(data),
            original_filename=filename[:255],
        )
        db.add(stored)
        db.flush()

    material = Material(
        subject_id=subject_id,
        stored_file_id=stored.id,
        uploader_id=user.id,
        title=display_title,
        material_type=material_type,
    )
    db.add(material)
    db.flush()

    similar = _find_similar(db, subject_id, material)
    if similar is not None:
        matched, score = similar
        material.duplicate_status = DUPLICATE_PENDING_REVIEW
        db.add(_build_review(subject_id, material.id, matched.id, score))
        audit.record_event(
            db,
            action="material.duplicate_review_created",
            user_id=user.id,
            subject_id=subject_id,
            metadata={
                "candidate_material_id": str(material.id),
                "matched_material_id": str(matched.id),
                "similarity": round(score, 4),
            },
            commit=False,
        )
    else:
        material.duplicate_status = DUPLICATE_NONE

    audit.record_event(
        db,
        action="material.uploaded",
        user_id=user.id,
        subject_id=subject_id,
        metadata={
            "material_id": str(material.id),
            "material_type": material_type,
            "size_bytes": len(data),
        },
        commit=False,
    )
    db.commit()
    db.refresh(material)
    db.refresh(stored)
    return UploadOutcome(
        material=material,
        stored_file=stored,
        created=True,
        duplicate=material.duplicate_status,
        duplicate_material_id=None,
    )


def _find_exact_duplicate(
    db: Session, subject_id: uuid.UUID, sha256: str
) -> tuple[Material, StoredFile] | None:
    row = db.execute(
        select(Material, StoredFile)
        .join(StoredFile, Material.stored_file_id == StoredFile.id)
        .where(
            Material.subject_id == subject_id,
            Material.deleted_at.is_(None),
            StoredFile.sha256 == sha256,
        )
        .order_by(Material.created_at.asc())
    ).first()
    return (row[0], row[1]) if row else None


def _find_similar(
    db: Session, subject_id: uuid.UUID, candidate: Material
) -> tuple[Material, float] | None:
    rows = db.execute(
        select(Material).where(
            Material.subject_id == subject_id,
            Material.deleted_at.is_(None),
            Material.id != candidate.id,
        )
    ).scalars().all()
    target = _normalize(candidate.title)
    best: tuple[Material, float] | None = None
    for other in rows:
        score = difflib.SequenceMatcher(None, target, _normalize(other.title)).ratio()
        if score >= settings.duplicate_similarity_threshold and (
            best is None or score > best[1]
        ):
            best = (other, score)
    return best


def _build_review(
    subject_id: uuid.UUID, candidate_id: uuid.UUID, matched_id: uuid.UUID, score: float
):
    from app.models.material import DuplicateReview

    return DuplicateReview(
        subject_id=subject_id,
        candidate_material_id=candidate_id,
        matched_material_id=matched_id,
        similarity_score=score,
    )


def list_materials(
    db: Session,
    user: Profile,
    *,
    subject_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[tuple[Material, StoredFile]], int]:
    _access_for_subject(db, subject_id, user)
    base = (
        select(Material, StoredFile)
        .join(StoredFile, Material.stored_file_id == StoredFile.id)
        .where(Material.subject_id == subject_id, Material.deleted_at.is_(None))
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(Material.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return [(r[0], r[1]) for r in rows], int(total)


def get_material(
    db: Session, user: Profile, material_id: uuid.UUID
) -> tuple[Material, StoredFile]:
    row = db.execute(
        select(Material, StoredFile)
        .join(StoredFile, Material.stored_file_id == StoredFile.id)
        .where(Material.id == material_id, Material.deleted_at.is_(None))
    ).first()
    if row is None:
        raise MaterialNotFound("Material not found.")
    material, stored = row
    _access_for_subject(db, material.subject_id, user)
    return material, stored


def create_download_url(
    db: Session,
    storage: StorageProvider,
    user: Profile,
    material_id: uuid.UUID,
    *,
    ttl_seconds: int | None = None,
) -> tuple[str, int]:
    material, stored = get_material(db, user, material_id)
    ttl = ttl_seconds or settings.signed_url_ttl_seconds
    signed = storage.create_download_url(stored.storage_key, expires_in=ttl)
    audit.record_event(
        db,
        action="material.download_url_issued",
        user_id=user.id,
        subject_id=material.subject_id,
        metadata={"material_id": str(material.id)},
    )
    return signed.url, signed.expires_in


def delete_material(db: Session, user: Profile, material_id: uuid.UUID) -> None:
    material, _ = get_material(db, user, material_id)
    access = _access_for_subject(db, material.subject_id, user)
    is_owner = access.role == subject_service.SUBJECT_ROLE_OWNER
    if not is_owner and material.uploader_id != user.id:
        raise MaterialForbidden("Only the uploader or subject owner can delete this material.")
    material.deleted_at = func.now()
    db.commit()
    audit.record_event(
        db,
        action="material.deleted",
        user_id=user.id,
        subject_id=material.subject_id,
        metadata={"material_id": str(material.id)},
    )


def cleanup_orphan_stored_files(
    db: Session, storage: StorageProvider, *, older_than: datetime
) -> int:
    """Delete stored files with no material references (abandoned uploads)."""
    referenced = select(Material.stored_file_id)
    orphans = db.execute(
        select(StoredFile).where(
            StoredFile.id.not_in(referenced),
            StoredFile.created_at < older_than,
        )
    ).scalars().all()
    removed = 0
    for stored in orphans:
        try:
            storage.delete_object(stored.storage_key)
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass
        db.delete(stored)
        removed += 1
    if removed:
        db.commit()
    return removed


def list_reviews(
    db: Session,
    user: Profile,
    *,
    subject_id: uuid.UUID,
    status: str = REVIEW_PENDING,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[DuplicateReview], int]:
    access = _access_for_subject(db, subject_id, user)
    subject_service.require_owner(access)
    base = select(DuplicateReview).where(
        DuplicateReview.subject_id == subject_id, DuplicateReview.status == status
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(DuplicateReview.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return list(rows), int(total)


def resolve_review(
    db: Session,
    user: Profile,
    review_id: uuid.UUID,
    *,
    decision: str,
) -> DuplicateReview:
    review = db.get(DuplicateReview, review_id)
    if review is None:
        raise MaterialNotFound("Duplicate review not found.")
    access = _access_for_subject(db, review.subject_id, user)
    subject_service.require_owner(access)
    if decision not in {"confirm", "dismiss"}:
        raise MaterialError("Invalid review decision.")

    if review.status == REVIEW_PENDING:
        review.status = REVIEW_CONFIRMED if decision == "confirm" else REVIEW_DISMISSED
        review.reviewer_id = user.id
        review.reviewed_at = func.now()
        candidate = db.get(Material, review.candidate_material_id)
        if candidate is not None:
            candidate.duplicate_status = (
                DUPLICATE_CONFIRMED if decision == "confirm" else DUPLICATE_DISMISSED
            )
        audit.record_event(
            db,
            action="material.duplicate_review_resolved",
            user_id=user.id,
            subject_id=review.subject_id,
            metadata={"review_id": str(review.id), "decision": decision},
            commit=False,
        )
        db.commit()
        db.refresh(review)
    return review


__all__ = [
    "MaterialError",
    "MaterialForbidden",
    "MaterialNotFound",
    "MaterialValidationError",
    "UploadOutcome",
    "cleanup_orphan_stored_files",
    "create_download_url",
    "create_material",
    "delete_material",
    "get_material",
    "list_materials",
    "list_reviews",
    "resolve_review",
]
