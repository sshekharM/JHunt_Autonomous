"""delete_object: a missing object is already gone (fine); any other storage
error must surface, or callers would record a resume as purged while it remains."""
from unittest.mock import MagicMock, patch

import pytest
from minio.error import S3Error

from app.services import storage_service


def _s3_error(code: str) -> S3Error:
    return S3Error(code, "msg", "/r", "req", "host", MagicMock())


@pytest.mark.asyncio
async def test_delete_object_removes_from_resume_bucket():
    with patch.object(storage_service, "_client") as client:
        await storage_service.delete_object("u_x/1/cv.pdf")
    client.remove_object.assert_called_once_with(storage_service.settings.minio_bucket_resumes, "u_x/1/cv.pdf")


@pytest.mark.asyncio
async def test_delete_object_ignores_missing_object():
    with patch.object(storage_service, "_client") as client:
        client.remove_object.side_effect = _s3_error("NoSuchKey")
        await storage_service.delete_object("gone.pdf")


@pytest.mark.asyncio
async def test_delete_object_raises_other_storage_errors():
    with patch.object(storage_service, "_client") as client:
        client.remove_object.side_effect = _s3_error("AccessDenied")
        with pytest.raises(S3Error):
            await storage_service.delete_object("u_x/1/cv.pdf")
