from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: datetime
    logger_name: str
    level: str
    message: str


class InMemoryLogSink:
    def __init__(self, max_entries: int = 500) -> None:
        self._entries: deque[LogEntry] = deque(maxlen=max_entries)
        self._lock = Lock()

    def write(self, entry: LogEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def snapshot(self) -> list[LogEntry]:
        with self._lock:
            return list(self._entries)


class _InMemoryLogHandler(logging.Handler):
    def __init__(self, sink: InMemoryLogSink) -> None:
        super().__init__()
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc),
            logger_name=record.name,
            level=record.levelname,
            message=record.getMessage(),
        )
        self.sink.write(entry)


_CONFIG_LOCK = Lock()
_SHARED_SINK = InMemoryLogSink()


def get_shared_sink() -> InMemoryLogSink:
    return _SHARED_SINK


def _attach_sink_handler(logger: logging.Logger, sink: InMemoryLogSink) -> logging.Logger:
    with _CONFIG_LOCK:
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if not any(
            isinstance(handler, _InMemoryLogHandler) and handler.sink is sink
            for handler in logger.handlers
        ):
            logger.addHandler(_InMemoryLogHandler(sink))

    return logger


def get_logger(name: str, sink: InMemoryLogSink | None = None) -> logging.Logger:
    active_sink = sink or _SHARED_SINK
    logger = logging.getLogger(f"ai_test_tool.{name}")

    return _attach_sink_handler(logger, active_sink)


def attach_external_logger(name: str, sink: InMemoryLogSink | None = None) -> logging.Logger:
    active_sink = sink or _SHARED_SINK
    logger = logging.getLogger(name)
    return _attach_sink_handler(logger, active_sink)