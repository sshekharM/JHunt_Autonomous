"""Initial shared schema tables.

Creates: users, admin_users, skill_taxonomy, consent_records, jobs,
         system_portal_accounts and all required enum types.

Revision ID: 0001_initial_shared_schema
Revises: (none)
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_shared_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Enum types --------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE oauth_provider_enum AS ENUM
                ('google', 'linkedin', 'facebook', 'microsoft');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_tier_enum AS ENUM
                ('free', 'pro', 'enterprise');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE taxonomy_source_enum AS ENUM
                ('esco', 'onet', 'dynamic_discovery', 'manual');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE taxonomy_status_enum AS ENUM
                ('active', 'pending_review', 'rejected');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE admin_role_enum AS ENUM
                ('super_admin', 'ops_admin', 'content_admin', 'support_admin');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE portal_name_enum AS ENUM
                ('naukri', 'linkedin', 'glassdoor', 'indeed', 'monster', 'shine');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE portal_account_health_enum AS ENUM
                ('healthy', 'degraded', 'blocked', 'unknown');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # --- users -------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email_hash", sa.String(64), nullable=False),
        sa.Column("email_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("thumbprint", sa.String(64), nullable=False),
        sa.Column("schema_name", sa.String(70), nullable=False),
        sa.Column(
            "oauth_provider",
            postgresql.ENUM("google", "linkedin", "facebook", "microsoft",
                            name="oauth_provider_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("oauth_sub", sa.String(256), nullable=False),
        sa.Column("totp_secret", sa.String(64), nullable=False),
        sa.Column("totp_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("onboarding_complete", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("onboarding_step", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "tier",
            postgresql.ENUM("free", "pro", "enterprise",
                            name="user_tier_enum", create_type=False),
            nullable=False,
            server_default="free",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("email_hash", name="uq_users_email_hash"),
        sa.UniqueConstraint("thumbprint", name="uq_users_thumbprint"),
        sa.UniqueConstraint("schema_name", name="uq_users_schema_name"),
    )
    op.create_index("ix_users_email_hash", "users", ["email_hash"])
    op.create_index("ix_users_thumbprint", "users", ["thumbprint"])

    # --- admin_users -------------------------------------------------------
    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email_hash", sa.String(64), nullable=False),
        sa.Column("email_encrypted", sa.LargeBinary, nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("super_admin", "ops_admin", "content_admin", "support_admin",
                            name="admin_role_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("totp_secret", sa.String(64), nullable=False),
        sa.Column("totp_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email_hash", name="uq_admin_users_email_hash"),
    )
    op.create_index("ix_admin_users_email_hash", "admin_users", ["email_hash"])

    # --- skill_taxonomy ----------------------------------------------------
    op.create_table(
        "skill_taxonomy",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("skill_name", sa.String(256), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("subcategory", sa.String(128), nullable=True),
        sa.Column(
            "source",
            postgresql.ENUM("esco", "onet", "dynamic_discovery", "manual",
                            name="taxonomy_source_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("active", "pending_review", "rejected",
                            name="taxonomy_status_enum", create_type=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column("auto_suggested_category", sa.String(128), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("esco_uri", sa.String(512), nullable=True),
        sa.Column("onet_code", sa.String(32), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("skill_name", name="uq_skill_taxonomy_skill_name"),
    )
    op.create_index("ix_skill_taxonomy_skill_name", "skill_taxonomy", ["skill_name"])

    # --- consent_records ---------------------------------------------------
    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("consent_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=False),
        sa.Column("consented_to_data_processing", sa.Boolean, nullable=False),
        sa.Column("consented_to_auto_apply", sa.Boolean, nullable=False),
        sa.Column("consented_to_llm_processing", sa.Boolean, nullable=False),
        sa.Column("llm_choice", sa.String(32), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])

    # --- jobs (shared / global crawled jobs) --------------------------------
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("portal", sa.String(32), nullable=False),
        sa.Column("portal_job_id", sa.String(256), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("company", sa.String(256), nullable=False),
        sa.Column("location", sa.String(256), nullable=False),
        sa.Column("job_url", sa.String(1024), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("skills_required", postgresql.JSONB, nullable=False,
                  server_default="[]"),
        sa.Column("salary_range", sa.String(256), nullable=False, server_default=""),
        sa.Column("experience_required", sa.String(128), nullable=False, server_default=""),
        sa.Column("is_easy_apply", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("portal", "portal_job_id", name="uq_job_portal_id"),
    )
    op.create_index("ix_jobs_portal", "jobs", ["portal"])
    op.create_index("ix_jobs_portal_job_id", "jobs", ["portal_job_id"])
    op.create_index("ix_jobs_company", "jobs", ["company"])
    op.create_index("ix_jobs_is_active", "jobs", ["is_active"])
    op.create_index("ix_jobs_crawled_at", "jobs", ["crawled_at"])

    # --- system_portal_accounts --------------------------------------------
    op.create_table(
        "system_portal_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "portal",
            postgresql.ENUM("naukri", "linkedin", "glassdoor", "indeed", "monster", "shine",
                            name="portal_name_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("email_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("password_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("session_cookies_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "health",
            postgresql.ENUM("healthy", "degraded", "blocked", "unknown",
                            name="portal_account_health_enum", create_type=False),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_crawl", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("portal", name="uq_system_portal_accounts_portal"),
    )


def downgrade() -> None:
    op.drop_table("system_portal_accounts")
    op.drop_table("jobs")
    op.drop_table("consent_records")
    op.drop_table("skill_taxonomy")
    op.drop_table("admin_users")
    op.drop_table("users")

    for enum_name in (
        "portal_account_health_enum",
        "portal_name_enum",
        "admin_role_enum",
        "taxonomy_status_enum",
        "taxonomy_source_enum",
        "user_tier_enum",
        "oauth_provider_enum",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
