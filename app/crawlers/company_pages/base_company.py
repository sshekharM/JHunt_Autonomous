"""
Base framework for direct company career page crawlers.
"""
from abc import ABC, abstractmethod
from app.crawlers.base import BaseCrawler, RawJob
import structlog

logger = structlog.get_logger("crawlers.company")


class BaseCompanyCrawler(BaseCrawler, ABC):
    """
    Base for crawling individual company career pages.
    Each company subclass overrides careers_url and _parse_jobs().
    """
    careers_url: str = ""
    company_name: str = ""

    async def search_jobs(self, context, keywords, location="India", page_num=1) -> list[RawJob]:
        page = await context.new_page()
        try:
            await page.goto(self.careers_url, wait_until="domcontentloaded", timeout=30000)
            from app.crawlers.anti_detection import human_delay, random_scroll
            await human_delay(self.portal_name)
            await random_scroll(page)
            content = await page.content()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "lxml")
            jobs = self._parse_jobs(soup, keywords)
            return jobs
        except Exception as exc:
            logger.error("company_crawler.search_error", company=self.company_name, error=str(exc))
            return []
        finally:
            await page.close()

    @abstractmethod
    def _parse_jobs(self, soup, keywords: list[str]) -> list[RawJob]:
        """Parse job listings from the careers page HTML."""
        ...

    async def login(self, context) -> bool:
        return True

    async def check_application_status(self, context, portal_application_id) -> str:
        return "applied"
