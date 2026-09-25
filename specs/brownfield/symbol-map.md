# Codebase Map (136 files, generated 2026-09-23T06:37:20.354622+00:00)

Ranked by internal fan-in. `Lstart-Lend` anchors are for Read(offset=START, limit=END-START+1).

## app/security/audit_log.py  (python, fan-in 80)
- `def audit(`  # L9-L33

## app/database.py  (python, fan-in 78)
- `class Base(DeclarativeBase):`  # L22-L23
- `async def get_db():`  # L26-L31
- `async def get_tenant_db(schema_name: str):`  # L34-L41
- `async def provision_user_schema(schema_name: str) -> None:`  # L44-L47

## app/crawlers/anti_detection.py  (python, fan-in 68)
- `def random_user_agent() -> str:`  # L37-L38
- `def random_viewport() -> dict:`  # L41-L42
- `async def human_delay(portal: str = "default") -> None:`  # L45-L48
- `async def micro_delay() -> None:`  # L51-L53
- `async def human_type(page: Page, selector: str, text: str) -> None:`  # L56-L62
- `async def random_scroll(page: Page) -> None:`  # L65-L69
- `async def configure_stealth_context(context: BrowserContext) -> None:`  # L72-L79

## alembic/__init__.py  (python, fan-in 49)

## app/crawlers/base.py  (python, fan-in 39)
- `class RawJob:`  # L17-L31
- `class ApplicationReceipt:`  # L35-L41
- `class BaseCrawler(ABC):`  # L44-L114
  - `async def login(self, context: BrowserContext) -> bool:`  # L61-L62
  - `async def search_jobs(`  # L65-L72
  - `async def apply(`  # L75-L83
  - `async def check_application_status(`  # L86-L91
  - `async def is_session_valid(self, context: BrowserContext) -> bool:`  # L93-L102
  - `def _extract_skills_from_text(self, text: str, taxonomy_skills: set[str]) -> list[str]:`  # L104-L114

## app/billing/gates.py  (python, fan-in 33)
- `def can_use_portal(user: User, portal_count: int) -> bool:`  # L9-L13
- `def can_apply_today(user: User, applied_today: int, cap: int) -> bool:`  # L16-L21
- `def can_use_llm_api(user: User) -> bool:`  # L24-L28
- `def activate_plan(tier: str) -> None:`  # L31-L39

## app/ml/matcher.py  (python, fan-in 32)
- `def _get_st_model():`  # L22-L30
- `def compute_match(`  # L33-L57
- `def _tfidf_match(user_skills: list[str], job_skills: list[str]) -> dict:`  # L60-L93
- `def _semantic_match(user_skills: list[str], job_skills: list[str]) -> dict:`  # L96-L137
- `def meets_threshold(match_result: dict, threshold: float) -> bool:`  # L140-L141

## app/services/job_service.py  (python, fan-in 31)
- `async def store_jobs(`  # L17-L91
- `async def get_matched_jobs_for_user(`  # L94-L137
- `async def get_unmatched_jobs(`  # L140-L163
- `async def mark_jobs_inactive(`  # L166-L189

## app/ml/taxonomy_discovery.py  (python, fan-in 29)
- `def extract_candidate_skills(jd_text: str, known_skills: set[str]) -> list[str]:`  # L31-L44
- `async def queue_discovered_skills(`  # L47-L87
- `class SoftSignals:`  # L90-L110
  - `def score(job_extra: dict, user_preferences: dict) -> float:`  # L98-L110
- `def activate_soft_signals():`  # L113-L115

## app/services/__init__.py  (python, fan-in 29)

## app/models/user.py  (python, fan-in 27)
- `class OAuthProvider(str, enum.Enum):`  # L9-L13
- `class UserTier(str, enum.Enum):`  # L16-L19
- `class User(Base):`  # L22-L65

## app/security/encryption.py  (python, fan-in 27)
- `def encrypt(value: str) -> bytes:`  # L8-L10
- `def decrypt(token: bytes) -> str:`  # L13-L15
- `def sha256_hash(value: str) -> str:`  # L18-L20
- `def generate_thumbprint(email: str, phone: str) -> str:`  # L23-L26
- `def schema_name_from_thumbprint(thumbprint: str) -> str:`  # L29-L31

## app/config.py  (python, fan-in 24)
- `class Settings(BaseSettings):`  # L6-L116
  - `def database_url(self) -> str:`  # L23-L27
  - `def sync_database_url(self) -> str:`  # L30-L34
  - `def allowed_ip_list(self) -> List[str]:`  # L90-L91
  - `def is_production(self) -> bool:`  # L115-L116

## app/tenant_models/profile.py  (python, fan-in 24)
- `class TenantBase(DeclarativeBase):`  # L16-L18
- `class WFHPreference(str, enum.Enum):`  # L21-L25
- `class LLMChoice(str, enum.Enum):`  # L28-L30
- `class NotificationPlatform(str, enum.Enum):`  # L33-L35
- `class StatusCheckFrequency(int, enum.Enum):`  # L38-L42
- `class UserProfile(TenantBase):`  # L45-L72
- `class UserPreferences(TenantBase):`  # L75-L126

## app/dependencies.py  (python, fan-in 22)
- `async def get_current_user(`  # L11-L32
- `async def get_current_admin(`  # L35-L52
- `def require_role(*roles: AdminRole):`  # L55-L63

## app/services/application_service.py  (python, fan-in 19)
- `def _crawler_for_portal(portal: str) -> BaseCrawler:`  # L60-L76
- `async def apply_to_job(`  # L79-L195
- `async def transition_status(`  # L198-L235
- `async def queue_for_hitl(`  # L238-L284

## app/routers/applications.py  (python, fan-in 18)
- `class PauseRequest(BaseModel):`  # L20-L21
- `class CompanyBlacklistRequest(BaseModel):`  # L24-L25
- `class TitleBlacklistRequest(BaseModel):`  # L28-L29
- `class AccountDeletionRequest(BaseModel):`  # L32-L33
- `async def list_applications(`  # L37-L69
- `async def get_application(`  # L73-L111
- `async def withdraw_application(`  # L115-L126
- `async def pause_auto_apply(`  # L130-L142
- `async def resume_auto_apply(`  # L146-L157
- `async def add_company_blacklist(`  # L161-L175
- `async def remove_company_blacklist(`  # L179-L190
- `async def add_title_blacklist(`  # L194-L208
- `async def remove_title_blacklist(`  # L212-L223
- `async def get_blacklists(`  # L227-L238
- `async def delete_account(`  # L242-L252

## app/tenant_models/application.py  (python, fan-in 18)
- `class ApplicationStatus(str, enum.Enum):`  # L9-L20
- `class ApplicationFailureReason(str, enum.Enum):`  # L23-L28
- `class JobApplication(TenantBase):`  # L31-L68
- `class ApplicationStatusLog(TenantBase):`  # L71-L84

## app/crawlers/session_manager.py  (python, fan-in 16)
- `async def _get_redis() -> aioredis.Redis:`  # L27-L31
- `async def _get_browser() -> Browser:`  # L34-L47
- `async def get_context(portal: str) -> BrowserContext:`  # L50-L82
- `async def save_session_cookies(portal: str, context: BrowserContext) -> None:`  # L85-L92
- `async def load_session_cookies(portal: str) -> Optional[list]:`  # L95-L106
- `async def clear_session(portal: str) -> None:`  # L109-L119
- `async def handle_session_expiry(`  # L122-L148
- `async def save_crawl_state(portal: str, state: dict) -> None:`  # L151-L154
- `async def load_crawl_state(portal: str) -> Optional[dict]:`  # L157-L161
- `async def shutdown() -> None:`  # L164-L175

## app/crawlers/indeed.py  (python, fan-in 15)
- `class IndeedCrawler(BaseCrawler):`  # L21-L180
  - `async def login(self, context: BrowserContext) -> bool:`  # L24-L59
  - `async def search_jobs(`  # L61-L91
  - `def _parse_html(self, soup: BeautifulSoup) -> list[RawJob]:`  # L93-L116
  - `async def _playwright_search(self, context, keyword_str, location, page_num) -> list[RawJob]:`  # L118-L132
  - `async def apply(`  # L134-L177
  - `async def check_application_status(self, context: BrowserContext, portal_application_id: str) -> str:`  # L179-L180

## installer/core/env_writer.py  (python, fan-in 14)
- `def _fernet_key() -> str:`  # L7-L16
- `def _db_url(config: dict) -> str:`  # L19-L28
- `def write_env(config: dict, install_dir: str) -> str:`  # L31-L155

## app/compliance/deletion.py  (python, fan-in 13)
- `class DeletionMode(str, Enum):`  # L12-L15
- `async def execute_deletion(`  # L18-L32
- `async def _hard_delete(user: User, db: AsyncSession) -> dict:`  # L35-L46
- `async def _soft_delete(user: User, db: AsyncSession) -> dict:`  # L49-L65
- `async def _anonymise(user: User, db: AsyncSession) -> dict:`  # L68-L95

## app/billing/plans.py  (python, fan-in 12)
- `class Plan:`  # L9-L16

## app/crawlers/naukri.py  (python, fan-in 11)
- `class NaukriCrawler(BaseCrawler):`  # L25-L306
  - `async def login(self, context: BrowserContext) -> bool:`  # L28-L70
  - `async def search_jobs(`  # L72-L118
  - `def _parse_api_response(self, data: dict) -> list[RawJob]:`  # L120-L142
  - `async def _scrape_search_page(`  # L144-L192
  - `async def apply(`  # L194-L248
  - `async def check_application_status(`  # L250-L277
  - `async def _answer_screening_questions(`  # L279-L297
  - `async def _extract_application_id(self, page) -> Optional[str]:`  # L299-L306

## app/services/resume_service.py  (python, fan-in 11)
- `def _render_html(resume_data: dict) -> str:`  # L70-L113
- `async def parse_master_resume(minio_key: str) -> str:`  # L120-L127
- `async def generate_tailored_resume(`  # L130-L159
- `async def render_tailored_pdf(`  # L162-L187
- `async def store_tailored_resume(`  # L190-L207

## alembic/env.py  (python, fan-in 0)
- `def _include_object(obj, name, type_, reflected, compare_to):`  # L62-L68
- `def _configure_for_schema(connection, schema: str | None = None):`  # L71-L87
- `def run_migrations_offline() -> None:`  # L90-L102
- `def run_migrations_online() -> None:`  # L105-L120
- `def run_tenant_migrations(schema_name: str, database_url: str | None = None) -> None:`  # L123-L145

## alembic/versions/0001_initial_shared_schema.py  (python, fan-in 0)
- `def upgrade() -> None:`  # L20-L231
- `def downgrade() -> None:`  # L234-L251

## alembic/versions/0002_phase4_columns.py  (python, fan-in 0)
- `def upgrade() -> None:`  # L21-L34
- `def downgrade() -> None:`  # L37-L39

## app/__init__.py  (python, fan-in 0)

## app/billing/__init__.py  (python, fan-in 0)

## app/billing/stripe_client.py  (python, fan-in 0)
- `def create_checkout_session(user_id: str, plan: str) -> str:`  # L11-L12
- `def handle_webhook(payload: bytes, sig_header: str) -> dict:`  # L15-L16

## app/compliance/__init__.py  (python, fan-in 0)

## app/compliance/consent_store.py  (python, fan-in 0)
- `async def record_consent(`  # L21-L43

## app/compliance/dpdpa.py  (python, fan-in 0)
- `class ConsentRecord(Base):`  # L12-L31

## app/crawlers/__init__.py  (python, fan-in 0)

## app/crawlers/company_pages/__init__.py  (python, fan-in 0)

## app/crawlers/company_pages/base_company.py  (python, fan-in 0)
- `class BaseCompanyCrawler(BaseCrawler, ABC):`  # L11-L46
  - `async def search_jobs(self, context, keywords, location="India", page_num=1) -> list[RawJob]:`  # L19-L35
  - `def _parse_jobs(self, soup, keywords: list[str]) -> list[RawJob]:`  # L38-L40
  - `async def login(self, context) -> bool:`  # L42-L43
  - `async def check_application_status(self, context, portal_application_id) -> str:`  # L45-L46

## app/crawlers/glassdoor.py  (python, fan-in 0)
- `class GlassdoorCrawler(BaseCrawler):`  # L19-L153
  - `async def login(self, context: BrowserContext) -> bool:`  # L22-L49
  - `async def search_jobs(`  # L51-L89
  - `async def _parse_card(self, card) -> Optional[RawJob]:`  # L91-L114
  - `async def apply(`  # L116-L150
  - `async def check_application_status(self, context: BrowserContext, portal_application_id: str) -> str:`  # L152-L153

## app/crawlers/linkedin.py  (python, fan-in 0)
- `class LinkedInCrawler(BaseCrawler):`  # L25-L281
  - `async def login(self, context: BrowserContext) -> bool:`  # L28-L67
  - `async def search_jobs(`  # L69-L111
  - `async def _parse_job_card(self, card, page) -> Optional[RawJob]:`  # L113-L140
  - `async def apply(`  # L142-L244
  - `async def check_application_status(`  # L246-L264
  - `def _match_profile_field(self, label: str, profile: dict) -> Optional[str]:`  # L266-L281

## app/crawlers/monster.py  (python, fan-in 0)
- `class MonsterCrawler(BaseCrawler):`  # L20-L181
  - `async def login(self, context: BrowserContext) -> bool:`  # L23-L53
  - `async def search_jobs(`  # L55-L83
  - `def _parse_search_html(self, html: str, location: str) -> list[RawJob]:`  # L85-L115
  - `async def _playwright_search(self, context: BrowserContext, url: str, location: str) -> list[RawJob]:`  # L117-L129
  - `async def apply(`  # L131-L174
  - `async def check_application_status(`  # L176-L181

## app/crawlers/shine.py  (python, fan-in 0)
- `class ShineCrawler(BaseCrawler):`  # L20-L179
  - `async def login(self, context: BrowserContext) -> bool:`  # L23-L53
  - `async def search_jobs(`  # L55-L81
  - `def _parse_search_html(self, html: str, location: str) -> list[RawJob]:`  # L83-L113
  - `async def _playwright_search(self, context: BrowserContext, url: str, location: str) -> list[RawJob]:`  # L115-L127
  - `async def apply(`  # L129-L172
  - `async def check_application_status(`  # L174-L179

## app/llm/__init__.py  (python, fan-in 0)

## app/llm/anthropic_client.py  (python, fan-in 0)
- `def _get_client() -> anthropic.AsyncAnthropic:`  # L10-L14
- `async def generate(prompt: str, system_prompt: str = "") -> str:`  # L17-L36

## app/llm/cover_letter_prompt.py  (python, fan-in 0)
- `def build_cover_letter_prompt(`  # L1-L38

## app/llm/ollama_client.py  (python, fan-in 0)
- `async def generate(prompt: str, system_prompt: str = "") -> str:`  # L8-L28

## app/llm/resume_prompt.py  (python, fan-in 0)
- `def build_resume_tailoring_prompt(`  # L1-L69

## app/llm/router.py  (python, fan-in 0)
- `async def generate(prompt: str, user_llm_choice: str, system_prompt: str = "") -> str:`  # L7-L17

## app/main.py  (python, fan-in 0)
- `async def health():`  # L81-L82
- `async def global_exception_handler(request: Request, exc: Exception):`  # L86-L94

## app/ml/__init__.py  (python, fan-in 0)

## app/ml/explainer.py  (python, fan-in 0)
- `def format_explanation(match_result: dict) -> str:`  # L6-L27
- `def dashboard_explainability(match_result: dict) -> dict:`  # L30-L41

## app/ml/feedback.py  (python, fan-in 0)
- `async def record_outcome(`  # L14-L33
- `async def compute_user_score_adjustment(tenant_db: AsyncSession) -> dict:`  # L36-L58

## app/models/__init__.py  (python, fan-in 0)

## app/models/admin.py  (python, fan-in 0)
- `class AdminRole(str, enum.Enum):`  # L9-L13
- `class AdminUser(Base):`  # L16-L36

## app/models/job.py  (python, fan-in 0)
- `class Job(Base):`  # L12-L43

## app/models/portal_account.py  (python, fan-in 0)
- `class PortalName(str, enum.Enum):`  # L9-L15
- `class PortalAccountHealth(str, enum.Enum):`  # L18-L22
- `class SystemPortalAccount(Base):`  # L25-L58

## app/models/skill_taxonomy.py  (python, fan-in 0)
- `class TaxonomyStatus(str, enum.Enum):`  # L9-L12
- `class TaxonomySource(str, enum.Enum):`  # L15-L19
- `class SkillTaxonomy(Base):`  # L22-L44

## app/notifications/__init__.py  (python, fan-in 0)

## app/notifications/discord_bot.py  (python, fan-in 0)
- `def _run_bot():`  # L14-L22
- `def start_discord_bot():`  # L25-L28
- `async def send_to_channel(channel_id: str, text: str) -> bool:`  # L31-L46
- `async def provision_user_channel(user_display_name: str) -> str | None:`  # L49-L76

## app/notifications/email_client.py  (python, fan-in 0)
- `async def send_email(to: str, subject: str, body_html: str) -> bool:`  # L14-L21
- `async def _send_sendgrid(to: str, subject: str, body_html: str) -> bool:`  # L24-L42
- `async def _send_smtp(to: str, subject: str, body_html: str) -> bool:`  # L45-L64

## app/notifications/telegram_bot.py  (python, fan-in 0)
- `def get_bot():`  # L10-L15
- `async def send_message(chat_id: str, text: str) -> bool:`  # L18-L28
- `def get_bot_link(user_id: str) -> str:`  # L31-L32

## app/routers/__init__.py  (python, fan-in 0)

## app/routers/admin/__init__.py  (python, fan-in 0)

## app/routers/admin/config.py  (python, fan-in 0)
- `class SystemConfigUpdate(BaseModel):`  # L11-L13
- `async def get_config(`  # L17-L24
- `async def update_config(`  # L28-L38

## app/routers/admin/crawls.py  (python, fan-in 0)
- `async def trigger_crawl(`  # L13-L22

## app/routers/admin/ops.py  (python, fan-in 0)
- `async def ops_dashboard(`  # L14-L43

## app/routers/admin/portals.py  (python, fan-in 0)
- `async def list_portal_accounts(`  # L14-L28
- `async def update_portal_health(`  # L32-L47

## app/routers/admin/taxonomy.py  (python, fan-in 0)
- `class SkillReviewAction(BaseModel):`  # L13-L16
- `async def list_pending_skills(`  # L20-L30
- `async def review_skill(`  # L34-L52

## app/routers/dashboard.py  (python, fan-in 0)
- `async def get_dashboard(`  # L13-L98

## conftest.py  (python, fan-in 0)

_67 file(s) omitted — map budget 4000 tokens._
