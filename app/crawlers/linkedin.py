"""
LinkedIn crawler — Playwright-based.
System account used for job search only.
User's personal session used for Easy Apply.

Anti-ban measures: strict rate limits, no bulk actions, human-like behaviour.
"""
import re
from typing import Optional
from playwright.async_api import BrowserContext
from app.crawlers.base import BaseCrawler, RawJob, ApplicationReceipt
from app.crawlers.anti_detection import (
    human_delay, human_type, random_scroll, micro_delay
)
from app.crawlers.session_manager import save_session_cookies
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("crawlers.linkedin")

LI_BASE = "https://www.linkedin.com"
LI_JOBS = "https://www.linkedin.com/jobs/search"


class LinkedInCrawler(BaseCrawler):
    portal_name = "linkedin"

    async def login(self, context: BrowserContext) -> bool:
        from app.config import settings

        page = await context.new_page()
        try:
            await page.goto(f"{LI_BASE}/login", wait_until="domcontentloaded", timeout=30000)
            await human_delay("linkedin")

            await human_type(page, "input#username", settings.linkedin_system_email)
            await human_type(page, "input#password", settings.linkedin_system_password)
            await micro_delay()
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=20000)

            if "feed" in page.url or "mynetwork" in page.url or "jobs" in page.url:
                await save_session_cookies("linkedin", context)
                audit("crawler.login_success", details={"portal": "linkedin"})
                logger.info("linkedin.login_success")
                await page.close()
                return True

            # CAPTCHA or challenge detected
            if "checkpoint" in page.url or "challenge" in page.url:
                logger.warning("linkedin.checkpoint_detected", url=page.url)
                audit("crawler.login_challenge", details={"portal": "linkedin", "url": page.url})
                await page.close()
                return False

            logger.warning("linkedin.login_failed", url=page.url)
            await page.close()
            return False

        except Exception as exc:
            logger.error("linkedin.login_error", error=str(exc))
            audit("crawler.login_failed", details={"portal": "linkedin"}, error=exc)
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
        keyword_str = " ".join(keywords)
        start = (page_num - 1) * 25

        page = await context.new_page()
        try:
            url = (
                f"{LI_JOBS}?keywords={keyword_str.replace(' ', '%20')}"
                f"&location={location.replace(' ', '%20')}"
                f"&f_TPR=r86400"  # last 24 hours
                f"&f_JT=F"        # full-time
                f"&start={start}"
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await human_delay("linkedin")
            await random_scroll(page)
            await human_delay("linkedin")

            jobs = []
            cards = await page.query_selector_all("div.job-search-card, li.jobs-search-results__list-item")

            for card in cards[:20]:
                try:
                    job = await self._parse_job_card(card, page)
                    if job:
                        jobs.append(job)
                except Exception as exc:
                    logger.warning("linkedin.card_parse_error", error=str(exc))

            await save_session_cookies("linkedin", context)
            return jobs

        except Exception as exc:
            logger.error("linkedin.search_error", error=str(exc))
            return []
        finally:
            await page.close()

    async def _parse_job_card(self, card, page) -> Optional[RawJob]:
        try:
            title_el = await card.query_selector("h3.base-search-card__title, a.job-card-list__title")
            company_el = await card.query_selector("h4.base-search-card__subtitle, a.job-card-container__company-name")
            loc_el = await card.query_selector("span.job-search-card__location, li.job-card-container__metadata-item")
            link_el = await card.query_selector("a.base-card__full-link, a.job-card-list__title")

            if not title_el or not link_el:
                return None

            href = await link_el.get_attribute("href") or ""
            job_id_match = re.search(r"/jobs/view/(\d+)", href)
            job_id = job_id_match.group(1) if job_id_match else href[-20:]

            # Check for Easy Apply badge
            easy_apply = await card.query_selector("span.job-search-card__easy-apply-label") is not None

            return RawJob(
                portal="linkedin",
                portal_job_id=job_id,
                title=await title_el.inner_text(),
                company=await company_el.inner_text() if company_el else "",
                location=await loc_el.inner_text() if loc_el else "India",
                job_url=href if href.startswith("http") else f"{LI_BASE}{href}",
                is_easy_apply=easy_apply,
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
        """Apply via LinkedIn Easy Apply using the user's personal session."""
        if not job.is_easy_apply:
            return ApplicationReceipt(
                success=False,
                failure_reason="not_easy_apply",
                requires_manual=True,
            )

        page = await context.new_page()
        try:
            await page.goto(job.job_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay("linkedin")

            # Click Easy Apply button
            easy_apply_btn = await page.query_selector(
                "button.jobs-apply-button, button[aria-label*='Easy Apply']"
            )
            if not easy_apply_btn:
                return ApplicationReceipt(
                    success=False, failure_reason="easy_apply_button_not_found",
                    requires_manual=True,
                )

            await easy_apply_btn.click()
            await page.wait_for_selector("div.jobs-easy-apply-modal", timeout=10000)
            await micro_delay()

            missing_fields = []

            # Step through the Easy Apply modal
            for step in range(10):  # Max 10 steps
                await micro_delay()

                # Check for file upload (resume)
                upload_input = await page.query_selector("input[type='file']")
                if upload_input and resume_path:
                    await upload_input.set_input_files(resume_path)
                    await micro_delay()

                # Fill text fields from user profile
                text_inputs = await page.query_selector_all(
                    "div.jobs-easy-apply-form-section__grouping input[type='text'],"
                    "div.jobs-easy-apply-form-section__grouping textarea"
                )
                for inp in text_inputs:
                    label = await inp.get_attribute("aria-label") or ""
                    value = self._match_profile_field(label, user_profile)
                    if value:
                        await inp.fill(str(value))
                    else:
                        missing_fields.append(label)

                # Fill select dropdowns
                selects = await page.query_selector_all(
                    "div.jobs-easy-apply-form-section__grouping select"
                )
                for sel in selects:
                    label = await sel.get_attribute("aria-label") or ""
                    value = self._match_profile_field(label, user_profile)
                    if value:
                        await sel.select_option(label=str(value))

                # Next / Submit button
                next_btn = await page.query_selector(
                    "button[aria-label='Continue to next step'],"
                    "button[aria-label='Submit application'],"
                    "button[aria-label='Review your application']"
                )
                if not next_btn:
                    break

                btn_text = await next_btn.inner_text()
                await next_btn.click()
                await micro_delay()

                if "submit" in btn_text.lower():
                    # Application submitted
                    audit("crawler.applied", details={"portal": "linkedin", "job_id": job.portal_job_id})
                    return ApplicationReceipt(
                        success=True,
                        missing_fields=missing_fields if missing_fields else [],
                    )

            return ApplicationReceipt(
                success=False,
                failure_reason="modal_flow_incomplete",
                requires_manual=True,
                missing_fields=missing_fields,
            )

        except Exception as exc:
            logger.error("linkedin.apply_error", job_id=job.portal_job_id, error=str(exc))
            return ApplicationReceipt(success=False, failure_reason=str(exc))
        finally:
            await page.close()

    async def check_application_status(
        self,
        context: BrowserContext,
        portal_application_id: str,
    ) -> str:
        page = await context.new_page()
        try:
            await page.goto(
                f"{LI_BASE}/my-items/saved-jobs/",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await human_delay("linkedin")
            # LinkedIn doesn't expose per-application status easily; return applied
            return "applied"
        except Exception:
            return "unknown"
        finally:
            await page.close()

    def _match_profile_field(self, label: str, profile: dict) -> Optional[str]:
        """Map a form field label to a user profile value."""
        label_lower = label.lower()
        if "notice" in label_lower:
            return str(profile.get("notice_period_days", ""))
        if "phone" in label_lower or "mobile" in label_lower:
            return profile.get("phone", "")
        if "experience" in label_lower or "year" in label_lower:
            return str(profile.get("years_experience", ""))
        if "city" in label_lower or "location" in label_lower:
            return profile.get("city", "")
        if "current" in label_lower and "salary" in label_lower:
            return str(profile.get("current_salary", ""))
        if "expected" in label_lower and "salary" in label_lower:
            return str(profile.get("salary_min_lpa", ""))
        return None
