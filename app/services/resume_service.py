"""
Resume service: parse → tailor via LLM → render PDF → store in MinIO.
"""
import io
import json
import uuid
from datetime import datetime, timezone

import pdfplumber
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
# WeasyPrint requires GTK libraries. On Linux (including Docker Linux containers
# running on Windows Server) the required libraries are installed via apt in
# Dockerfile. Do NOT run WeasyPrint on a bare Windows host — use Docker.
from weasyprint import HTML

from app.config import settings
from app.llm import router as llm_router
from app.llm.resume_prompt import build_resume_tailoring_prompt
from app.services.storage_service import download_resume, upload_resume
from app.tenant_models.resume import TailoredResume

logger = structlog.get_logger("services.resume")

# ---------------------------------------------------------------------------
# Inline HTML template — clean, ATS-friendly IT resume layout
# ---------------------------------------------------------------------------
_RESUME_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: "DejaVu Sans", Arial, sans-serif; font-size: 11px;
         color: #1a1a1a; padding: 24px 32px; }}
  h1 {{ font-size: 20px; font-weight: 700; letter-spacing: 0.5px; }}
  h2 {{ font-size: 13px; font-weight: 700; text-transform: uppercase;
       letter-spacing: 0.8px; border-bottom: 1px solid #333;
       padding-bottom: 3px; margin: 14px 0 6px; }}
  h3 {{ font-size: 11px; font-weight: 700; }}
  p, li {{ line-height: 1.5; }}
  ul {{ padding-left: 16px; }}
  .summary {{ font-style: italic; margin-bottom: 6px; }}
  .job-header {{ display: flex; justify-content: space-between; }}
  .dates {{ color: #555; font-size: 10px; }}
  .skills-list {{ display: flex; flex-wrap: wrap; gap: 4px; }}
  .skill-tag {{ background: #eef; border: 1px solid #99b; border-radius: 3px;
               padding: 1px 6px; font-size: 10px; }}
</style>
</head>
<body>
  <h1>{name}</h1>

  <h2>Professional Summary</h2>
  <p class="summary">{summary}</p>

  <h2>Skills</h2>
  <div class="skills-list">
    {skills_html}
  </div>

  <h2>Experience</h2>
  {experience_html}

  <h2>Education</h2>
  {education_html}

  {certifications_section}
</body>
</html>"""


def _render_html(resume_data: dict) -> str:
    name = resume_data.get("name", "Candidate")
    summary = resume_data.get("summary", "")

    skills_html = "".join(
        f'<span class="skill-tag">{s}</span>'
        for s in resume_data.get("skills", [])
    )

    exp_parts = []
    for exp in resume_data.get("experience", []):
        bullets = "".join(f"<li>{b}</li>" for b in exp.get("bullets", []))
        exp_parts.append(
            f'<div style="margin-bottom:8px;">'
            f'<div class="job-header">'
            f'<h3>{exp.get("title", "")} — {exp.get("company", "")}</h3>'
            f'<span class="dates">{exp.get("start_date", "")} – {exp.get("end_date", "Present")}</span>'
            f'</div><ul>{bullets}</ul></div>'
        )
    experience_html = "".join(exp_parts) or "<p>—</p>"

    edu_parts = []
    for edu in resume_data.get("education", []):
        edu_parts.append(
            f'<p><strong>{edu.get("degree", "")}</strong>, '
            f'{edu.get("institution", "")} ({edu.get("year", "")})</p>'
        )
    education_html = "".join(edu_parts) or "<p>—</p>"

    certs = resume_data.get("certifications", [])
    if certs:
        cert_items = "".join(f"<li>{c}</li>" for c in certs)
        certifications_section = f"<h2>Certifications</h2><ul>{cert_items}</ul>"
    else:
        certifications_section = ""

    return _RESUME_HTML_TEMPLATE.format(
        name=name,
        summary=summary,
        skills_html=skills_html,
        experience_html=experience_html,
        education_html=education_html,
        certifications_section=certifications_section,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def parse_master_resume(minio_key: str) -> str:
    """Download PDF from MinIO and extract all text with pdfplumber."""
    pdf_bytes = await download_resume(minio_key)
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    text = "\n".join(pages)
    logger.info("resume.parsed", minio_key=minio_key, chars=len(text))
    return text


async def generate_tailored_resume(
    master_text: str,
    job: dict,
    user_skills: list[str],
    user_llm_choice: str,
) -> dict:
    """Use LLM to tailor the resume; return parsed JSON dict."""
    system_prompt, user_prompt = build_resume_tailoring_prompt(
        master_resume_text=master_text,
        job_title=job.get("title", ""),
        job_description=job.get("description", ""),
        required_skills=job.get("skills_required", []),
        user_skills=user_skills,
    )
    raw = await llm_router.generate(user_prompt, user_llm_choice, system_prompt=system_prompt)

    # Strip accidental markdown fences before parsing
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]

    resume_data = json.loads(cleaned)
    logger.info(
        "resume.tailored",
        job_title=job.get("title"),
        backend=user_llm_choice,
        sections=list(resume_data.keys()),
    )
    return resume_data


async def render_tailored_pdf(
    resume_data: dict,
    schema_name: str,
    job_id: str,
) -> str:
    """Render resume_data to PDF via WeasyPrint, upload to MinIO, return MinIO key."""
    html_str = _render_html(resume_data)
    pdf_bytes = HTML(string=html_str).write_pdf()

    filename = f"tailored_{job_id}_{uuid.uuid4().hex[:8]}.pdf"
    key = await upload_resume(schema_name, pdf_bytes, filename)
    logger.info("resume.pdf_rendered", key=key, size_bytes=len(pdf_bytes))
    return key


async def store_tailored_resume(
    user_id: str,
    job_id: str,
    pdf_minio_key: str,
    llm_choice: str,
    tenant_db: AsyncSession,
) -> str:
    """Persist TailoredResume record; return record id."""
    record = TailoredResume(
        job_id=job_id,
        minio_key=pdf_minio_key,
        llm_choice_used=llm_choice,
    )
    tenant_db.add(record)
    await tenant_db.commit()
    await tenant_db.refresh(record)
    logger.info("resume.stored", record_id=record.id, user_id=user_id)
    return record.id
