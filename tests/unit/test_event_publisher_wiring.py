"""Verifies app.main._build_event_publisher picks the right publisher(s) for every
combination of SQS_QUEUE_URL / EVENTBRIDGE_BUS_NAME, without booting the full app."""

from app.core.config import Settings
from app.events.eventbridge import EventBridgeEventPublisher
from app.events.publishers import LoggingEventPublisher, MultiEventPublisher
from app.events.sqs import SQSEventPublisher
from app.main import _build_event_publisher

SQS_URL = "https://sqs.eu-west-2.amazonaws.com/123456789012/queue"
BUS_NAME = "order-events-bus"


def test_neither_configured_falls_back_to_logging() -> None:
    settings = Settings(_env_file=None)
    assert isinstance(_build_event_publisher(settings), LoggingEventPublisher)


def test_only_sqs_configured_uses_sqs_publisher_directly() -> None:
    settings = Settings(_env_file=None, sqs_queue_url=SQS_URL)
    assert isinstance(_build_event_publisher(settings), SQSEventPublisher)


def test_only_eventbridge_configured_uses_eventbridge_publisher_directly() -> None:
    settings = Settings(_env_file=None, eventbridge_bus_name=BUS_NAME)
    assert isinstance(_build_event_publisher(settings), EventBridgeEventPublisher)


def test_both_configured_uses_multi_publisher_wrapping_both() -> None:
    settings = Settings(_env_file=None, sqs_queue_url=SQS_URL, eventbridge_bus_name=BUS_NAME)
    publisher = _build_event_publisher(settings)
    assert isinstance(publisher, MultiEventPublisher)
    # _publishers is private; inspected here only to confirm both sinks were wrapped, in
    # the right order, which MultiEventPublisher exposes no public way to check.
    assert len(publisher._publishers) == 2
    assert isinstance(publisher._publishers[0], SQSEventPublisher)
    assert isinstance(publisher._publishers[1], EventBridgeEventPublisher)
