"""
Unit tests for resume_service.
All external I/O (MinIO, LLM, Playwright) is mocked.
"""
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# parse_master_resume
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_master_resume_returns_text():
    """parse_master_resume should extract text from downloaded PDF bytes."""
    sample_text = "John Doe\nSenior Python Developer\n5 years experience"

    # Build a minimal in-memory PDF via pdfplumber's Page mock
    fake_page = MagicMock()
    fake_page.extract_text.return_value = sample_text
    fake_pdf = MagicMock()
    fake_pdf.__enter__ = MagicMock(return_value=fake_pdf)
    fake_pdf.__exit__ = MagicMock(return_value=False)
    fake_pdf.pages = [fake_page]

    with (
        patch("app.services.resume_service.download_resume", new=AsyncMock(return_value=b"%PDF-fake")),
        patch("app.services.resume_service.pdfplumber.open", return_value=fake_pdf),
    ):
        from app.services.resume_service import parse_master_resume
        result = await parse_master_resume("user_abc/resume.pdf")

    assert sample_text in result


@pytest.mark.asyncio
async def test_parse_master_resume_multi_page():
    """Text from multiple pages should be joined."""
    pages = ["Page one content", "Page two content"]

    fake_pages = [MagicMock() for _ in pages]
    for fp, text in zip(fake_pages, pages):
        fp.extract_text.return_value = text

    fake_pdf = MagicMock()
    fake_pdf.__enter__ = MagicMock(return_value=fake_pdf)
    fake_pdf.__exit__ = MagicMock(return_value=False)
    fake_pdf.pages = fake_pages

    with (
        patch("app.services.resume_service.download_resume", new=AsyncMock(return_value=b"%PDF")),
        patch("app.services.resume_service.pdfplumber.open", return_value=fake_pdf),
    ):
        from app.services.resume_service import parse_master_resume
        result = await parse_master_resume("key")

    assert "Page one content" in result
    assert "Page two content" in result


# ---------------------------------------------------------------------------
# generate_tailored_resume
# ---------------------------------------------------------------------------

_SAMPLE_LLM_JSON = {
    "summary": "Experienced Python developer.",
    "skills": ["Python", "FastAPI", "PostgreSQL"],
    "experience": [
        {
            "company": "Acme Corp",
            "title": "Backend Engineer",
            "start_date": "Jan 2020",
            "end_date": "Present",
            "bullets": ["Built REST APIs", "Led migration to FastAPI"],
        }
    ],
    "education": [{"institution": "IIT Delhi", "degree": "B.Tech CS", "year": "2019"}],
    "certifications": ["AWS Certified Developer"],
}


@pytest.mark.asyncio
async def test_generate_tailored_resume_parses_json():
    """generate_tailored_resume should parse valid LLM JSON response."""
    with patch(
        "app.services.resume_service.llm_router.generate",
        new=AsyncMock(return_value=json.dumps(_SAMPLE_LLM_JSON)),
    ):
        from app.services.resume_service import generate_tailored_resume
        result = await generate_tailored_resume(
            master_text="John Doe Python developer ...",
            job={"title": "Backend Dev", "description": "Python FastAPI", "skills_required": ["Python"]},
            user_skills=["Python", "FastAPI"],
            user_llm_choice="ollama",
        )

    assert result["summary"] == _SAMPLE_LLM_JSON["summary"]
    assert "Python" in result["skills"]
    assert len(result["experience"]) == 1


@pytest.mark.asyncio
async def test_generate_tailored_resume_strips_markdown_fences():
    """LLM responses wrapped in ```json ... ``` should still parse correctly."""
    wrapped = f"```json\n{json.dumps(_SAMPLE_LLM_JSON)}\n```"
    with patch(
        "app.services.resume_service.llm_router.generate",
        new=AsyncMock(return_value=wrapped),
    ):
        from app.services.resume_service import generate_tailored_resume
        result = await generate_tailored_resume(
            master_text="resume text",
            job={"title": "Dev", "description": "desc", "skills_required": []},
            user_skills=[],
            user_llm_choice="anthropic",
        )

    assert "summary" in result


# ---------------------------------------------------------------------------
# render_tailored_pdf
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_tailored_pdf_returns_minio_key():
    """render_tailored_pdf should render via Playwright and upload to MinIO."""
    fake_pdf_bytes = b"%PDF-1.4 fake content"

    # Mock the Playwright async context manager chain
    mock_page = AsyncMock()
    mock_page.pdf = AsyncMock(return_value=fake_pdf_bytes)
    mock_page.set_content = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw = AsyncMock()
    mock_pw.chromium = mock_chromium
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=False)

    captured_upload = {}

    async def fake_upload(schema_name, content, filename):
        captured_upload["schema_name"] = schema_name
        captured_upload["content"] = content
        return f"{schema_name}/tailored_{filename}"

    with (
        patch("app.services.resume_service.async_playwright", return_value=mock_pw),
        patch("app.services.resume_service.upload_resume", new=fake_upload),
    ):
        from app.services.resume_service import render_tailored_pdf
        key = await render_tailored_pdf(
            resume_data={**_SAMPLE_LLM_JSON, "name": "Jane Doe"},
            schema_name="user_schema_1",
            job_id="job-xyz",
        )

    assert key.startswith("user_schema_1/")
    assert captured_upload["content"] == fake_pdf_bytes
    mock_page.pdf.assert_called_once()
