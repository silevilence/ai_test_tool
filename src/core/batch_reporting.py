from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil

from evalscope.report import gen_html_report_file
from evalscope.report import gen_perf_table
from evalscope.report import gen_table


@dataclass(frozen=True, slots=True)
class MultiModelSummaryReport:
    batch_dir: str
    reports_dir: str
    report_html_path: str
    report_table_path: str
    perf_table_path: str


def build_multi_model_summary_report(
    outputs_dirs: Sequence[str],
    batch_name: str | None = None,
    table_func: Callable[..., str] = gen_table,
    perf_table_func: Callable[..., str | None] = gen_perf_table,
    html_report_func: Callable[[str, str], str] = gen_html_report_file,
) -> MultiModelSummaryReport | None:
    resolved_output_dirs = [Path(output_dir).resolve() for output_dir in outputs_dirs if str(output_dir).strip()]
    if not resolved_output_dirs:
        return None

    report_dirs = [output_dir / "reports" for output_dir in resolved_output_dirs if (output_dir / "reports").is_dir()]
    if not report_dirs:
        return None

    batch_root = Path(os.path.commonpath([str(path.parent) for path in report_dirs]))
    batch_dir = batch_root / (batch_name or f"multi_model_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    reports_dir = batch_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    for report_dir in report_dirs:
        _copy_report_artifacts(report_dir, reports_dir)

    report_table = table_func(
        reports_path_list=[str(report_dir) for report_dir in report_dirs],
        add_overall_metric=True,
    )
    perf_table = perf_table_func(reports_path_list=[str(report_dir) for report_dir in report_dirs]) or ""

    report_table_path = batch_dir / "report_table.txt"
    perf_table_path = batch_dir / "perf_table.txt"
    report_table_path.write_text(report_table, encoding="utf-8")
    perf_table_path.write_text(perf_table, encoding="utf-8")

    report_html_path = html_report_func(str(reports_dir), output_html_name="report.html")
    return MultiModelSummaryReport(
        batch_dir=str(batch_dir),
        reports_dir=str(reports_dir),
        report_html_path=str(Path(report_html_path)),
        report_table_path=str(report_table_path),
        perf_table_path=str(perf_table_path),
    )


def _copy_report_artifacts(source_reports_dir: Path, target_reports_dir: Path) -> None:
    for child in source_reports_dir.iterdir():
        if child.name == "report.html":
            continue

        target_path = _resolve_unique_target(target_reports_dir, child.name)
        if child.is_dir():
            shutil.copytree(child, target_path)
            continue

        if child.suffix.lower() == ".json":
            shutil.copy2(child, target_path)


def _resolve_unique_target(parent_dir: Path, child_name: str) -> Path:
    candidate = parent_dir / child_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        next_candidate = parent_dir / f"{stem}_{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1