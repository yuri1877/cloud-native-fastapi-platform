"""The generated OpenAPI document, checked against the API standards in the project spec:
a valid document, an exact and deliberate API surface, operation IDs, documented status codes,
one error schema, integer money, bounded pagination, bearer security and working examples."""

import re

import jsonschema
import pytest
from openapi_spec_validator import validate

from tests.contract.openapi_helpers import (
    CONTRACT,
    Spec,
    component,
    documented_statuses,
    json_response_schema,
    operation_by_id,
    operations,
    query_parameters,
    request_body_schema,
)

pytestmark = pytest.mark.contract

USER_FIELDS = {"id", "email", "name", "created_at", "updated_at"}
ORDER_FIELDS = {"id", "user_id", "status", "total_amount", "currency", "created_at", "updated_at"}
ORDER_STATUSES = ["CANCELLED", "COMPLETED", "PENDING", "PROCESSING"]

# operationId -> what a successful response must look like
SUCCESS_SHAPES = {
    "create_user": ("resource", USER_FIELDS),
    "get_user": ("resource", USER_FIELDS),
    "update_user": ("resource", USER_FIELDS),
    "list_users": ("page", USER_FIELDS),
    "create_order": ("resource", ORDER_FIELDS),
    "get_order": ("resource", ORDER_FIELDS),
    "update_order": ("resource", ORDER_FIELDS),
    "list_orders": ("page", ORDER_FIELDS),
    "get_current_principal": ("resource", {"subject", "email", "roles"}),
    "health_live": ("resource", {"status"}),
    "health_ready": ("resource", {"status", "checks"}),
    "delete_user": ("empty", set()),
    "delete_order": ("empty", set()),
}


def test_the_document_is_valid_openapi(openapi_spec: Spec) -> None:
    assert openapi_spec["openapi"].startswith("3.")
    validate(openapi_spec)


def test_the_api_surface_is_exactly_the_documented_contract(openapi_spec: Spec) -> None:
    actual = {(m, p, op.get("operationId")) for p, m, op in operations(openapi_spec)}
    expected = {(method, path, op_id) for op_id, (method, path, _, _) in CONTRACT.items()}
    assert actual == expected


def test_operation_ids_are_unique_snake_case(openapi_spec: Spec) -> None:
    ids = [op.get("operationId") for _, _, op in operations(openapi_spec)]
    assert all(ids), "an operation has no operationId"
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", op_id) for op_id in ids)


def test_every_operation_has_a_summary_and_a_tag(openapi_spec: Spec) -> None:
    for path, method, operation in operations(openapi_spec):
        assert operation.get("summary"), f"{method} {path} has no summary"
        assert operation.get("tags"), f"{method} {path} has no tag"


def test_the_document_has_a_title_and_a_semantic_version(openapi_spec: Spec) -> None:
    assert openapi_spec["info"]["title"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", openapi_spec["info"]["version"])


@pytest.mark.parametrize("operation_id", sorted(CONTRACT))
def test_each_operation_documents_its_success_and_error_statuses(
    openapi_spec: Spec, operation_id: str
) -> None:
    _, _, success, errors = CONTRACT[operation_id]
    _, _, operation = operation_by_id(openapi_spec, operation_id)
    documented = documented_statuses(operation)

    assert {s for s in documented if s < 300} == {success}
    assert {s for s in documented if s >= 400} == errors


def test_every_error_response_declares_the_standard_error_schema(openapi_spec: Spec) -> None:
    for path, method, operation in operations(openapi_spec):
        for status in sorted(s for s in documented_statuses(operation) if s >= 400):
            schema = json_response_schema(openapi_spec, operation, status)
            where = f"{method} {path} {status}"
            assert schema is not None, f"{where} has no body schema"
            assert set(schema["properties"]) == {"error"}, where
            error = schema["properties"]["error"]
            assert set(error["properties"]) == {"code", "message", "request_id"}, where
            assert {"code", "message"} <= set(error["required"]), where


@pytest.mark.parametrize("operation_id", sorted(SUCCESS_SHAPES))
def test_success_responses_have_the_documented_shape(openapi_spec: Spec, operation_id: str) -> None:
    kind, fields = SUCCESS_SHAPES[operation_id]
    _, _, operation = operation_by_id(openapi_spec, operation_id)
    _, _, success, _ = CONTRACT[operation_id]
    schema = json_response_schema(openapi_spec, operation, success)

    if kind == "empty":
        assert schema is None
        return
    assert schema is not None
    if kind == "page":
        assert set(schema["required"]) == {"items", "total", "limit", "offset"}
        assert schema["properties"]["items"]["type"] == "array"
        schema = schema["properties"]["items"]["items"]
    assert set(schema["properties"]) == fields
    assert set(schema["required"]) == fields


def test_money_is_an_integer_and_status_is_a_closed_set(openapi_spec: Spec) -> None:
    for name in ("OrderRead", "OrderCreate"):
        assert component(openapi_spec, name)["properties"]["total_amount"]["type"] == "integer"
    assert (
        component(openapi_spec, "OrderCreate")["properties"]["total_amount"]["exclusiveMinimum"]
        == 0
    )

    status = component(openapi_spec, "OrderRead")["properties"]["status"]
    assert sorted(status["enum"]) == ORDER_STATUSES
    currency = component(openapi_spec, "OrderCreate")["properties"]["currency"]
    assert currency["pattern"] == "^[A-Z]{3}$"


@pytest.mark.parametrize(
    "operation_id", ["create_user", "update_user", "create_order", "update_order"]
)
def test_request_bodies_reject_unknown_fields(openapi_spec: Spec, operation_id: str) -> None:
    _, _, operation = operation_by_id(openapi_spec, operation_id)
    assert request_body_schema(openapi_spec, operation)["additionalProperties"] is False


@pytest.mark.parametrize("operation_id", ["list_users", "list_orders"])
def test_list_operations_document_bounded_pagination(openapi_spec: Spec, operation_id: str) -> None:
    _, _, operation = operation_by_id(openapi_spec, operation_id)
    parameters = query_parameters(openapi_spec, operation)

    assert (parameters["limit"]["minimum"], parameters["limit"]["maximum"]) == (1, 100)
    assert parameters["limit"]["default"] == 20
    assert (parameters["offset"]["minimum"], parameters["offset"]["default"]) == (0, 0)


def test_orders_can_be_filtered_by_user_and_status(openapi_spec: Spec) -> None:
    _, _, operation = operation_by_id(openapi_spec, "list_orders")
    assert {"user_id", "status"} <= set(query_parameters(openapi_spec, operation))


def test_protected_operations_declare_bearer_security(openapi_spec: Spec) -> None:
    schemes = openapi_spec["components"]["securitySchemes"]
    for path, method, operation in operations(openapi_spec):
        if path.startswith("/api/v1"):
            names = {name for requirement in operation["security"] for name in requirement}
            assert names, f"{method} {path} declares no security"
            for name in names:
                assert (schemes[name]["type"], schemes[name]["scheme"]) == ("http", "bearer")
        else:
            assert not operation.get("security"), f"{method} {path} should be open"


@pytest.mark.parametrize(
    "name",
    [
        "UserCreate",
        "UserUpdate",
        "UserRead",
        "OrderCreate",
        "OrderUpdate",
        "OrderRead",
        "PrincipalRead",
    ],
)
def test_schemas_carry_examples_that_validate_against_themselves(
    openapi_spec: Spec, name: str
) -> None:
    schema = component(openapi_spec, name)
    assert schema.get("examples"), f"{name} has no examples"
    for example in schema["examples"]:
        jsonschema.validate(example, schema)
