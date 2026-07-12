import structlog
from app.llm import router as llm_router
from app.llm.cover_letter_prompt import build_cover_letter_prompt

logger = structlog.get_logger("services.cover_letter")


async def generate_cover_letter(
    user_profile: dict,
    job: dict,
    matched_skills: list[str],
    user_llm_choice: str,
) -> str:
    """Generate a cover letter for the given job; return plain text."""
    system_prompt, user_prompt = build_cover_letter_prompt(
        user_name=user_profile.get("name", "Candidate"),
        job_title=job.get("title", ""),
        company_name=job.get("company", ""),
        job_description=job.get("description", ""),
        matched_skills=matched_skills,
        years_experience=user_profile.get("years_exp", 0),
    )
    text = await llm_router.generate(user_prompt, user_llm_choice, system_prompt=system_prompt)
    logger.info(
        "cover_letter.generated",
        job_title=job.get("title"),
        company=job.get("company"),
        backend=user_llm_choice,
        chars=len(text),
    )
    return text.strip()
