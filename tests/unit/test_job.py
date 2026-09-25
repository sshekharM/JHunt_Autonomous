"""Shared Job model matches the shared migrations (JSONB columns, query indexes)."""
from sqlalchemy.dialects.postgresql import JSONB

from app.models.job import Job

COLS = Job.__table__.columns


def test_job_json_columns_are_jsonb():
    assert isinstance(COLS["skills_required"].type, JSONB)
    assert isinstance(COLS["extra"].type, JSONB)


def test_job_query_columns_are_indexed():
    assert COLS["is_active"].index is True
    assert COLS["crawled_at"].index is True
