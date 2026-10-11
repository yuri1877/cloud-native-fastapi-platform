import pytest

from app.core.metrics import Metrics, database_operation

ROUTE = "/api/v1/users/{user_id}"


def _value(metrics: Metrics, name: str, **labels: str) -> float | None:
    return metrics.registry.get_sample_value(name, labels)


def test_a_request_is_counted_and_timed() -> None:
    metrics = Metrics()
    metrics.observe_request(method="GET", route=ROUTE, status_code=200, duration_seconds=0.02)

    assert (
        _value(metrics, "http_requests_total", method="GET", route=ROUTE, status_code="200") == 1.0
    )
    assert _value(metrics, "http_request_duration_seconds_count", method="GET", route=ROUTE) == 1.0
    duration_sum = _value(metrics, "http_request_duration_seconds_sum", method="GET", route=ROUTE)
    assert duration_sum == pytest.approx(0.02)


def test_a_successful_request_is_not_an_error() -> None:
    metrics = Metrics()
    metrics.observe_request(method="GET", route=ROUTE, status_code=200, duration_seconds=0.01)
    assert _value(metrics, "http_errors_total", method="GET", route=ROUTE) is None


@pytest.mark.parametrize("status_code", [400, 401, 404, 409, 422])
def test_client_errors_are_not_counted_as_errors(status_code: int) -> None:
    metrics = Metrics()
    metrics.observe_request(
        method="GET", route=ROUTE, status_code=status_code, duration_seconds=0.01
    )
    assert _value(metrics, "http_errors_total", method="GET", route=ROUTE) is None


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_server_errors_are_counted(status_code: int) -> None:
    metrics = Metrics()
    metrics.observe_request(
        method="GET", route=ROUTE, status_code=status_code, duration_seconds=0.01
    )
    assert _value(metrics, "http_errors_total", method="GET", route=ROUTE) == 1.0
    assert (
        _value(
            metrics, "http_requests_total", method="GET", route=ROUTE, status_code=str(status_code)
        )
        == 1.0
    )


def test_unrecognised_http_methods_share_one_label_value() -> None:
    """A client can send any method token; letting each through would let it mint series."""
    metrics = Metrics()
    metrics.observe_request(method="BREW", route=ROUTE, status_code=405, duration_seconds=0.01)
    metrics.observe_request(method="FOO", route=ROUTE, status_code=405, duration_seconds=0.01)

    assert (
        _value(metrics, "http_requests_total", method="OTHER", route=ROUTE, status_code="405")
        == 2.0
    )
    assert (
        _value(metrics, "http_requests_total", method="BREW", route=ROUTE, status_code="405")
        is None
    )


def test_each_instance_has_its_own_registry() -> None:
    """Regression guard: a shared default registry raises on the second registration."""
    first, second = Metrics(), Metrics()
    first.observe_request(method="GET", route=ROUTE, status_code=200, duration_seconds=0.01)

    other = _value(second, "http_requests_total", method="GET", route=ROUTE, status_code="200")
    assert other is None


def test_render_produces_prometheus_text() -> None:
    metrics = Metrics()
    metrics.observe_request(method="GET", route=ROUTE, status_code=200, duration_seconds=0.01)
    metrics.observe_database(operation="SELECT", duration_seconds=0.002)

    text = metrics.render().decode()
    assert "# TYPE http_requests_total counter" in text
    assert "# TYPE http_request_duration_seconds histogram" in text
    assert "# TYPE http_errors_total counter" in text
    assert "# TYPE database_operation_duration_seconds histogram" in text
    expected = 'http_requests_total{method="GET",route="/api/v1/users/{user_id}",status_code="200"}'
    assert f"{expected} 1.0" in text


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("SELECT users.id FROM users", "SELECT"),
        ("  select 1", "SELECT"),
        ("INSERT INTO users (email) VALUES (%s)", "INSERT"),
        ("UPDATE users SET name = 'x'", "UPDATE"),
        ("DELETE FROM users", "DELETE"),
        ("CREATE TABLE t (id INTEGER)", "OTHER"),
        ("WITH x AS (SELECT 1) SELECT * FROM x", "OTHER"),
        ("/* a comment */ SELECT 1", "OTHER"),
        ("", "OTHER"),
    ],
)
def test_database_operation_label(statement: str, expected: str) -> None:
    assert database_operation(statement) == expected
