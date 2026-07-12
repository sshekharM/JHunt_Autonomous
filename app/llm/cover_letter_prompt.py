def build_cover_letter_prompt(
    user_name: str,
    job_title: str,
    company_name: str,
    job_description: str,
    matched_skills: list[str],
    years_experience: int,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for cover letter generation."""
    system_prompt = (
        "You are a professional cover letter writer for the Indian IT job market. "
        "Write concise, confident, and authentic cover letters. "
        "Output only the cover letter text — no subject line, no JSON, no extra commentary."
    )

    skills_str = ", ".join(matched_skills) if matched_skills else "relevant technical skills"

    user_prompt = f"""Write a professional cover letter for the following application.

Candidate: {user_name}
Years of experience: {years_experience}
Applying for: {job_title} at {company_name}

Matched skills to highlight: {skills_str}

Job description excerpt:
{job_description[:1500]}

Requirements:
- Maximum 3 paragraphs
- Paragraph 1: Express genuine interest in the role and company; mention the job title explicitly.
- Paragraph 2: Highlight 2-3 matched skills with brief, concrete evidence from the candidate's background.
- Paragraph 3: Close confidently; invite next steps.
- Tone: professional but warm; avoid clichés like "I am writing to apply".
- Do not invent specific project names, metrics, or achievements not given above.
- Plain text only — no markdown, no bullet points."""

    return system_prompt, user_prompt
