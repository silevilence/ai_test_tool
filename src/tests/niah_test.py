from __future__ import annotations

from typing import Any

from tests.base_strategy import BaseEvalStrategy, EvalResult


__test__ = False


class NeedleInHaystackStrategy(BaseEvalStrategy):
    def __init__(self, model_config: Any, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(model_config=model_config, parameters=parameters)

    def prepare(self) -> None:
        self.set_status("prepared")

    def execute(self) -> None:
        self.set_result(
            EvalResult(
                status="completed",
                artifacts={"message": "Needle in a haystack evaluation is not implemented yet."},
            )
        )