"""
Glassdoor crawler — Playwright-based.
Glassdoor heavily relies on JS rendering and has login walls for full job details.
"""
import re
from typing import Optional
from playwright.async_api import BrowserContext
from app.crawlers.base import BaseCrawler, RawJob, ApplicationReceipt
from app.crawlers.anti_detection import human_delay, human_type, random_scroll, micro_delay
from app.crawlers.session_manager import save_session_cookies
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("crawlers.glassdoor")

GD_BASE = "https://www.glassdoor.co.in"


class GlassdoorCrawler(BaseCrawler):
    portal_name = "glassdoor"

    async def login(self, context: BrowserContext) -> bool:
        from app.config import settings

        page = await context.new_page()
        try:
            await page.goto(f"{GD_BASE}/profile/login_input.htm", wait_until="domcontentloaded")
            await human_delay("glassdoor")

            await human_type(page, "input[name='username'], input[type='email']", settings.glassdoor_system_email)
            await human_type(page, "input[name='password'], input[type='password']", settings.glassdoor_system_password)
            await micro_delay()
            await page.click("button[type='submit'], button.email-login-button")
            await page.wait_for_load_state("networkidle", timeout=20000)

            if "profile" in page.url or "glassdoor.co.in" in page.url and "login" not in page.url:
                await save_session_cookies("glassdoor", context)
                audit("crawler.login_success", details={"portal": "glassdoor"})
                await page.close()
                return True

            logger.warning("glassdoor.login_failed", url=page.url)
            await page.close()
            return False

        except Exception as exc:
            logger.error("glassdoor.login_error", error=str(exc))
            await page.close()
            return False

    async def search_jobs(
        self,
        context: BrowserContext,
        keywords: list[str],
        location: str = "India",
        page_num: int = 1,
    ) -> list[RawJob]:
        keyword_str = " ".join(keywords)
        page = await context.new_page()
        try:
            url = (
                f"{GD_BASE}/Job/jobs.htm"
                f"?sc.keyword={keyword_str.replace(' ', '+')}"
                f"&locT=N&locId=115&jobType=fulltime"
                f"&p={page_num}"
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await human_delay("glassdoor")
            await random_scroll(page)

            jobs = []
            cards = await page.query_selector_all("li.react-job-listing, div[data-test='jobListing']")

            for card in cards[:20]:
                try:
                    job = await self._parse_card(card)
                    if job:
                        jobs.append(job)
                except Exception:
                    continue

            await save_session_cookies("glassdoor", context)
            return jobs

        except Exception as exc:
            logger.error("glassdoor.search_error", error=str(exc))
            return []
        finally:
            await page.close()

    async def _parse_card(self, card) -> Optional[RawJob]:
        try:
            title_el = await card.query_selector("a.jobLink span, a[data-test='job-title']")
            company_el = await card.query_selector("div.jobHeader a, div.employer-name")
            loc_el = await card.query_selector("span.loc, div.location")
            link_el = await card.query_selector("a.jobLink, a[data-test='job-title']")

            if not title_el:
                return None

            href = await link_el.get_attribute("href") if link_el else ""
            job_id_match = re.search(r"jobListingId=(\d+)", href or "")
            job_id = job_id_match.group(1) if job_id_match else href[-20:] if href else ""

            return RawJob(
                portal="glassdoor",
                portal_job_id=job_id,
                title=await title_el.inner_text(),
                company=await company_el.inner_text() if company_el else "",
                location=await loc_el.inner_text() if loc_el else location,
                job_url=f"{GD_BASE}{href}" if href and not href.startswith("http") else (href or ""),
            )
        except Exception:
            return None

    async def apply(
        self,
        context: BrowserContext,
        job: RawJob,
        user_profile: dict,
        resume_path: Optional[str] = None,
        cover_letter: Optional[str] = None,
    ) -> ApplicationReceipt:
        """Glassdoor typically redirects to the company's ATS — flag as manual."""
        page = await context.new_page()
        try:
            await page.goto(job.job_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay("glassdoor")

            apply_btn = await page.query_selector("button[data-test='applyButton'], a.apply-btn")
            if not apply_btn:
                return ApplicationReceipt(success=False, failure_reason="apply_button_not_found", requires_manual=True)

            # Check if it redirects externally (ATS)
            async with page.expect_navigation(timeout=10000) as nav_info:
                await apply_btn.click()
            nav = await nav_info.value
            if nav and GD_BASE not in nav.url:
                return ApplicationReceipt(
                    success=False,
                    failure_reason="redirects_to_external_ats",
                    requires_manual=True,
                )
            return ApplicationReceipt(success=True)

        except Exception as exc:
            logger.error("glassdoor.apply_error", error=str(exc))
            return ApplicationReceipt(success=False, failure_reason=str(exc), requires_manual=True)
        finally:
            await page.close()

    async def check_application_status(self, context: BrowserContext, portal_application_id: str) -> str:
        return "applied"
