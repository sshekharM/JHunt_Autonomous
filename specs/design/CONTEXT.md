# Context

Ubiquitous language for jH_ANS (Autonomous Job Hunt System). Terms confirmed
against source during `/brownfield` discovery; each entry cites where the term
is defined. Definitions describe the domain meaning, not the implementation.

Evidence gathered from `specs/brownfield/code-graph.json` and direct source
reads. `specs/brownfield/naming-clusters.md` produced no clusters for this
repo (its root-noun heuristic only strips a fixed set of role suffixes such as
`Service`/`Repository`, and this codebase's class names — `IndeedCrawler`,
`SoftSignals` — do not end in them), so these terms were confirmed from source.

## Terms

### Portal
An external job board that the system crawls and applies on behalf of a user.
The closed set is `naukri`, `linkedin`, `glassdoor`, `indeed`, `monster`,
`shine` (`app/models/portal_account.py` — `PortalName`). "Portal" always means
the third-party site, never an internal screen.

### System Portal Account
A credential the operator owns and uses for *crawling* a portal, shared across
all users. Distinct from a user's own portal session, which is used for
*applying*. Health is tracked as `healthy` / `degraded`
(`app/models/portal_account.py` — `SystemPortalAccount`, `PortalAccountHealth`).

### Thumbprint
The immutable identity of a user, derived as `sha256(email + ":" + phone)`
(`app/security/encryption.py` — `generate_thumbprint`). It is the uniqueness
key for an account: two registrations with the same email+phone collide by
design. It is also the seed for the user's tenant schema name.

### Tenant Schema
The private PostgreSQL schema holding one user's data, named
`u_<first 32 chars of thumbprint>` (`app/security/encryption.py` —
`schema_name_from_thumbprint`). Tenant isolation in this system is
schema-level, not row-level: per-user data lives in `app/tenant_models/`, and
operator-wide data lives in `app/models/`.

### Shared Schema
The `public` schema holding cross-user data: users, admins, jobs, system portal
accounts, skill taxonomy (`app/models/`). Contrast with Tenant Schema.

### Raw Job
A job as scraped from a portal, before normalization, deduplication, or
storage (`app/crawlers/base.py` — `RawJob`). Crawlers emit Raw Jobs; the job
service turns them into stored Jobs.

### Match
The computed fit between a user's skills and a job's skills, produced by
`compute_match` (`app/ml/matcher.py`) via TF-IDF or a semantic
(sentence-transformer) strategy. A match is acted on only when it clears the
user's configured threshold (`meets_threshold`).

### Soft Signals
A small, deliberately capped bonus (maximum 0.05) added to a match score for
non-skill preferences such as company size and remote work
(`app/ml/taxonomy_discovery.py` — `SoftSignals`). Disabled by default; turned
on by `activate_soft_signals()`. Soft Signals adjust ranking, never
eligibility.

### Skill Taxonomy
The operator-curated vocabulary of skills used to extract skills from job
descriptions and profiles (`app/models/skill_taxonomy.py`,
`app/services/taxonomy_service.py`).

### Discovered Skill
A candidate skill term found in a job description that is not yet in the Skill
Taxonomy, queued for admin approval rather than used immediately
(`app/ml/taxonomy_discovery.py` — `extract_candidate_skills`,
`queue_discovered_skills`).

### Application
A user's submission to a specific job on a specific portal, with a lifecycle:
`pending_hitl` → `applying` → `applied` → (`viewed`, `shortlisted`,
`interview_scheduled`, `rejected`) plus terminal failure states
(`app/tenant_models/application.py` — `ApplicationStatus`). Status history is
append-only (`ApplicationStatusLog`).

### HITL (Human In The Loop)
The review step where an application is held as `pending_hitl` and surfaced to
the user for approval instead of being submitted automatically
(`app/services/application_service.py` — `queue_for_hitl`). HITL is the brake
on autonomous applying.

### Auto-Apply
The autonomous path where a matched job is applied to without per-application
user approval (`app/tasks/auto_apply.py`). A user can pause and resume it
(`app/routers/applications.py`).

### Application Receipt
The evidence returned by a portal that a submission succeeded — the portal's
own reference for the application (`app/crawlers/base.py` —
`ApplicationReceipt`).

### Blacklist
A user-owned exclusion list, by company or by job title, that suppresses
matching and applying (`app/routers/applications.py` — company and title
blacklist endpoints).

### Tier
The user's billing level: `free`, `pro`, `enterprise`
(`app/models/user.py` — `UserTier`). Only `free` is active; `pro` and
`enterprise` are marked scaffold/inactive in source.

### Gate (Billing Gate)
A tier-based permission check applied before a metered action — which portals
are usable, whether the daily application cap is reached, whether the paid LLM
API may be called (`app/billing/gates.py`). "Gate" in this codebase means a
billing entitlement check, not a CI/quality gate.

### Anti-Detection
The set of human-behaviour simulations (randomized user agent and viewport,
delays, typing cadence, scrolling, stealth context) applied to crawler browser
sessions (`app/crawlers/anti_detection.py`). It also encodes per-portal request
rate limits.

### Consent (DPDPA)
A recorded, timestamped user permission required under India's Digital Personal
Data Protection Act, stored as an auditable record
(`app/compliance/dpdpa.py` — `ConsentRecord`; `app/compliance/consent_store.py`).

### Deletion Mode
How a data-deletion request is honoured: `hard` (erase), `soft` (mark deleted),
or `anonymise` (retain records with identifiers stripped)
(`app/compliance/deletion.py` — `DeletionMode`).

### Screening Q&A
Portal-specific questions asked during an application (for example notice
period or expected salary) and the user's stored answers, reused to complete
future applications (`app/tenant_models/screening_qa.py`,
`app/services/screening_service.py`).

### Audit
An append-only record of a security- or compliance-relevant action
(`app/security/audit_log.py` — `audit`). It is the single most widely used
function in the codebase (fan-in 80).
