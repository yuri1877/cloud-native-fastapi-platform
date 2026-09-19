# CLAUDE_IMPLEMENTATION_PLAN.md

# Claude Implementation Plan

## Cloud-Native FastAPI Platform --- PROJECT_SPEC v1.0

**Target implementation agent:** Claude\
**Specification:** `PROJECT_SPEC_v1.0.md`\
**Implementation style:** Incremental, test-driven, production-oriented\
**Primary objective:** Build the repository exactly against the project
specification while keeping the implementation understandable,
maintainable, secure and portfolio-ready.

------------------------------------------------------------------------

# 1. Mission

Implement the Cloud-Native FastAPI Platform as a complete reference
repository.

Claude must treat `PROJECT_SPEC_v1.0.md` as the source of truth.

Do not prematurely implement every AWS service.

Build vertically in small, verifiable increments.

Every phase must leave the repository in a working state.

------------------------------------------------------------------------

# 2. Implementation Rules

## 2.1 General

Claude must:

-   Read `PROJECT_SPEC_v1.0.md` before making implementation decisions.
-   Prefer simple, explicit designs.
-   Avoid speculative abstractions.
-   Keep application logic independently testable.
-   Keep AWS-specific concerns isolated.
-   Maintain documentation as implementation evolves.
-   Add tests with implementation.
-   Never introduce credentials into source control.
-   Never commit `.env` files containing secrets.
-   Never use long-lived AWS credentials in GitHub Actions.
-   Use OIDC for GitHub-to-AWS authentication.
-   Explain significant deviations from the specification.

## 2.2 Change discipline

For each implementation phase:

1.  Inspect current repository.
2.  Identify relevant specification requirements.
3.  Implement the smallest coherent change.
4.  Add/update tests.
5.  Run formatting.
6.  Run linting.
7.  Run type checking.
8.  Run tests.
9.  Update documentation.
10. Summarize changes and verification.

Do not make unrelated changes.

------------------------------------------------------------------------

# 3. Phase 0 --- Repository Assessment

Before creating code:

``` text
Inspect:
- existing files
- existing git state
- project configuration
- installed tooling
- existing application code
- existing Terraform
- existing documentation
```

Create an implementation baseline.

Expected result:

``` text
Repository understood
Specification understood
Implementation plan understood
No destructive changes made
```

------------------------------------------------------------------------

# 4. Phase 1 --- Repository Bootstrap

Create the initial structure:

``` text
cloud-native-fastapi-platform/
├── app/
├── worker/
├── tests/
├── migrations/
├── terraform/
├── docker/
├── docs/
├── ADR/
├── scripts/
├── load-tests/
└── .github/workflows/
```

Create:

``` text
README.md
LICENSE
CHANGELOG.md
CONTRIBUTING.md
SECURITY.md
.env.example
.gitignore
.dockerignore
pyproject.toml
```

Use `uv` for Python dependency management.

Pin compatible dependency versions.

Initial dependencies should include the minimum required stack:

``` text
fastapi
uvicorn
pydantic
pydantic-settings
sqlalchemy
asyncpg
alembic
pytest
pytest-asyncio
httpx
ruff
```

Add additional dependencies only when required by an implementation
phase.

Verification:

``` bash
uv sync
ruff check .
pytest
```

------------------------------------------------------------------------

# 5. Phase 2 --- FastAPI Application Skeleton

Create:

``` text
app/main.py
app/core/config.py
app/core/logging.py
app/core/exceptions.py
app/api/v1/router.py
```

Implement:

``` text
GET /health/live
GET /health/ready
```

Configure:

-   application metadata
-   API version
-   OpenAPI metadata
-   environment configuration
-   structured logging foundation
-   exception handling foundation

Verify:

``` bash
uv run uvicorn app.main:app --reload
```

Confirm:

``` text
/docs
/openapi.json
/health/live
/health/ready
```

------------------------------------------------------------------------

# 6. Phase 3 --- Configuration

Implement strongly typed configuration using Pydantic Settings.

Required configuration concepts:

``` text
application name
environment
log level
AWS region
database configuration
```

Rules:

-   Development may use `.env`.
-   `.env` must be gitignored.
-   `.env.example` contains placeholders only.
-   Production secrets must not be stored in environment files committed
    to Git.

Add configuration tests.

------------------------------------------------------------------------

# 7. Phase 4 --- Database Layer

Create:

``` text
app/db/
├── database.py
└── session.py

app/models/
└── user.py
```

Implement:

-   SQLAlchemy declarative base
-   async engine
-   async session factory
-   connection pooling
-   clean shutdown

Add Alembic.

Create initial user migration.

Verify:

``` bash
alembic upgrade head
```

Integration tests should use an isolated database.

------------------------------------------------------------------------

# 8. Phase 5 --- User Domain

Create:

``` text
app/schemas/user.py
app/repositories/user_repository.py
app/services/user_service.py
app/api/v1/users.py
```

Implement:

``` text
GET    /api/v1/users
GET    /api/v1/users/{id}
POST   /api/v1/users
PATCH  /api/v1/users/{id}
DELETE /api/v1/users/{id}
```

Implement:

-   validation
-   duplicate email handling
-   not-found handling
-   pagination
-   deterministic ordering
-   appropriate HTTP status codes

Add:

``` text
unit tests
repository tests
API integration tests
```

Do not expose SQLAlchemy entities directly.

------------------------------------------------------------------------

# 9. Phase 6 --- Order Domain

Create:

``` text
app/models/order.py
app/schemas/order.py
app/repositories/order_repository.py
app/services/order_service.py
app/api/v1/orders.py
```

Implement:

``` text
GET    /api/v1/orders
GET    /api/v1/orders/{id}
POST   /api/v1/orders
PATCH  /api/v1/orders/{id}
DELETE /api/v1/orders/{id}
```

Implement:

-   user relationship
-   order status
-   validation
-   monetary representation
-   transactional behaviour
-   not-found handling
-   conflict handling

Do not use floating-point arithmetic for monetary values.

Prefer integer minor units or a suitable decimal representation.

------------------------------------------------------------------------

# 10. Phase 7 --- Error Handling

Create a centralized error model.

Implement:

``` text
AppException
NotFoundException
ConflictException
AuthenticationException
AuthorizationException
```

Implement consistent error serialization.

Every API error should provide:

``` text
code
message
request_id
```

Do not leak:

-   stack traces
-   SQL statements
-   credentials
-   internal exception messages
-   infrastructure details

Add tests for every important error path.

------------------------------------------------------------------------

# 11. Phase 8 --- Request Correlation

Introduce request correlation IDs.

Flow:

``` text
Incoming request
      ↓
Read X-Request-ID if trusted/present
      ↓
Generate one if absent
      ↓
Attach to request context
      ↓
Include in logs
      ↓
Return in response headers
```

Use a safe correlation ID strategy.

Do not trust arbitrary headers as security identities.

Add tests.

------------------------------------------------------------------------

# 12. Phase 9 --- Authentication

Implement authentication using a standard OIDC/OAuth2/JWT-compatible
approach.

Application responsibilities:

-   extract bearer token
-   validate token
-   validate issuer
-   validate audience
-   validate expiry
-   expose authenticated principal

Do not implement password authentication unless explicitly required.

Create:

``` text
app/core/security.py
app/dependencies/auth.py
```

Tests must cover:

-   missing token
-   malformed token
-   expired token
-   invalid issuer
-   invalid audience
-   valid token

------------------------------------------------------------------------

# 13. Phase 10 --- Authorization

Implement a simple RBAC model.

Example conceptual roles:

``` text
user
operator
admin
```

Keep the authorization layer independent from individual route
implementations.

Example:

``` text
Authenticated principal
        ↓
Required permission
        ↓
Allow / deny
```

Document the authorization model.

Add tests for:

-   allowed operation
-   forbidden operation
-   missing role
-   admin privileges

------------------------------------------------------------------------

# 14. Phase 11 --- Event Architecture

Introduce an event abstraction.

Create a domain event model.

Example:

``` text
OrderCreated
```

Required fields:

``` text
event_id
event_type
event_version
occurred_at
source
data
```

Design for:

-   idempotency
-   retries
-   observability
-   schema evolution

Do not tightly couple business logic to AWS SDK calls.

Use an abstraction such as:

``` text
EventPublisher
```

with infrastructure-specific implementations.

------------------------------------------------------------------------

# 15. Phase 12 --- SQS Integration

Implement an SQS adapter.

Expected flow:

``` text
Order Service
     ↓
Event Publisher
     ↓
SQS
     ↓
Worker
```

Implement:

-   message serialization
-   message attributes where useful
-   retry handling
-   visibility timeout considerations
-   dead-letter queue
-   idempotent processing

Create a worker process under:

``` text
worker/
```

Worker must support graceful shutdown.

------------------------------------------------------------------------

# 16. Phase 13 --- EventBridge Integration

Implement EventBridge integration for selected domain events.

Use EventBridge for event routing rather than replacing SQS's role as a
durable work queue.

Document the distinction:

``` text
SQS
→ work distribution / buffering

EventBridge
→ event routing / integration
```

Create an ADR describing this architectural boundary.

------------------------------------------------------------------------

# 17. Phase 14 --- Observability

Implement structured JSON logging.

Required fields:

``` text
timestamp
level
service
environment
request_id
trace_id
logger
message
```

For API requests:

``` text
method
route
status_code
duration_ms
```

Do not log secrets or tokens.

------------------------------------------------------------------------

# 18. Phase 15 --- Metrics

Introduce application metrics.

Minimum metrics:

``` text
http_requests_total
http_request_duration
http_errors_total
database_operation_duration
```

Where practical, use Prometheus-compatible metric naming.

Avoid unbounded/high-cardinality labels.

Document the metrics model.

------------------------------------------------------------------------

# 19. Phase 16 --- Distributed Tracing

Add OpenTelemetry-compatible tracing.

Trace:

``` text
API request
 ↓
service operation
 ↓
database call
 ↓
event publication
```

Propagate trace context into asynchronous processing where practical.

Document trace correlation.

------------------------------------------------------------------------

# 20. Phase 17 --- Docker

Create a production Dockerfile.

Requirements:

-   slim base image
-   pinned dependencies
-   non-root user
-   minimal attack surface
-   no credentials
-   health check strategy
-   deterministic build

Add:

``` text
docker-compose.yml
```

for local development with:

``` text
FastAPI
PostgreSQL
Redis if required
```

Do not add Redis merely for demonstration if no application requirement
exists.

------------------------------------------------------------------------

# 21. Phase 18 --- Automated Testing

Create:

``` text
tests/
├── unit/
├── integration/
├── contract/
└── e2e/
```

Test categories:

### Unit

Business logic.

### Integration

Database and API integration.

### Contract

OpenAPI/API contract.

### E2E

Small number of critical user journeys.

Avoid excessive E2E tests.

------------------------------------------------------------------------

# 22. Phase 19 --- Quality Tooling

Configure:

``` text
Ruff
pytest
mypy or pyright
```

Add project configuration to `pyproject.toml`.

Recommended command set:

``` bash
uv run ruff format .
uv run ruff check .
uv run mypy app
uv run pytest
```

All commands must be reproducible locally and in CI.

------------------------------------------------------------------------

# 23. Phase 20 --- Security Tooling

Introduce appropriate scanning.

At minimum consider:

``` text
dependency vulnerability scanning
secret scanning
SAST
container image scanning
Terraform security scanning
```

Do not add tools purely for appearance.

Each security tool should have a documented purpose.

------------------------------------------------------------------------

# 24. Phase 21 --- Terraform Foundation

Create:

``` text
terraform/
├── modules/
└── environments/
    ├── dev/
    ├── staging/
    └── prod/
```

Create reusable modules.

Initial modules:

``` text
networking
iam
security
```

Establish:

-   provider constraints
-   backend configuration
-   naming conventions
-   tagging
-   variables
-   outputs

Use environment-specific configuration.

------------------------------------------------------------------------

# 25. Phase 22 --- AWS Networking

Implement:

``` text
VPC
public subnets
private application subnets
private database subnets
route tables
internet gateway where required
NAT architecture where required
security groups
```

Requirements:

-   multiple AZs
-   no public database
-   least-privilege ingress
-   least-privilege egress where practical

Document the network architecture.

------------------------------------------------------------------------

# 26. Phase 23 --- Aurora PostgreSQL

Create Aurora Terraform module.

Implement:

-   cluster
-   instances/serverless capacity according to selected design
-   subnet group
-   security groups
-   encryption
-   backups
-   parameter configuration
-   monitoring
-   deletion protection where appropriate for production

Do not hard-code passwords.

Use Secrets Manager integration.

Document:

-   connection management
-   pooling
-   backup strategy
-   scaling
-   failure behaviour

------------------------------------------------------------------------

# 27. Phase 24 --- Compute Platform

Implement EKS unless an ADR changes the selected compute model.

Architecture:

``` text
Load balancing / ingress
        ↓
EKS Service
        ↓
FastAPI container
```

Implement:

-   EKS cluster
-   node pool
-   autoscaling
-   IAM role
-   execution role
-   CloudWatch logging
-   health checks
-   deployment configuration

------------------------------------------------------------------------

# 28. Phase 25 --- API Gateway / Ingress

Implement the selected API ingress architecture.

If API Gateway fronts the service:

``` text
API Gateway
     ↓
integration
     ↓
application
```

Document:

-   authentication
-   throttling
-   request limits
-   logging
-   WAF
-   routing

Avoid duplicating responsibilities without a documented reason.

------------------------------------------------------------------------

# 29. Phase 26 --- SQS and EventBridge Infrastructure

Terraform must provision:

``` text
SQS queue
DLQ
queue policy
EventBridge bus/rules
targets
appropriate IAM
```

Configure sensible:

-   visibility timeout
-   retention
-   redrive policy
-   encryption
-   retry behaviour

Document operational procedures for poison messages.

------------------------------------------------------------------------

# 30. Phase 27 --- Secrets and IAM

Implement:

``` text
Secrets Manager
IAM task role
IAM execution role
CI/CD deployment role
```

Follow least privilege.

Separate:

``` text
runtime permissions
deployment permissions
developer permissions
```

CI/CD should assume an AWS role through OIDC.

------------------------------------------------------------------------

# 31. Phase 28 --- Observability Infrastructure

Provision appropriate:

``` text
CloudWatch log groups
alarms
dashboards where useful
metric configuration
tracing integration
```

Important alarms may include:

``` text
API 5xx rate
high latency
EKS failures
CPU/memory saturation
Aurora health
SQS queue depth
DLQ message count
```

Avoid alerting on every low-level metric.

Alerts must be actionable.

------------------------------------------------------------------------

# 32. Phase 29 --- GitHub Actions

Create workflows:

``` text
.github/workflows/
├── pull-request.yml
├── ci.yml
├── terraform-plan.yml
├── deploy-dev.yml
├── deploy-staging.yml
└── deploy-prod.yml
```

PR workflow:

``` text
lint
type check
tests
security scan
terraform fmt/check
terraform validate
```

Deployment:

``` text
build
test
container scan
push image
terraform plan
approval
terraform apply
deploy
smoke test
```

Use GitHub OIDC.

Never store permanent AWS access keys in GitHub secrets.

------------------------------------------------------------------------

# 33. Phase 30 --- Environment Promotion

Promotion model:

``` text
feature branch
      ↓
Pull Request
      ↓
CI
      ↓
main
      ↓
dev
      ↓
staging
      ↓
production
```

Production must have explicit protection.

Deployment should be reversible.

------------------------------------------------------------------------

# 34. Phase 31 --- Load Testing

Create:

``` text
load-tests/
```

Use an appropriate load-testing tool.

Measure:

``` text
RPS
p50
p95
p99
error rate
database latency
resource utilization
queue latency
```

Do not claim SLA compliance unless supported by repeatable evidence.

Document test environment and methodology.

------------------------------------------------------------------------

# 35. Phase 32 --- Resilience Testing

Test scenarios such as:

``` text
database unavailable
SQS unavailable
worker crash
application task restart
invalid message
duplicate event
dependency timeout
```

Verify:

-   appropriate retries
-   graceful failure
-   no data corruption
-   useful logs
-   alarms
-   recovery behaviour

------------------------------------------------------------------------

# 36. Phase 33 --- Documentation

Create/update:

``` text
README.md
ARCHITECTURE.md
SECURITY.md
CONTRIBUTING.md
CHANGELOG.md
docs/
ADR/
```

Documentation must explain:

-   architecture
-   deployment
-   security
-   API
-   operations
-   troubleshooting
-   architectural trade-offs

The README must be portfolio-ready.

------------------------------------------------------------------------

# 37. Phase 34 --- Architecture Diagrams

Provide diagrams for:

1.  Context architecture.
2.  AWS infrastructure.
3.  Application architecture.
4.  API request flow.
5.  Authentication flow.
6.  Order/event flow.
7.  CI/CD pipeline.
8.  Network architecture.
9.  Observability flow.

Prefer Mermaid where practical so diagrams remain version controlled.

------------------------------------------------------------------------

# 38. Phase 35 --- ADR Completion

Minimum ADRs:

``` text
ADR-001 FastAPI application framework
ADR-002 EKS compute platform
ADR-003 Aurora PostgreSQL database
ADR-004 SQS and EventBridge architecture
ADR-005 Authentication architecture
ADR-006 Observability architecture
ADR-007 Terraform module/environment strategy
ADR-008 GitHub Actions OIDC deployment
```

Each ADR must document alternatives and consequences.

------------------------------------------------------------------------

# 39. Phase 36 --- Portfolio Review

Perform a final review from three perspectives.

## Solutions Architect

Check:

-   architecture clarity
-   scalability
-   security
-   resilience
-   trade-offs
-   cost awareness

## Cloud DevOps Engineer

Check:

-   IaC quality
-   CI/CD
-   deployment safety
-   monitoring
-   automation
-   environment separation

## Software Engineer

Check:

-   code quality
-   test quality
-   API design
-   maintainability
-   error handling
-   dependency management

------------------------------------------------------------------------

# 40. Final Verification Checklist

Run:

``` bash
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest
```

Terraform:

``` bash
terraform fmt -check -recursive
terraform validate
terraform plan
```

Container:

``` bash
docker build .
```

Verify:

``` text
API starts
Health endpoint works
OpenAPI works
Database migrations work
Authentication works
Authorization works
API tests pass
Event flow works
Worker works
Docker works
Terraform validates
CI passes
Documentation is complete
```

------------------------------------------------------------------------

# 41. Definition of Implementation Completion

Claude must not declare the project complete merely because the API
starts.

Completion requires evidence across:

``` text
Application
Database
Security
Testing
Containerisation
Terraform
AWS
CI/CD
Observability
Documentation
Operations
Portfolio presentation
```

------------------------------------------------------------------------

# 42. Implementation Reporting Format

At the end of each phase, report:

``` text
## Phase
<phase name>

## Implemented
- item
- item
- item

## Tests
- command
- result

## Validation
- lint
- type check
- tests
- infrastructure validation

## Documentation
- files updated

## Decisions
- decision made
- rationale

## Remaining
- item
- item
```

Do not report a successful check unless the command was actually
executed.

------------------------------------------------------------------------

# 43. Claude Operating Principles

Claude should behave as a senior engineer implementing a production
reference architecture.

Priorities:

``` text
Correctness
    >
Security
    >
Maintainability
    >
Testability
    >
Operational clarity
    >
Performance
    >
Complexity
```

When two valid approaches exist:

1.  Prefer the simpler approach.
2.  Prefer the approach that is easier to operate.
3.  Prefer explicit configuration over magic.
4.  Document material trade-offs.
5.  Avoid introducing technology solely to make the portfolio appear
    more complex.

------------------------------------------------------------------------

# 44. Final Portfolio Narrative

When complete, the project should support this concise narrative:

> Designed and implemented a production-grade cloud-native API platform
> using Python FastAPI and AWS. The solution applies layered application
> architecture, PostgreSQL/Aurora data architecture, event-driven
> processing with SQS/EventBridge, OIDC/JWT security, Terraform-based
> infrastructure, GitHub Actions CI/CD, containerisation, automated
> testing, observability, resilience engineering and production
> operational practices.

This narrative must be supported by actual implementation evidence in
the repository.
