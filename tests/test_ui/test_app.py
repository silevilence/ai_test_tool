from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.config import ModelConfig
from core.config import ModelConfigStore
from core.logger import LogEntry
from tests.base_strategy import EvalResult
from ui.app import _estimate_niah_expected_sample_count
from ui.app import _build_niah_batch_result_summary
from ui.app import _choose_niah_heatmap_model_name
from ui.app import _iter_niah_editable_control_tags
from ui.app import _niah_model_selection_tag
from ui.app import _read_niah_parameters
from ui.app import _resolve_niah_progress_counts
from ui.app import apply_windows_viewport_title
from ui.app import build_app_shell
from ui.app import build_main_window_state
from ui.components import (
    build_navigation_items,
    build_log_panel_state,
    build_model_config_field_specs,
    build_model_config_form_state,
    build_model_config_list_items,
    build_model_config_usage_notes,
    build_progress_state,
    build_status_state,
    format_log_entries,
)


def test_build_app_shell_exposes_default_layout_state() -> None:
    shell = build_app_shell()

    assert shell.title == "LLM API 评测工具"
    assert shell.width >= 1024
    assert shell.height >= 720
    assert shell.navigation_width == 260
    assert shell.status_text == "Ready"
    assert shell.progress_value == 0.0
    assert shell.progress_overlay == "0%"
    assert shell.log_output == "No logs yet."
    assert shell.default_section_tag == "nav_model_config"
    assert [item.label for item in shell.navigation_items] == [
        "模型配置",
        "测试任务",
        "结果概览",
    ]


def test_build_main_window_state_fills_the_viewport() -> None:
    shell = build_app_shell()

    main_window = build_main_window_state(shell)

    assert main_window.width == shell.width
    assert main_window.height == shell.height
    assert main_window.pos == (0, 0)
    assert main_window.no_move is True
    assert main_window.no_resize is True
    assert main_window.no_collapse is True
    assert main_window.no_close is True
    assert main_window.no_title_bar is True


def test_apply_windows_viewport_title_uses_native_unicode_setter() -> None:
    calls: list[tuple[int, str]] = []

    updated = apply_windows_viewport_title(
        platform_handle=1234,
        title="LLM API 评测工具",
        platform_name="nt",
        set_title_func=lambda handle, value: calls.append((handle, value)),
    )

    assert updated is True
    assert calls == [(1234, "LLM API 评测工具")]


def test_apply_windows_viewport_title_falls_back_to_window_lookup() -> None:
    calls: list[tuple[int, str]] = []

    updated = apply_windows_viewport_title(
        platform_handle=None,
        title="LLM API 评测工具",
        platform_name="nt",
        set_title_func=lambda handle, value: calls.append((handle, value)),
        find_window_func=lambda current_title: 5678 if current_title == "ai_test_tool" else None,
        fallback_window_title="ai_test_tool",
    )

    assert updated is True
    assert calls == [(5678, "LLM API 评测工具")]


def test_build_navigation_items_covers_primary_sections() -> None:
    items = build_navigation_items()

    assert [item.tag for item in items] == [
        "nav_model_config",
        "nav_test_tasks",
        "nav_results_overview",
    ]


def test_component_builders_provide_default_states() -> None:
    status = build_status_state()
    progress = build_progress_state()
    config_form = build_model_config_form_state()
    log_panel = build_log_panel_state()

    assert status.text == "Ready"
    assert progress.value == 0.0
    assert progress.overlay == "0%"
    assert config_form.display_name == ""
    assert config_form.base_url == ""
    assert config_form.api_key == ""
    assert config_form.model_name == ""
    assert log_panel.expanded is True
    assert log_panel.show_log_output is True
    assert log_panel.toggle_label == "收起日志"


def test_build_log_panel_state_supports_collapsing_without_hiding_status() -> None:
    collapsed_panel = build_log_panel_state(expanded=False)
    expanded_panel = build_log_panel_state(expanded=True)

    assert collapsed_panel.expanded is False
    assert collapsed_panel.show_log_output is False
    assert collapsed_panel.toggle_label == "展开日志"
    assert collapsed_panel.panel_height < expanded_panel.panel_height
    assert collapsed_panel.status_row_height > 0


def test_build_model_config_list_items_returns_display_names() -> None:
    configs = [
        ModelConfig(
            display_name="Local Qwen",
            base_url="http://localhost:8000/v1",
            api_key="secret",
            model_name="qwen2.5-7b-instruct",
        )
    ]

    assert build_model_config_list_items(configs) == ("Local Qwen",)


def test_model_config_panel_exposes_field_guidance() -> None:
    field_specs = build_model_config_field_specs()
    usage_notes = build_model_config_usage_notes()

    assert [field.label for field in field_specs] == [
        "配置名称",
        "Base URL",
        "API Key",
        "Model Name",
    ]
    assert field_specs[0].hint == "例如：OpenAI Production"
    assert field_specs[1].hint == "例如：https://api.openai.com/v1"
    assert field_specs[2].hint == "粘贴模型服务提供的密钥"
    assert field_specs[3].hint == "例如：gpt-4.1-mini"
    assert any("先填写左侧四个字段" in note for note in usage_notes)
    assert any("右侧列表可用于回填编辑" in note for note in usage_notes)


def test_format_log_entries_returns_placeholder_for_empty_logs() -> None:
    assert format_log_entries([]) == "No logs yet."


def test_format_log_entries_renders_readable_log_lines() -> None:
    entries = [
        LogEntry(
            timestamp=datetime(2026, 4, 29, 10, 30, tzinfo=timezone.utc),
            logger_name="ai_test_tool.ui",
            level="INFO",
            message="UI initialized",
        )
    ]

    rendered = format_log_entries(entries)

    assert "INFO" in rendered
    assert "ai_test_tool.ui" in rendered
    assert "UI initialized" in rendered


def test_read_niah_parameters_returns_multiple_selected_model_configs() -> None:
    store = ModelConfigStore()
    model_alpha = ModelConfig(
        display_name="Alpha",
        base_url="https://alpha.example/v1",
        api_key="alpha-key",
        model_name="alpha-model",
    )
    model_beta = ModelConfig(
        display_name="Beta",
        base_url="https://beta.example/v1",
        api_key="beta-key",
        model_name="beta-model",
    )
    judge = ModelConfig(
        display_name="Judge",
        base_url="https://judge.example/v1",
        api_key="judge-key",
        model_name="judge-model",
    )
    store.upsert(model_alpha)
    store.upsert(model_beta)
    store.upsert(judge)

    class FakeDPG:
        def __init__(self) -> None:
            self._values = {
                _niah_model_selection_tag("Alpha"): True,
                _niah_model_selection_tag("Beta"): True,
                _niah_model_selection_tag("Judge"): False,
                "niah_judge_model_config_list": "Judge",
                "niah_retrieval_question": "Where is the answer?",
                "niah_needles_text": "needle one\nneedle two",
                "niah_context_lengths_min": 1024,
                "niah_context_lengths_max": 4096,
                "niah_context_lengths_num_intervals": 4,
                "niah_document_depth_percent_min": 10,
                "niah_document_depth_percent_max": 90,
                "niah_document_depth_percent_intervals": 5,
                "niah_tokenizer_path": "Qwen/Qwen3-0.6B",
                "niah_show_score": True,
                "niah_subset_english": True,
                "niah_subset_chinese": False,
            }

        def get_value(self, tag: str) -> object:
            return self._values.get(tag)

    selected_models, parameters = _read_niah_parameters(FakeDPG(), store)

    assert [config.display_name for config in selected_models] == ["Alpha", "Beta"]
    assert parameters["retrieval_question"] == "Where is the answer?"
    assert parameters["subset_list"] == ["english"]
    assert parameters["judge_model"] == {
        "api_url": "https://judge.example/v1",
        "api_key": "judge-key",
        "model_name": "judge-model",
    }


def test_build_niah_batch_result_summary_includes_collection_report() -> None:
    summary = _build_niah_batch_result_summary(
        model_results=[
            (
                "Alpha",
                EvalResult(
                    status="completed",
                    metrics={"acc": 0.75, "sample_count": 12.0},
                    artifacts={"outputs_dir": "outputs/run-a"},
                ),
                None,
            ),
            (
                "Beta",
                EvalResult(status="failed", error_message="boom"),
                "boom",
            ),
        ],
        collection_report_html_path=str(Path("outputs") / "batch-summary" / "reports" / "report.html"),
    )

    assert "批量任务完成: 1/2 成功" in summary
    assert "Alpha: completed | acc=75.00% | samples=12" in summary
    assert "Beta: failed | boom" in summary
    assert "汇总 HTML 报告" in summary


def test_iter_niah_editable_control_tags_targets_real_controls_only() -> None:
    store = ModelConfigStore()
    store.upsert(
        ModelConfig(
            display_name="Alpha",
            base_url="https://alpha.example/v1",
            api_key="alpha-key",
            model_name="alpha-model",
        )
    )
    store.upsert(
        ModelConfig(
            display_name="Beta",
            base_url="https://beta.example/v1",
            api_key="beta-key",
            model_name="beta-model",
        )
    )

    tags = _iter_niah_editable_control_tags(store)

    assert "niah_model_config_list" not in tags
    assert _niah_model_selection_tag("Alpha") in tags
    assert _niah_model_selection_tag("Beta") in tags
    assert "niah_run_button" not in tags


def test_resolve_niah_progress_counts_prefers_expected_grid_total() -> None:
    class FakeParameters:
        context_lengths_num_intervals = 2
        document_depth_percent_intervals = 2
        subset_list = ("english",)

    class FakeStrategy:
        niah_parameters = FakeParameters()

    assert _estimate_niah_expected_sample_count(FakeStrategy()) == 4
    assert _resolve_niah_progress_counts(
        FakeStrategy(),
        {
            "processed_count": 2,
            "total_count": 100,
            "percent": 2.0,
        },
    ) == (2, 4, 50.0, 100)


def test_choose_niah_heatmap_model_name_prefers_existing_selection() -> None:
    assert _choose_niah_heatmap_model_name(("DSV4 flash", "DSV4 pro"), "DSV4 pro") == "DSV4 pro"
    assert _choose_niah_heatmap_model_name(("DSV4 flash", "DSV4 pro"), "missing") == "DSV4 flash"
    assert _choose_niah_heatmap_model_name((), "missing") is None