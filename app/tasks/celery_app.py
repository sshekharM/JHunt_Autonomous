from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "jhans",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.crawl_jobs",
        "app.tasks.match_jobs",
        "app.tasks.auto_apply",
        "app.tasks.status_check",
        "app.tasks.notify",
        "app.tasks.ml_retrain",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    worker_max_tasks_per_child=50,
)

celery_app.conf.beat_schedule = {
    "crawl-naukri": {
        "task": "app.tasks.crawl_jobs.crawl_portal",
        "schedule": crontab(minute=0, hour="*/4"),
        "args": ("naukri",),
    },
    "crawl-linkedin": {
        "task": "app.tasks.crawl_jobs.crawl_portal",
        "schedule": crontab(minute=15, hour="*/4"),
        "args": ("linkedin",),
    },
    "crawl-glassdoor": {
        "task": "app.tasks.crawl_jobs.crawl_portal",
        "schedule": crontab(minute=30, hour="*/4"),
        "args": ("glassdoor",),
    },
    "crawl-indeed": {
        "task": "app.tasks.crawl_jobs.crawl_portal",
        "schedule": crontab(minute=45, hour="*/4"),
        "args": ("indeed",),
    },
    "match-jobs-hourly": {
        "task": "app.tasks.match_jobs.match_all_users",
        "schedule": crontab(minute=0, hour="*"),
    },
    "auto-apply-every-6h": {
        "task": "app.tasks.auto_apply.run_auto_apply_for_all",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    "status-check-daily": {
        "task": "app.tasks.status_check.check_all_application_statuses",
        "schedule": crontab(minute=0, hour=9),
    },
    "ml-retrain-nightly": {
        "task": "app.tasks.ml_retrain.retrain_all_user_models",
        "schedule": crontab(minute=0, hour=2),
    },
}
