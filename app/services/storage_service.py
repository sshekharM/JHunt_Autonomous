from minio import Minio
from minio.error import S3Error
from app.config import settings
import uuid

_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def _ensure_bucket() -> None:
    if not _client.bucket_exists(settings.minio_bucket_resumes):
        _client.make_bucket(settings.minio_bucket_resumes)


async def upload_resume(schema_name: str, content: bytes, filename: str) -> str:
    """Upload resume PDF to MinIO; return object key."""
    _ensure_bucket()
    import io
    key = f"{schema_name}/{uuid.uuid4()}/{filename}"
    _client.put_object(
        settings.minio_bucket_resumes,
        key,
        io.BytesIO(content),
        length=len(content),
        content_type="application/pdf",
    )
    return key


async def download_resume(key: str) -> bytes:
    response = _client.get_object(settings.minio_bucket_resumes, key)
    return response.read()


async def delete_object(key: str) -> None:
    try:
        _client.remove_object(settings.minio_bucket_resumes, key)
    except S3Error:
        pass
