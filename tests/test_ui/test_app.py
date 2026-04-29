from __future__ import annotations

from datetime import datetime, timezone

from core.config import ModelConfig
from core.logger import LogEntry
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