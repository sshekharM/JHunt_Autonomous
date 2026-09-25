# CHG-007 — DPDPA consent withdrawal (R11 follow-up)

## Problem

Consent is captured once, at onboarding step 9 (`record_consent`, CHG R11), and
there is no way to take it back. DPDP Act 2023 s.6(4) requires that withdrawing
consent is as easy as giving it, and that processing based on the withdrawn
consent stops. Today nothing checks consent before the auto-apply task runs or
before a user's resume is sent to an LLM provider.

## Acceptance criteria

1. `consent_records` stays append-only. Migration `0006` (down_revision `0005`)
   adds `event` (string, NOT NULL, server default `'granted'`); existing rows
   read as `'granted'`. Its downgrade drops the column again.
2. `current_consent(user_id, db)` returns the user's latest consent record, or
   `None` when there is none. `consent_history(user_id, db)` returns every
   record, oldest first.
3. `withdraw_consent(user_id, scopes, ip, ua, db)` with scopes drawn from
   `auto_apply`, `llm_processing`, `data_processing` writes one **new** row with
   `event='withdrawn'`: the withdrawn scopes are False, the other flags,
   `llm_choice`, `consent_version` and `consent_text_hash` are copied from the
   latest record, and `ip_address`/`user_agent` come from the request. No
   existing row is changed or deleted.
4. The withdrawal writes the audit event `consent.withdrawn` with the user id
   and the withdrawn scopes only — no IP address or user agent.
5. Withdrawing scopes that are already withdrawn writes no row and no audit
   event and still succeeds. The user row is read with `SELECT … FOR UPDATE`
   first, so two withdrawals at once cannot copy a stale flag back to True.
6. `GET /api/consent` (logged-in user) returns the current flags and the
   history (event, flags, timestamp) — no IP address or user agent.
7. `POST /api/consent/withdraw` with body `{"scopes": [...]}` withdraws them and
   returns 200 with the current flags. An empty list or an unknown scope is
   422. A user with no consent on record gets 409. Both endpoints need a
   logged-in user (401 otherwise) and the router is registered in `app.main`.
8. Withdrawing `auto_apply` sets the user's tenant preference
   `auto_apply_enabled` to False, and `apply_matched_jobs` does nothing for a
   user whose current consent does not allow auto-apply. It writes the audit
   event `consent.enforced` with the scope.
9. When the current consent does not allow `llm_processing`, the auto-apply
   task does not tailor resumes or write cover letters (the only paths that
   send the user's data to an LLM provider); it stops before loading jobs and
   writes `consent.enforced`. Queuing jobs for human review (HITL), which uses
   no LLM, still runs.
10. Withdrawing `data_processing` schedules the account for deletion through
    the existing `execute_deletion(user, DeletionMode.soft_delete, db)` entry
    point in `app/compliance/deletion.py` (which is not changed). The response
    carries the deletion summary.
11. Every consent check requires `data_processing` as well as the scope, and a
    user with no consent record is refused (fail closed).

## Out of scope

- Granting consent again after a withdrawal. There is no re-grant endpoint,
  and onboarding step 9 now returns 409 once onboarding is complete so it
  cannot be replayed as one. A user who wants auto-apply back must be handled
  in a later story.
- A UI for withdrawal. This story adds the API only.
- Changing `app/compliance/deletion.py`. Its soft delete deactivates the user
  and audits a 30-day deadline, but it does not write
  `users.scheduled_deletion_at` and no job purges accounts after the deadline.
  That gap is pre-existing (it affects `DELETE /api/applications/account` the
  same way) and needs explicit human approval to fix (R12).
- `screening_service.answer_screening_question` also calls an LLM but has no
  caller in the app today; it is not gated here.

## Implementation Status

Status: COMPLETE (review fixes applied; see specs/reviews/)
Implemented: 2026-09-25 (branch `feat/totp-and-consent`)
Files changed: alembic/versions/0006_consent_withdrawal.py (new),
app/compliance/dpdpa.py, app/compliance/consent_store.py,
app/services/consent_service.py (new), app/schemas/consent.py (new),
app/routers/consent.py (new), app/main.py, app/tasks/auto_apply.py,
app/routers/onboarding.py (step 9 replay guard). Not changed:
app/compliance/deletion.py.
Tests added/updated: tests/unit/test_0006_consent_withdrawal.py,
tests/unit/test_dpdpa.py, tests/unit/test_consent_withdrawal.py,
tests/unit/test_consent_service.py, tests/unit/test_consent.py,
tests/unit/test_auto_apply.py, tests/unit/test_onboarding.py,
tests/unit/test_0003_align_shared_schema_with_models.py (chain to 0006),
tests/integration/test_consent_withdrawal_db.py (RUN_DB_TESTS=1 only).
Characterisation pins: tests/unit/test_main.py, tests/unit/test_auto_apply_pins.py.
AC coverage:
  - AC1: test_upgrade_adds_event_and_existing_rows_read_as_granted,
    test_downgrade_removes_exactly_what_upgrade_added (0006),
    test_consent_record_event_column_is_required_and_defaults_to_granted,
    test_head_has_exactly_the_model_tables_and_columns
  - AC2: test_current_consent_returns_the_latest_record_for_the_user,
    test_current_consent_is_none_without_a_record,
    test_consent_history_returns_every_record_oldest_first
  - AC3: test_withdrawal_appends_a_new_row_and_leaves_the_old_one_alone,
    test_withdrawal_carries_scopes_already_withdrawn_earlier,
    test_withdrawal_sorts_after_the_record_it_replaces_even_if_this_clock_is_behind
  - AC4: test_withdrawal_is_audited_with_user_and_scopes_only
  - AC5: test_withdrawing_an_already_withdrawn_scope_writes_nothing,
    test_withdrawal_locks_the_user_row_before_reading_consent,
    test_withdrawal_without_consent_on_record_is_refused
  - AC6: test_get_consent_shows_current_flags_and_history_without_network_identifiers,
    test_get_consent_without_any_record,
    test_current_flags_come_from_the_enforced_current_consent
  - AC7: test_withdraw_passes_the_request_details_and_returns_the_new_flags,
    test_bad_scope_lists_are_422_and_never_reach_the_service[*],
    test_withdraw_without_consent_on_record_is_409,
    test_endpoints_need_a_logged_in_user[*], test_the_router_is_registered_in_the_app,
    test_an_oversized_user_agent_is_cut_to_the_column_size
  - AC8: test_withdrawing_auto_apply_switches_the_preference_off,
    test_without_auto_apply_consent_nothing_of_the_user_is_touched[auto_apply_withdrawn],
    test_a_retry_after_a_failed_side_effect_completes_it
  - AC9: test_llm_withdrawn_stops_before_any_job_is_loaded,
    test_llm_withdrawn_still_queues_jobs_for_human_review,
    test_a_withdrawal_during_the_run_stops_llm_use_for_the_remaining_jobs,
    test_full_consent_goes_on_to_the_resume_tailoring_path
  - AC10: test_withdrawing_data_processing_schedules_account_deletion,
    test_withdrawing_data_processing_returns_the_deletion_summary
  - AC11: test_withdrawn_data_processing_stops_every_scope[*],
    test_no_consent_record_allows_nothing[*], test_an_unknown_scope_is_not_allowed,
    test_without_auto_apply_consent_nothing_of_the_user_is_touched[*]
  - Step 9 replay guard: test_step9_cannot_be_replayed_to_grant_consent_again

Known limits (not fixed here):
  - Reversibility of 0006 proven on SQLite only; no Docker/PostgreSQL was
    available to run the PostgreSQL round trip or the concurrency of the lock.
  - Soft delete (deletion.py) does not write `scheduled_deletion_at` and no
    job purges accounts after 30 days (R12, needs human approval).
  - Deploy order: run `alembic upgrade head` before starting this code; the
    model reads `consent_records.event`.
