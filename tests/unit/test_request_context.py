import pytest

from app.core.request_context import (
    generate_request_id,
    get_request_id,
    get_trace_id,
    is_safe_request_id,
    set_request_id,
    set_trace_id,
)


def test_generate_request_id_is_url_safe_and_unique() -> None:
    a, b = generate_request_id(), generate_request_id()
    assert a != b
    assert is_safe_request_id(a)


@pytest.mark.parametrize("value", ["abc12345", "abc-123_XYZ", "a" * 128])
def test_safe_ids_accepted(value: str) -> None:
    assert is_safe_request_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "short",  # below minimum length
        "a" * 129,  # above maximum length
        "has spaces here",
        "has\nnewline",
        "has\r\ncrlf-injection: value",
        "<script>alert(1)</script>",
        "id;drop table users",
    ],
)
def test_unsafe_ids_rejected(value: str) -> None:
    assert not is_safe_request_id(value)


def test_request_id_context_defaults_to_none_and_can_be_set() -> None:
    assert get_request_id() is None
    set_request_id("abc12345")
    assert get_request_id() == "abc12345"


def test_trace_id_context_defaults_to_none_and_can_be_set() -> None:
    assert get_trace_id() is None
    set_trace_id("trace-abc123")
    assert get_trace_id() == "trace-abc123"
