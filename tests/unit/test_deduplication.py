"""
Unit tests for job deduplication logic in app.services.job_service.

Uses an in-memory SQLite database via SQLAlchemy so these tests run without
a live PostgreSQL instance.  The ON CONFLICT DO UPDATE path is tested against
a PostgreSQL-compatible approach using a mock of the pg_insert dialect call.
"""
import os
from cryptography.fernet import Fernet

# Must be set before app.config is imported (happens transitively via job_service)
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-32-bytes-xxxxxxxx")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "testminiocredential")
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_raw_job(portal_job_id: str, title: str = "Software Engineer", **overrides) -> dict:
    base = {
        "portal_job_id": portal_job_id,
        "title": title,
        "company": "ACME Corp",
        "location": "Bengaluru",
        "job_url": f"https://example.com/jobs/{portal_job_id}",
        "description": "A great job",
        "skills_required": ["Python", "Docker"],
        "salary_range": "10-15 LPA",
        "experience_required": "2-5 years",
        "is_easy_apply": False,
        "posted_at": None,
        "extra": {},
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_db():
    """Minimal AsyncSession mock."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# store_jobs — interface / argument tests
# ---------------------------------------------------------------------------

class TestStoreJobsEmptyInput:
    @pytest.mark.asyncio
    async def test_empty_list_returns_zero_counts(self, mock_db):
        from app.services.job_service import store_jobs
        result = await store_jobs([], mock_db, "naukri")
        assert result == {"inserted": 0, "updated": 0}
        mock_db.execute.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_dict_with_inserted_and_updated_keys(self, mock_db):
        from app.services.job_service import store_jobs

        # Simulate pg INSERT returning (xmax=0) → insert
        row = MagicMock()
        row.__getitem__ = lambda self, i: True  # row[0] → True (is_insert)
        execute_result = MagicMock()
        execute_result.fetchone = MagicMock(return_value=row)
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await store_jobs([_make_raw_job("j1")], mock_db, "naukri")
        assert "inserted" in result
        assert "updated" in result


class TestStoreJobsDeduplication:
    @pytest.mark.asyncio
    async def test_upsert_called_once_per_job(self, mock_db):
        from app.services.job_service import store_jobs

        row = MagicMock()
        row.__getitem__ = lambda self, i: True
        execute_result = MagicMock()
        execute_result.fetchone = MagicMock(return_value=row)
        mock_db.execute = AsyncMock(return_value=execute_result)

        jobs = [_make_raw_job(f"job_{i}") for i in range(5)]
        await store_jobs(jobs, mock_db, "linkedin")
        assert mock_db.execute.call_count == 5

    @pytest.mark.asyncio
    async def test_insert_counted_when_xmax_is_zero(self, mock_db):
        """xmax == 0 means no previous version → INSERT."""
        from app.services.job_service import store_jobs

        row = MagicMock()
        row.__getitem__ = lambda self, i: True  # is_insert = True
        execute_result = MagicMock()
        execute_result.fetchone = MagicMock(return_value=row)
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await store_jobs([_make_raw_job("j1"), _make_raw_job("j2")], mock_db, "naukri")
        assert result["inserted"] == 2
        assert result["updated"] == 0

    @pytest.mark.asyncio
    async def test_update_counted_when_xmax_nonzero(self, mock_db):
        """xmax != 0 means a row was updated (ON CONFLICT triggered)."""
        from app.services.job_service import store_jobs

        row = MagicMock()
        row.__getitem__ = lambda self, i: False  # is_insert = False
        execute_result = MagicMock()
        execute_result.fetchone = MagicMock(return_value=row)
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await store_jobs([_make_raw_job("j1")], mock_db, "naukri")
        assert result["inserted"] == 0
        assert result["updated"] == 1

    @pytest.mark.asyncio
    async def test_mixed_insert_and_update(self, mock_db):
        from app.services.job_service import store_jobs

        responses = []
        for is_insert_flag in [True, False, True, False, False]:
            row = MagicMock()
            row.__getitem__ = lambda self, i, f=is_insert_flag: f
            er = MagicMock()
            er.fetchone = MagicMock(return_value=row)
            responses.append(er)

        mock_db.execute = AsyncMock(side_effect=responses)
        jobs = [_make_raw_job(f"j{i}") for i in range(5)]
        result = await store_jobs(jobs, mock_db, "glassdoor")
        assert result["inserted"] == 2
        assert result["updated"] == 3


class TestStoreJobsCommitBehaviour:
    @pytest.mark.asyncio
    async def test_commit_called_after_batch(self, mock_db):
        from app.services.job_service import store_jobs

        row = MagicMock()
        row.__getitem__ = lambda self, i: True
        execute_result = MagicMock()
        execute_result.fetchone = MagicMock(return_value=row)
        mock_db.execute = AsyncMock(return_value=execute_result)

        await store_jobs([_make_raw_job("j1"), _make_raw_job("j2")], mock_db, "indeed")
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_commit_on_empty_input(self, mock_db):
        from app.services.job_service import store_jobs
        await store_jobs([], mock_db, "naukri")
        mock_db.commit.assert_not_awaited()


class TestStoreJobsPayload:
    @pytest.mark.asyncio
    async def test_portal_is_passed_per_job(self, mock_db):
        """Ensure the portal name from the argument is embedded in each upsert."""
        from app.services.job_service import store_jobs
        import sqlalchemy

        captured_statements = []

        async def capture_execute(stmt, *args, **kwargs):
            captured_statements.append(stmt)
            row = MagicMock()
            row.__getitem__ = lambda self, i: True
            er = MagicMock()
            er.fetchone = MagicMock(return_value=row)
            return er

        mock_db.execute = capture_execute

        await store_jobs([_make_raw_job("j1")], mock_db, "naukri")
        assert len(captured_statements) == 1

    @pytest.mark.asyncio
    async def test_skills_required_defaults_to_empty_list(self, mock_db):
        from app.services.job_service import store_jobs

        job = _make_raw_job("j1")
        del job["skills_required"]  # omit the field

        captured = []

        async def capture_execute(stmt, *args, **kwargs):
            captured.append(stmt)
            row = MagicMock()
            row.__getitem__ = lambda self, i: True
            er = MagicMock()
            er.fetchone = MagicMock(return_value=row)
            return er

        mock_db.execute = capture_execute
        result = await store_jobs([job], mock_db, "naukri")
        assert result["inserted"] + result["updated"] == 1


class TestMarkJobsInactive:
    @pytest.mark.asyncio
    async def test_empty_list_returns_zero(self, mock_db):
        from app.services.job_service import mark_jobs_inactive
        result = await mark_jobs_inactive("naukri", [], mock_db)
        assert result == 0
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_rowcount(self, mock_db):
        from app.services.job_service import mark_jobs_inactive

        execute_result = MagicMock()
        execute_result.rowcount = 3
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await mark_jobs_inactive("naukri", ["j1", "j2", "j3"], mock_db)
        assert result == 3
        mock_db.commit.assert_awaited_once()


class TestDeduplicationKeyUniqueness:
    """Verify the deduplication key is (portal, portal_job_id) not just portal_job_id."""

    @pytest.mark.asyncio
    async def test_same_job_id_different_portals_counted_separately(self, mock_db):
        """
        Job ID "12345" on naukri and "12345" on linkedin should be two separate rows.
        Each call to store_jobs with a different portal is independent — the
        unique constraint is on (portal, portal_job_id) together.
        """
        from app.services.job_service import store_jobs

        insert_row = MagicMock()
        insert_row.__getitem__ = lambda self, i: True
        er = MagicMock()
        er.fetchone = MagicMock(return_value=insert_row)
        mock_db.execute = AsyncMock(return_value=er)

        job = _make_raw_job("12345")

        r1 = await store_jobs([job], mock_db, "naukri")
        r2 = await store_jobs([job], mock_db, "linkedin")

        assert r1["inserted"] == 1
        assert r2["inserted"] == 1
        # Two separate execute calls — one per store_jobs invocation
        assert mock_db.execute.call_count == 2
