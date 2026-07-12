"""
Human-readable skill gap explanations for the dashboard.
"""


def format_explanation(match_result: dict) -> str:
    """
    Returns a short sentence explaining the match score.
    Example: "73% match — you have 8 of 11 required skills. Missing: Kubernetes, Terraform."
    """
    score_pct = round(match_result["score"] * 100, 1)
    matched = match_result.get("matched", [])
    missing = match_result.get("missing", [])
    total = len(matched) + len(missing)

    parts = [f"{score_pct}% match"]
    if total > 0:
        parts.append(f"you have {len(matched)} of {total} required skills")
    if missing:
        shown = missing[:5]
        extra = len(missing) - 5
        missing_str = ", ".join(shown)
        if extra > 0:
            missing_str += f" and {extra} more"
        parts.append(f"Missing: {missing_str}")

    return " — ".join(parts) + "."


def dashboard_explainability(match_result: dict) -> dict:
    """
    Structured explainability payload for the frontend.
    """
    return {
        "score": match_result["score"],
        "score_pct": round(match_result["score"] * 100, 1),
        "matched_skills": match_result.get("matched", []),
        "missing_skills": match_result.get("missing", []),
        "coverage_pct": match_result.get("coverage_pct", 0.0),
        "summary": format_explanation(match_result),
    }
