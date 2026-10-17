"""Cloudflare R2 storage provider (S3-compatible) via boto3.

Credentials are read from settings; they are never logged or returned to the
client. Download access is granted only through short-lived presigned URLs.
"""

from __future__ import annotations

from typing import Any

from app.storage.base import ObjectInfo, ObjectNotFound, ObjectTooLarge, SignedUrl


class R2StorageProvider:
    name = "r2"

    def __init__(
        self,
        *,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        endpoint_url: str,
    ) -> None:
        import boto3  # imported lazily so the local provider needs no SDK

        self._bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    def put_object(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, **extra)

    def get_object(self, key: str, max_bytes: int) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.NoSuchKey as exc:  # type: ignore[attr-defined]
            raise ObjectNotFound(f"Object not found: {key}") from exc
        body = response["Body"].read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ObjectTooLarge(f"Object exceeds {max_bytes} bytes.")
        return body

    def head_object(self, key: str) -> ObjectInfo | None:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception:  # noqa: BLE001 - provider-specific 404 handling
            return None
        return ObjectInfo(
            key=key,
            size_bytes=int(response.get("ContentLength", 0)),
            content_type=response.get("ContentType"),
        )

    def delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def create_download_url(self, key: str, *, expires_in: int) -> SignedUrl:
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=int(expires_in),
        )
        return SignedUrl(url=url, expires_in=int(expires_in), method="GET")


__all__ = ["R2StorageProvider"]
