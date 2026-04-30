from __future__ import annotations

from core.config import ModelConfig
from evalscope.report.report import Category
from evalscope.report.report import Metric
from evalscope.report.report import Report
from evalscope.report.report import Subset
from tests.niah_test import NeedleInHaystackStrategy


def _build_model_config() -> ModelConfig:
    return ModelConfig(
        display_name="Local Qwen",
        base_url="http://localhost:8000/v1",
        api_key="secret",
        model_name="qwen2.5-7b-instruct",
    )


def test_niah_strategy_builds_evalscope_task_config_with_judge_model() -> None:
    strategy = NeedleInHaystackStrategy(
        model_config=_build_model_config(),
        parameters={
            "retrieval_question": "What is hidden in the long context?",
            "needles": ["The hidden answer is azure.", "The backup answer is teal."],
            "context_lengths_min": 2048,
            "context_lengths_max": 8192,
            "context_lengths_num_intervals": 4,
            "document_depth_percent_min": 10,
            "document_depth_percent_max": 90,
            "document_depth_percent_intervals": 5,
            "tokenizer_path": "Qwen/Qwen2.5-0.5B",
            "show_score": True,
            "subset_list": ["english"],
            "limit": 8,
            "work_dir": "./outputs/niah-tests",
            "judge_model": {
                "api_url": "https://api.openai.com/v1",
                "api_key": "judge-secret",
                "model_name": "gpt-4o-mini",
            },
        },
    )

    task_config = strategy.build_task_config()

    assert task_config.model == "qwen2.5-7b-instruct"
    assert task_config.api_url == "http://localhost:8000/v1"
    assert task_config.api_key == "secret"
    assert task_config.datasets == ["needle_haystack"]
    assert task_config.limit == 8
    assert task_config.work_dir == "./outputs/niah-tests"
    assert task_config.enable_progress_tracker is True
    assert task_config.judge_strategy == "llm"
    assert task_config.judge_model_args == {
        "api_url": "https://api.openai.com/v1",
        "api_key": "judge-secret",
        "model_id": "gpt-4o-mini",
    }
    assert task_config.dataset_args == {
        "needle_haystack": {
            "subset_list": ["english"],
            "extra_params": {
                "retrieval_question": "What is hidden in the long context?",
                "needles": ["The hidden answer is azure.", "The backup answer is teal."],
                "context_lengths_min": 2048,
                "context_lengths_max": 8192,
                "context_lengths_num_intervals": 4,
                "document_depth_percent_min": 10,
                "document_depth_percent_max": 90,
                "document_depth_percent_intervals": 5,
                "tokenizer_path": "Qwen/Qwen2.5-0.5B",
                "show_score": True,
            },
        }
    }


def test_niah_strategy_execute_normalizes_evalscope_results() -> None:
    captured: dict[str, object] = {}

    def fake_run_task(task_cfg: object) -> dict[str, object]:
        captured["task_cfg"] = task_cfg
        return {
            "needle_haystack": {
                "summary": {"avg_scores": {"acc": 0.75}},
                "reports": [
                    {
                        "subset": "english",
                        "metrics": {"acc": 1.0},
                        "metadata": {"context_length": 1000, "depth_percent": 0},
                    },
                    {
                        "subset": "english",
                        "metrics": {"acc": 0.5},
                        "metadata": {"context_length": 2000, "depth_percent": 50},
                    },
                ],
                "outputs_dir": "outputs/niah-run",
                "heatmap_path": "outputs/niah-run/heatmap.png",
            }
        }

    strategy = NeedleInHaystackStrategy(
        model_config=_build_model_config(),
        parameters={
            "needles": ["The hidden answer is azure."],
            "judge_model": {
                "api_url": "https://api.openai.com/v1",
                "api_key": "judge-secret",
                "model_name": "gpt-4o-mini",
            },
        },
        run_task_func=fake_run_task,
    )

    strategy.prepare()
    strategy.execute()
    result = strategy.get_results()

    assert captured["task_cfg"] is strategy.task_config
    assert result.status == "completed"
    assert result.metrics == {"acc": 0.75, "sample_count": 2.0}
    assert result.artifacts["outputs_dir"] == "outputs/niah-run"
    assert result.artifacts["heatmap_path"] == "outputs/niah-run/heatmap.png"
    assert result.artifacts["heatmap"] == {
        "context_lengths": [1000, 2000],
        "depth_percents": [0, 50],
        "matrix": [[1.0, None], [None, 0.5]],
    }


def test_niah_strategy_execute_normalizes_evalscope_report_objects() -> None:
    report = Report(
        name="needle_haystack",
        dataset_name="needle_haystack",
        model_name="qwen2.5-7b-instruct",
        metrics=[
            Metric(
                name="acc",
                categories=[
                    Category(
                        name=("english",),
                        subsets=[Subset(name="english", score=0.82, num=100)],
                    )
                ],
            )
        ],
    )

    def fake_run_task(_task_cfg: object) -> dict[str, object]:
        return {
            "needle_haystack": {
                "summary": report,
                "reports": [report],
            }
        }

    strategy = NeedleInHaystackStrategy(
        model_config=_build_model_config(),
        parameters={
            "work_dir": "./outputs/niah-report-object",
            "judge_model": {
                "api_url": "https://api.openai.com/v1",
                "api_key": "judge-secret",
                "model_name": "gpt-4o-mini",
            },
        },
        run_task_func=fake_run_task,
    )

    strategy.prepare()
    strategy.execute()
    result = strategy.get_results()

    assert result.status == "completed"
    assert result.metrics["acc"] == 0.82
    assert result.metrics["sample_count"] == 1.0
    assert result.artifacts["outputs_dir"] == "./outputs/niah-report-object"
    assert result.artifacts["summary"]["dataset_name"] == "needle_haystack"
