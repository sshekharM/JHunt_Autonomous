"""
Naukri.com crawler — highest-volume Indian IT job portal.
Uses httpx for job search (server-rendered pages) and
Playwright for session-dependent actions (login, apply).
"""
import re
import json
from typing import Optional
from datetime import datetime, timezone
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext
from app.crawlers.base import BaseCrawler, RawJob, ApplicationReceipt
from app.crawlers.anti_detection import human_delay, human_type, random_scroll, micro_delay
from app.crawlers.session_manager import save_session_cookies
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("crawlers.naukri")

NAUKRI_BASE = "https://www.naukri.com"
NAUKRI_API_SEARCH = "https://www.naukri.com/jobapi/v3/search"


class NaukriCrawler(BaseCrawler):
    portal_name = "naukri"

    async def login(self, context: BrowserContext) -> bool:
        """Log in to Naukri using system credentials via Playwright."""
        from app.config import settings
        from app.security.encryption import decrypt

        page = await context.new_page()
        try:
            await page.goto(f"{NAUKRI_BASE}/nlogin/login.php", wait_until="domcontentloaded")
            await human_delay("naukri")

            # Accept cookies if prompted
            try:
                await page.click("button#onetrust-accept-btn-handler", timeout=3000)
                await micro_delay()
            except Exception:
                pass

            await human_type(page, "input#usernameField", settings.naukri_system_email)
            await human_type(page, "input#passwordField", settings.naukri_system_password)
            await micro_delay()
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Verify login
            if "login" not in page.url.lower():
                await save_session_cookies("naukri", context)
                audit("crawler.login_success", details={"portal": "naukri"})
                logger.info("naukri.login_success")
                await page.close()
                return True

            logger.warning("naukri.login_failed", url=page.url)
            await page.close()
            return False

        except Exception as exc:
            logger.error("naukri.login_error", error=str(exc))
            audit("crawler.login_failed", details={"portal": "naukri"}, error=exc)
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
        """
        Search Naukri for IT jobs using their JSON search API.
        Falls back to HTML scraping if the API is unavailable.
        """
        keyword_str = " ".join(keywords)
        cookies = await context.cookies()
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Cookie": cookie_header,
            "appid": "109",
            "systemid": "Naukri",
        }
        params = {
            "noOfResults": 20,
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": keyword_str,
            "location": location,
            "pageNo": page_num,
            "experience": 0,
            "k": keyword_str,
            "l": location,
        }

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(NAUKRI_API_SEARCH, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    return self._parse_api_response(data)

            # Fallback: Playwright scrape
            return await self._scrape_search_page(context, keyword_str, location, page_num)

        except Exception as exc:
            logger.error("naukri.search_error", error=str(exc))
            return []

    def _parse_api_response(self, data: dict) -> list[RawJob]:
        jobs = []
        for item in data.get("jobDetails", []):
            try:
                job = RawJob(
                    portal="naukri",
                    portal_job_id=str(item.get("jobId", "")),
                    title=item.get("title", ""),
                    company=item.get("companyName", ""),
                    location=", ".join(item.get("placeholders", [{}])[0].get("label", "").split(",")),
                    job_url=item.get("jdURL", ""),
                    description=item.get("jobDescription", ""),
                    skills_required=[s.get("label", "") for s in item.get("tagsAndSkills", [])],
                    salary_range=item.get("placeholders", [{}])[1].get("label", "") if len(item.get("placeholders", [])) > 1 else "",
                    experience_required=item.get("placeholders", [{}])[0].get("label", "") if item.get("placeholders") else "",
                    posted_at=None,
                    is_easy_apply=False,
                )
                if job.portal_job_id and job.title:
                    jobs.append(job)
            except Exception as exc:
                logger.warning("naukri.parse_item_error", error=str(exc))
        return jobs

    async def _scrape_search_page(
        self,
        context: BrowserContext,
        keyword: str,
        location: str,
        page_num: int,
    ) -> list[RawJob]:
        """Playwright HTML scrape fallback."""
        page = await context.new_page()
        try:
            url = f"{NAUKRI_BASE}/{keyword.replace(' ', '-')}-jobs-in-{location.replace(' ', '-').lower()}?pageNo={page_num}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await human_delay("naukri")
            await random_scroll(page)

            content = await page.content()
            soup = BeautifulSoup(content, "lxml")
            jobs = []

            for card in soup.select("article.jobTuple"):
                try:
                    title_el = card.select_one("a.title")
                    company_el = card.select_one("a.subTitle")
                    loc_el = card.select_one("li.location span")
                    link = title_el["href"] if title_el else ""
                    job_id = re.search(r"-(\d+)\.htm", link)

                    job = RawJob(
                        portal="naukri",
                        portal_job_id=job_id.group(1) if job_id else link[-20:],
                        title=title_el.get_text(strip=True) if title_el else "",
                        company=company_el.get_text(strip=True) if company_el else "",
                        location=loc_el.get_text(strip=True) if loc_el else location,
                        job_url=link if link.startswith("http") else f"{NAUKRI_BASE}{link}",
                        skills_required=[
                            s.get_text(strip=True) for s in card.select("li.tag")
                        ],
                    )
                    if job.portal_job_id and job.title:
                        jobs.append(job)
                except Exception:
                    continue

            return jobs
        except Exception as exc:
            logger.error("naukri.scrape_error", error=str(exc))
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
        """Apply to a Naukri job via Playwright using the user's personal session."""
        page = await context.new_page()
        try:
            await page.goto(job.job_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay("naukri")

            # Look for Apply button
            apply_btn = await page.query_selector("button#apply-button, a#apply-button, button.apply-button")
            if not apply_btn:
                return ApplicationReceipt(
                    success=False,
                    failure_reason="Apply button not found",
                    requires_manual=True,
                )

            await apply_btn.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            await human_delay("naukri")

            # Check for screening questions
            questions = await page.query_selector_all("div.screening-question, div.assessment-question")
            if questions:
                missing = await self._answer_screening_questions(page, questions, user_profile)
                if missing:
                    return ApplicationReceipt(
                        success=False,
                        failure_reason="unanswered_screening_questions",
                        requires_manual=True,
                        missing_fields=missing,
                    )

            # Submit
            submit_btn = await page.query_selector("button[type='submit'], button.submit-btn")
            if submit_btn:
                await submit_btn.click()
                await page.wait_for_load_state("networkidle", timeout=10000)

            # Extract application ID
            app_id = await self._extract_application_id(page)
            audit("crawler.applied", details={"portal": "naukri", "job_id": job.portal_job_id})
            return ApplicationReceipt(success=True, portal_application_id=app_id)

        except Exception as exc:
            logger.error("naukri.apply_error", job_id=job.portal_job_id, error=str(exc))
            return ApplicationReceipt(success=False, failure_reason=str(exc))
        finally:
            await page.close()

    async def check_application_status(
        self,
        context: BrowserContext,
        portal_application_id: str,
    ) -> str:
        """Check application status from Naukri's applied jobs page."""
        page = await context.new_page()
        try:
            await page.goto(
                f"{NAUKRI_BASE}/mnjuser/appliedjobs",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await human_delay("naukri")
            content = await page.content()
            soup = BeautifulSoup(content, "lxml")

            for row in soup.select("div.applied-job-row, tr.applied-job"):
                if portal_application_id in str(row):
                    status_el = row.select_one(".status, .application-status")
                    if status_el:
                        return status_el.get_text(strip=True).lower()
            return "applied"
        except Exception as exc:
            logger.error("naukri.status_check_error", app_id=portal_application_id, error=str(exc))
            return "unknown"
        finally:
            await page.close()

    async def _answer_screening_questions(
        self, page, questions, user_profile: dict
    ) -> list[str]:
        """Attempt to auto-answer screening questions. Returns list of unanswerable fields."""
        missing = []
        for q in questions:
            text = await q.inner_text()
            answered = False
            # Try to match against saved answers / profile fields
            for field_key, field_val in user_profile.items():
                if any(kw in text.lower() for kw in [field_key.lower(), "experience", "notice", "ctc"]):
                    input_el = await q.query_selector("input, select, textarea")
                    if input_el:
                        await input_el.fill(str(field_val))
                        answered = True
                        break
            if not answered:
                missing.append(text[:100])
        return missing

    async def _extract_application_id(self, page) -> Optional[str]:
        """Try to extract a Naukri application confirmation ID from the page."""
        try:
            content = await page.content()
            match = re.search(r"application[_\s]?id[\":\s]+([A-Z0-9\-]+)", content, re.IGNORECASE)
            return match.group(1) if match else None
        except Exception:
            return None
