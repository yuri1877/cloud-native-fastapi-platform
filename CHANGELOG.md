# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Repository bootstrap (Phase 1): directory layout, tooling configuration, project documents.
- FastAPI application skeleton (Phase 2): app factory, typed settings, JSON logging
  foundation, centralised error contract, `/health/live` and `/health/ready`.
- Configuration (Phase 3): database settings with pool tuning, `DATABASE_URL` held as a secret,
  required in staging/prod, validation errors that never echo input values.
- Database layer (Phase 4): async engine and session factory, `User` model, Alembic (async env,
  initial `users` migration), database-aware `/health/ready` (503 `NOT_READY` on failure),
  integration tests against an isolated `TEST_DATABASE_URL` database.
- User domain (Phase 5): full CRUD, case-insensitive unique email, pagination, deterministic
  ordering (created_at, id), `PATCH` semantics that require at least one non-null field.
- Order domain (Phase 6): full CRUD, integer minor-unit money (never float), ISO 4217 currency
  validation, PENDING -> PROCESSING/CANCELLED -> COMPLETED/CANCELLED status machine, amount only
  editable while PENDING, deletion restricted to PENDING/CANCELLED, filtering by user_id/status.
- Error handling (Phase 7): AuthenticationException (401 + WWW-Authenticate) and
  AuthorizationException (403) added to the exception hierarchy ahead of Phases 9-10; full test
  coverage of the standard error shape across every error path.
