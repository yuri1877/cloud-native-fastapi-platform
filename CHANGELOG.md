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
