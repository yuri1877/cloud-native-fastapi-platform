from worker.idempotency import InMemoryProcessedEventTracker


async def test_unseen_event_is_not_processed() -> None:
    tracker = InMemoryProcessedEventTracker()
    assert await tracker.already_processed("event-1") is False


async def test_marked_event_is_processed() -> None:
    tracker = InMemoryProcessedEventTracker()
    await tracker.mark_processed("event-1")
    assert await tracker.already_processed("event-1") is True


async def test_tracker_distinguishes_between_event_ids() -> None:
    tracker = InMemoryProcessedEventTracker()
    await tracker.mark_processed("event-1")
    assert await tracker.already_processed("event-2") is False
