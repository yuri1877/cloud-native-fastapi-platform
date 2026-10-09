from app.core.middleware import route_template


def test_a_path_without_parameters_is_unchanged() -> None:
    assert route_template("/health/live", {}) == "/health/live"


def test_a_path_parameter_value_becomes_its_placeholder() -> None:
    template = route_template("/api/v1/users/3f2b8c1e", {"user_id": "3f2b8c1e"})
    assert template == "/api/v1/users/{user_id}"


def test_every_parameter_is_replaced() -> None:
    template = route_template("/api/v1/users/u-1/orders/o-1", {"user_id": "u-1", "order_id": "o-1"})
    assert template == "/api/v1/users/{user_id}/orders/{order_id}"


def test_non_string_values_match_by_their_string_form() -> None:
    assert route_template("/items/42", {"item_id": 42}) == "/items/{item_id}"


def test_literal_prefix_segments_are_kept() -> None:
    """The prefix comes from the real path, so router nesting cannot drop it."""
    assert route_template("/api/v1/me", {}) == "/api/v1/me"
