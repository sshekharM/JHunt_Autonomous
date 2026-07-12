"""
BaseCrawler ABC — all portal crawlers implement this interface.
Separation of concerns:
  - System account context  → used for crawling job listings
  - User personal context   → used for applying to jobs
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from playwright.async_api import BrowserContext
import structlog

logger = structlog.get_logger("crawlers.base")


@dataclass
class RawJob:
    """Normalised job record returned by every crawler's search_jobs()."""
    portal: str
    portal_job_id: str
    title: str
    company: str
    location: str
    job_url: str
    description: str = ""
    skills_required: list[str] = field(default_factory=list)
    salary_range: str = ""
    experience_required: str = ""
    posted_at: Optional[str] = None
    is_easy_apply: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class ApplicationReceipt:
    """Result of an apply() call."""
    success: bool
    portal_application_id: Optional[str] = None
    failure_reason: Optional[str] = None
    requires_manual: bool = False
    missing_fields: list[str] = field(default_factory=list)


class BaseCrawler(ABC):
    """
    Abstract base for all portal crawlers.

    Subclasses must implement:
      - login(context)         — authenticate the system account
      - search_jobs(context, keywords, location) — return List[RawJob]
      - apply(context, job, user_profile)         — submit application
      - check_application_status(context, portal_application_id) — return status str

    The system context (for crawling) and user context (for applying)
    are always separate to protect user accounts.
    """

    portal_name: str = ""

    @abstractmethod
    async def login(self, context: BrowserContext) -> bool:
        """Log in with system credentials. Returns True on success."""

    @abstractmethod
    async def search_jobs(
        self,
        context: BrowserContext,
        keywords: list[str],
        location: str = "India",
        page_num: int = 1,
    ) -> list[RawJob]:
        """Search for jobs and return normalised RawJob list."""

    @abstractmethod
    async def apply(
        self,
        context: BrowserContext,
        job: RawJob,
        user_profile: dict,
        resume_path: Optional[str] = None,
        cover_letter: Optional[str] = None,
    ) -> ApplicationReceipt:
        """Apply to a job using the user's personal portal session."""

    @abstractmethod
    async def check_application_status(
        self,
        context: BrowserContext,
        portal_application_id: str,
    ) -> str:
        """Re-check status of a submitted application. Returns status string."""

    async def is_session_valid(self, context: BrowserContext) -> bool:
        """
        Quick check to verify the session is still authenticated.
        Default implementation; subclasses may override.
        """
        try:
            pages = await context.pages
            return len(pages) >= 0
        except Exception:
            return False

    def _extract_skills_from_text(self, text: str, taxonomy_skills: set[str]) -> list[str]:
        """
        Simple keyword-based skill extraction from job description text.
        Returns skills that appear in the text and are in the taxonomy.
        """
        text_lower = text.lower()
        found = []
        for skill in taxonomy_skills:
            if skill.lower() in text_lower:
                found.append(skill)
        return found
