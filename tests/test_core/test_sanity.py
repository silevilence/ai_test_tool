def test_application_entrypoint_is_callable() -> None:
    from main import main

    assert callable(main)


def test_logger_captures_messages_in_memory() -> None:
    from core.logger import InMemoryLogSink, get_logger

    sink = InMemoryLogSink(max_entries=10)
    logger = get_logger("sanity", sink=sink)

    logger.info("framework ready")

    entries = sink.snapshot()
    assert len(entries) == 1
    assert entries[0].level == "INFO"
    assert entries[0].message == "framework ready"