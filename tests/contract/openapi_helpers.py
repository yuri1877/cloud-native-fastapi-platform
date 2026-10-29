"""Helpers for reading the generated OpenAPI document and checking real responses against it.

Not a test file. `CONTRACT` is the API surface the project has promised: changing it is a
change to the public contract and should be deliberate.
"""

from collections.abc import Iterator
from typing import Any

import jsonschema
from httpx import Response

Spec = dict[str, Any]

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

# operationId -> (method, path, success status, error statuses the API documents)
CONTRACT: dict[str, tuple[str, str, int, set[int]]] = {
    "health_live": ("GET", "/health/live", 200, set()),
    "health_ready": ("GET", "/health/ready", 200, {503}),
    "get_current_principal": ("GET", "/api/v1/me", 200, {401}),
    "list_users": ("GET", "/api/v1/users", 200, {401, 422}),
    "create_user": ("POST", "/api/v1/users", 201, {401, 403, 409, 422}),
    "get_user": ("GET", "/api/v1/users/{user_id}", 200, {401, 404, 422}),
    "update_user": ("PATCH", "/api/v1/users/{user_id}", 200, {401, 403, 404, 409, 422}),
    "delete_user": ("DELETE", "/api/v1/users/{user_id}", 204, {401, 403, 404, 409, 422}),
    "list_orders": ("GET", "/api/v1/orders", 200, {401, 422}),
    "create_order": ("POST", "/api/v1/orders", 201, {401, 403, 404, 422}),
    "get_order": ("GET", "/api/v1/orders/{order_id}", 200, {401, 404, 422}),
    "update_order": ("PATCH", "/api/v1/orders/{order_id}", 200, {401, 403, 404, 409, 422}),
    "delete_order": ("DELETE", "/api/v1/orders/{order_id}", 204, {401, 403, 404, 409, 422}),
}


def operations(spec: Spec) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """(path, METHOD, operation) for every operation in the document."""
    for path, item in spec["paths"].items():
        for method in HTTP_METHODS:
            if method in item:
                yield path, method.upper(), item[method]


def operation_by_id(spec: Spec, operation_id: str) -> tuple[str, str, dict[str, Any]]:
    matches = [m for m in operations(spec) if m[2].get("operationId") == operation_id]
    assert len(matches) == 1, f"expected exactly one {operation_id}, found {len(matches)}"
    return matches[0]


def resolve(spec: Spec, node: Any) -> Any:
    """Inline every `$ref` in `node`, giving a plain, self-contained JSON Schema.

    This API's schemas are not recursive, so inlining terminates.
    """
    if isinstance(node, dict):
        if "$ref" in node:
            target: Any = spec
            for part in node["$ref"].removeprefix("#/").split("/"):
                target = target[part]
            return resolve(spec, target)
        return {key: resolve(spec, value) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve(spec, item) for item in node]
    return node


def component(spec: Spec, name: str) -> dict[str, Any]:
    """A named schema from `components`, resolved. FastAPI suffixes a model used for both
    input and output with -Input/-Output, so those spellings are tried too."""
    schemas = spec["components"]["schemas"]
    for candidate in (name, f"{name}-Output", f"{name}-Input"):
        if candidate in schemas:
            return resolve(spec, schemas[candidate])
    raise KeyError(name)


def documented_statuses(operation: dict[str, Any]) -> set[int]:
    return {int(code) for code in operation["responses"] if code.isdigit()}


def json_response_schema(spec: Spec, operation: dict[str, Any], status: int) -> Any:
    """The resolved JSON schema documented for `status`, or None if it has no JSON body."""
    response = operation["responses"].get(str(status))
    if response is None:
        return None
    content = response.get("content", {}).get("application/json")
    return resolve(spec, content["schema"]) if content else None


def request_body_schema(spec: Spec, operation: dict[str, Any]) -> Any:
    return resolve(spec, operation["requestBody"]["content"]["application/json"]["schema"])


def query_parameters(spec: Spec, operation: dict[str, Any]) -> dict[str, Any]:
    return {
        parameter["name"]: resolve(spec, parameter["schema"])
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "query"
    }


def assert_conforms(spec: Spec, operation_id: str, response: Response, *, status: int) -> None:
    """The response has the expected status, that status is documented for the operation, the
    body matches the documented schema, and the request-ID rules hold."""
    assert response.status_code == status, (
        f"{operation_id}: expected {status}, got {response.status_code}: {response.text}"
    )
    _, _, operation = operation_by_id(spec, operation_id)
    assert str(status) in operation["responses"], f"{operation_id}: {status} is not documented"

    schema = json_response_schema(spec, operation, status)
    if schema is None:
        assert not response.content, f"{operation_id}: {status} is documented without a body"
    else:
        jsonschema.validate(response.json(), schema)

    request_id = response.headers.get("x-request-id")
    assert request_id, f"{operation_id}: the response has no X-Request-ID header"
    if status >= 400:
        assert response.json()["error"]["request_id"] == request_id
