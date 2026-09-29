# Error handling

## Contract
Every API error has the same shape:

```json
{"error": {"code": "USER_NOT_FOUND", "message": "User was not found", "request_id": null}}
```

`request_id` is always present but is `null` until Phase 8 adds request correlation IDs.
Internal details (stack traces, SQL, credentials, infrastructure) are never returned; unexpected
exceptions are logged server-side and mapped to a generic `500 INTERNAL_ERROR`.

## Exception hierarchy (`app/core/exceptions.py`)
| Exception | Status | Default code | Used for |
|---|---|---|---|
| `AppException` | 500 | `INTERNAL_ERROR` | Base class; also used directly with a custom `status_code`/`code` for one-off cases (e.g. 503 when the database isn't configured). |
| `NotFoundException` | 404 | `NOT_FOUND` | Resource does not exist (`USER_NOT_FOUND`, `ORDER_NOT_FOUND`). |
| `ConflictException` | 409 | `CONFLICT` | Request conflicts with current state (`EMAIL_ALREADY_EXISTS`, `INVALID_STATUS_TRANSITION`, `ORDER_NOT_DELETABLE`, `USER_HAS_ORDERS`). |
| `AuthenticationException` | 401 | `AUTHENTICATION_REQUIRED` | Caller's identity could not be established. Adds a `WWW-Authenticate: Bearer` header. Wired to routes in Phase 9. |
| `AuthorizationException` | 403 | `FORBIDDEN` | Caller is known but not permitted. Wired to routes in Phase 10. |

Route handlers raise these directly from the service layer; a global handler converts them to the
JSON error contract, so routers never build error responses by hand.

`RequestValidationError` (422) and any other `HTTPException` (404 for unmatched routes, etc.) are
also normalised into the same shape by dedicated handlers, and a catch-all `Exception` handler is
the last line of defence against leaking details.

## Adding a new error
1. Raise the closest existing exception with a domain-specific `code` (e.g.
   `ConflictException("...", code="ORDER_NOT_DELETABLE")`), or add a new subclass if no existing
   status code fits.
2. Document the new status code in the route's `responses=` mapping so it appears in OpenAPI.
3. Add a test asserting the status code, error `code`, and that no internal detail leaks.
