import json
import logging

from app.core.logging import JsonFormatter


def test_json_formatter_emits_required_fields() -> None:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    payload = json.loads(JsonFormatter("svc", "test").format(record))
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["service"] == "svc"
    assert payload["environment"] == "test"
    assert payload["logger"] == "app.test"
    assert "timestamp" in payload
