"""Backend-proxied serving of locally stored objects.

Only used by the local storage provider (development/tests). R2 downloads use
provider presigned URLs and never reach this route. Access requires a valid
HMAC signature and a non-expired timestamp.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.storage import get_storage
from app.storage.base import ObjectNotFound, StorageProvider
from app.storage.local import LocalStorageProvider

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/local/{key:path}")
def serve_local_object(
    key: str,
    expires: int,
    sig: str,
    storage: StorageProvider = Depends(get_storage),
) -> FileResponse:
    if not isinstance(storage, LocalStorageProvider):
        raise HTTPException(status_code=404, detail="Not found.")
    if not storage.verify_download(key, expires, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired link.")
    try:
        path = storage.path_for(key)
    except ObjectNotFound as exc:
        raise HTTPException(status_code=404, detail="Not found.") from exc
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)
