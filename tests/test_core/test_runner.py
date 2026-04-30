from __future__ import annotations

from core.config import ModelConfig
from core.runner import TaskRunner
from tests.base_strategy import BaseEvalStrategy, EvalResult


class RecordingStrategy(BaseEvalStrategy):
    def __init__(self, *args, should_fail: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.should_fail = should_fail
        self.calls: list[str] = []

    def prepare(self) -> None:
        self.calls.append("prepare")
        self.set_status("prepared")

    def execute(self) -> None:
        self.calls.append("execute")
        if self.should_fail:
            raise RuntimeError("boom")
        self.set_result(
            EvalResult(
                status="completed",
                metrics={"latency_ms": 123.0},
                artifacts={"rows": 1},
            )
        )


def _build_model_config() -> ModelConfig:
    return ModelConfig(
        display_name="Local Qwen",
        base_url="http://localhost:8000/v1",
        api_key="secret",
        model_name="qwen2.5-7b-instruct",
    )


def test_task_runner_executes_strategy_lifecycle_and_persists_result() -> None:
    runner = TaskRunner()
    strategy = RecordingStrategy(model_config=_build_model_config())
    statuses: list[str] = []

    runner.register_callback(lambda update: statuses.append(update.status))
    runner.submit_strategy(task_id="niah-1", strategy=strategy)

    try:
        assert runner.wait_for_task("niah-1", timeout=1.0) is True

        snapshot = runner.get_task_snapshot("niah-1")

        assert snapshot is not None
        assert snapshot.status == "completed"
        assert snapshot.result == EvalResult(
            status="completed",
            metrics={"latency_ms": 123.0},
            artifacts={"rows": 1},
        )
        assert snapshot.error_message is None
        assert strategy.calls == ["prepare", "execute"]
        assert statuses == ["queued", "preparing", "running", "completed"]
    finally:
        runner.shutdown()


def test_task_runner_reports_failed_strategy_execution() -> None:
    runner = TaskRunner()
    strategy = RecordingStrategy(model_config=_build_model_config(), should_fail=True)

    runner.submit_strategy(task_id="niah-2", strategy=strategy)

    try:
        assert runner.wait_for_task("niah-2", timeout=1.0) is True

        snapshot = runner.get_task_snapshot("niah-2")

        assert snapshot is not None
        assert snapshot.status == "failed"
        assert snapshot.result == EvalResult(status="failed", error_message="boom")
        assert snapshot.error_message == "boom"
    finally:
        runner.shutdown()


def test_task_runner_executes_submitted_strategies_in_queue_order() -> None:
    runner = TaskRunner()
    execution_order: list[str] = []

    class OrderedStrategy(RecordingStrategy):
        def execute(self) -> None:
            execution_order.append(self.model_config.display_name)
            super().execute()

    first = OrderedStrategy(
        model_config=ModelConfig(
            display_name="Model A",
            base_url="http://localhost:8000/v1",
            api_key="secret-a",
            model_name="model-a",
        )
    )
    second = OrderedStrategy(
        model_config=ModelConfig(
            display_name="Model B",
            base_url="http://localhost:8000/v1",
            api_key="secret-b",
            model_name="model-b",
        )
    )

    runner.submit_strategy(task_id="niah-batch-1", strategy=first)
    runner.submit_strategy(task_id="niah-batch-2", strategy=second)

    try:
        assert runner.wait_for_task("niah-batch-1", timeout=1.0) is True
        assert runner.wait_for_task("niah-batch-2", timeout=1.0) is True
        assert execution_order == ["Model A", "Model B"]
    finally:
        runner.shutdown()