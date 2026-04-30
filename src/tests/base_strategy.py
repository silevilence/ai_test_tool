from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from threading import Event, Lock
from typing import Any

from core.config import ModelConfig


@dataclass(frozen=True, slots=True)
class EvalResult:
    status: str
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    def with_status(self, status: str, error_message: str | None = None) -> EvalResult:
        return replace(self, status=status, error_message=error_message)


class BaseEvalStrategy(ABC):
    def __init__(self, model_config: ModelConfig, parameters: dict[str, Any] | None = None) -> None:
        self.model_config = model_config
        self.parameters = parameters or {}
        self._cancel_event = Event()
        self._result_lock = Lock()
        self._result = EvalResult(status="idle")

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def set_status(self, status: str) -> None:
        with self._result_lock:
            self._result = self._result.with_status(status=status)

    def set_result(self, result: EvalResult) -> None:
        with self._result_lock:
            self._result = EvalResult(
                status=result.status,
                metrics=dict(result.metrics),
                artifacts=dict(result.artifacts),
                error_message=result.error_message,
            )

    @abstractmethod
    def prepare(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def execute(self) -> None:
        raise NotImplementedError

    def get_results(self) -> EvalResult:
        with self._result_lock:
            return EvalResult(
                status=self._result.status,
                metrics=dict(self._result.metrics),
                artifacts=dict(self._result.artifacts),
                error_message=self._result.error_message,
            )

    def cancel(self) -> None:
        self._cancel_event.set()
        self.set_result(EvalResult(status="cancelled"))