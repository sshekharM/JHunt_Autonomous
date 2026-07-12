def build_resume_tailoring_prompt(
    master_resume_text: str,
    job_title: str,
    job_description: str,
    required_skills: list[str],
    user_skills: list[str],
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for resume tailoring."""
    system_prompt = (
        "You are an expert resume writer with deep knowledge of the Indian IT job market. "
        "You tailor resumes to maximise ATS keyword match and recruiter impact. "
        "You NEVER fabricate experience, qualifications, or skills — every statement must "
        "be grounded in what the candidate has already provided. "
        "Output only valid JSON — no markdown fences, no prose outside the JSON."
    )

    matched_skills = sorted(set(required_skills) & set(user_skills))
    missing_skills = sorted(set(required_skills) - set(user_skills))

    user_prompt = f"""Tailor the following resume for the role: {job_title}

=== JOB DESCRIPTION ===
{job_description}

=== REQUIRED SKILLS ===
{', '.join(required_skills) if required_skills else 'Not specified'}

=== CANDIDATE'S EXISTING SKILLS ===
{', '.join(user_skills) if user_skills else 'Not specified'}

=== MATCHED SKILLS (highlight these prominently) ===
{', '.join(matched_skills) if matched_skills else 'None'}

=== SKILLS GAP (do NOT invent these — omit or mention honestly if relevant) ===
{', '.join(missing_skills) if missing_skills else 'None'}

=== MASTER RESUME TEXT ===
{master_resume_text}

Instructions:
1. Rewrite the professional summary to target the role and highlight matched skills.
2. Reorder bullet points in experience sections to lead with role-relevant achievements.
3. Place matched skills at the top of the skills section.
4. Keep all dates, titles, company names, and facts exactly as in the source.
5. Do not add any skill, certification, or experience the candidate does not have.
6. Output a single JSON object with this exact structure:
{{
  "summary": "<professional summary string>",
  "skills": ["skill1", "skill2", ...],
  "experience": [
    {{
      "company": "...",
      "title": "...",
      "start_date": "...",
      "end_date": "...",
      "bullets": ["...", "..."]
    }}
  ],
  "education": [
    {{
      "institution": "...",
      "degree": "...",
      "year": "..."
    }}
  ],
  "certifications": ["cert1", "cert2"]
}}"""

    return system_prompt, user_prompt
