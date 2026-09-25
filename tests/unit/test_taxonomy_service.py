"""
Characterization tests for app.services.taxonomy_service.

No real DB — every AsyncSession is a fake. Each test resets the module-level
skill cache so tests cannot leak state into each other.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.skill_taxonomy import TaxonomySource, TaxonomyStatus
from app.services import taxonomy_service


@pytest.fixture(autouse=True)
def _reset_cache():
    taxonomy_service.invalidate_cache()
    yield
    taxonomy_service.invalidate_cache()


def _db_with_rows(rows):
    db = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


# ---------------------------------------------------------------------------
# get_all_active_skills
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_all_active_skills_uses_cache_when_present():
    taxonomy_service._skill_cache = ["Python"]
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=AssertionError("should not query DB"))

    skills = await taxonomy_service.get_all_active_skills(db, use_cache=True)

    assert skills == ["Python"]


@pytest.mark.asyncio
async def test_get_all_active_skills_defaults_to_using_cache():
    """use_cache defaults to True; pin the default so a mutant flipping it
    to False (which would force a DB query here) is caught."""
    taxonomy_service._skill_cache = ["Python"]
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=AssertionError("should not query DB"))

    skills = await taxonomy_service.get_all_active_skills(db)

    assert skills == ["Python"]


@pytest.mark.asyncio
async def test_get_all_active_skills_bypasses_cache_when_disabled():
    taxonomy_service._skill_cache = ["Stale"]
    db = _db_with_rows([("Python",), ("SQL",)])

    skills = await taxonomy_service.get_all_active_skills(db, use_cache=False)

    assert skills == ["Python", "SQL"]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_all_active_skills_seeds_when_table_empty():
    db = _db_with_rows([])

    with patch(
        "app.services.taxonomy_service.seed_from_file", new=AsyncMock(return_value=["Java"])
    ) as mock_seed:
        skills = await taxonomy_service.get_all_active_skills(db, use_cache=False)

    mock_seed.assert_awaited_once_with(db)
    assert skills == ["Java"]
    assert taxonomy_service._skill_cache == ["Java"]


def test_invalidate_cache_clears_module_state():
    taxonomy_service._skill_cache = ["Python"]
    taxonomy_service.invalidate_cache()
    assert taxonomy_service._skill_cache is None


# ---------------------------------------------------------------------------
# seed_from_file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_from_file_returns_empty_when_file_missing():
    with patch("app.services.taxonomy_service._SEED_FILE") as mock_path:
        mock_path.exists.return_value = False
        result = await taxonomy_service.seed_from_file(AsyncMock())
    assert result == []


def _seed_db():
    db = AsyncMock()

    async def fake_execute(_stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        return result

    db.execute = AsyncMock(side_effect=fake_execute)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_seed_from_file_inserts_all_new_skills(tmp_path):
    seed_file = tmp_path / "it_skills.json"
    seed_file.write_text(json.dumps([
        {"skill_name": "Python", "category": "Languages", "source": "manual"},
        {"skill_name": "  ", "category": "Languages", "source": "manual"},
        {"skill_name": "SQL", "category": "Languages", "source": "manual"},
    ]))
    db = _seed_db()

    with patch("app.services.taxonomy_service._SEED_FILE", seed_file), patch(
        "app.services.taxonomy_service.audit"
    ) as mock_audit:
        added = await taxonomy_service.seed_from_file(db)

    assert added == ["Python", "SQL"]
    assert db.add.call_count == 2
    db.commit.assert_awaited_once()
    mock_audit.assert_called_once_with("taxonomy.seeded", details={"count": 2})


@pytest.mark.asyncio
async def test_seed_from_file_skips_insert_for_existing_skill(tmp_path):
    seed_file = tmp_path / "it_skills.json"
    seed_file.write_text(json.dumps([{"skill_name": "Python", "category": "Languages"}]))

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = MagicMock()  # already exists
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()

    with patch("app.services.taxonomy_service._SEED_FILE", seed_file), patch(
        "app.services.taxonomy_service.audit"
    ):
        added = await taxonomy_service.seed_from_file(db)

    assert added == ["Python"]
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# lookup_skill
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lookup_skill_is_case_insensitive():
    found = MagicMock()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = found
    db.execute = AsyncMock(return_value=result)

    row = await taxonomy_service.lookup_skill("PYTHON", db)

    assert row is found
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_lookup_skill_returns_none_when_absent():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    row = await taxonomy_service.lookup_skill("Nonexistent", db)

    assert row is None


# ---------------------------------------------------------------------------
# add_skill
# ---------------------------------------------------------------------------

async def _run_add_skill():
    taxonomy_service._skill_cache = ["stale"]
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    with patch("app.services.taxonomy_service.audit") as mock_audit:
        row = await taxonomy_service.add_skill(
            "Kubernetes", "DevOps", TaxonomySource.dynamic_discovery, db,
            status=TaxonomyStatus.pending_review,
        )
    return db, mock_audit, row


@pytest.mark.asyncio
async def test_add_skill_persists_and_invalidates_cache():
    db, _, row = await _run_add_skill()
    db.add.assert_called_once_with(row)
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(row)
    assert taxonomy_service._skill_cache is None
    assert row.skill_name == "Kubernetes"
    assert row.category == "DevOps"
    assert row.status == TaxonomyStatus.pending_review


@pytest.mark.asyncio
async def test_add_skill_audits_with_expected_details():
    _, mock_audit, _ = await _run_add_skill()
    mock_audit.assert_called_once_with(
        "taxonomy.skill_added",
        details={
            "skill": "Kubernetes",
            "source": TaxonomySource.dynamic_discovery,
            "status": TaxonomyStatus.pending_review,
        },
    )


# ---------------------------------------------------------------------------
# get_skills_by_category / get_keyword_sets_for_crawling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_skills_by_category_returns_matching_rows():
    rows = [MagicMock(), MagicMock()]
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=result)

    found = await taxonomy_service.get_skills_by_category("Languages", db)

    assert found == rows


@pytest.mark.asyncio
async def test_get_keyword_sets_for_crawling_groups_by_category():
    db = _db_with_rows([
        ("Languages", "Python"),
        ("Languages", "SQL"),
        ("DevOps", "Docker"),
    ])

    buckets = await taxonomy_service.get_keyword_sets_for_crawling(db)

    assert buckets == {
        "Languages": ["Python", "SQL"],
        "DevOps": ["Docker"],
    }
