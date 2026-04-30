from __future__ import annotations

from pathlib import Path

from core.batch_reporting import build_multi_model_summary_report


def test_build_multi_model_summary_report_collects_reports_and_writes_artifacts(tmp_path: Path) -> None:
    first_output_dir = tmp_path / "run-a"
    second_output_dir = tmp_path / "run-b"
    (first_output_dir / "reports" / "model-a").mkdir(parents=True)
    (second_output_dir / "reports" / "model-b").mkdir(parents=True)
    (first_output_dir / "reports" / "model-a" / "needle_haystack.json").write_text("{}", encoding="utf-8")
    (second_output_dir / "reports" / "model-b" / "needle_haystack.json").write_text("{}", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_table_func(*, reports_path_list: list[str], add_overall_metric: bool) -> str:
        captured["table_paths"] = reports_path_list
        captured["add_overall_metric"] = add_overall_metric
        return "table output"

    def fake_perf_table_func(*, reports_path_list: list[str]) -> str:
        captured["perf_paths"] = reports_path_list
        return "perf output"

    def fake_html_report_func(reports_dir: str, output_html_name: str = "report.html") -> str:
        captured["html_reports_dir"] = reports_dir
        html_path = Path(reports_dir) / output_html_name
        html_path.write_text("<html></html>", encoding="utf-8")
        return str(html_path)

    artifacts = build_multi_model_summary_report(
        outputs_dirs=[str(first_output_dir), str(second_output_dir)],
        batch_name="batch-summary",
        table_func=fake_table_func,
        perf_table_func=fake_perf_table_func,
        html_report_func=fake_html_report_func,
    )

    assert artifacts is not None
    assert Path(artifacts.batch_dir).name == "batch-summary"
    assert Path(artifacts.report_html_path).exists()
    assert Path(artifacts.report_table_path).read_text(encoding="utf-8") == "table output"
    assert Path(artifacts.perf_table_path).read_text(encoding="utf-8") == "perf output"
    assert (Path(artifacts.reports_dir) / "model-a" / "needle_haystack.json").exists()
    assert (Path(artifacts.reports_dir) / "model-b" / "needle_haystack.json").exists()
    assert captured["table_paths"] == [
        str(first_output_dir / "reports"),
        str(second_output_dir / "reports"),
    ]
    assert captured["perf_paths"] == [
        str(first_output_dir / "reports"),
        str(second_output_dir / "reports"),
    ]
    assert captured["add_overall_metric"] is True
    assert captured["html_reports_dir"] == artifacts.reports_dir