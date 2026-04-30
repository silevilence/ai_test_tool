from __future__ import annotations

import os
from pathlib import Path
import re
import time
from dataclasses import dataclass
from statistics import mean
from typing import Any, Callable

os.environ.setdefault("MPLBACKEND", "Agg")

from evalscope import run_task
from evalscope.config import TaskConfig

from tests.base_strategy import BaseEvalStrategy, EvalResult


__test__ = False

NIAH_DATASET_NAME = "needle_haystack"
DEFAULT_RETRIEVAL_QUESTION = "What is the best thing to do in San Francisco?"
DEFAULT_NEEDLES = (
    "The best thing to do in San Francisco is eat a sandwich and sit in Dolores Park on a sunny day.",
)
DEFAULT_CONTEXT_LENGTHS_MIN = 1000
DEFAULT_CONTEXT_LENGTHS_MAX = 32000
DEFAULT_CONTEXT_LENGTHS_NUM_INTERVALS = 10
DEFAULT_DOCUMENT_DEPTH_PERCENT_MIN = 0
DEFAULT_DOCUMENT_DEPTH_PERCENT_MAX = 100
DEFAULT_DOCUMENT_DEPTH_PERCENT_INTERVALS = 10
DEFAULT_TOKENIZER_PATH = "Qwen/Qwen3-0.6B"
DEFAULT_SUBSET_LIST = ("english", "chinese")
_CONTEXT_DEPTH_PATTERN = re.compile(r"Context#(?P<context>\d+)\s+Depth#(?P<depth>\d+(?:\.\d+)?)")


@dataclass(frozen=True, slots=True)
class NIAHJudgeModelConfig:
    api_url: str
    api_key: str
    model_name: str

    def to_evalscope_args(self) -> dict[str, str]:
        return {
            "api_url": self.api_url,
            "api_key": self.api_key,
            "model_id": self.model_name,
        }


@dataclass(frozen=True, slots=True)
class NIAHParameters:
    retrieval_question: str = DEFAULT_RETRIEVAL_QUESTION
    needles: tuple[str, ...] = DEFAULT_NEEDLES
    context_lengths_min: int = DEFAULT_CONTEXT_LENGTHS_MIN
    context_lengths_max: int = DEFAULT_CONTEXT_LENGTHS_MAX
    context_lengths_num_intervals: int = DEFAULT_CONTEXT_LENGTHS_NUM_INTERVALS
    document_depth_percent_min: int = DEFAULT_DOCUMENT_DEPTH_PERCENT_MIN
    document_depth_percent_max: int = DEFAULT_DOCUMENT_DEPTH_PERCENT_MAX
    document_depth_percent_intervals: int = DEFAULT_DOCUMENT_DEPTH_PERCENT_INTERVALS
    tokenizer_path: str = DEFAULT_TOKENIZER_PATH
    show_score: bool = False
    subset_list: tuple[str, ...] = DEFAULT_SUBSET_LIST
    limit: int | None = None
    work_dir: str = "./outputs"
    judge_model: NIAHJudgeModelConfig | None = None

    @classmethod
    def from_mapping(cls, parameters: dict[str, Any]) -> NIAHParameters:
        raw_needles = parameters.get("needles")
        if raw_needles is None:
            raw_needles = _parse_needles_text(parameters.get("needles_text"))

        judge_model = _build_judge_model(parameters.get("judge_model"))
        return cls(
            retrieval_question=str(parameters.get("retrieval_question") or DEFAULT_RETRIEVAL_QUESTION).strip(),
            needles=_normalize_needles(raw_needles),
            context_lengths_min=int(parameters.get("context_lengths_min", DEFAULT_CONTEXT_LENGTHS_MIN)),
            context_lengths_max=int(parameters.get("context_lengths_max", DEFAULT_CONTEXT_LENGTHS_MAX)),
            context_lengths_num_intervals=int(
                parameters.get("context_lengths_num_intervals", DEFAULT_CONTEXT_LENGTHS_NUM_INTERVALS)
            ),
            document_depth_percent_min=int(
                parameters.get("document_depth_percent_min", DEFAULT_DOCUMENT_DEPTH_PERCENT_MIN)
            ),
            document_depth_percent_max=int(
                parameters.get("document_depth_percent_max", DEFAULT_DOCUMENT_DEPTH_PERCENT_MAX)
            ),
            document_depth_percent_intervals=int(
                parameters.get("document_depth_percent_intervals", DEFAULT_DOCUMENT_DEPTH_PERCENT_INTERVALS)
            ),
            tokenizer_path=str(parameters.get("tokenizer_path") or DEFAULT_TOKENIZER_PATH).strip(),
            show_score=bool(parameters.get("show_score", False)),
            subset_list=_normalize_subsets(parameters.get("subset_list")),
            limit=_normalize_optional_int(parameters.get("limit")),
            work_dir=str(parameters.get("work_dir") or "./outputs").strip(),
            judge_model=judge_model,
        )

    def validate(self) -> None:
        if not self.retrieval_question:
            raise ValueError("Retrieval question is required")
        if not self.needles:
            raise ValueError("At least one needle is required")
        if self.context_lengths_min <= 0:
            raise ValueError("Minimum context length must be greater than zero")
        if self.context_lengths_max < self.context_lengths_min:
            raise ValueError("Maximum context length must be greater than or equal to minimum")
        if self.context_lengths_num_intervals <= 0:
            raise ValueError("Context length intervals must be greater than zero")
        if not 0 <= self.document_depth_percent_min <= 100:
            raise ValueError("Minimum document depth percent must be between 0 and 100")
        if not 0 <= self.document_depth_percent_max <= 100:
            raise ValueError("Maximum document depth percent must be between 0 and 100")
        if self.document_depth_percent_max < self.document_depth_percent_min:
            raise ValueError("Maximum document depth percent must be greater than or equal to minimum")
        if self.document_depth_percent_intervals <= 0:
            raise ValueError("Document depth intervals must be greater than zero")
        if not self.tokenizer_path:
            raise ValueError("Tokenizer path is required")
        if not self.subset_list:
            raise ValueError("At least one subset must be selected")
        if self.judge_model is None:
            raise ValueError("Judge model configuration is required for needle-in-a-haystack evaluation")

    def to_task_config_kwargs(self, model_config: Any) -> dict[str, Any]:
        self.validate()
        return {
            "model": model_config.model_name,
            "api_url": model_config.base_url,
            "api_key": model_config.api_key,
            "datasets": [NIAH_DATASET_NAME],
            "enable_progress_tracker": True,
            "dataset_args": {
                NIAH_DATASET_NAME: {
                    "subset_list": list(self.subset_list),
                    "extra_params": {
                        "retrieval_question": self.retrieval_question,
                        "needles": list(self.needles),
                        "context_lengths_min": self.context_lengths_min,
                        "context_lengths_max": self.context_lengths_max,
                        "context_lengths_num_intervals": self.context_lengths_num_intervals,
                        "document_depth_percent_min": self.document_depth_percent_min,
                        "document_depth_percent_max": self.document_depth_percent_max,
                        "document_depth_percent_intervals": self.document_depth_percent_intervals,
                        "tokenizer_path": self.tokenizer_path,
                        "show_score": self.show_score,
                    },
                }
            },
            "limit": self.limit,
            "work_dir": self.work_dir,
            "judge_strategy": "llm",
            "judge_model_args": self.judge_model.to_evalscope_args(),
        }


def _normalize_needles(raw_needles: Any) -> tuple[str, ...]:
    if raw_needles is None:
        raw_needles = DEFAULT_NEEDLES

    if isinstance(raw_needles, str):
        raw_needles = [raw_needles]

    needles = tuple(str(item).strip() for item in raw_needles if str(item).strip())
    return needles


def _parse_needles_text(raw_needles_text: Any) -> list[str] | None:
    if raw_needles_text is None:
        return None

    text = str(raw_needles_text).strip()
    if not text:
        return []

    return [line.strip() for line in text.splitlines() if line.strip()]


def _normalize_subsets(raw_subset_list: Any) -> tuple[str, ...]:
    if raw_subset_list is None:
        return DEFAULT_SUBSET_LIST

    if isinstance(raw_subset_list, str):
        raw_subset_list = [raw_subset_list]

    subsets = tuple(str(item).strip() for item in raw_subset_list if str(item).strip())
    return subsets or DEFAULT_SUBSET_LIST


def _normalize_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _build_judge_model(raw_judge_model: Any) -> NIAHJudgeModelConfig | None:
    if raw_judge_model is None:
        return None

    if isinstance(raw_judge_model, NIAHJudgeModelConfig):
        return raw_judge_model

    api_url = str(raw_judge_model.get("api_url") or "").strip()
    api_key = str(raw_judge_model.get("api_key") or "").strip()
    model_name = str(raw_judge_model.get("model_name") or raw_judge_model.get("model_id") or "").strip()

    if not api_url or not api_key or not model_name:
        raise ValueError("Judge model requires api_url, api_key, and model_name")

    return NIAHJudgeModelConfig(api_url=api_url, api_key=api_key, model_name=model_name)


def _extract_primary_score(data: Any) -> float | None:
    if isinstance(data, (int, float)):
        return float(data)
    mapping = _coerce_mapping(data)
    if not mapping:
        return None

    candidates = (
        mapping.get("acc"),
        mapping.get("accuracy"),
        mapping.get("score"),
        (mapping.get("avg_scores") or {}).get("acc") if isinstance(mapping.get("avg_scores"), dict) else None,
        (mapping.get("metrics") or {}).get("acc") if isinstance(mapping.get("metrics"), dict) else None,
        (mapping.get("score") or {}).get("acc") if isinstance(mapping.get("score"), dict) else None,
    )
    for candidate in candidates:
        if isinstance(candidate, (int, float)):
            return float(candidate)

    metrics = mapping.get("metrics")
    if isinstance(metrics, list):
        for metric in metrics:
            extracted = _extract_primary_score(metric)
            if extracted is not None:
                return extracted

    return None


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        coerced = to_dict()
        if isinstance(coerced, dict):
            return coerced

    return {}


def _normalize_report_list(reports: Any) -> list[dict[str, Any]]:
    if not isinstance(reports, list):
        return []

    return [coerced for report in reports if (coerced := _coerce_mapping(report))]


def _extract_heatmap_points(report: dict[str, Any]) -> list[tuple[int, int, float]]:
    metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
    direct_context_length = metadata.get("context_length", report.get("context_length"))
    direct_depth_percent = metadata.get("depth_percent", report.get("depth_percent"))
    direct_score = _extract_primary_score(report.get("metrics") or report.get("summary") or report.get("score"))
    if isinstance(direct_context_length, int) and isinstance(direct_depth_percent, int) and direct_score is not None:
        return [(direct_context_length, direct_depth_percent, direct_score)]

    points: list[tuple[int, int, float]] = []
    metrics = report.get("metrics")
    if not isinstance(metrics, list):
        return points

    for metric in metrics:
        metric_mapping = _coerce_mapping(metric)
        metric_name = metric_mapping.get("name")
        if not isinstance(metric_name, str):
            continue

        match = _CONTEXT_DEPTH_PATTERN.fullmatch(metric_name)
        if match is None:
            continue

        score = _extract_primary_score(metric_mapping)
        if score is None:
            continue

        points.append((int(match.group("context")), int(float(match.group("depth"))), score))

    return points


def _build_heatmap_artifact(reports: list[dict[str, Any]]) -> dict[str, Any]:
    points: dict[tuple[int, int], float] = {}
    context_lengths: set[int] = set()
    depth_percents: set[int] = set()

    for report in reports:
        for context_length, depth_percent, score in _extract_heatmap_points(report):
            context_lengths.add(context_length)
            depth_percents.add(depth_percent)
            points[(context_length, depth_percent)] = score

    sorted_context_lengths = sorted(context_lengths)
    sorted_depth_percents = sorted(depth_percents)
    matrix = [
        [points.get((context_length, depth_percent)) for depth_percent in sorted_depth_percents]
        for context_length in sorted_context_lengths
    ]

    return {
        "context_lengths": sorted_context_lengths,
        "depth_percents": sorted_depth_percents,
        "matrix": matrix,
    }


def _resolve_outputs_dir(dataset_result: dict[str, Any], task_config: TaskConfig | None) -> str | None:
    outputs_dir = dataset_result.get("outputs_dir")
    if isinstance(outputs_dir, str) and outputs_dir:
        return outputs_dir

    if task_config is None or not getattr(task_config, "work_dir", None):
        return None

    return str(task_config.work_dir)


def _resolve_heatmap_path(dataset_result: dict[str, Any], outputs_dir: str | None) -> str | None:
    heatmap_path = dataset_result.get("heatmap_path")
    if isinstance(heatmap_path, str) and heatmap_path:
        return heatmap_path

    if not outputs_dir:
        return None

    reports_dir = Path(outputs_dir) / "reports"
    candidates = sorted(reports_dir.glob("needle_haystack_heatmap_*.png"))
    if candidates:
        return str(candidates[0])

    return None


def _resolve_report_html_path(outputs_dir: str | None) -> str | None:
    if not outputs_dir:
        return None

    report_path = Path(outputs_dir) / "reports" / "report.html"
    if report_path.exists():
        return str(report_path)

    return None


def _ensure_non_interactive_matplotlib_backend() -> None:
    os.environ.setdefault("MPLBACKEND", "Agg")
    try:
        import matplotlib

        if str(matplotlib.get_backend()).lower() != "agg":
            matplotlib.use("Agg", force=True)
    except Exception:
        return


def _close_matplotlib_figures() -> None:
    try:
        import matplotlib.pyplot as plt

        plt.close("all")
    except Exception:
        return


def _patch_evalscope_progress_tracker() -> None:
    from evalscope.utils.tqdm_utils.progress_tracker import ProgressTracker

    if getattr(ProgressTracker._write, "_ai_test_tool_retry_patch", False):
        return

    original_write = ProgressTracker._write

    def retrying_write(self: Any, force: bool = True) -> None:
        last_error: PermissionError | None = None
        for attempt in range(5):
            try:
                original_write(self, force)
                return
            except PermissionError as error:
                last_error = error
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))

        if last_error is not None:
            raise last_error

    retrying_write._ai_test_tool_retry_patch = True  # type: ignore[attr-defined]
    ProgressTracker._write = retrying_write


class NeedleInHaystackStrategy(BaseEvalStrategy):
    def __init__(
        self,
        model_config: Any,
        parameters: dict[str, Any] | None = None,
        run_task_func: Callable[[TaskConfig], dict[str, Any]] | None = None,
        task_config_factory: Callable[..., TaskConfig] | None = None,
    ) -> None:
        super().__init__(model_config=model_config, parameters=parameters)
        self._run_task = run_task_func or run_task
        self._task_config_factory = task_config_factory or TaskConfig
        self.task_config: TaskConfig | None = None
        self.niah_parameters = NIAHParameters.from_mapping(self.parameters)

    def build_task_config(self) -> TaskConfig:
        return self._task_config_factory(**self.niah_parameters.to_task_config_kwargs(self.model_config))


    def prepare(self) -> None:
        self.task_config = self.build_task_config()
        self.set_status("prepared")

    def execute(self) -> None:
        task_config = self.task_config or self.build_task_config()
        _ensure_non_interactive_matplotlib_backend()
        _patch_evalscope_progress_tracker()
        try:
            raw_result = self._run_task(task_config)
        finally:
            _close_matplotlib_figures()
        self.set_result(self._normalize_evalscope_result(raw_result))

    def _normalize_evalscope_result(self, raw_result: dict[str, Any]) -> EvalResult:
        dataset_result = raw_result.get(NIAH_DATASET_NAME, raw_result)
        dataset_result_mapping = _coerce_mapping(dataset_result)
        summary = _coerce_mapping(dataset_result_mapping.get("summary") or dataset_result)
        reports = _normalize_report_list(dataset_result_mapping.get("reports"))
        if not reports and summary:
            reports = [summary]

        score = _extract_primary_score(summary)
        if score is None:
            report_scores = [
                extracted
                for extracted in (_extract_primary_score(report) for report in reports)
                if extracted is not None
            ]
            score = mean(report_scores) if report_scores else 0.0

        outputs_dir = _resolve_outputs_dir(dataset_result_mapping, self.task_config)
        heatmap = _build_heatmap_artifact(reports)
        return EvalResult(
            status="completed",
            metrics={
                "acc": float(score),
                "sample_count": float(len(reports)),
            },
            artifacts={
                "outputs_dir": outputs_dir,
                "heatmap_path": _resolve_heatmap_path(dataset_result_mapping, outputs_dir),
                "report_html_path": _resolve_report_html_path(outputs_dir),
                "heatmap": heatmap,
                "summary": summary,
            },
        )