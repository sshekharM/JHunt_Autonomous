"""
Indeed India crawler — uses httpx for search + Playwright for apply.
Indeed India: https://in.indeed.com
"""
import re
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext
from app.crawlers.base import BaseCrawler, RawJob, ApplicationReceipt
from app.crawlers.anti_detection import human_delay, human_type, random_scroll, micro_delay
from app.crawlers.session_manager import save_session_cookies
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("crawlers.indeed")

INDEED_BASE = "https://in.indeed.com"


class IndeedCrawler(BaseCrawler):
    portal_name = "indeed"

    async def login(self, context: BrowserContext) -> bool:
        from app.config import settings

        page = await context.new_page()
        try:
            await page.goto(f"{INDEED_BASE}/account/login", wait_until="domcontentloaded")
            await human_delay("indeed")

            # Indeed login — email first, then password on next screen
            email_input = await page.query_selector("input[type='email'], input#ifl-InputFormField-3")
            if email_input:
                await human_type(page, "input[type='email']", settings.indeed_system_email)
                await page.click("button[type='submit']")
                await page.wait_for_load_state("networkidle", timeout=15000)
                await human_delay("indeed")

            pwd_input = await page.query_selector("input[type='password']")
            if pwd_input:
                await human_type(page, "input[type='password']", settings.indeed_system_password)
                await page.click("button[type='submit']")
                await page.wait_for_load_state("networkidle", timeout=15000)

            if "indeed.com" in page.url and "login" not in page.url and "auth" not in page.url:
                await save_session_cookies("indeed", context)
                audit("crawler.login_success", details={"portal": "indeed"})
                await page.close()
                return True

            logger.warning("indeed.login_failed", url=page.url)
            await page.close()
            return False

        except Exception as exc:
            logger.error("indeed.login_error", error=str(exc))
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
        start = (page_num - 1) * 10
        cookies = await context.cookies()
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-IN,en;q=0.9",
            "Cookie": cookie_header,
        }
        url = f"{INDEED_BASE}/jobs?q={keyword_str.replace(' ', '+')}&l={location.replace(' ', '+')}&start={start}&sort=date"

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return await self._playwright_search(context, keyword_str, location, page_num)

                soup = BeautifulSoup(resp.text, "lxml")
                return self._parse_html(soup)

        except Exception as exc:
            logger.error("indeed.search_error", error=str(exc))
            return []

    def _parse_html(self, soup: BeautifulSoup) -> list[RawJob]:
        jobs = []
        for card in soup.select("div.job_seen_beacon, div.resultContent"):
            try:
                title_el = card.select_one("h2.jobTitle a, a.jcs-JobTitle")
                company_el = card.select_one("span.companyName, a.companyName")
                loc_el = card.select_one("div.companyLocation")
                href = title_el["href"] if title_el and title_el.get("href") else ""
                job_id_match = re.search(r"jk=([a-z0-9]+)", href)
                job_id = job_id_match.group(1) if job_id_match else href[-20:]

                job = RawJob(
                    portal="indeed",
                    portal_job_id=job_id,
                    title=title_el.get_text(strip=True) if title_el else "",
                    company=company_el.get_text(strip=True) if company_el else "",
                    location=loc_el.get_text(strip=True) if loc_el else "India",
                    job_url=f"{INDEED_BASE}{href}" if href and not href.startswith("http") else href,
                )
                if job.portal_job_id and job.title:
                    jobs.append(job)
            except Exception:
                continue
        return jobs

    async def _playwright_search(self, context, keyword_str, location, page_num) -> list[RawJob]:
        page = await context.new_page()
        try:
            start = (page_num - 1) * 10
            url = f"{INDEED_BASE}/jobs?q={keyword_str.replace(' ', '+')}&l={location.replace(' ', '+')}&start={start}&sort=date"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await human_delay("indeed")
            await random_scroll(page)
            content = await page.content()
            soup = BeautifulSoup(content, "lxml")
            return self._parse_html(soup)
        except Exception:
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
            await human_delay("indeed")

            apply_btn = await page.query_selector(
                "button#indeedApplyButton, a.indeed-apply-button, button[data-indeed-apply]"
            )
            if not apply_btn:
                return ApplicationReceipt(
                    success=False, failure_reason="apply_button_not_found", requires_manual=True
                )

            await apply_btn.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            await human_delay("indeed")

            # Indeed's apply flow varies — check for resume upload
            upload = await page.query_selector("input[type='file']")
            if upload and resume_path:
                await upload.set_input_files(resume_path)
                await micro_delay()

            submit_btn = await page.query_selector("button[type='submit'], button.ia-continueButton")
            if submit_btn:
                await submit_btn.click()
                await page.wait_for_load_state("networkidle", timeout=10000)

            audit("crawler.applied", details={"portal": "indeed", "job_id": job.portal_job_id})
            return ApplicationReceipt(success=True)

        except Exception as exc:
            logger.error("indeed.apply_error", error=str(exc))
            return ApplicationReceipt(success=False, failure_reason=str(exc))
        finally:
            await page.close()

    async def check_application_status(self, context: BrowserContext, portal_application_id: str) -> str:
        return "applied"
