from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.config import ModelConfig


class BaseEvalStrategy(ABC):
    def __init__(self, model_config: ModelConfig, parameters: dict[str, Any] | None = None) -> None:
        self.model_config = model_config
        self.parameters = parameters or {}

    @abstractmethod
    def prepare(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def execute(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_results(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cancel(self) -> None:
        raise NotImplementedError