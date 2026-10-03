# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Repository bootstrap (Phase 1): directory layout, tooling configuration, project documents.
- FastAPI application skeleton (Phase 2): app factory, typed settings, JSON logging
  foundation, centralised error contract, `/health/live` and `/health/ready`.
- Configuration (Phase 3): database settings with pool tuning, `DATABASE_URL` held as  a  
  secret, required in staging/prod, validation errors that never echo input values.
- Database layer (Phase 4): async engine and session factory, `User` model, Alembic
  (async env, initial `users` migration), database-aware `/health/ready` (503 `NOT_READY` on failure),
  integration tests against an isolated `TEST_DATABASE_URL` database.
- User domain (Phase 5): full CRUD, case-insensitive unique email, pagination, deterministic
  ordering (created_at, id), `PATCH` semantics that require at least one non-null field.
- Order domain (Phase 6): full CRUD, integer minor-unit money (never float), ISO 4217
  currency validation, PENDING -> PROCESSING/CANCELLED -> COMPLETED/CANCELLED status machine, amount only editable while PENDING, deletion restricted to PENDING/CANCELLED, filtering by user_id/status.
- Error handling (Phase 7): AuthenticationException (401 + WWW-Authenticate) and
  AuthorizationException (403) added to the exception hierarchy ahead of Phases 9-10; full test coverage of the standard error shape across every error path.
- Request correlation (Phase 8): `RequestIDMiddleware` reads a safely-formatted inbound
  `X-Request-ID` or generates one, exposes it via request state and a contextvar, returns it on every response (success and error), and includes it (plus a placeholder `trace_id`) in every structured log line. Inbound IDs are validated against an allowlist and never trusted as a security identity.
- Authentication (Phase 9): Fix `get_current_principal` was reading settings via the globally
  cached `get_settings()` (environment-variable derived) instead of the app's own
  `Settings` instance, so an app built from an explicit `Settings` object (as tests do)
  could silently validate against the wrong OIDC configuration. Introduced
  `get_app_settings()`, reading `request.app.state.settings`; `create_app()` now stores
  the settings it was built with on `app.state`.
- Authorization (Phase 10): Implement authentication using a standard OIDC/OAuth2
  JWT-compatible approach.
