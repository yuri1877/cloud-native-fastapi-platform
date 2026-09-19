# PROJECT_SPEC_v1.0.md

# Cloud-Native FastAPI Platform

## Production-Grade Solutions Architect / Cloud DevOps Portfolio Case Study

**Version:** 1.0\
**Status:** Approved baseline specification\
**Primary purpose:** Portfolio-grade reference implementation and
technical case study\
**Target role positioning:** Solutions Architect / Cloud DevOps /
Platform Engineer\
**Cloud platform:** AWS\
**Application platform:** Python + FastAPI\
**Infrastructure as Code:** Terraform\
**CI/CD:** GitHub Actions

------------------------------------------------------------------------

## 1. Executive Summary

This project is a production-grade, cloud-native API platform designed
to demonstrate end-to-end capability across:

-   Solutions Architecture
-   Python/FastAPI application engineering
-   REST API and OpenAPI design
-   AWS cloud architecture
-   PostgreSQL/Aurora data architecture
-   Event-driven architecture
-   Security engineering
-   Infrastructure as Code with Terraform
-   Containerisation
-   CI/CD
-   Observability
-   Automated testing
-   Reliability and performance engineering
-   Operational readiness

The repository must be developed as a realistic engineering product
rather than as a tutorial or simple CRUD application.

The final repository should be suitable for:

1.  Demonstrating architecture and engineering capability to prospective
    contracting clients.
2.  Serving as a reusable reference architecture.
3.  Providing a realistic GitHub portfolio project.
4.  Supporting technical interviews and architecture discussions.
5.  Demonstrating production engineering practices from requirements
    through deployment and operations.

------------------------------------------------------------------------

# 2. Project Vision

Build a secure, observable, scalable API platform using FastAPI and AWS,
with clean separation between application code, infrastructure,
deployment automation, and architectural documentation.

The implementation must demonstrate the complete lifecycle:

``` text
Requirements
    ↓
Architecture
    ↓
API Contract
    ↓
Application Development
    ↓
Testing
    ↓
Containerisation
    ↓
Infrastructure as Code
    ↓
CI/CD
    ↓
AWS Deployment
    ↓
Observability
    ↓
Security
    ↓
Performance / Resilience
    ↓
Production Readiness
```

------------------------------------------------------------------------

# 3. Portfolio Positioning

The project should explicitly demonstrate the capabilities expected from
a:

-   Solutions Architect
-   Cloud Solutions Architect
-   Cloud DevOps Engineer
-   Platform Engineer
-   AWS Architect
-   Senior Python/FastAPI Engineer

The project must therefore document not only **what was implemented**,
but also **why architectural decisions were made**.

The repository should contain Architecture Decision Records (ADRs) for
significant decisions.

Examples:

-   Why FastAPI?
-   Why PostgreSQL/Aurora?
-   Why EKS versus Lambda?
-   Why SQS?
-   Why EventBridge?
-   Why Terraform?
-   Why GitHub Actions?
-   Why the selected authentication model?
-   Why the selected observability strategy?

------------------------------------------------------------------------

# 4. Functional Scope

The application will implement a representative business domain centred
around users and orders.

## 4.1 User API

Required operations:

``` text
GET     /api/v1/users
GET     /api/v1/users/{user_id}
POST    /api/v1/users
PATCH   /api/v1/users/{user_id}
DELETE  /api/v1/users/{user_id}
```

## 4.2 Order API

Required operations:

``` text
GET     /api/v1/orders
GET     /api/v1/orders/{order_id}
POST    /api/v1/orders
PATCH   /api/v1/orders/{order_id}
DELETE  /api/v1/orders/{order_id}
```

## 4.3 Operational endpoints

``` text
GET /health/live
GET /health/ready
GET /metrics
```

Swagger/OpenAPI documentation must be available through the
FastAPI/OpenAPI mechanism in non-production environments.

------------------------------------------------------------------------

# 5. API Design Standards

The API must:

-   Use RESTful resource naming.
-   Use `/api/v1` versioning.
-   Use appropriate HTTP status codes.
-   Validate requests with Pydantic v2.
-   Validate responses.
-   Provide consistent error responses.
-   Generate OpenAPI documentation.
-   Include request/response examples.
-   Include operation IDs.
-   Use pagination for collection endpoints.
-   Support filtering where appropriate.
-   Support deterministic ordering.
-   Return correlation/request IDs.
-   Avoid exposing database implementation details.

Example:

``` http
POST /api/v1/users
Content-Type: application/json
Authorization: Bearer <token>
```

Response:

``` json
{
  "id": "uuid",
  "email": "user@example.com",
  "name": "Example User",
  "created_at": "2026-09-19T10:00:00Z"
}
```

------------------------------------------------------------------------

# 6. Error Contract

All application errors should follow a consistent structure.

Example:

``` json
{
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "User was not found",
    "request_id": "correlation-id"
  }
}
```

Expected HTTP mappings:

  Condition                   Status
  ------------------------- --------
  Successful read/update         200
  Created                        201
  Accepted                       202
  Bad request                    400
  Authentication required        401
  Forbidden                      403
  Not found                      404
  Conflict                       409
  Validation error               422
  Rate limited                   429
  Internal error                 500

Internal exception details must never be exposed to API consumers.

------------------------------------------------------------------------

# 7. Application Architecture

The application must use layered architecture:

``` text
API Router
    ↓
Application Service
    ↓
Repository
    ↓
Database
```

Recommended separation:

``` text
app/
├── api/
├── core/
├── models/
├── schemas/
├── services/
├── repositories/
├── db/
└── dependencies/
```

Responsibilities:

### Router

Responsible for:

-   HTTP concerns
-   request parsing
-   dependency injection
-   authentication/authorization integration
-   response status codes

### Service

Responsible for:

-   business logic
-   orchestration
-   business validation
-   transaction boundaries where appropriate

### Repository

Responsible for:

-   persistence
-   database queries
-   database-specific implementation

### Schema

Responsible for:

-   request validation
-   response serialization
-   API contracts

### Model

Responsible for:

-   persistence representation

Database models must not be used directly as public API contracts.

------------------------------------------------------------------------

# 8. Python Standards

Target:

``` text
Python 3.12+
```

Required characteristics:

-   Type hints throughout application code.
-   Async APIs where appropriate.
-   Pydantic v2.
-   SQLAlchemy 2.x.
-   Ruff.
-   pytest.
-   mypy or pyright.
-   uv for dependency management.

Avoid unnecessary abstractions.

Prefer readable, maintainable code over framework complexity.

------------------------------------------------------------------------

# 9. Database Architecture

Primary database:

``` text
PostgreSQL
```

AWS production target:

``` text
Amazon Aurora PostgreSQL
```

Use:

-   SQLAlchemy 2.x
-   async PostgreSQL driver
-   Alembic
-   connection pooling
-   transaction management

The application must not contain hard-coded database credentials.

Database schema changes must be delivered through Alembic migrations.

------------------------------------------------------------------------

# 10. Data Model

Minimum entities:

## User

``` text
id
email
name
created_at
updated_at
```

## Order

``` text
id
user_id
status
total_amount
currency
created_at
updated_at
```

Recommended order status:

``` text
PENDING
PROCESSING
COMPLETED
CANCELLED
```

The model should be intentionally simple enough for the portfolio while
providing enough domain behaviour to demonstrate architecture.

------------------------------------------------------------------------

# 11. Event-Driven Architecture

The platform must demonstrate asynchronous processing.

Recommended flow:

``` text
FastAPI
   │
   │ Order created
   ▼
Service
   │
   ▼
SQS
   │
   ▼
Worker
   │
   ▼
Business processing
```

EventBridge should be used for domain/event routing where appropriate.

Example domain event:

``` json
{
  "event_type": "OrderCreated",
  "event_version": "1",
  "event_id": "uuid",
  "occurred_at": "timestamp",
  "source": "order-service",
  "data": {
    "order_id": "uuid",
    "user_id": "uuid"
  }
}
```

Events must be designed for:

-   idempotency
-   traceability
-   schema evolution
-   retry handling
-   dead-letter processing

------------------------------------------------------------------------

# 12. AWS Architecture

The reference production architecture should be based on:

``` text
                    Internet
                       │
                       ▼
                  Route 53
                       │
                       ▼
                CloudFront / WAF
                       │
                       ▼
                  API Gateway
                       │
                       ▼
               FastAPI Service
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
       Aurora        SQS       EventBridge
      PostgreSQL
          │
          ▼
    Secrets Manager
```

The exact compute platform must be documented in an ADR.

Preferred primary deployment target:

``` text
EKS
```

The architecture should keep the application portable enough that an
alternative deployment model can be discussed without rewriting business
logic.

------------------------------------------------------------------------

# 13. Networking

Terraform must provision an appropriate VPC architecture.

Expected baseline:

``` text
VPC
├── Public subnets
│   └── Load balancing / ingress where required
│
├── Private application subnets
│   └── FastAPI workloads
│
└── Private database subnets
    └── Aurora PostgreSQL
```

Requirements:

-   Multiple Availability Zones.
-   Security groups with least privilege.
-   No public database access.
-   Appropriate route tables.
-   NAT or equivalent egress architecture where required.
-   VPC endpoints where economically and architecturally appropriate.

------------------------------------------------------------------------

# 14. Security Architecture

Security is a first-class requirement.

The platform must implement:

-   HTTPS/TLS.
-   OIDC/OAuth2/JWT authentication.
-   Authorization controls.
-   IAM least privilege.
-   Secrets Manager.
-   KMS encryption where appropriate.
-   Private database networking.
-   Security groups.
-   AWS WAF where applicable.
-   Audit logging.
-   Dependency vulnerability scanning.
-   Container image scanning.
-   No secrets committed to Git.

Authentication and authorization must be separated conceptually:

``` text
Authentication
    ↓
Who is the caller?

Authorization
    ↓
What may the caller do?
```

------------------------------------------------------------------------

# 15. Configuration and Secrets

Configuration must be environment-driven.

Example:

``` text
APP_ENV
LOG_LEVEL
DATABASE_URL
AWS_REGION
```

Secrets must not be stored in:

-   Git
-   Dockerfiles
-   Terraform source
-   GitHub workflow YAML
-   application source

Production secrets should use AWS Secrets Manager.

------------------------------------------------------------------------

# 16. Observability

The service must provide:

### Logs

Structured JSON logs containing:

-   timestamp
-   log level
-   service
-   environment
-   request ID
-   trace ID where available
-   HTTP method
-   route
-   status
-   duration

### Metrics

At minimum:

-   request count
-   request latency
-   error count
-   HTTP status distribution
-   database operation metrics where appropriate
-   queue depth
-   worker failures

### Tracing

Use OpenTelemetry-compatible tracing.

Trace important flows:

``` text
Client
 ↓
API Gateway
 ↓
FastAPI
 ↓
Database
 ↓
SQS
 ↓
Worker
```

------------------------------------------------------------------------

# 17. Health Checks

Implement:

``` text
/health/live
/health/ready
```

### Liveness

Must answer whether the process is alive.

It should not depend on external services.

### Readiness

Should verify critical dependencies required to serve traffic.

Avoid causing healthy application processes to restart simply because a
downstream dependency is temporarily unavailable.

------------------------------------------------------------------------

# 18. Testing Strategy

Testing must include:

## Unit tests

Test:

-   services
-   business rules
-   validation
-   error handling

## Integration tests

Test:

-   API routes
-   database interactions
-   repositories
-   authentication integration where practical

## Contract/API tests

Validate:

-   OpenAPI contract
-   status codes
-   response schemas
-   error schemas

## End-to-end tests

Provide a limited set of high-value end-to-end scenarios.

## Performance tests

Include baseline load testing for:

-   normal API requests
-   database-heavy endpoints
-   concurrent users
-   asynchronous processing

------------------------------------------------------------------------

# 19. Quality Gates

Pull requests must execute:

``` text
Formatting
    ↓
Linting
    ↓
Type checking
    ↓
Unit tests
    ↓
Integration tests
    ↓
Security scanning
    ↓
Docker build
```

A failed quality gate must prevent promotion.

------------------------------------------------------------------------

# 20. Docker Requirements

The container must:

-   Use a slim production image.
-   Run as a non-root user.
-   Avoid unnecessary packages.
-   Use deterministic dependencies.
-   Expose only required ports.
-   Receive configuration through environment variables/secrets.
-   Produce useful logs through stdout/stderr.
-   Support health checking.

------------------------------------------------------------------------

# 21. Terraform Requirements

Terraform must be modular.

Recommended structure:

``` text
terraform/
├── modules/
│   ├── networking/
│   ├── eks/
│   ├── aurora/
│   ├── api_gateway/
│   ├── security/
│   ├── iam/
│   ├── sqs/
│   ├── eventbridge/
│   ├── observability/
│   └── secrets/
│
└── environments/
    ├── dev/
    ├── staging/
    └── prod/
```

Requirements:

-   Remote state.
-   State locking using the current AWS-recommended mechanism.
-   Provider version constraints.
-   Module versioning strategy.
-   Variables and outputs.
-   Least-privilege IAM.
-   No secrets in state where avoidable.
-   Separate environment configuration.
-   `terraform fmt`.
-   `terraform validate`.
-   `terraform plan`.
-   Automated security checks.

------------------------------------------------------------------------

# 22. CI/CD

GitHub Actions must implement:

``` text
Pull Request
    ↓
Static analysis
    ↓
Tests
    ↓
Security scanning
    ↓
Terraform validation
    ↓
Docker build
    ↓
Image scan
```

Deployment:

``` text
main
 ↓
Build
 ↓
Push image
 ↓
Terraform plan
 ↓
Approval where required
 ↓
Terraform apply
 ↓
Deploy application
 ↓
Smoke tests
```

Production deployment should use GitHub environment protection and
approval.

AWS authentication from GitHub Actions should use OIDC rather than
long-lived AWS access keys.

------------------------------------------------------------------------

# 23. Infrastructure Environments

Minimum environments:

``` text
dev
staging
prod
```

Environment separation must prevent accidental cross-environment
changes.

Each environment should have:

-   separate configuration
-   separate Terraform state
-   appropriate IAM permissions
-   appropriate deployment controls

------------------------------------------------------------------------

# 24. Repository Structure

The final repository should resemble:

``` text
cloud-native-fastapi-platform/
│
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
│
├── ARCHITECTURE.md
├── PROJECT_SPEC_v1.0.md
├── CLAUDE_IMPLEMENTATION_PLAN.md
│
├── ADR/
│   ├── 001-fastapi.md
│   ├── 002-compute-platform.md
│   ├── 003-database.md
│   ├── 004-event-driven-architecture.md
│   ├── 005-authentication.md
│   └── 006-observability.md
│
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── security/
│   ├── operations/
│   └── deployment/
│
├── app/
│   ├── main.py
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── repositories/
│   ├── db/
│   └── dependencies/
│
├── worker/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── e2e/
│
├── migrations/
│
├── terraform/
│   ├── modules/
│   └── environments/
│
├── docker/
│
├── scripts/
│
├── load-tests/
│
├── .github/
│   ├── workflows/
│   └── CODEOWNERS
│
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
└── .env.example
```

------------------------------------------------------------------------

# 25. Documentation Requirements

The README must contain:

1.  Project overview.
2.  Business problem.
3.  Architecture diagram.
4.  Technology stack.
5.  Repository structure.
6.  Local development.
7.  Testing.
8.  API documentation.
9.  Security architecture.
10. AWS architecture.
11. Terraform architecture.
12. CI/CD architecture.
13. Observability.
14. Deployment process.
15. Architectural decisions.
16. Trade-offs.
17. Cost considerations.
18. Performance considerations.
19. Reliability strategy.
20. Future improvements.

The documentation should read like a professional client-facing case
study.

------------------------------------------------------------------------

# 26. Architecture Decision Records

Every significant architecture decision must have an ADR.

ADR format:

``` text
# ADR-XXX: Decision Title

## Context

What problem are we solving?

## Decision

What decision was made?

## Alternatives Considered

What alternatives were evaluated?

## Rationale

Why was the decision made?

## Consequences

What are the positive and negative consequences?

## Status

Accepted / Superseded / Deprecated
```

------------------------------------------------------------------------

# 27. Non-Functional Requirements

The platform must be designed for:

### Scalability

Horizontal scaling of API workloads.

### Availability

Multi-AZ infrastructure for production.

### Security

Least privilege and defence in depth.

### Maintainability

Clear module and application boundaries.

### Observability

Logs, metrics and traces.

### Reliability

Retries, idempotency and dead-letter handling.

### Performance

Async I/O and appropriate database pooling.

### Operability

Automated deployment, health checks and rollback strategy.

### Cost awareness

Document major AWS cost drivers and scaling considerations.

------------------------------------------------------------------------

# 28. Reliability Patterns

Where appropriate, implement:

-   timeouts
-   bounded retries
-   exponential backoff
-   idempotency
-   dead-letter queues
-   graceful shutdown
-   connection pooling
-   circuit-breaking strategy where justified
-   transactional boundaries
-   safe deployment strategy

Do not blindly retry non-idempotent operations.

------------------------------------------------------------------------

# 29. Performance Requirements

The initial implementation should establish measurable baseline targets
rather than arbitrary claims.

Performance testing should measure:

-   p50 latency
-   p95 latency
-   p99 latency
-   requests per second
-   error rate
-   database latency
-   queue processing latency
-   resource utilization

Results should be documented rather than presented as guaranteed SLAs.

------------------------------------------------------------------------

# 30. Portfolio Deliverables

The completed project must provide:

1.  Production-quality FastAPI application.
2.  Complete automated test suite.
3.  Docker-based local development.
4.  Terraform AWS infrastructure.
5.  GitHub Actions CI/CD.
6.  Security controls.
7.  Observability implementation.
8.  Architecture diagrams.
9.  ADRs.
10. API documentation.
11. Operational documentation.
12. Performance test results.
13. Deployment documentation.
14. Portfolio-ready README.
15. Demonstrable architectural trade-offs.

------------------------------------------------------------------------

# 31. Definition of Done

The project is complete when:

-   [ ] API contract is documented.
-   [ ] FastAPI application is implemented.
-   [ ] User API is implemented.
-   [ ] Order API is implemented.
-   [ ] PostgreSQL integration is implemented.
-   [ ] Alembic migrations are implemented.
-   [ ] Authentication is implemented.
-   [ ] Authorization is implemented.
-   [ ] SQS integration is implemented.
-   [ ] EventBridge integration is implemented where applicable.
-   [ ] Error handling is standardized.
-   [ ] Structured logging is implemented.
-   [ ] Metrics are implemented.
-   [ ] Distributed tracing is implemented.
-   [ ] Health/readiness endpoints exist.
-   [ ] Unit tests exist.
-   [ ] Integration tests exist.
-   [ ] Contract tests exist.
-   [ ] Docker image builds successfully.
-   [ ] Security scanning passes.
-   [ ] Terraform modules are implemented.
-   [ ] Dev environment deploys successfully.
-   [ ] Staging deployment exists.
-   [ ] Production architecture is documented.
-   [ ] GitHub Actions CI/CD is implemented.
-   [ ] AWS OIDC authentication is used by CI/CD.
-   [ ] Architecture diagrams are complete.
-   [ ] ADRs are complete.
-   [ ] README is portfolio-ready.
-   [ ] Performance baseline has been measured.
-   [ ] Operational runbook exists.
-   [ ] Disaster/recovery considerations are documented.

------------------------------------------------------------------------

# 32. Guiding Engineering Principles

The implementation must follow these principles:

1.  Security by design.
2.  Infrastructure as Code.
3.  Automation first.
4.  Immutable deployments.
5.  Least privilege.
6.  Explicit contracts.
7.  Separation of concerns.
8.  Observability by default.
9.  Test automation.
10. Failure-aware architecture.
11. Document architectural decisions.
12. Prefer simplicity over unnecessary complexity.
13. Make trade-offs explicit.
14. Design for operational ownership.
15. Treat documentation as part of the product.

------------------------------------------------------------------------

# 33. Expected Portfolio Outcome

The final repository should allow a reviewer to understand:

> A realistic business requirement was translated into an AWS
> architecture, implemented as a production-quality FastAPI service,
> provisioned using Terraform, secured using cloud-native controls,
> tested automatically, deployed through GitHub Actions, and
> instrumented for production operations.

That narrative is the primary portfolio objective of this project.
