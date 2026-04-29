from __future__ import annotations

from typing import Any

from tests.base_strategy import BaseEvalStrategy


__test__ = False


class NeedleInHaystackStrategy(BaseEvalStrategy):
    def __init__(self, model_config: Any, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(model_config=model_config, parameters=parameters)
        self._results: dict[str, Any] = {"status": "idle"}

    def prepare(self) -> None:
        self._results["status"] = "prepared"

    def execute(self) -> None:
        self._results["status"] = "not_implemented"

    def get_results(self) -> dict[str, Any]:
        return dict(self._results)

    def cancel(self) -> None:
        self._results["status"] = "cancelled"