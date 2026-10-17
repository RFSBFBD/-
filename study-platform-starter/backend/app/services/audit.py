"""Audit event recording. Bounded metadata only; never store secrets."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent

MAX_METADATA_KEYS = 20


def record_event(
    db: Session,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user_id,
        action=action,
        subject_id=subject_id,
        metadata_json=_bounded(metadata),
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def _bounded(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    keys = list(metadata)[:MAX_METADATA_KEYS]
    return {key: metadata[key] for key in keys}


__all__ = ["record_event"]
