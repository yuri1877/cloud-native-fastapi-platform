# ADR-005: Authentication architecture

## Context
The platform needs to know who is calling it. The spec requires an OIDC/OAuth2/JWT-compatible
approach and explicitly rules out password authentication unless required.

## Decision
Verify bearer JWTs issued by an external OIDC-compatible identity provider, using its published
JWKS endpoint to resolve signing keys. The application never issues or stores credentials itself.

## Alternatives considered
- **Password auth (local user table + hashed passwords).** Rejected: the spec explicitly avoids
  this unless required, and it adds a credential store, reset flows and a password-hashing
  policy to maintain — out of scope for demonstrating platform/API engineering.
- **API keys / static bearer tokens.** Rejected: no standard claim structure (issuer, audience,
  expiry), no built-in rotation via JWKS, and no path to per-caller roles without inventing one.
- **mTLS.** Sound for service-to-service traffic but a heavier operational burden (certificate
  issuance and rotation) than this portfolio project's scope justifies for a public HTTP API.

## Rationale
- Asymmetric signing (JWKS) means the API only ever holds public keys; a compromised API process
  cannot mint tokens.
- Issuer/audience/expiry are standard OIDC claims, so any compliant IdP (Auth0, Cognito, Keycloak,
  Okta) works without custom integration code.
- `jwt.PyJWKClient` caches keys and supports rotation via `kid`, so signing-key rollover on the
  IdP side does not require an application deployment.

## Consequences
- **Positive:** no credential storage or password-reset surface in this codebase; standard,
  auditable claim validation; portable to any OIDC provider.
- **Negative:** requires an external IdP to be configured and reachable (via JWKS) in every
  environment except local `dev`; adds a network dependency (JWKS fetch) to token verification,
  mitigated by client-side caching.
- **Deferred:** which roles a token needs for which endpoint is decided in ADR-006/Phase 10, not
  here — this ADR covers identity only.

## Status
Accepted
