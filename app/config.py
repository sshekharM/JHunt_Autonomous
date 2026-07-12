from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_env: str = "development"
    app_secret_key: str
    app_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "jhans"
    postgres_user: str = "jhans"
    postgres_password: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str
    minio_bucket_resumes: str = "jhans-resumes"
    minio_secure: bool = False

    # Encryption
    fernet_key: str

    # OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    facebook_client_id: str = ""
    facebook_client_secret: str = ""
    # Microsoft External ID — inactive at launch
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = ""

    # LLM
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Notifications
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    discord_bot_token: str = ""
    discord_guild_id: str = ""

    # Email
    email_provider: str = "smtp"
    sendgrid_api_key: str = ""
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "noreply@jhans.local"

    # Security
    allowed_ips: str = "127.0.0.1"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 8
    totp_issuer: str = "jH_ANS"

    @property
    def allowed_ip_list(self) -> List[str]:
        return [ip.strip() for ip in self.allowed_ips.split(",")]

    # Retention
    resume_retention_days: int = 0  # 0 = disabled

    # Crawling
    crawl_max_concurrency: int = 5
    crawl_interval_hours: int = 4

    # System portal accounts
    naukri_system_email: str = ""
    naukri_system_password: str = ""
    linkedin_system_email: str = ""
    linkedin_system_password: str = ""
    glassdoor_system_email: str = ""
    glassdoor_system_password: str = ""
    indeed_system_email: str = ""
    indeed_system_password: str = ""
    monster_system_email: str = ""
    monster_system_password: str = ""
    shine_system_email: str = ""
    shine_system_password: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
