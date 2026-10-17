"""Subject lifecycle and membership services.

Every operation takes the authenticated ``Profile`` and enforces membership
server-side. Submitted user IDs are never trusted. Cross-subject existence is
never disclosed: a subject a caller cannot access is reported as not found.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.profile import Profile
from app.models.subject import (
    SUBJECT_ROLE_MEMBER,
    SUBJECT_ROLE_OWNER,
    SUBJECT_ROLES,
    Subject,
    SubjectMember,
)

_WHITESPACE = re.compile(r"\s+")


class SubjectError(Exception):
    """Base class for subject domain errors."""

    status_code = 400


class SubjectValidationError(SubjectError):
    status_code = 422


class SubjectNotFound(SubjectError):
    status_code = 404


class SubjectNameConflict(SubjectError):
    status_code = 409


class SubjectArchived(SubjectError):
    status_code = 409


class NotSubjectOwner(SubjectError):
    status_code = 403


class MemberAlreadyExists(SubjectError):
    status_code = 409


class MemberNotFound(SubjectError):
    status_code = 404


@dataclass(frozen=True)
class SubjectAccess:
    subject: Subject
    role: str


def normalize_subject_name(name: str) -> str:
    return _WHITESPACE.sub(" ", name.strip()).casefold()


def _validate_name(name: str) -> str:
    cleaned = _WHITESPACE.sub(" ", name.strip())
    if not cleaned:
        raise SubjectValidationError("Subject name must not be empty.")
    if len(cleaned) > 120:
        raise SubjectValidationError("Subject name must be 120 characters or fewer.")
    return cleaned


def get_membership(db: Session, subject_id: uuid.UUID, user_id: uuid.UUID) -> SubjectMember | None:
    return db.get(SubjectMember, (subject_id, user_id))


def get_subject_access(db: Session, subject_id: uuid.UUID, user: Profile) -> SubjectAccess:
    row = db.execute(
        select(Subject, SubjectMember.role)
        .join(SubjectMember, SubjectMember.subject_id == Subject.id)
        .where(Subject.id == subject_id, SubjectMember.user_id == user.id)
    ).first()
    if row is None:
        raise SubjectNotFound("Subject not found.")
    subject, role = row
    return SubjectAccess(subject=subject, role=role)


def require_owner(access: SubjectAccess) -> None:
    if access.role != SUBJECT_ROLE_OWNER:
        raise NotSubjectOwner("Only the subject owner can perform this action.")


def create_subject(db: Session, owner: Profile, name: str) -> Subject:
    cleaned = _validate_name(name)
    subject = Subject(
        created_by=owner.id,
        name=cleaned,
        normalized_name=normalize_subject_name(cleaned),
    )
    db.add(subject)
    try:
        db.flush()
        db.add(SubjectMember(subject_id=subject.id, user_id=owner.id, role=SUBJECT_ROLE_OWNER))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SubjectNameConflict("You already have an active subject with this name.") from exc
    db.refresh(subject)
    return subject


def list_subjects(
    db: Session,
    user: Profile,
    *,
    include_archived: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[SubjectAccess], int]:
    conditions = [SubjectMember.user_id == user.id]
    if not include_archived:
        conditions.append(Subject.archived_at.is_(None))

    base = (
        select(Subject, SubjectMember.role)
        .join(SubjectMember, SubjectMember.subject_id == Subject.id)
        .where(*conditions)
    )
    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()

    rows = db.execute(
        base.order_by(Subject.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return [SubjectAccess(subject=s, role=r) for s, r in rows], int(total)


def rename_subject(db: Session, access: SubjectAccess, name: str) -> Subject:
    require_owner(access)
    if access.subject.archived_at is not None:
        raise SubjectArchived("Archived subjects cannot be renamed.")
    cleaned = _validate_name(name)
    access.subject.name = cleaned
    access.subject.normalized_name = normalize_subject_name(cleaned)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SubjectNameConflict("You already have an active subject with this name.") from exc
    db.refresh(access.subject)
    return access.subject


def archive_subject(db: Session, access: SubjectAccess) -> Subject:
    require_owner(access)
    if access.subject.archived_at is None:
        access.subject.archived_at = func.now()
        db.commit()
        db.refresh(access.subject)
    return access.subject


def unarchive_subject(db: Session, access: SubjectAccess) -> Subject:
    require_owner(access)
    if access.subject.archived_at is not None:
        access.subject.archived_at = None
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise SubjectNameConflict(
                "An active subject with this name already exists."
            ) from exc
        db.refresh(access.subject)
    return access.subject


def list_members(db: Session, subject_id: uuid.UUID) -> list[SubjectMember]:
    return list(
        db.execute(
            select(SubjectMember)
            .where(SubjectMember.subject_id == subject_id)
            .order_by(SubjectMember.joined_at.asc())
        ).scalars()
    )


def add_member(
    db: Session,
    access: SubjectAccess,
    *,
    user_id: uuid.UUID,
    role: str = SUBJECT_ROLE_MEMBER,
) -> SubjectMember:
    require_owner(access)
    if role not in SUBJECT_ROLES:
        raise SubjectValidationError("Invalid subject role.")
    if role == SUBJECT_ROLE_OWNER:
        raise SubjectValidationError("Ownership cannot be granted through membership.")
    if db.get(Profile, user_id) is None:
        raise MemberNotFound("Target user does not exist.")
    membership = SubjectMember(subject_id=access.subject.id, user_id=user_id, role=role)
    db.add(membership)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise MemberAlreadyExists("User is already a member of this subject.") from exc
    db.refresh(membership)
    return membership


def remove_member(db: Session, access: SubjectAccess, user_id: uuid.UUID) -> None:
    require_owner(access)
    membership = db.get(SubjectMember, (access.subject.id, user_id))
    if membership is None:
        raise MemberNotFound("Membership not found.")
    if membership.role == SUBJECT_ROLE_OWNER:
        raise SubjectValidationError("The owner cannot be removed from the subject.")
    db.delete(membership)
    db.commit()


__all__ = [
    "MemberAlreadyExists",
    "MemberNotFound",
    "NotSubjectOwner",
    "SubjectAccess",
    "SubjectArchived",
    "SubjectError",
    "SubjectNameConflict",
    "SubjectNotFound",
    "SubjectValidationError",
    "add_member",
    "archive_subject",
    "create_subject",
    "get_membership",
    "get_subject_access",
    "list_members",
    "list_subjects",
    "normalize_subject_name",
    "remove_member",
    "rename_subject",
    "require_owner",
    "unarchive_subject",
]
