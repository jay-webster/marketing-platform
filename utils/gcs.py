import asyncio
import io
import logging

from fastapi import UploadFile

logger = logging.getLogger(__name__)

_gcs_client = None


def _get_client():
    global _gcs_client
    if _gcs_client is None:
        from google.cloud import storage  # noqa: PLC0415
        _gcs_client = storage.Client()
    return _gcs_client


def _gcs_object_name(batch_id: str, doc_id: str, filename: str) -> str:
    return f"batches/{batch_id}/{doc_id}/{filename}"


async def upload_to_gcs(
    file: UploadFile,
    bucket_name: str,
    batch_id: str,
    doc_id: str,
) -> str:
    """Stream UploadFile directly to GCS. Returns the object name. No local disk write."""
    object_name = _gcs_object_name(batch_id, doc_id, file.filename or "file")

    def _upload() -> str:
        client = _get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        file.file.seek(0)
        blob.upload_from_file(
            file.file,
            content_type=file.content_type or "application/octet-stream",
        )
        return object_name

    return await asyncio.to_thread(_upload)


async def download_stream_from_gcs(bucket_name: str, object_name: str) -> io.BytesIO:
    """Download a GCS object to an in-memory BytesIO stream."""
    def _download() -> io.BytesIO:
        client = _get_client()
        blob = client.bucket(bucket_name).blob(object_name)
        buf = io.BytesIO()
        blob.download_to_file(buf)
        buf.seek(0)
        return buf

    return await asyncio.to_thread(_download)


async def delete_from_gcs(bucket_name: str, object_name: str) -> None:
    """Delete a GCS object. Idempotent — silences NotFound."""
    def _delete() -> None:
        try:
            client = _get_client()
            client.bucket(bucket_name).blob(object_name).delete()
        except Exception as exc:
            # Import here to avoid hard dependency at module load
            try:
                from google.api_core.exceptions import NotFound  # noqa: PLC0415
                if isinstance(exc, NotFound):
                    return
            except ImportError:
                pass
            logger.warning("GCS delete failed for %s: %s", object_name, exc)

    await asyncio.to_thread(_delete)
