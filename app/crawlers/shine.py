"""
Shine.com crawler.
Uses httpx for job search and Playwright for login/apply.
"""
import re
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext
from app.crawlers.base import BaseCrawler, RawJob, ApplicationReceipt
from app.crawlers.anti_detection import human_delay, human_type, random_scroll, micro_delay
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("crawlers.shine")

SHINE_BASE = "https://www.shine.com"


class ShineCrawler(BaseCrawler):
    portal_name = "shine"

    async def login(self, context: BrowserContext) -> bool:
        from app.config import settings

        page = await context.new_page()
        try:
            await page.goto(f"{SHINE_BASE}/login/", wait_until="domcontentloaded")
            await human_delay("shine")

            await human_type(page, "input[type='email'], input[name='email'], #email", settings.shine_system_email)
            await human_type(page, "input[type='password'], input[name='password'], #password", settings.shine_system_password)
            await micro_delay()
            await page.click("button[type='submit'], .login-btn, input[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=15000)

            if "login" not in page.url.lower():
                audit("crawler.login_success", details={"portal": "shine"})
                logger.info("shine.login_success")
                await page.close()
                return True

            logger.warning("shine.login_failed", url=page.url)
            await page.close()
            return False

        except Exception as exc:
            logger.error("shine.login_error", error=str(exc))
            try:
                await page.close()
            except Exception:
                pass
            return False

    async def search_jobs(
        self,
        context: BrowserContext,
        keywords: list[str],
        location: str = "India",
        page_num: int = 1,
    ) -> list[RawJob]:
        keyword_str = "+".join(k.replace(" ", "+") for k in keywords)
        loc_str = location.replace(" ", "+")
        url = (
            f"{SHINE_BASE}/job-search/it-jobs-in-india/"
            f"?q={keyword_str}&loc={loc_str}&p={page_num}"
        )

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )
                if resp.status_code == 200:
                    return self._parse_search_html(resp.text, location)
        except Exception as exc:
            logger.error("shine.search_http_error", error=str(exc))

        # Playwright fallback
        return await self._playwright_search(context, url, location)

    def _parse_search_html(self, html: str, location: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []
        for card in soup.select(".job-listing-item, .shine-job-item, article.job-item"):
            try:
                title_el = card.select_one("h3 a, h2 a, .job-title a")
                company_el = card.select_one(".comp-name, .company-name, span.company")
                loc_el = card.select_one(".loc, .location, span.location")
                link = title_el.get("href", "") if title_el else ""
                if link and not link.startswith("http"):
                    link = f"{SHINE_BASE}{link}"

                job_id_match = re.search(r"/(\d{5,})/?", link)
                job_id = job_id_match.group(1) if job_id_match else link[-20:]

                skills = [s.get_text(strip=True) for s in card.select(".tag, .skill, span.skill-tag")]

                job = RawJob(
                    portal="shine",
                    portal_job_id=job_id,
                    title=title_el.get_text(strip=True) if title_el else "",
                    company=company_el.get_text(strip=True) if company_el else "",
                    location=loc_el.get_text(strip=True) if loc_el else location,
                    job_url=link,
                    skills_required=skills,
                )
                if job.portal_job_id and job.title:
                    jobs.append(job)
            except Exception:
                continue
        return jobs

    async def _playwright_search(self, context: BrowserContext, url: str, location: str) -> list[RawJob]:
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await human_delay("shine")
            await random_scroll(page)
            content = await page.content()
            return self._parse_search_html(content, location)
        except Exception as exc:
            logger.error("shine.playwright_search_error", error=str(exc))
            return []
        finally:
            await page.close()

    async def apply(
        self,
        context: BrowserContext,
        job: RawJob,
        user_profile: dict,
        resume_path: Optional[str] = None,
        cover_letter: Optional[str] = None,
    ) -> ApplicationReceipt:
        page = await context.new_page()
        try:
            await page.goto(job.job_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay("shine")

            apply_btn = await page.query_selector(
                "a.apply-now, button.apply-now, .apply-btn, "
                "a[data-apply], button[data-label='Apply Now']"
            )
            if not apply_btn:
                return ApplicationReceipt(
                    success=False,
                    failure_reason="Apply button not found",
                    requires_manual=True,
                )

            await apply_btn.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            await human_delay("shine")

            # Handle Shine's apply modal
            modal = await page.query_selector(".apply-modal, #applyModal, .modal-dialog")
            if modal:
                submit_btn = await modal.query_selector("button[type='submit'], .btn-apply, .submit-btn")
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_load_state("networkidle", timeout=10000)

            audit("crawler.applied", details={"portal": "shine", "job_id": job.portal_job_id})
            return ApplicationReceipt(success=True, portal_application_id=None)

        except Exception as exc:
            logger.error("shine.apply_error", job_id=job.portal_job_id, error=str(exc))
            return ApplicationReceipt(success=False, failure_reason=str(exc))
        finally:
            await page.close()

    async def check_application_status(
        self,
        context: BrowserContext,
        portal_application_id: str,
    ) -> str:
        return "applied"
