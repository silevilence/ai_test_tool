from __future__ import annotations

from core.config import ModelConfig
from tests.base_strategy import BaseEvalStrategy, EvalResult


class DummyStrategy(BaseEvalStrategy):
    def prepare(self) -> None:
        self.set_status("prepared")

    def execute(self) -> None:
        self.set_result(
            EvalResult(
                status="completed",
                metrics={"score": 0.95},
                artifacts={"answer": "ok"},
            )
        )


def test_base_eval_strategy_exposes_standard_result_model() -> None:
    strategy = DummyStrategy(
        model_config=ModelConfig(
            display_name="Local Qwen",
            base_url="http://localhost:8000/v1",
            api_key="secret",
            model_name="qwen2.5-7b-instruct",
        )
    )

    assert strategy.get_results() == EvalResult(status="idle")

    strategy.prepare()
    strategy.execute()

    assert strategy.get_results() == EvalResult(
        status="completed",
        metrics={"score": 0.95},
        artifacts={"answer": "ok"},
    )


def test_base_eval_strategy_cancel_marks_strategy_as_cancelled() -> None:
    strategy = DummyStrategy(
        model_config=ModelConfig(
            display_name="OpenAI",
            base_url="https://api.openai.com/v1",
            api_key="secret",
            model_name="gpt-4.1-mini",
        )
    )

    strategy.cancel()

    assert strategy.is_cancelled is True
    assert strategy.get_results() == EvalResult(status="cancelled")