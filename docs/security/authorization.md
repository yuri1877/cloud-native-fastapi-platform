# Authorization

## Model
Simple role hierarchy, independent of route implementations (routes attach a dependency;
none of them check roles themselves):

Authenticated principal (Phase 9)
|
Required role (this layer)
|
Allow / deny


| Role | Level | Can do |
|---|---|---|
| `user` | 1 | Read (list/get) |
| `operator` | 2 | Read + create/update |
| `admin` | 3 | Read + create/update + delete |

A role at a given level implies every level below it (`admin` can do everything `operator`
and `user` can). Roles come from the JWT's `roles` claim (`app/core/security.build_principal`);
a token with no recognised role in `{user, operator, admin}` meets no requirement at all.
Unrecognised role strings are ignored rather than rejected, so an IdP can add new roles this
API doesn't know about yet without breaking existing tokens.

## Enforcement
`app/dependencies/authz.py` exposes three ready-made dependencies -- `require_user`,
`require_operator`, `require_admin` -- attached per-route via `dependencies=[Depends(...)]`:

| Route | Requirement |
|---|---|
| `GET /api/v1/users`, `GET /api/v1/users/{id}` | `require_user` |
| `POST /api/v1/users`, `PATCH /api/v1/users/{id}` | `require_operator` |
| `DELETE /api/v1/users/{id}` | `require_admin` |
| `GET /api/v1/orders`, `GET /api/v1/orders/{id}` | `require_user` |
| `POST /api/v1/orders`, `PATCH /api/v1/orders/{id}` | `require_operator` |
| `DELETE /api/v1/orders/{id}` | `require_admin` |
| `GET /api/v1/me` | authentication only, no role required |

Authentication is always checked before authorization: a missing/invalid token yields `401`
before any role is evaluated; a valid token with an insufficient role yields `403
INSUFFICIENT_ROLE`.

## Not yet implemented
Authorization here is role-based only, not ownership-based: an `operator`/`admin` can act on
any user's orders, not only their own. Per-resource ownership would be a natural extension but
is out of scope for this portfolio project's RBAC demonstration.

## Testing
`tests/unit/test_authorization.py` tests the role hierarchy in isolation. 
`tests/integration/test_authorization.py` exercises the full HTTP stack.
