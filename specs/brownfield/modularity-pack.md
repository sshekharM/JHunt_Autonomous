# Modularity review pack

Deterministic evidence from the code-graph. Judge each against the source; 
do not flag a `likely-legitimate` hub as a god module without a concrete reason.

## Hubs (25)
- `app/security/audit_log.py` — fan-in 80, instability 0 — review for misplaced responsibility
- `app/database.py` — fan-in 78, instability 0.013 — review for misplaced responsibility
- `app/crawlers/anti_detection.py` — fan-in 68, instability 0 — review for misplaced responsibility
- `alembic/__init__.py` — fan-in 49, instability 0 — review for misplaced responsibility
- `app/crawlers/base.py` — fan-in 39, instability 0 — review for misplaced responsibility
- `app/billing/gates.py` — fan-in 33, instability 0.154 — review for misplaced responsibility
- `app/ml/matcher.py` — fan-in 32, instability 0 — review for misplaced responsibility
- `app/services/job_service.py` — fan-in 31, instability 0.088 — review for misplaced responsibility
- `app/ml/taxonomy_discovery.py` — fan-in 29, instability 0.065 — review for misplaced responsibility
- `app/services/__init__.py` — fan-in 29, instability 0 — review for misplaced responsibility
- `app/security/encryption.py` — fan-in 27, instability 0.036 — review for misplaced responsibility
- `app/models/user.py` — fan-in 27, instability 0.036 — likely-legitimate (name suggests factory/schema/util)
- `app/tenant_models/profile.py` — fan-in 24, instability 0 — likely-legitimate (name suggests factory/schema/util)
- `app/config.py` — fan-in 24, instability 0 — likely-legitimate (name suggests factory/schema/util)
- `app/dependencies.py` — fan-in 22, instability 0.214 — review for misplaced responsibility
- `app/services/application_service.py` — fan-in 19, instability 0.587 — review for misplaced responsibility
- `app/routers/applications.py` — fan-in 18, instability 0.55 — review for misplaced responsibility
- `app/tenant_models/application.py` — fan-in 18, instability 0.053 — likely-legitimate (name suggests factory/schema/util)
- `app/crawlers/session_manager.py` — fan-in 16, instability 0.484 — review for misplaced responsibility
- `app/crawlers/indeed.py` — fan-in 15, instability 0.583 — review for misplaced responsibility
- `installer/core/env_writer.py` — fan-in 14, instability 0 — review for misplaced responsibility
- `app/compliance/deletion.py` — fan-in 13, instability 0.278 — review for misplaced responsibility
- `app/billing/plans.py` — fan-in 12, instability 0 — review for misplaced responsibility
- `app/crawlers/naukri.py` — fan-in 11, instability 0.703 — review for misplaced responsibility
- `app/services/resume_service.py` — fan-in 11, instability 0.476 — review for misplaced responsibility

## Import cycles (0)

## Duplication candidates (3)
- same imports: `app/crawlers/glassdoor.py`, `app/crawlers/indeed.py`, `app/crawlers/linkedin.py`
- same imports: `app/crawlers/monster.py`, `app/crawlers/shine.py`
- same imports: `installer/pages/install.py`, `installer/pages/prerequisites.py`
