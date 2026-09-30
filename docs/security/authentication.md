# Authentication

## Model
OIDC/OAuth2 bearer JWTs, verified with a JWKS-published public key (asymmetric — the API
never holds a shared signing secret). No password authentication is implemented; identity
comes from an external identity provider (IdP).

```
Authentication              Authorization (Phase 10)
     |                            |
Who is the caller?     What may the caller do?
(this document)              (docs/security/authorization.md)
```

## Configuration
| Variable | Notes |
|---|---|
| `OIDC_ISSUER` | Must exactly match the token's `iss` claim. |
| `OIDC_AUDIENCE` | Must exactly match the token's `aud` claim. |
| `OIDC_JWKS_URL` | JWKS endpoint; signing keys are fetched and cached from here, keyed by `kid`. |

All three must be set together (validated in `app/core/config.py`); if none are set, auth is
disabled — acceptable in `dev` only, and rejected by config validation in `staging`/`prod`.

## Request flow
```
Authorization: Bearer <token>
        |
HTTPBearer extracts the token (app/dependencies/auth.py)
        |
JWKS client resolves the signing key by the token's "kid"
        |
jwt.decode verifies signature, issuer, audience, and required claims (exp, iat, sub)
        |
Claims mapped to a Principal (subject, email, roles) -> app/core/security.py
```

## Error mapping
| Condition | Status | Code |
|---|---|---|
| No `Authorization` header, or not a bearer token | 401 | `AUTHENTICATION_REQUIRED` |
| Signature invalid / malformed / unknown key ID / missing required claim | 401 | `INVALID_TOKEN` |
| `exp` in the past | 401 | `TOKEN_EXPIRED` |
| `iss` does not match `OIDC_ISSUER` | 401 | `INVALID_ISSUER` |
| `aud` does not match `OIDC_AUDIENCE` | 401 | `INVALID_AUDIENCE` |
| OIDC not configured at all | 503 | `AUTH_NOT_CONFIGURED` |

All 401 responses carry a `WWW-Authenticate: Bearer` header. Failure detail beyond the category
above (which PyJWT exception fired, key lookup internals) is logged server-side only, by
exception type, never returned to the caller — this avoids turning error messages into an oracle
for probing token validity.

## Usage
```
GET /api/v1/me
Authorization: Bearer <token>

200 {"subject": "auth0|abc123", "email": "user@example.com", "roles": ["user"]}
```

`GET /api/v1/me` is the reference protected endpoint: it returns the authenticated principal so a
client (or this test suite) can verify a token end-to-end. Verified against a real JWKS endpoint
in an integration environment; unit and integration tests here use a local RSA keypair and a
JWKS-client-shaped fake (`tests/unit/auth_helpers.py`) so no network call is required to test
signature, issuer, audience and expiry checks.

## Deferred to Phase 10
The `users`/`orders` routers are not yet protected by `get_current_principal` — attaching
authentication and the role checks that decide who may call each endpoint happens together in
the authorization phase, so route protection is designed once rather than adjusted twice.
