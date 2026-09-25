# Dependency Graph

```mermaid
flowchart LR
    py_alembic___init___py["__init__.py"]
    py_alembic_env_py["env.py"]
    py_alembic_versions_0001_initial_shared_schema_py["0001_initial_shared_schema.py"]
    py_alembic_versions_0002_phase4_columns_py["0002_phase4_columns.py"]
    py_app___init___py["__init__.py"]
    py_app_billing___init___py["__init__.py"]
    py_app_billing_gates_py["gates.py"]
    py_app_billing_plans_py["plans.py"]
    py_app_billing_stripe_client_py["stripe_client.py"]
    py_app_compliance_consent_store_py["consent_store.py"]
    py_app_compliance_deletion_py["deletion.py"]
    py_app_compliance_dpdpa_py["dpdpa.py"]
    py_app_config_py["config.py"]
    py_app_crawlers_anti_detection_py["anti_detection.py"]
    py_app_crawlers_base_py["base.py"]
    py_app_crawlers_glassdoor_py["glassdoor.py"]
    py_app_crawlers_indeed_py["indeed.py"]
    py_app_crawlers_linkedin_py["linkedin.py"]
    py_app_crawlers_naukri_py["naukri.py"]
    py_app_crawlers_session_manager_py["session_manager.py"]
    py_app_database_py["database.py"]
    py_app_dependencies_py["dependencies.py"]
    py_app_llm___init___py["__init__.py"]
    py_app_llm_cover_letter_prompt_py["cover_letter_prompt.py"]
    py_app_llm_resume_prompt_py["resume_prompt.py"]
    py_app_main_py["main.py"]
    py_app_ml_explainer_py["explainer.py"]
    py_app_ml_feedback_py["feedback.py"]
    py_app_ml_matcher_py["matcher.py"]
    py_app_ml_taxonomy_discovery_py["taxonomy_discovery.py"]
    py_app_models___init___py["__init__.py"]
    py_app_models_admin_py["admin.py"]
    py_app_models_job_py["job.py"]
    py_app_models_portal_account_py["portal_account.py"]
    py_app_models_skill_taxonomy_py["skill_taxonomy.py"]
    py_app_models_user_py["user.py"]
    py_app_notifications___init___py["__init__.py"]
    py_app_routers___init___py["__init__.py"]
    py_app_routers_admin___init___py["__init__.py"]
    py_app_routers_applications_py["applications.py"]
    py_app_routers_notifications_py["notifications.py"]
    py_app_security_audit_log_py["audit_log.py"]
    py_app_security_encryption_py["encryption.py"]
    py_app_security_rate_limiter_py["rate_limiter.py"]
    py_app_security_totp_py["totp.py"]
    py_app_services___init___py["__init__.py"]
    py_app_services_application_service_py["application_service.py"]
    py_app_services_auth_service_py["auth_service.py"]
    py_app_services_job_service_py["job_service.py"]
    py_app_services_notification_service_py["notification_service.py"]
    py_app_services_resume_service_py["resume_service.py"]
    py_app_services_storage_service_py["storage_service.py"]
    py_app_services_taxonomy_service_py["taxonomy_service.py"]
    py_app_tasks_celery_app_py["celery_app.py"]
    py_app_tasks_crawl_jobs_py["crawl_jobs.py"]
    py_app_tasks_match_jobs_py["match_jobs.py"]
    py_app_tasks_notify_py["notify.py"]
    py_app_tenant_models___init___py["__init__.py"]
    py_app_tenant_models_application_py["application.py"]
    py_app_tenant_models_job_py["job.py"]
    py_app_tenant_models_ml_feedback_py["ml_feedback.py"]
    py_app_tenant_models_notification_py["notification.py"]
    py_app_tenant_models_profile_py["profile.py"]
    py_app_tenant_models_resume_py["resume.py"]
    py_app_tenant_models_screening_qa_py["screening_qa.py"]
    py_app_tenant_models_skill_py["skill.py"]
    py_installer_core___init___py["__init__.py"]
    py_installer_core_env_writer_py["env_writer.py"]
    py_installer_core_prereq_checker_py["prereq_checker.py"]
    py_installer_pages_admin_py["admin.py"]
    py_installer_pages_base_py["base.py"]
    py_installer_pages_database_py["database.py"]
    py_installer_pages_install_py["install.py"]
    py_installer_pages_install_dir_py["install_dir.py"]
    py_installer_pages_llm_py["llm.py"]
    py_installer_pages_notifications_py["notifications.py"]
    py_installer_pages_oauth_py["oauth.py"]
    py_installer_pages_portals_py["portals.py"]
    py_installer_pages_prerequisites_py["prerequisites.py"]
    py_installer_pages_welcome_py["welcome.py"]
    py_alembic_env_py -->|imports| py_alembic___init___py
    py_alembic_env_py -->|imports| py_app_config_py
    py_alembic_env_py -->|imports| py_app_database_py
    py_alembic_env_py -->|imports| py_app_models___init___py
    py_alembic_env_py -->|imports| py_app_compliance_dpdpa_py
    py_alembic_env_py -->|imports| py_app_tenant_models_profile_py
    py_alembic_env_py -->|imports| py_app_tenant_models___init___py
    py_alembic_env_py -->|calls| py_alembic___init___py
    py_alembic_versions_0001_initial_shared_schema_py -->|imports| py_alembic___init___py
    py_alembic_versions_0001_initial_shared_schema_py -->|calls| py_alembic___init___py
    py_alembic_versions_0002_phase4_columns_py -->|imports| py_alembic___init___py
    py_alembic_versions_0002_phase4_columns_py -->|calls| py_alembic___init___py
    py_app_billing_gates_py -->|imports| py_app_models_user_py
    py_app_billing_gates_py -->|imports| py_app_billing_plans_py
    py_app_billing_gates_py -->|calls| py_app_billing_plans_py
    py_app_compliance_consent_store_py -->|imports| py_app_compliance_dpdpa_py
    py_app_compliance_consent_store_py -->|calls| py_app_compliance_dpdpa_py
    py_app_compliance_deletion_py -->|imports| py_app_models_user_py
    py_app_compliance_deletion_py -->|imports| py_app_security_audit_log_py
    py_app_compliance_deletion_py -->|calls| py_app_security_audit_log_py
    py_app_compliance_dpdpa_py -->|imports| py_app_database_py
    py_app_crawlers_glassdoor_py -->|imports| py_app_crawlers_base_py
    py_app_crawlers_glassdoor_py -->|imports| py_app_crawlers_anti_detection_py
    py_app_crawlers_glassdoor_py -->|imports| py_app_crawlers_session_manager_py
    py_app_crawlers_glassdoor_py -->|imports| py_app_security_audit_log_py
    py_app_crawlers_glassdoor_py -->|imports| py_app_config_py
    py_app_crawlers_glassdoor_py -->|calls| py_app_crawlers_anti_detection_py
    py_app_crawlers_glassdoor_py -->|calls| py_app_security_audit_log_py
    py_app_crawlers_glassdoor_py -->|calls| py_app_crawlers_session_manager_py
    py_app_crawlers_glassdoor_py -->|calls| py_app_crawlers_base_py
    py_app_crawlers_indeed_py -->|imports| py_app_crawlers_base_py
    py_app_crawlers_indeed_py -->|imports| py_app_crawlers_anti_detection_py
    py_app_crawlers_indeed_py -->|imports| py_app_crawlers_session_manager_py
    py_app_crawlers_indeed_py -->|imports| py_app_security_audit_log_py
    py_app_crawlers_indeed_py -->|imports| py_app_config_py
    py_app_crawlers_indeed_py -->|calls| py_app_crawlers_anti_detection_py
    py_app_crawlers_indeed_py -->|calls| py_app_security_audit_log_py
    py_app_crawlers_indeed_py -->|calls| py_app_crawlers_session_manager_py
    py_app_crawlers_indeed_py -->|calls| py_app_crawlers_base_py
    py_app_crawlers_linkedin_py -->|imports| py_app_crawlers_base_py
    py_app_crawlers_linkedin_py -->|imports| py_app_crawlers_anti_detection_py
    py_app_crawlers_linkedin_py -->|imports| py_app_crawlers_session_manager_py
    py_app_crawlers_linkedin_py -->|imports| py_app_security_audit_log_py
    py_app_crawlers_linkedin_py -->|imports| py_app_config_py
    py_app_crawlers_linkedin_py -->|calls| py_app_crawlers_anti_detection_py
    py_app_crawlers_linkedin_py -->|calls| py_app_security_audit_log_py
    py_app_crawlers_linkedin_py -->|calls| py_app_crawlers_session_manager_py
    py_app_crawlers_linkedin_py -->|calls| py_app_crawlers_base_py
    py_app_crawlers_naukri_py -->|imports| py_app_crawlers_base_py
    py_app_crawlers_naukri_py -->|imports| py_app_crawlers_anti_detection_py
    py_app_crawlers_naukri_py -->|imports| py_app_crawlers_session_manager_py
    py_app_crawlers_naukri_py -->|imports| py_app_security_audit_log_py
    py_app_crawlers_naukri_py -->|imports| py_app_config_py
    py_app_crawlers_naukri_py -->|imports| py_app_security_encryption_py
    py_app_crawlers_naukri_py -->|calls| py_app_crawlers_anti_detection_py
    py_app_crawlers_naukri_py -->|calls| py_app_security_audit_log_py
    py_app_crawlers_naukri_py -->|calls| py_app_crawlers_session_manager_py
    py_app_crawlers_naukri_py -->|calls| py_app_crawlers_base_py
    py_app_crawlers_session_manager_py -->|imports| py_app_config_py
    py_app_crawlers_session_manager_py -->|imports| py_app_security_encryption_py
    py_app_crawlers_session_manager_py -->|imports| py_app_crawlers_anti_detection_py
    py_app_crawlers_session_manager_py -->|imports| py_app_security_audit_log_py
    py_app_crawlers_session_manager_py -->|imports| py_app_database_py
    py_app_crawlers_session_manager_py -->|imports| py_app_services___init___py
    py_app_crawlers_session_manager_py -->|calls| py_app_crawlers_anti_detection_py
    py_app_crawlers_session_manager_py -->|calls| py_app_security_encryption_py
    py_app_crawlers_session_manager_py -->|calls| py_app_security_audit_log_py
    py_app_crawlers_session_manager_py -->|calls| py_app_database_py
    py_app_crawlers_session_manager_py -->|calls| py_app_services___init___py
    py_app_database_py -->|imports| py_app_config_py
    py_app_dependencies_py -->|imports| py_app_database_py
    py_app_dependencies_py -->|imports| py_app_models_user_py
    py_app_dependencies_py -->|imports| py_app_models_admin_py
    py_app_dependencies_py -->|imports| py_app_services_auth_service_py
    py_app_dependencies_py -->|calls| py_app_services_auth_service_py
    py_app_main_py -->|imports| py_app_config_py
    py_app_main_py -->|imports| py_app_security_rate_limiter_py
    py_app_main_py -->|imports| py_app_routers___init___py
    py_app_main_py -->|imports| py_app_routers_applications_py
    py_app_main_py -->|imports| py_app_routers_admin___init___py
    py_app_ml_feedback_py -->|imports| py_app_tenant_models_ml_feedback_py
    py_app_ml_feedback_py -->|imports| py_app_security_audit_log_py
    py_app_ml_feedback_py -->|calls| py_app_tenant_models_ml_feedback_py
    py_app_ml_feedback_py -->|calls| py_app_security_audit_log_py
    py_app_ml_taxonomy_discovery_py -->|imports| py_app_models_skill_taxonomy_py
    py_app_ml_taxonomy_discovery_py -->|calls| py_app_models_skill_taxonomy_py
    py_app_models_admin_py -->|imports| py_app_database_py
    py_app_models_job_py -->|imports| py_app_database_py
    py_app_models_portal_account_py -->|imports| py_app_database_py
    py_app_models_skill_taxonomy_py -->|imports| py_app_database_py
    py_app_models_user_py -->|imports| py_app_database_py
    py_app_routers_applications_py -->|imports| py_app_compliance_deletion_py
    py_app_routers_applications_py -->|imports| py_app_database_py
    py_app_routers_applications_py -->|imports| py_app_dependencies_py
    py_app_routers_applications_py -->|imports| py_app_models_user_py
    py_app_routers_applications_py -->|imports| py_app_services_application_service_py
    py_app_routers_applications_py -->|imports| py_app_tenant_models_application_py
    py_app_routers_applications_py -->|imports| py_app_tenant_models_profile_py
    py_app_routers_applications_py -->|calls| py_app_database_py
    py_app_routers_applications_py -->|calls| py_app_tenant_models_application_py
    py_app_routers_applications_py -->|calls| py_app_services_application_service_py
    py_app_routers_applications_py -->|calls| py_app_compliance_deletion_py
    py_app_routers_notifications_py -->|imports| py_app_database_py
    py_app_routers_notifications_py -->|imports| py_app_models_user_py
    py_app_routers_notifications_py -->|imports| py_app_dependencies_py
    py_app_routers_notifications_py -->|imports| py_app_services_auth_service_py
    py_app_routers_notifications_py -->|calls| py_app_database_py
    py_app_security_encryption_py -->|imports| py_app_config_py
    py_app_security_totp_py -->|imports| py_app_config_py
    py_app_services_application_service_py -->|imports| py_app_crawlers_base_py
    py_app_services_application_service_py -->|imports| py_app_crawlers_session_manager_py
    py_app_services_application_service_py -->|imports| py_app_ml_feedback_py
    py_app_services_application_service_py -->|imports| py_app_security_audit_log_py
    py_app_services_application_service_py -->|imports| py_app_tenant_models_application_py
    py_app_services_application_service_py -->|imports| py_app_tenant_models_ml_feedback_py
    py_app_services_application_service_py -->|imports| py_app_tenant_models_screening_qa_py
    py_app_services_application_service_py -->|imports| py_app_crawlers_naukri_py
    py_app_services_application_service_py -->|imports| py_app_crawlers_linkedin_py
    py_app_services_application_service_py -->|imports| py_app_crawlers_glassdoor_py
    py_app_services_application_service_py -->|imports| py_app_crawlers_indeed_py
    py_app_services_application_service_py -->|imports| py_app_tenant_models_job_py
    py_app_services_application_service_py -->|imports| py_app_tasks_notify_py
    py_app_services_application_service_py -->|calls| py_app_crawlers_base_py
    py_app_services_application_service_py -->|calls| py_app_tenant_models_application_py
    py_app_services_application_service_py -->|calls| py_app_security_audit_log_py
    py_app_services_application_service_py -->|calls| py_app_crawlers_session_manager_py
    py_app_services_application_service_py -->|calls| py_app_tenant_models_screening_qa_py
    py_app_services_application_service_py -->|calls| py_app_ml_feedback_py
    py_app_services_application_service_py -->|calls| py_app_tasks_notify_py
    py_app_services_auth_service_py -->|imports| py_app_config_py
    py_app_services_auth_service_py -->|imports| py_app_security_encryption_py
    py_app_services_auth_service_py -->|imports| py_app_security_totp_py
    py_app_services_auth_service_py -->|imports| py_app_security_audit_log_py
    py_app_services_auth_service_py -->|calls| py_app_security_encryption_py
    py_app_services_job_service_py -->|imports| py_app_models_job_py
    py_app_services_job_service_py -->|imports| py_app_security_audit_log_py
    py_app_services_job_service_py -->|calls| py_app_security_audit_log_py
    py_app_services_notification_service_py -->|imports| py_app_models_user_py
    py_app_services_notification_service_py -->|imports| py_app_notifications___init___py
    py_app_services_notification_service_py -->|imports| py_app_routers_notifications_py
    py_app_services_notification_service_py -->|imports| py_app_security_encryption_py
    py_app_services_notification_service_py -->|imports| py_app_tenant_models_notification_py
    py_app_services_notification_service_py -->|imports| py_app_tenant_models_profile_py
    py_app_services_notification_service_py -->|calls| py_app_security_encryption_py
    py_app_services_notification_service_py -->|calls| py_app_routers_notifications_py
    py_app_services_notification_service_py -->|calls| py_app_notifications___init___py
    py_app_services_notification_service_py -->|calls| py_app_tenant_models_notification_py
    py_app_services_resume_service_py -->|imports| py_app_config_py
    py_app_services_resume_service_py -->|imports| py_app_llm___init___py
    py_app_services_resume_service_py -->|imports| py_app_llm_resume_prompt_py
    py_app_services_resume_service_py -->|imports| py_app_services_storage_service_py
    py_app_services_resume_service_py -->|imports| py_app_tenant_models_resume_py
    py_app_services_resume_service_py -->|calls| py_app_services_storage_service_py
    py_app_services_resume_service_py -->|calls| py_app_llm_resume_prompt_py
    py_app_services_resume_service_py -->|calls| py_app_llm___init___py
    py_app_services_resume_service_py -->|calls| py_app_tenant_models_resume_py
    py_app_services_storage_service_py -->|imports| py_app_config_py
    py_app_services_taxonomy_service_py -->|imports| py_app_models_skill_taxonomy_py
    py_app_services_taxonomy_service_py -->|imports| py_app_security_audit_log_py
    py_app_services_taxonomy_service_py -->|calls| py_app_security_audit_log_py
    py_app_services_taxonomy_service_py -->|calls| py_app_models_skill_taxonomy_py
    py_app_tasks_celery_app_py -->|imports| py_app_config_py
    py_app_tasks_crawl_jobs_py -->|imports| py_app_tasks_celery_app_py
    py_app_tasks_crawl_jobs_py -->|imports| py_app_security_audit_log_py
    py_app_tasks_crawl_jobs_py -->|imports| py_app_tasks_match_jobs_py
    py_app_tasks_crawl_jobs_py -->|imports| py_app_crawlers_session_manager_py
    py_app_tasks_crawl_jobs_py -->|imports| py_app_database_py
    py_app_tasks_crawl_jobs_py -->|imports| py_app_services_job_service_py
    py_app_tasks_crawl_jobs_py -->|imports| py_app_services_taxonomy_service_py
    py_app_tasks_crawl_jobs_py -->|imports| py_app_models_portal_account_py
    py_app_tasks_crawl_jobs_py -->|calls| py_app_security_audit_log_py
    py_app_tasks_crawl_jobs_py -->|calls| py_app_tasks_match_jobs_py
    py_app_tasks_crawl_jobs_py -->|calls| py_app_database_py
    py_app_tasks_crawl_jobs_py -->|calls| py_app_crawlers_session_manager_py
    py_app_tasks_crawl_jobs_py -->|calls| py_app_services_taxonomy_service_py
    py_app_tasks_crawl_jobs_py -->|calls| py_app_models_portal_account_py
    py_app_tasks_crawl_jobs_py -->|calls| py_app_services_job_service_py
    py_app_tasks_crawl_jobs_py -->|calls| py_app_tasks_celery_app_py
    py_app_tasks_match_jobs_py -->|imports| py_app_tasks_celery_app_py
    py_app_tasks_match_jobs_py -->|imports| py_app_security_audit_log_py
    py_app_tasks_match_jobs_py -->|imports| py_app_database_py
    py_app_tasks_match_jobs_py -->|imports| py_app_services_job_service_py
    py_app_tasks_match_jobs_py -->|imports| py_app_ml_matcher_py
    py_app_tasks_match_jobs_py -->|imports| py_app_ml_feedback_py
    py_app_tasks_match_jobs_py -->|imports| py_app_tenant_models_skill_py
    py_app_tasks_match_jobs_py -->|imports| py_app_tenant_models_job_py
    py_app_tasks_match_jobs_py -->|imports| py_app_models_user_py
    py_app_tasks_match_jobs_py -->|imports| py_app_tasks_notify_py
    py_app_tasks_match_jobs_py -->|calls| py_app_database_py
    py_app_tasks_match_jobs_py -->|calls| py_app_tasks_notify_py
    py_app_tasks_match_jobs_py -->|calls| py_app_services_job_service_py
    py_app_tasks_match_jobs_py -->|calls| py_app_ml_feedback_py
    py_app_tasks_match_jobs_py -->|calls| py_app_tenant_models_job_py
    py_app_tasks_match_jobs_py -->|calls| py_app_ml_matcher_py
    py_app_tasks_match_jobs_py -->|calls| py_app_security_audit_log_py
    py_app_tasks_match_jobs_py -->|calls| py_app_models_user_py
    py_app_tasks_notify_py -->|imports| py_app_database_py
    py_app_tasks_notify_py -->|imports| py_app_tasks_celery_app_py
    py_app_tasks_notify_py -->|imports| py_app_tenant_models_notification_py
    py_app_tasks_notify_py -->|imports| py_app_services___init___py
    py_app_tasks_notify_py -->|calls| py_app_database_py
    py_app_tasks_notify_py -->|calls| py_app_services___init___py
    py_app_tasks_notify_py -->|calls| py_app_tenant_models_notification_py
    py_app_tenant_models_application_py -->|imports| py_app_tenant_models_profile_py
    py_app_tenant_models_job_py -->|imports| py_app_tenant_models_profile_py
    py_app_tenant_models_ml_feedback_py -->|imports| py_app_tenant_models_profile_py
    py_app_tenant_models_notification_py -->|imports| py_app_tenant_models_profile_py
    py_app_tenant_models_resume_py -->|imports| py_app_tenant_models_profile_py
    py_app_tenant_models_screening_qa_py -->|imports| py_app_tenant_models_profile_py
    py_app_tenant_models_skill_py -->|imports| py_app_tenant_models_profile_py
    py_installer_pages_admin_py -->|imports| py_installer_pages_base_py
    py_installer_pages_database_py -->|imports| py_installer_pages_base_py
    py_installer_pages_install_py -->|imports| py_installer_pages_base_py
    py_installer_pages_install_py -->|imports| py_installer_core___init___py
    py_installer_pages_install_py -->|calls| py_installer_core___init___py
    py_installer_pages_install_dir_py -->|imports| py_installer_pages_base_py
    py_installer_pages_llm_py -->|imports| py_installer_pages_base_py
    py_installer_pages_notifications_py -->|imports| py_installer_pages_base_py
    py_installer_pages_oauth_py -->|imports| py_installer_pages_base_py
    py_installer_pages_portals_py -->|imports| py_installer_pages_base_py
    py_installer_pages_prerequisites_py -->|imports| py_installer_pages_base_py
    py_installer_pages_prerequisites_py -->|imports| py_installer_core___init___py
    py_installer_pages_prerequisites_py -->|calls| py_installer_core___init___py
    py_installer_pages_welcome_py -->|imports| py_installer_pages_base_py
```

_Graph rendered with top 80 hubs by fan-in. Full graph: `code-graph.json` (136 nodes, 933 internal edges)._
