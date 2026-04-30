from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import time
import webbrowser
from uuid import uuid4

from core.batch_reporting import MultiModelSummaryReport
from core.batch_reporting import build_multi_model_summary_report
from core.config import ModelConfig
from core.config import ModelConfigStore
from core.logger import attach_external_logger
from core.logger import get_logger
from core.logger import get_shared_sink
from core.runner import FinalTaskStatus
from core.runner import TaskRunner
from core.runner import TaskSnapshot
from tests.base_strategy import EvalResult
from tests.niah_test import NeedleInHaystackStrategy
from ui.components import (
    NavigationItem,
    add_log_output,
    add_progress_indicator,
    add_status_bar,
    build_app_design_palette,
    build_help_disclosure_state,
    build_navigation_items,
    build_niah_layout_state,
    build_log_panel_state,
    build_model_config_field_specs,
    build_model_config_form_state,
    build_model_config_list_items,
    build_model_config_usage_notes,
    build_niah_column_weights,
    build_niah_heatmap_state,
    build_niah_overview_metrics,
    build_niah_parameter_specs,
    build_niah_panel_state,
    build_progress_state,
    build_section_hero_state,
    build_status_state,
    format_log_entries,
    resolve_niah_layout_dimensions,
    summarize_help_text,
)


_SECTION_PANEL_TAGS = {
    "nav_model_config": "section_model_config",
    "nav_test_tasks": "section_test_tasks",
    "nav_results_overview": "section_results_overview",
}

_SECTION_TITLES = {
    "nav_model_config": "模型配置",
    "nav_test_tasks": "测试任务",
    "nav_results_overview": "结果概览",
}


if os.name == "nt":
    import ctypes


_CONTENT_BOTTOM_PADDING = 12
_TASK_STATUS_PROGRESS = {
    "queued": (0.05, "已排队"),
    "preparing": (0.2, "准备中"),
    "running": (0.65, "运行中"),
    "completed": (1.0, "已完成"),
    "failed": (1.0, "失败"),
    "cancelled": (0.0, "已取消"),
}
_NIAH_TOP_PANEL_HEIGHT_EXPANDED = 430
_NIAH_TOP_PANEL_HEIGHT_COLLAPSED = 660
_NIAH_SUMMARY_HEIGHT_EXPANDED = 120
_NIAH_SUMMARY_HEIGHT_COLLAPSED = 140
_NIAH_HEATMAP_HEIGHT_EXPANDED = 230
_NIAH_HEATMAP_HEIGHT_COLLAPSED = 430
_NIAH_MAIN_SPLITTER_WIDTH = 10
_NIAH_RESULT_SPLITTER_HEIGHT = 10
_NIAH_RIGHT_PANEL_CHROME_HEIGHT = 108
_PROGRESS_POLL_INTERVAL_SECONDS = 0.5
_SECTION_HERO_WRAP = 980
_CARD_TEXT_WRAP = 520
_NIAH_EDITABLE_TAGS = (
    "niah_select_all_models_button",
    "niah_clear_models_button",
    "niah_judge_model_config_list",
    "niah_retrieval_question",
    "niah_needles_text",
    "niah_tokenizer_path",
    "niah_context_lengths_min",
    "niah_context_lengths_max",
    "niah_context_lengths_num_intervals",
    "niah_document_depth_percent_min",
    "niah_document_depth_percent_max",
    "niah_document_depth_percent_intervals",
    "niah_subset_english",
    "niah_subset_chinese",
    "niah_show_score",
)


@dataclass(frozen=True, slots=True)
class AppShell:
    title: str
    width: int
    height: int
    navigation_width: int
    brand_title: str
    brand_subtitle: str
    status_text: str
    progress_value: float
    progress_overlay: str
    log_output: str
    default_section_tag: str
    navigation_items: tuple[NavigationItem, ...]


@dataclass(frozen=True, slots=True)
class MainWindowState:
    width: int
    height: int
    pos: tuple[int, int]
    no_move: bool
    no_resize: bool
    no_collapse: bool
    no_close: bool
    no_title_bar: bool


@dataclass(slots=True)
class NIAHBatchRuntimeState:
    task_ids: tuple[str, ...]
    task_id_to_model_name: dict[str, str]
    task_id_to_strategy: dict[str, NeedleInHaystackStrategy]
    results: dict[str, tuple[EvalResult | None, str | None]] = field(default_factory=dict)
    current_task_index: int = 0
    summary_report: MultiModelSummaryReport | None = None

    @property
    def total_count(self) -> int:
        return len(self.task_ids)

    @property
    def completed_count(self) -> int:
        return len(self.results)

    @property
    def current_task_id(self) -> str | None:
        if not self.task_ids or self.current_task_index >= len(self.task_ids):
            return None
        return self.task_ids[self.current_task_index]

    @property
    def current_model_name(self) -> str | None:
        current_task_id = self.current_task_id
        if current_task_id is None:
            return None
        return self.task_id_to_model_name.get(current_task_id)

    @property
    def current_strategy(self) -> NeedleInHaystackStrategy | None:
        current_task_id = self.current_task_id
        if current_task_id is None:
            return None
        return self.task_id_to_strategy.get(current_task_id)

    def contains_task(self, task_id: str) -> bool:
        return task_id in self.task_id_to_strategy

    def record_result(self, snapshot: TaskSnapshot) -> None:
        self.results[snapshot.task_id] = (snapshot.result, snapshot.error_message)

    def advance(self) -> str | None:
        self.current_task_index += 1
        return self.current_task_id

    def ordered_results(self) -> list[tuple[str, EvalResult | None, str | None]]:
        ordered: list[tuple[str, EvalResult | None, str | None]] = []
        for task_id in self.task_ids:
            result, error_message = self.results.get(task_id, (None, None))
            ordered.append((self.task_id_to_model_name.get(task_id, task_id), result, error_message))
        return ordered


@dataclass(slots=True)
class AppRuntimeState:
    store: ModelConfigStore
    task_runner: TaskRunner
    update_queue: SimpleQueue[TaskSnapshot]
    active_task_id: str | None = None
    active_strategy: NeedleInHaystackStrategy | None = None
    active_task_status: str | None = None
    active_task_started_at: float | None = None
    last_progress_poll_at: float = 0.0
    active_batch: NIAHBatchRuntimeState | None = None
    niah_layout_state: object = field(default_factory=build_niah_layout_state)
    latest_model_results: dict[str, EvalResult] = field(default_factory=dict)
    selected_heatmap_model_name: str | None = None
    active_drag_handle: str | None = None
    last_drag_mouse_pos: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class HelpPopupPayload:
    title: str
    description: str
    supporting_text: str = ""
    wrap: int = _CARD_TEXT_WRAP


def build_app_shell() -> AppShell:
    return AppShell(
        title="LLM API 评测工具",
        width=1520,
        height=980,
        navigation_width=248,
        brand_title="Eval Console",
        brand_subtitle="面向模型联调、批量评测与长上下文检索的桌面工作台",
        status_text="控制台就绪",
        progress_value=0.0,
        progress_overlay="IDLE",
        log_output="No logs yet.",
        default_section_tag="nav_model_config",
        navigation_items=build_navigation_items(),
    )


def build_main_window_state(shell: AppShell) -> MainWindowState:
    return MainWindowState(
        width=shell.width,
        height=shell.height,
        pos=(0, 0),
        no_move=True,
        no_resize=True,
        no_collapse=True,
        no_close=True,
        no_title_bar=True,
    )


def _resolve_model_config_store_path() -> Path:
    app_data_dir = Path(os.environ.get("APPDATA", Path.home()))
    return app_data_dir / "ai_test_tool" / "model_configs.json"


def _resolve_chinese_font_path() -> Path | None:
    windows_dir = Path(os.environ.get("WINDIR", "C:/Windows"))
    candidates = (
        windows_dir / "Fonts" / "msyh.ttc",
        windows_dir / "Fonts" / "msyh.ttf",
        windows_dir / "Fonts" / "simhei.ttf",
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _bind_default_font(dpg: object, logger_name: str) -> None:
    font_path = _resolve_chinese_font_path()
    logger = get_logger(logger_name)

    if font_path is None:
        logger.warning("Chinese font not found; using DearPyGui default font")
        return

    with dpg.font_registry():
        font_id = dpg.add_font(str(font_path), 18)

    dpg.bind_font(font_id)


def _set_native_windows_title(platform_handle: int, title: str) -> None:
    ctypes.windll.user32.SetWindowTextW(int(platform_handle), title)


def _find_native_window_by_title(window_title: str) -> int | None:
    if os.name != "nt" or not window_title:
        return None

    handle = ctypes.windll.user32.FindWindowW(None, window_title)
    return int(handle) if handle else None


def apply_windows_viewport_title(
    platform_handle: int | None,
    title: str,
    platform_name: str | None = None,
    set_title_func: Callable[[int, str], None] | None = None,
    find_window_func: Callable[[str], int | None] | None = None,
    fallback_window_title: str | None = None,
) -> bool:
    active_platform_name = platform_name or os.name
    if active_platform_name != "nt":
        return False

    resolved_handle = platform_handle
    if not resolved_handle:
        title_finder = find_window_func or _find_native_window_by_title
        resolved_handle = title_finder(fallback_window_title or "")

    if not resolved_handle:
        return False

    title_setter = set_title_func or _set_native_windows_title
    title_setter(int(resolved_handle), title)
    return True


def _hex_to_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = color.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Unsupported color value: {color}")

    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)) + (alpha,)


def _add_theme_color_if_supported(dpg: object, target: object, color: str) -> None:
    if target is None:
        return
    dpg.add_theme_color(target, _hex_to_rgba(color))


def _add_theme_style_if_supported(dpg: object, target: object, value_x: float, value_y: float | None = None) -> None:
    if target is None:
        return
    if value_y is None:
        dpg.add_theme_style(target, value_x)
        return
    dpg.add_theme_style(target, value_x, value_y)


def _create_app_themes(dpg: object) -> None:
    if dpg.does_item_exist("app_global_theme"):
        return

    palette = build_app_design_palette()

    with dpg.theme(tag="app_global_theme"):
        with dpg.theme_component(dpg.mvAll):
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_WindowBg", None), palette.background)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ChildBg", None), palette.panel)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_PopupBg", None), palette.sidebar)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Border", None), palette.border)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_FrameBg", None), palette.surface)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_FrameBgHovered", None), palette.surface_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_FrameBgActive", None), palette.surface_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Button", None), palette.surface_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonHovered", None), palette.accent_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonActive", None), palette.accent)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Header", None), palette.surface)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_HeaderHovered", None), palette.surface_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_HeaderActive", None), palette.surface_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Text", None), palette.text_primary)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_TextDisabled", None), palette.text_muted)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_CheckMark", None), palette.accent)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_SliderGrab", None), palette.accent_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_SliderGrabActive", None), palette.accent)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_WindowPadding", None), 18, 18)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FramePadding", None), 12, 10)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_CellPadding", None), 10, 8)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_ItemSpacing", None), 12, 10)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_WindowBorderSize", None), 0)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FrameRounding", None), 10)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_ChildRounding", None), 14)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_GrabRounding", None), 10)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_ScrollbarRounding", None), 10)

    with dpg.theme(tag="app_card_theme"):
        with dpg.theme_component(dpg.mvChildWindow):
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ChildBg", None), palette.panel)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Border", None), palette.border)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_ChildBorderSize", None), 1)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_ChildRounding", None), 16)

    with dpg.theme(tag="app_console_theme"):
        with dpg.theme_component(dpg.mvInputText):
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_FrameBg", None), palette.console)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Border", None), palette.border)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Text", None), palette.text_primary)

    with dpg.theme(tag="app_nav_button_theme"):
        with dpg.theme_component(dpg.mvButton):
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Button", None), palette.surface)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonHovered", None), palette.surface_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonActive", None), palette.surface_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Text", None), palette.text_primary)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FrameRounding", None), 12)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FramePadding", None), 14, 12)

    with dpg.theme(tag="app_help_button_theme"):
        with dpg.theme_component(dpg.mvButton):
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Button", None), palette.surface_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonHovered", None), palette.accent_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonActive", None), palette.accent)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Text", None), palette.text_primary)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FrameRounding", None), 14)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FramePadding", None), 6, 4)

    with dpg.theme(tag="app_nav_button_active_theme"):
        with dpg.theme_component(dpg.mvButton):
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Button", None), palette.accent)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonHovered", None), palette.accent_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonActive", None), palette.accent_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Text", None), palette.background)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FrameRounding", None), 12)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FramePadding", None), 14, 12)

    with dpg.theme(tag="app_accent_button_theme"):
        with dpg.theme_component(dpg.mvButton):
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Button", None), palette.accent)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonHovered", None), palette.accent_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonActive", None), palette.accent_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Text", None), palette.background)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FrameRounding", None), 12)
            _add_theme_style_if_supported(dpg, getattr(dpg, "mvStyleVar_FramePadding", None), 14, 12)

    with dpg.theme(tag="app_splitter_theme"):
        with dpg.theme_component(dpg.mvButton):
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_Button", None), palette.surface_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonHovered", None), palette.accent_alt)
            _add_theme_color_if_supported(dpg, getattr(dpg, "mvThemeCol_ButtonActive", None), palette.accent)


def _bind_theme_if_exists(dpg: object, item_tag: str, theme_tag: str) -> None:
    if dpg.does_item_exist(item_tag) and dpg.does_item_exist(theme_tag):
        dpg.bind_item_theme(item_tag, theme_tag)


def _update_section_hero(dpg: object, section_tag: str) -> None:
    hero_state = build_section_hero_state(section_tag)
    for tag, value in (
        ("active_section_eyebrow", hero_state.eyebrow),
        ("active_section_title", hero_state.title),
        ("active_section_description", hero_state.description),
        ("active_section_supporting_text", hero_state.supporting_text),
    ):
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, value)


def _sync_navigation_button_state(dpg: object, active_section_tag: str) -> None:
    for item_tag in _SECTION_PANEL_TAGS:
        theme_tag = "app_nav_button_active_theme" if item_tag == active_section_tag else "app_nav_button_theme"
        _bind_theme_if_exists(dpg, item_tag, theme_tag)


def _estimate_expected_sample_count_from_inputs(dpg: object) -> int | None:
    required_tags = (
        "niah_context_lengths_num_intervals",
        "niah_document_depth_percent_intervals",
        "niah_subset_english",
        "niah_subset_chinese",
    )
    if not all(dpg.does_item_exist(tag) for tag in required_tags):
        return None

    context_interval_count = int(dpg.get_value("niah_context_lengths_num_intervals") or 0)
    depth_interval_count = int(dpg.get_value("niah_document_depth_percent_intervals") or 0)
    subset_count = int(bool(dpg.get_value("niah_subset_english"))) + int(bool(dpg.get_value("niah_subset_chinese")))
    if context_interval_count <= 0 or depth_interval_count <= 0 or subset_count <= 0:
        return None

    return context_interval_count * depth_interval_count * subset_count


def _update_niah_overview_metrics(dpg: object, store: ModelConfigStore | None) -> None:
    if store is None:
        selected_model_names: tuple[str, ...] = ()
    else:
        selected_model_names = _get_selected_niah_model_display_names(dpg, store)

    judge_model_name = ""
    if dpg.does_item_exist("niah_judge_model_config_list"):
        judge_model_name = str(dpg.get_value("niah_judge_model_config_list") or "").strip()

    show_score = bool(dpg.get_value("niah_show_score")) if dpg.does_item_exist("niah_show_score") else False
    metrics = build_niah_overview_metrics(
        selected_model_names=selected_model_names,
        judge_model_name=judge_model_name,
        expected_sample_count=_estimate_expected_sample_count_from_inputs(dpg),
        show_score=show_score,
    )

    for index, metric in enumerate(metrics):
        label_tag = f"niah_overview_metric_label_{index}"
        value_tag = f"niah_overview_metric_value_{index}"
        detail_tag = f"niah_overview_metric_detail_{index}"
        if dpg.does_item_exist(label_tag):
            dpg.set_value(label_tag, metric.label)
        if dpg.does_item_exist(value_tag):
            dpg.set_value(value_tag, metric.value)
        if dpg.does_item_exist(detail_tag):
            dpg.set_value(detail_tag, metric.detail)


def _handle_niah_configuration_changed(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    _update_niah_overview_metrics(dpg, user_data)


def _set_status_text(dpg: object, message: str) -> None:
    if dpg.does_item_exist("status_bar"):
        dpg.set_value("status_bar", message)


def _set_model_config_form_values(dpg: object, config: ModelConfig | None = None) -> None:
    form_state = build_model_config_form_state() if config is None else build_model_config_form_state(
        display_name=config.display_name,
        base_url=config.base_url,
        api_key=config.api_key,
        model_name=config.model_name,
    )
    dpg.set_value("config_display_name", form_state.display_name)
    dpg.set_value("config_base_url", form_state.base_url)
    dpg.set_value("config_api_key", form_state.api_key)
    dpg.set_value("config_model_name", form_state.model_name)


def _read_model_config_form(dpg: object) -> ModelConfig:
    config = ModelConfig(
        display_name=dpg.get_value("config_display_name").strip(),
        base_url=dpg.get_value("config_base_url").strip(),
        api_key=dpg.get_value("config_api_key").strip(),
        model_name=dpg.get_value("config_model_name").strip(),
    )

    if not config.display_name:
        raise ValueError("Display name is required")
    if not config.base_url:
        raise ValueError("Base URL is required")
    if not config.api_key:
        raise ValueError("API key is required")
    if not config.model_name:
        raise ValueError("Model name is required")

    return config


def _refresh_model_config_list(
    dpg: object,
    store: ModelConfigStore,
    selected_display_name: str | None = None,
) -> None:
    items = list(build_model_config_list_items(store.list_all()))
    selected_model_names = _get_selected_niah_model_display_names(dpg, store)
    dpg.configure_item("config_list", items=items)
    dpg.configure_item("config_list_hint", show=not items)

    if dpg.does_item_exist("niah_model_config_list"):
        _refresh_niah_model_selection(dpg, store, selected_display_names=selected_model_names)
    if dpg.does_item_exist("niah_judge_model_config_list"):
        dpg.configure_item("niah_judge_model_config_list", items=items)

    if items and selected_display_name in items:
        dpg.set_value("config_list", selected_display_name)

        if dpg.does_item_exist("niah_judge_model_config_list") and not dpg.get_value("niah_judge_model_config_list"):
            dpg.set_value("niah_judge_model_config_list", selected_display_name)

    _update_niah_overview_metrics(dpg, store)


def _show_section(dpg: object, section_tag: str) -> None:
    for navigation_tag, panel_tag in _SECTION_PANEL_TAGS.items():
        dpg.configure_item(panel_tag, show=navigation_tag == section_tag)

    _update_section_hero(dpg, section_tag)
    _sync_navigation_button_state(dpg, section_tag)


def _handle_navigation(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    section_tag = str(user_data)
    _show_section(dpg, section_tag)
    _set_status_text(dpg, f"Viewing {_SECTION_TITLES[section_tag]}")


def _handle_save_model_config(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    store = user_data
    logger = get_logger("ui.model_config")

    try:
        config = _read_model_config_form(dpg)
    except ValueError as error:
        _set_status_text(dpg, str(error))
        return

    store.upsert(config)
    _refresh_model_config_list(dpg, store, selected_display_name=config.display_name)
    _set_status_text(dpg, f"Saved config {config.display_name}")
    logger.info("Saved model config %s", config.display_name)


def _handle_clear_model_config_form(_sender: object, _app_data: object, _user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    _set_model_config_form_values(dpg)
    _set_status_text(dpg, "Cleared model config form")


def _handle_delete_model_config(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    store = user_data
    selection = dpg.get_value("config_list")
    if not selection:
        _set_status_text(dpg, "Select a config to delete")
        return

    store.remove(selection)
    _set_model_config_form_values(dpg)
    _refresh_model_config_list(dpg, store)
    _set_status_text(dpg, f"Deleted config {selection}")
    get_logger("ui.model_config").info("Deleted model config %s", selection)


def _handle_select_model_config(_sender: object, app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    if not app_data:
        return

    store = user_data
    config = store.get(str(app_data))
    if config is None:
        return

    _set_model_config_form_values(dpg, config)
    _set_status_text(dpg, f"Loaded config {config.display_name}")


def _add_help_button(
    dpg: object,
    button_tag: str,
    payload: HelpPopupPayload,
) -> None:
    disclosure_state = build_help_disclosure_state()
    dpg.add_button(
        label=disclosure_state.label,
        tag=button_tag,
        width=28,
        height=28,
        callback=_open_help_popup,
        user_data=payload,
    )
    _bind_theme_if_exists(dpg, button_tag, "app_help_button_theme")
    with dpg.tooltip(button_tag):
        tooltip_text = summarize_help_text(
            " ".join(part for part in (payload.description, payload.supporting_text) if part),
            max_chars=disclosure_state.summary_max_chars,
        )
        dpg.add_text(tooltip_text)


def _ensure_help_popup_window(dpg: object) -> None:
    if dpg.does_item_exist("app_help_popup_window"):
        return

    with dpg.window(
        tag="app_help_popup_window",
        popup=True,
        show=False,
        no_title_bar=True,
        no_resize=True,
        no_move=True,
        no_saved_settings=True,
        autosize=True,
    ):
        dpg.add_text("", tag="app_help_popup_title")
        dpg.add_separator()
        dpg.add_text("", tag="app_help_popup_description", wrap=_SECTION_HERO_WRAP)
        dpg.add_spacer(height=6, tag="app_help_popup_spacer")
        dpg.add_text("", tag="app_help_popup_supporting", wrap=_SECTION_HERO_WRAP)


def _open_help_popup(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    payload = user_data if isinstance(user_data, HelpPopupPayload) else None
    if payload is None:
        return

    _ensure_help_popup_window(dpg)
    dpg.set_value("app_help_popup_title", payload.title)
    dpg.set_value("app_help_popup_description", payload.description)
    dpg.set_value("app_help_popup_supporting", payload.supporting_text)
    dpg.configure_item("app_help_popup_description", wrap=payload.wrap)
    dpg.configure_item("app_help_popup_supporting", wrap=payload.wrap, show=bool(payload.supporting_text))
    dpg.configure_item("app_help_popup_spacer", show=bool(payload.supporting_text))

    mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
    popup_position = (int(mouse_x) + 12, int(mouse_y) + 12)
    dpg.configure_item("app_help_popup_window", pos=popup_position, show=True)


def _add_card_heading(
    dpg: object,
    eyebrow: str,
    title: str,
    description: str,
    help_tag_prefix: str,
) -> None:
    dpg.add_text(eyebrow)
    with dpg.group(horizontal=True):
        dpg.add_text(title)
        _add_help_button(
            dpg,
            button_tag=f"{help_tag_prefix}_help_button",
            payload=HelpPopupPayload(
                title=title,
                description=description,
            ),
        )


def _build_section_hero(dpg: object, section_tag: str) -> None:
    hero_state = build_section_hero_state(section_tag)
    with dpg.group(tag="section_hero_card"):
        dpg.add_text(hero_state.eyebrow, tag="active_section_eyebrow")
        with dpg.group(horizontal=True):
            dpg.add_text(hero_state.title, tag="active_section_title")
            _add_help_button(
                dpg,
                button_tag="active_section_help_button",
                payload=HelpPopupPayload(
                    title=hero_state.title,
                    description=hero_state.description,
                    supporting_text=hero_state.supporting_text,
                    wrap=_SECTION_HERO_WRAP,
                ),
            )
        dpg.add_separator()


def _build_niah_overview_metric_cards(dpg: object) -> None:
    metrics = build_niah_overview_metrics()
    with dpg.group(horizontal=True):
        for index, metric in enumerate(metrics):
            card_tag = f"niah_overview_metric_card_{index}"
            with dpg.child_window(tag=card_tag, border=True, width=190, autosize_y=True):
                dpg.add_text(metric.label, tag=f"niah_overview_metric_label_{index}")
                dpg.add_text(metric.value, tag=f"niah_overview_metric_value_{index}")
                dpg.add_text(metric.detail, tag=f"niah_overview_metric_detail_{index}", wrap=150)
            _bind_theme_if_exists(dpg, card_tag, "app_card_theme")


def _build_model_config_panel(dpg: object, store: ModelConfigStore) -> None:
    with dpg.group(tag="section_model_config", show=True):
        with dpg.group(horizontal=True):
            with dpg.child_window(tag="model_config_form_card", width=660, border=True, autosize_y=True):
                _add_card_heading(
                    dpg,
                    "PRIMARY INPUTS",
                    "接入参数",
                    "直接填写四个字段并保存。这个区域只负责采集与回填，不承载额外说明面板。",
                    help_tag_prefix="model_config_form_card",
                )
                dpg.add_text("本地配置默认保存在当前用户目录；Windows 下会使用系统凭据保护 API Key。", wrap=_CARD_TEXT_WRAP)
                dpg.add_spacer(height=8)
                for field in build_model_config_field_specs():
                    dpg.add_text(field.label)
                    dpg.add_input_text(
                        tag=field.tag,
                        label="",
                        hint=field.hint,
                        password=field.password,
                        width=-1,
                    )
                    dpg.add_text(field.help_text)
                    dpg.add_spacer(height=6)

                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="保存配置",
                        callback=_handle_save_model_config,
                        user_data=store,
                    )
                    dpg.add_button(
                        label="清空表单",
                        callback=_handle_clear_model_config_form,
                    )
                    dpg.add_button(
                        label="删除配置",
                        callback=_handle_delete_model_config,
                        user_data=store,
                    )
                dpg.add_text("保存后可以从右侧列表选择配置，自动回填到左侧表单。")
            _bind_theme_if_exists(dpg, "model_config_form_card", "app_card_theme")

            with dpg.child_window(tag="model_config_list_card", border=True, autosize_x=True, autosize_y=True):
                _add_card_heading(
                    dpg,
                    "REGISTRY",
                    "已保存配置",
                    "单击列表项即可回填左侧表单，适合在多个供应商或多套环境之间快速切换。",
                    help_tag_prefix="model_config_list_card",
                )
                dpg.add_listbox(
                    tag="config_list",
                    items=[],
                    width=-1,
                    num_items=12,
                    callback=_handle_select_model_config,
                    user_data=store,
                )
                dpg.add_text("暂无已保存配置", tag="config_list_hint")
                dpg.add_text("点击某一项后，左侧会显示该配置的详细内容。")
            _bind_theme_if_exists(dpg, "model_config_list_card", "app_card_theme")

        _refresh_model_config_list(dpg, store)
        _set_model_config_form_values(dpg)


def _set_task_progress(dpg: object, status: str) -> None:
    progress_value, overlay = _TASK_STATUS_PROGRESS.get(status, (0.0, status))
    if dpg.does_item_exist("task_progress"):
        dpg.set_value("task_progress", progress_value)
        dpg.configure_item("task_progress", overlay=overlay)


def _niah_model_selection_tag(display_name: str) -> str:
    encoded = base64.urlsafe_b64encode(display_name.encode("utf-8")).decode("ascii").rstrip("=")
    return f"niah_model_option_{encoded or 'empty'}"


def _get_selected_niah_model_display_names(dpg: object, store: ModelConfigStore) -> tuple[str, ...]:
    selected_display_names: list[str] = []
    for config in store.list_all():
        try:
            if dpg.get_value(_niah_model_selection_tag(config.display_name)):
                selected_display_names.append(config.display_name)
        except Exception:
            continue

    return tuple(selected_display_names)


def _update_niah_model_selection_summary(dpg: object, selected_display_names: tuple[str, ...]) -> None:
    if not dpg.does_item_exist("niah_model_selection_summary"):
        return

    if not selected_display_names:
        dpg.set_value("niah_model_selection_summary", "已选 0 个模型")
        return

    dpg.set_value(
        "niah_model_selection_summary",
        f"已选 {len(selected_display_names)} 个模型: {', '.join(selected_display_names)}",
    )


def _refresh_niah_model_selection(
    dpg: object,
    store: ModelConfigStore,
    selected_display_names: tuple[str, ...] = (),
) -> None:
    if not dpg.does_item_exist("niah_model_config_list"):
        return

    dpg.delete_item("niah_model_config_list", children_only=True)
    configs = store.list_all()
    if not configs:
        dpg.add_text("暂无可选模型配置，请先在“模型配置”页面保存。", parent="niah_model_config_list")
        _update_niah_model_selection_summary(dpg, ())
        return

    selected_name_set = set(selected_display_names)
    for config in configs:
        dpg.add_checkbox(
            label=config.display_name,
            tag=_niah_model_selection_tag(config.display_name),
            default_value=config.display_name in selected_name_set,
            parent="niah_model_config_list",
            callback=_handle_toggle_niah_model_selection,
            user_data=store,
        )

    _update_niah_model_selection_summary(
        dpg,
        tuple(config.display_name for config in configs if config.display_name in selected_name_set),
    )


def _handle_toggle_niah_model_selection(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    store = user_data
    _update_niah_model_selection_summary(dpg, _get_selected_niah_model_display_names(dpg, store))
    _update_niah_overview_metrics(dpg, store)


def _set_all_niah_model_selection(dpg: object, store: ModelConfigStore, selected: bool) -> None:
    all_display_names: list[str] = []
    for config in store.list_all():
        tag = _niah_model_selection_tag(config.display_name)
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, selected)
        if selected:
            all_display_names.append(config.display_name)

    _update_niah_model_selection_summary(dpg, tuple(all_display_names) if selected else ())
    _update_niah_overview_metrics(dpg, store)


def _handle_select_all_niah_models(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    _set_all_niah_model_selection(dpg, user_data, True)


def _handle_clear_niah_models(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    _set_all_niah_model_selection(dpg, user_data, False)


def _set_niah_panel_status(dpg: object, message: str) -> None:
    if dpg.does_item_exist("niah_panel_status"):
        dpg.set_value("niah_panel_status", message)


def _set_niah_result_summary(dpg: object, message: str) -> None:
    if dpg.does_item_exist("niah_result_summary"):
        dpg.set_value("niah_result_summary", message)


def _set_niah_report_action(dpg: object, report_html_path: str | None) -> None:
    if not dpg.does_item_exist("niah_open_report_button"):
        return

    report_path = Path(report_html_path).resolve() if report_html_path else None
    is_available = bool(report_path and report_path.exists())
    dpg.configure_item(
        "niah_open_report_button",
        enabled=is_available,
        user_data=str(report_path) if is_available else None,
    )


def _open_niah_report(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    report_html_path = str(user_data or "").strip()
    if not report_html_path:
        _set_status_text(dpg, "当前没有可打开的 HTML 报告")
        return

    report_path = Path(report_html_path)
    if not report_path.exists():
        _set_status_text(dpg, f"HTML 报告不存在: {report_path}")
        return

    webbrowser.open_new_tab(report_path.resolve().as_uri())
    _set_status_text(dpg, f"已在浏览器中打开报告: {report_path.name}")


def _get_niah_layout_metrics(expanded: bool) -> tuple[int, int, int]:
    if expanded:
        return (
            _NIAH_TOP_PANEL_HEIGHT_EXPANDED,
            _NIAH_SUMMARY_HEIGHT_EXPANDED,
            _NIAH_HEATMAP_HEIGHT_EXPANDED,
        )

    return (
        _NIAH_TOP_PANEL_HEIGHT_COLLAPSED,
        _NIAH_SUMMARY_HEIGHT_COLLAPSED,
        _NIAH_HEATMAP_HEIGHT_COLLAPSED,
    )


def _apply_niah_panel_layout(dpg: object, expanded: bool) -> None:
    if not dpg.does_item_exist("niah_main_splitter"):
        return

    top_panel_height, _summary_height, _heatmap_height = _get_niah_layout_metrics(expanded)

    for tag in ("niah_left_panel", "niah_right_panel", "niah_main_splitter"):
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, height=top_panel_height)


def _choose_niah_heatmap_model_name(
    available_model_names: tuple[str, ...],
    selected_model_name: str | None,
) -> str | None:
    if selected_model_name in available_model_names:
        return selected_model_name
    if available_model_names:
        return available_model_names[0]
    return None


def _set_niah_heatmap_model_selector(
    dpg: object,
    runtime: AppRuntimeState,
    available_model_names: tuple[str, ...],
) -> None:
    if not dpg.does_item_exist("niah_heatmap_model_selector"):
        return

    selected_model_name = _choose_niah_heatmap_model_name(
        available_model_names,
        runtime.selected_heatmap_model_name,
    )
    runtime.selected_heatmap_model_name = selected_model_name
    dpg.configure_item(
        "niah_heatmap_model_selector",
        items=available_model_names,
        enabled=bool(available_model_names),
    )
    dpg.set_value("niah_heatmap_model_selector", selected_model_name or "")


def _update_visible_niah_heatmap(dpg: object, runtime: AppRuntimeState) -> None:
    model_name = runtime.selected_heatmap_model_name
    if model_name is None:
        _update_niah_heatmap(dpg, None)
        return

    result = runtime.latest_model_results.get(model_name)
    if result is None:
        _update_niah_heatmap(dpg, None)
        return

    _update_niah_heatmap(dpg, result.artifacts.get("heatmap"))


def _handle_select_niah_heatmap_model(_sender: object, app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    runtime = user_data
    runtime.selected_heatmap_model_name = str(app_data or "").strip() or None
    _update_visible_niah_heatmap(dpg, runtime)


def _get_niah_section_width(dpg: object) -> int:
    if not dpg.does_item_exist("section_test_tasks"):
        return 0

    try:
        width, _height = dpg.get_item_rect_size("section_test_tasks")
    except Exception:
        return 0

    return int(width)


def _get_niah_top_panel_height(dpg: object) -> int:
    expanded = True
    if dpg.does_item_exist("log_output"):
        expanded = bool(dpg.get_item_configuration("log_output").get("show", True))

    top_panel_height, _summary_height, _heatmap_height = _get_niah_layout_metrics(expanded)
    return top_panel_height


def _apply_niah_dynamic_layout(dpg: object, runtime: AppRuntimeState) -> None:
    if not dpg.does_item_exist("niah_main_split_group"):
        return

    container_width = _get_niah_section_width(dpg)
    if container_width <= 0:
        return

    top_panel_height = _get_niah_top_panel_height(dpg)
    dimensions = resolve_niah_layout_dimensions(
        runtime.niah_layout_state,
        container_width=container_width,
        top_panel_height=top_panel_height,
        splitter_width=_NIAH_MAIN_SPLITTER_WIDTH,
        result_splitter_height=_NIAH_RESULT_SPLITTER_HEIGHT,
        right_panel_chrome_height=_NIAH_RIGHT_PANEL_CHROME_HEIGHT,
    )
    runtime.niah_layout_state = build_niah_layout_state(
        left_panel_width=dimensions.left_panel_width,
        result_summary_height=dimensions.result_summary_height,
    )

    if dpg.does_item_exist("niah_left_panel"):
        dpg.configure_item(
            "niah_left_panel",
            width=dimensions.left_panel_width,
            height=dimensions.top_panel_height,
        )
    if dpg.does_item_exist("niah_main_splitter"):
        dpg.configure_item(
            "niah_main_splitter",
            width=_NIAH_MAIN_SPLITTER_WIDTH,
            height=dimensions.top_panel_height,
        )
    if dpg.does_item_exist("niah_right_panel"):
        dpg.configure_item(
            "niah_right_panel",
            width=dimensions.right_panel_width,
            height=dimensions.top_panel_height,
        )
    if dpg.does_item_exist("niah_result_summary"):
        dpg.configure_item("niah_result_summary", height=dimensions.result_summary_height)
    if dpg.does_item_exist("niah_result_splitter"):
        dpg.configure_item("niah_result_splitter", height=_NIAH_RESULT_SPLITTER_HEIGHT)
    if dpg.does_item_exist("niah_heatmap_plot"):
        dpg.configure_item("niah_heatmap_plot", height=dimensions.heatmap_height)


def _update_niah_drag_layout(dpg: object, runtime: AppRuntimeState) -> None:
    active_handle: str | None = None
    if dpg.does_item_exist("niah_main_splitter") and dpg.is_item_active("niah_main_splitter"):
        active_handle = "main"
    elif dpg.does_item_exist("niah_result_splitter") and dpg.is_item_active("niah_result_splitter"):
        active_handle = "result"

    if active_handle is None:
        runtime.active_drag_handle = None
        runtime.last_drag_mouse_pos = None
        _apply_niah_dynamic_layout(dpg, runtime)
        return

    mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
    if runtime.active_drag_handle != active_handle or runtime.last_drag_mouse_pos is None:
        runtime.active_drag_handle = active_handle
        runtime.last_drag_mouse_pos = (mouse_x, mouse_y)
        _apply_niah_dynamic_layout(dpg, runtime)
        return

    delta_x = mouse_x - runtime.last_drag_mouse_pos[0]
    delta_y = mouse_y - runtime.last_drag_mouse_pos[1]
    runtime.last_drag_mouse_pos = (mouse_x, mouse_y)
    if active_handle == "main" and delta_x:
        runtime.niah_layout_state = build_niah_layout_state(
            left_panel_width=runtime.niah_layout_state.left_panel_width + int(delta_x),
            result_summary_height=runtime.niah_layout_state.result_summary_height,
        )
    elif active_handle == "result" and delta_y:
        runtime.niah_layout_state = build_niah_layout_state(
            left_panel_width=runtime.niah_layout_state.left_panel_width,
            result_summary_height=runtime.niah_layout_state.result_summary_height + int(delta_y),
        )

    _apply_niah_dynamic_layout(dpg, runtime)


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--"

    rounded_seconds = int(round(seconds))
    hours, remainder = divmod(rounded_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _build_niah_runtime_summary(
    status: str,
    work_dir: str | None,
    elapsed_seconds: float | None,
    processed_count: int | None = None,
    total_count: int | None = None,
    percent: float | None = None,
    pipeline: str = "eval",
) -> str:
    lines = [
        f"EvalScope 管线: {pipeline}",
        f"状态: {status}",
        f"已用时间: {_format_duration(elapsed_seconds)}",
    ]

    if processed_count is not None and total_count is not None and percent is not None:
        lines.append(f"进度: {processed_count} / {total_count} ({percent:.2f}%)")
        if processed_count > 0 and elapsed_seconds is not None and elapsed_seconds > 0:
            seconds_per_item = elapsed_seconds / processed_count
            remaining_count = max(0, total_count - processed_count)
            lines.append(f"速度: {seconds_per_item:.2f} s/it")
            lines.append(f"预计剩余: {_format_duration(remaining_count * seconds_per_item)}")
    else:
        lines.append("进度: 等待 EvalScope 初始化进度文件...")

    lines.append(f"输出目录: {work_dir or '待创建'}")
    return "\n".join(lines)


def _build_active_niah_runtime_summary(
    runtime: AppRuntimeState,
    status: str,
    work_dir: str | None,
    elapsed_seconds: float | None,
    processed_count: int | None = None,
    total_count: int | None = None,
    percent: float | None = None,
    pipeline: str = "eval",
) -> str:
    base_summary = _build_niah_runtime_summary(
        status=status,
        work_dir=work_dir,
        elapsed_seconds=elapsed_seconds,
        processed_count=processed_count,
        total_count=total_count,
        percent=percent,
        pipeline=pipeline,
    )
    batch = runtime.active_batch
    if batch is None:
        return base_summary

    current_model_name = batch.current_model_name or "未知模型"
    return "\n".join(
        [
            f"批量进度: {batch.completed_count}/{batch.total_count}",
            f"当前模型: {current_model_name} ({batch.current_task_index + 1}/{batch.total_count})",
            base_summary,
        ]
    )


def _estimate_niah_expected_sample_count(strategy: NeedleInHaystackStrategy | None) -> int | None:
    if strategy is None:
        return None

    parameters = getattr(strategy, "niah_parameters", None)
    if parameters is None:
        return None

    context_interval_count = int(getattr(parameters, "context_lengths_num_intervals", 0) or 0)
    depth_interval_count = int(getattr(parameters, "document_depth_percent_intervals", 0) or 0)
    subset_list = tuple(getattr(parameters, "subset_list", ()) or ())
    subset_count = len(subset_list)
    if context_interval_count <= 0 or depth_interval_count <= 0 or subset_count <= 0:
        return None

    return context_interval_count * depth_interval_count * subset_count


def _resolve_niah_progress_counts(
    strategy: NeedleInHaystackStrategy | None,
    progress_state: dict[str, object],
) -> tuple[int | None, int | None, float | None, int | None]:
    processed_count = progress_state.get("processed_count")
    total_count = progress_state.get("total_count")
    percent = progress_state.get("percent")
    tracker_total_count = total_count if isinstance(total_count, int) else None

    if not isinstance(processed_count, int):
        return None, tracker_total_count, float(percent) if isinstance(percent, (int, float)) else None, tracker_total_count

    expected_total_count = _estimate_niah_expected_sample_count(strategy)
    if expected_total_count is not None and expected_total_count > 0:
        display_processed_count = min(processed_count, expected_total_count)
        display_percent = (display_processed_count / expected_total_count) * 100.0
        return display_processed_count, expected_total_count, display_percent, tracker_total_count

    if tracker_total_count is None or tracker_total_count <= 0:
        return processed_count, None, float(percent) if isinstance(percent, (int, float)) else None, None

    return processed_count, tracker_total_count, float(percent) if isinstance(percent, (int, float)) else None, tracker_total_count


def read_evalscope_progress_state(work_dir: str | Path | None) -> dict[str, object] | None:
    if not work_dir:
        return None

    progress_path = Path(work_dir) / "progress.json"
    if not progress_path.exists():
        return None

    try:
        payload = json.loads(progress_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _set_niah_controls_enabled(dpg: object, enabled: bool, store: ModelConfigStore | None = None) -> None:
    for tag in _iter_niah_editable_control_tags(store):
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, enabled=enabled)


def _iter_niah_editable_control_tags(store: ModelConfigStore | None) -> tuple[str, ...]:
    tags = list(_NIAH_EDITABLE_TAGS)
    if store is None:
        return tuple(tags)

    tags.extend(_niah_model_selection_tag(config.display_name) for config in store.list_all())
    return tuple(tags)


def _update_niah_pending_status(dpg: object, runtime: AppRuntimeState) -> None:
    strategy = runtime.active_strategy
    status = runtime.active_task_status or "queued"
    work_dir = strategy.task_config.work_dir if strategy and strategy.task_config else None
    elapsed_seconds = None
    if runtime.active_task_started_at is not None:
        elapsed_seconds = max(0.0, time.monotonic() - runtime.active_task_started_at)

    _set_niah_result_summary(
        dpg,
        _build_active_niah_runtime_summary(
            runtime=runtime,
            status=status,
            work_dir=work_dir,
            elapsed_seconds=elapsed_seconds,
        ),
    )


def _set_niah_run_busy(dpg: object, busy: bool, store: ModelConfigStore | None = None) -> None:
    _set_niah_controls_enabled(dpg, enabled=not busy, store=store)
    if not dpg.does_item_exist("niah_run_button"):
        return

    dpg.configure_item(
        "niah_run_button",
        enabled=not busy,
        label="运行中..." if busy else "运行捞针测试",
    )


def _set_task_progress_value(dpg: object, value: float, overlay: str) -> None:
    if dpg.does_item_exist("task_progress"):
        dpg.set_value("task_progress", value)
        dpg.configure_item("task_progress", overlay=overlay)


def _set_batch_task_progress(dpg: object, runtime: AppRuntimeState, status: str) -> None:
    batch = runtime.active_batch
    if batch is None:
        _set_task_progress(dpg, status)
        return

    task_progress, overlay_label = _TASK_STATUS_PROGRESS.get(status, (0.0, status))
    total_count = max(1, batch.total_count)
    value = min(1.0, (batch.completed_count + (0.0 if status in FinalTaskStatus else task_progress)) / total_count)
    current_count = batch.completed_count if status in FinalTaskStatus else min(total_count, batch.completed_count + 1)
    _set_task_progress_value(dpg, value, f"{current_count}/{total_count} {overlay_label}")


def _build_niah_batch_result_summary(
    model_results: list[tuple[str, EvalResult | None, str | None]],
    collection_report_html_path: str | None = None,
    collection_report_table_path: str | None = None,
    collection_report_error: str | None = None,
) -> str:
    total_count = len(model_results)
    success_count = sum(1 for _model_name, result, _error_message in model_results if result and result.status == "completed")
    lines = [f"批量任务完成: {success_count}/{total_count} 成功"]

    if collection_report_html_path:
        lines.append(f"汇总 HTML 报告: {collection_report_html_path}")
    if collection_report_table_path:
        lines.append(f"汇总表格: {collection_report_table_path}")
    if collection_report_error:
        lines.append(f"汇总报告生成失败: {collection_report_error}")

    for model_name, result, error_message in model_results:
        if result is not None and result.status == "completed":
            accuracy = float(result.metrics.get("acc", 0.0))
            sample_count = int(result.metrics.get("sample_count", 0.0))
            lines.append(f"{model_name}: completed | acc={accuracy:.2%} | samples={sample_count}")
            continue

        status = result.status if result is not None else "failed"
        detail = error_message or (result.error_message if result is not None else "任务失败") or "任务失败"
        lines.append(f"{model_name}: {status} | {detail}")

    return "\n".join(lines)


def _format_niah_progress_text(progress_state: dict[str, object], work_dir: str | None) -> str:
    processed_count = progress_state.get("processed_count")
    total_count = progress_state.get("total_count")
    percent = progress_state.get("percent")
    status = progress_state.get("status") or "running"
    pipeline = progress_state.get("pipeline") or "eval"

    if isinstance(processed_count, int) and isinstance(total_count, int) and isinstance(percent, (int, float)):
        return (
            f"EvalScope 管线: {pipeline}\n"
            f"状态: {status}\n"
            f"进度: {processed_count} / {total_count} ({float(percent):.2f}%)\n"
            f"输出目录: {work_dir or '待创建'}"
        )

    return f"EvalScope 管线: {pipeline}\n状态: {status}\n输出目录: {work_dir or '待创建'}"


def _update_niah_progress_from_tracker(dpg: object, runtime: AppRuntimeState) -> None:
    strategy = runtime.active_strategy
    if strategy is None or strategy.task_config is None:
        return

    now = time.monotonic()
    if (now - runtime.last_progress_poll_at) < _PROGRESS_POLL_INTERVAL_SECONDS:
        return

    runtime.last_progress_poll_at = now

    progress_state = read_evalscope_progress_state(strategy.task_config.work_dir)
    if not progress_state:
        _update_niah_pending_status(dpg, runtime)
        return

    processed_count, total_count, percent, tracker_total_count = _resolve_niah_progress_counts(strategy, progress_state)
    elapsed_seconds = None
    if runtime.active_task_started_at is not None:
        elapsed_seconds = max(0.0, now - runtime.active_task_started_at)
    if isinstance(percent, (int, float)) and isinstance(processed_count, int) and isinstance(total_count, int):
        batch = runtime.active_batch
        if batch is None:
            _set_task_progress_value(
                dpg,
                max(0.0, min(1.0, float(percent) / 100.0)),
                f"{processed_count}/{total_count}",
            )
        else:
            overall_value = min(
                1.0,
                (batch.completed_count + max(0.0, min(1.0, float(percent) / 100.0))) / max(1, batch.total_count),
            )
            _set_task_progress_value(
                dpg,
                overall_value,
                f"{min(batch.total_count, batch.completed_count + 1)}/{batch.total_count}",
            )

        current_model_name = batch.current_model_name if batch is not None else None
        panel_status = f"任务状态: running | {processed_count}/{total_count} ({float(percent):.2f}%)"
        if current_model_name:
            panel_status = f"当前模型: {current_model_name} | {panel_status}"
        _set_niah_panel_status(dpg, panel_status)

    summary = _build_active_niah_runtime_summary(
        runtime=runtime,
        status=str(progress_state.get("status") or runtime.active_task_status or "running"),
        work_dir=strategy.task_config.work_dir,
        elapsed_seconds=elapsed_seconds,
        processed_count=processed_count if isinstance(processed_count, int) else None,
        total_count=total_count if isinstance(total_count, int) else None,
        percent=float(percent) if isinstance(percent, (int, float)) else None,
        pipeline=str(progress_state.get("pipeline") or "eval"),
    )
    if isinstance(tracker_total_count, int) and isinstance(total_count, int) and tracker_total_count != total_count:
        summary = f"{summary}\nEvalScope 估算总样本: {tracker_total_count}"

    _set_niah_result_summary(dpg, summary)


def _update_niah_heatmap(dpg: object, heatmap_artifact: dict[str, object] | None) -> None:
    context_lengths = []
    depth_percents = []
    point_lookup: dict[tuple[int, int], float] = {}

    if isinstance(heatmap_artifact, dict):
        context_lengths = [
            value for value in heatmap_artifact.get("context_lengths", []) if isinstance(value, int)
        ]
        depth_percents = [
            value for value in heatmap_artifact.get("depth_percents", []) if isinstance(value, int)
        ]
        matrix = heatmap_artifact.get("matrix", [])
        if isinstance(matrix, list):
            for row_index, row in enumerate(matrix):
                if row_index >= len(context_lengths) or not isinstance(row, list):
                    continue
                for column_index, value in enumerate(row):
                    if column_index >= len(depth_percents) or not isinstance(value, (int, float)):
                        continue
                    point_lookup[(context_lengths[row_index], depth_percents[column_index])] = float(value)

    heatmap_state = build_niah_heatmap_state(
        points=[
            (context_length, depth_percent, value)
            for (context_length, depth_percent), value in point_lookup.items()
        ]
    )

    if dpg.does_item_exist("niah_heatmap_series"):
        dpg.delete_item("niah_heatmap_series")

    context_ticks = list(heatmap_state.context_lengths)
    depth_ticks = list(heatmap_state.depth_percents)
    render_values = [
        point_lookup.get((context_length, depth_percent), 0.0)
        for depth_percent in depth_ticks
        for context_length in context_ticks
    ]
    rows = max(1, len(depth_ticks))
    cols = max(1, len(context_ticks))
    x_max = max(1, cols - 1)
    y_max = max(1, rows - 1)

    dpg.add_heat_series(
        render_values or [0.0],
        rows,
        cols,
        parent="niah_heatmap_y_axis",
        tag="niah_heatmap_series",
        bounds_min=(0.0, 0.0),
        bounds_max=(float(x_max), float(y_max)),
        scale_min=0.0,
        scale_max=1.0,
        format="%0.2f",
    )

    if hasattr(dpg, "set_axis_ticks"):
        dpg.set_axis_ticks(
            "niah_heatmap_x_axis",
            tuple((str(value), index) for index, value in enumerate(context_ticks)),
        )
        dpg.set_axis_ticks(
            "niah_heatmap_y_axis",
            tuple((f"{value}%", index) for index, value in enumerate(depth_ticks)),
        )


def _read_niah_parameters(dpg: object, store: ModelConfigStore) -> tuple[list[ModelConfig], dict[str, object]]:
    selected_model_names = _get_selected_niah_model_display_names(dpg, store)
    selected_judge_name = str(dpg.get_value("niah_judge_model_config_list") or "").strip()

    selected_model_configs = [
        model_config
        for model_name in selected_model_names
        if (model_config := store.get(model_name)) is not None
    ]
    if not selected_model_configs:
        raise ValueError("请至少选择一个待测模型配置")

    judge_model_config = store.get(selected_judge_name)
    if judge_model_config is None:
        raise ValueError("请选择裁判模型配置")

    selected_subsets = []
    if dpg.get_value("niah_subset_english"):
        selected_subsets.append("english")
    if dpg.get_value("niah_subset_chinese"):
        selected_subsets.append("chinese")

    return selected_model_configs, {
        "retrieval_question": str(dpg.get_value("niah_retrieval_question") or "").strip(),
        "needles_text": str(dpg.get_value("niah_needles_text") or "").strip(),
        "context_lengths_min": int(dpg.get_value("niah_context_lengths_min")),
        "context_lengths_max": int(dpg.get_value("niah_context_lengths_max")),
        "context_lengths_num_intervals": int(dpg.get_value("niah_context_lengths_num_intervals")),
        "document_depth_percent_min": int(dpg.get_value("niah_document_depth_percent_min")),
        "document_depth_percent_max": int(dpg.get_value("niah_document_depth_percent_max")),
        "document_depth_percent_intervals": int(dpg.get_value("niah_document_depth_percent_intervals")),
        "tokenizer_path": str(dpg.get_value("niah_tokenizer_path") or "").strip(),
        "show_score": bool(dpg.get_value("niah_show_score")),
        "subset_list": selected_subsets,
        "judge_model": {
            "api_url": judge_model_config.base_url,
            "api_key": judge_model_config.api_key,
            "model_name": judge_model_config.model_name,
        },
    }


def _handle_run_niah(_sender: object, _app_data: object, user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    runtime = user_data
    try:
        model_configs, parameters = _read_niah_parameters(dpg, runtime.store)
        batch_task_id = f"niah-batch-{uuid4().hex[:8]}"
        task_ids: list[str] = []
        task_id_to_model_name: dict[str, str] = {}
        task_id_to_strategy: dict[str, NeedleInHaystackStrategy] = {}
        for index, model_config in enumerate(model_configs, start=1):
            strategy = NeedleInHaystackStrategy(model_config=model_config, parameters=parameters)
            strategy.prepare()
            task_id = f"{batch_task_id}-{index}"
            task_ids.append(task_id)
            task_id_to_model_name[task_id] = model_config.display_name
            task_id_to_strategy[task_id] = strategy
    except ValueError as error:
        _set_status_text(dpg, str(error))
        _set_niah_panel_status(dpg, str(error))
        return

    runtime.active_batch = NIAHBatchRuntimeState(
        task_ids=tuple(task_ids),
        task_id_to_model_name=task_id_to_model_name,
        task_id_to_strategy=task_id_to_strategy,
    )
    runtime.active_task_id = runtime.active_batch.current_task_id
    runtime.active_strategy = runtime.active_batch.current_strategy
    runtime.active_task_status = "queued"
    runtime.active_task_started_at = time.monotonic()
    runtime.last_progress_poll_at = 0.0
    runtime.latest_model_results = {}
    runtime.selected_heatmap_model_name = None
    _set_niah_heatmap_model_selector(dpg, runtime, ())
    for task_id in task_ids:
        runtime.task_runner.submit_strategy(task_id=task_id, strategy=task_id_to_strategy[task_id])
    _set_status_text(dpg, f"已提交 {len(task_ids)} 个模型的批量捞针任务")
    _set_niah_panel_status(dpg, f"批量任务已排队，等待后台执行。当前模型: {runtime.active_batch.current_model_name}")
    _update_niah_pending_status(dpg, runtime)
    _set_niah_run_busy(dpg, True, store=runtime.store)
    _set_batch_task_progress(dpg, runtime, "queued")


def _finalize_niah_batch(dpg: object, runtime: AppRuntimeState) -> None:
    batch = runtime.active_batch
    if batch is None:
        return

    ordered_results = batch.ordered_results()
    runtime.latest_model_results = {
        model_name: result
        for model_name, result, _error_message in ordered_results
        if result is not None and result.status == "completed"
    }
    _set_niah_heatmap_model_selector(dpg, runtime, tuple(runtime.latest_model_results.keys()))
    successful_results = [
        result
        for _model_name, result, _error_message in ordered_results
        if result is not None and result.status == "completed"
    ]
    outputs_dirs = [
        str(result.artifacts.get("outputs_dir"))
        for result in successful_results
        if isinstance(result.artifacts, dict) and result.artifacts.get("outputs_dir")
    ]
    collection_report: MultiModelSummaryReport | None = None
    collection_report_error: str | None = None
    if outputs_dirs:
        try:
            collection_report = build_multi_model_summary_report(outputs_dirs=outputs_dirs)
        except Exception as error:
            collection_report_error = str(error)

    batch.summary_report = collection_report
    success_count = len(successful_results)
    total_count = len(ordered_results)
    if success_count == total_count:
        final_status_text = f"批量捞针测试已完成，共 {total_count} 个模型成功。"
    elif success_count == 0:
        final_status_text = "批量捞针测试已结束，但所有模型均失败。"
    else:
        final_status_text = f"批量捞针测试已完成，{success_count}/{total_count} 个模型成功。"

    _set_status_text(dpg, final_status_text)
    _set_niah_panel_status(dpg, final_status_text)
    _set_niah_result_summary(
        dpg,
        _build_niah_batch_result_summary(
            model_results=ordered_results,
            collection_report_html_path=collection_report.report_html_path if collection_report else None,
            collection_report_table_path=collection_report.report_table_path if collection_report else None,
            collection_report_error=collection_report_error,
        ),
    )
    _set_niah_report_action(dpg, collection_report.report_html_path if collection_report else None)
    _update_visible_niah_heatmap(dpg, runtime)

    runtime.active_batch = None
    runtime.active_task_id = None
    runtime.active_strategy = None
    runtime.active_task_status = None
    runtime.active_task_started_at = None
    runtime.last_progress_poll_at = 0.0


def _apply_task_snapshot(dpg: object, runtime: AppRuntimeState, snapshot: TaskSnapshot) -> None:
    batch = runtime.active_batch
    if batch is None:
        if snapshot.task_id != runtime.active_task_id:
            return
    else:
        if snapshot.task_id != runtime.active_task_id or not batch.contains_task(snapshot.task_id):
            return

    runtime.active_task_status = snapshot.status
    current_model_name = batch.current_model_name if batch is not None else None
    if snapshot.status not in FinalTaskStatus:
        _set_batch_task_progress(dpg, runtime, snapshot.status)
        panel_status = f"任务状态: {snapshot.status}"
        if current_model_name:
            panel_status = (
                f"当前模型: {current_model_name} ({batch.current_task_index + 1}/{batch.total_count}) | {panel_status}"
            )
        _set_niah_panel_status(dpg, panel_status)
        _update_niah_pending_status(dpg, runtime)
        return

    active_strategy = runtime.active_strategy
    if batch is not None:
        batch.record_result(snapshot)
        if snapshot.status == "completed" and snapshot.result is not None:
            completed_model_name = batch.task_id_to_model_name.get(snapshot.task_id, snapshot.task_id)
            runtime.latest_model_results[completed_model_name] = snapshot.result
            _set_niah_heatmap_model_selector(dpg, runtime, tuple(runtime.latest_model_results.keys()))
            if runtime.selected_heatmap_model_name is None:
                runtime.selected_heatmap_model_name = completed_model_name
            _update_visible_niah_heatmap(dpg, runtime)

        next_task_id = batch.advance()
        if next_task_id is not None:
            runtime.active_task_id = next_task_id
            runtime.active_strategy = batch.current_strategy
            runtime.active_task_status = "queued"
            runtime.active_task_started_at = time.monotonic()
            runtime.last_progress_poll_at = 0.0
            _set_batch_task_progress(dpg, runtime, "queued")
            _set_niah_panel_status(
                dpg,
                (
                    f"模型 {batch.task_id_to_model_name.get(snapshot.task_id, snapshot.task_id)} 已{snapshot.status}，"
                    f"继续执行 {batch.current_model_name} ({batch.current_task_index + 1}/{batch.total_count})"
                ),
            )
            _set_niah_result_summary(dpg, _build_niah_batch_result_summary(batch.ordered_results()))
            return

        _set_batch_task_progress(dpg, runtime, "completed")
        _set_niah_run_busy(dpg, False, store=runtime.store)
        _finalize_niah_batch(dpg, runtime)
        return

    _set_niah_run_busy(dpg, False, store=runtime.store)
    runtime.active_strategy = None
    runtime.active_task_status = None
    runtime.active_task_started_at = None
    if snapshot.status == "completed" and snapshot.result is not None:
        accuracy = snapshot.result.metrics.get("acc", 0.0)
        sample_count = int(snapshot.result.metrics.get("sample_count", 0.0))
        outputs_dir = snapshot.result.artifacts.get("outputs_dir") or "未提供输出目录"
        heatmap_path = snapshot.result.artifacts.get("heatmap_path") or "未提供热力图路径"
        report_html_path = snapshot.result.artifacts.get("report_html_path") or "未提供 HTML 报告路径"
        model_name = active_strategy.model_config.display_name if active_strategy is not None else "当前模型"
        runtime.latest_model_results = {model_name: snapshot.result}
        runtime.selected_heatmap_model_name = model_name
        _set_niah_heatmap_model_selector(dpg, runtime, (model_name,))
        _set_status_text(dpg, "捞针测试已完成")
        _set_niah_panel_status(dpg, f"任务完成，准确率 {accuracy:.2%}。")
        _set_niah_result_summary(
            dpg,
            f"平均准确率: {accuracy:.2%}\n样本数: {sample_count}\n输出目录: {outputs_dir}\n热力图: {heatmap_path}\nHTML 报告: {report_html_path}",
        )
        _set_niah_report_action(
            dpg,
            snapshot.result.artifacts.get("report_html_path") if isinstance(snapshot.result.artifacts, dict) else None,
        )
        _update_visible_niah_heatmap(dpg, runtime)
        return

    if snapshot.status == "failed":
        _set_status_text(dpg, "捞针测试执行失败")
        _set_niah_panel_status(dpg, "任务失败，请检查日志输出。")
        outputs_dir = active_strategy.task_config.work_dir if active_strategy and active_strategy.task_config else "未创建输出目录"
        _set_niah_result_summary(
            dpg,
            f"{snapshot.error_message or '后台任务失败，未返回更多信息。'}\n输出目录: {outputs_dir}",
        )
        _set_niah_report_action(dpg, None)
        return

    _set_status_text(dpg, "捞针测试已取消")
    _set_niah_panel_status(dpg, "任务已取消。")
    _set_niah_result_summary(dpg, "任务已取消，未生成结果。")
    _set_niah_report_action(dpg, None)


def _drain_task_updates(dpg: object, runtime: AppRuntimeState) -> None:
    while True:
        try:
            snapshot = runtime.update_queue.get_nowait()
        except Empty:
            return

        _apply_task_snapshot(dpg, runtime, snapshot)


def _add_niah_help_text(dpg: object, message: str) -> None:
    dpg.add_text(message, wrap=500)


def _build_niah_numeric_group(
    dpg: object,
    fields: tuple[tuple[str, str, int, int | None, int | None], ...],
    callback: Callable[[object, object, object], None] | None = None,
    user_data: object | None = None,
) -> None:
    with dpg.table(
        header_row=False,
        policy=getattr(dpg, "mvTable_SizingStretchProp", 0),
        borders_innerV=False,
        borders_outerV=False,
        borders_innerH=False,
        borders_outerH=False,
        no_host_extendX=True,
        no_pad_outerX=True,
    ):
        for _index in range(len(fields)):
            dpg.add_table_column(init_width_or_weight=1.0, width_stretch=True)

        with dpg.table_row():
            for tag, label, default_value, min_value, max_value in fields:
                with dpg.group():
                    dpg.add_text(label)
                    kwargs = {
                        "tag": tag,
                        "label": "",
                        "width": -1,
                        "default_value": default_value,
                    }
                    if min_value is not None:
                        kwargs["min_value"] = min_value
                        kwargs["min_clamped"] = True
                    if max_value is not None:
                        kwargs["max_value"] = max_value
                        kwargs["max_clamped"] = True
                    if callback is not None:
                        kwargs["callback"] = callback
                        kwargs["user_data"] = user_data
                    dpg.add_input_int(**kwargs)


def _build_niah_panel(dpg: object, runtime: AppRuntimeState, show: bool) -> None:
    state = build_niah_panel_state()
    spec_map = {spec.tag: spec for spec in build_niah_parameter_specs()}
    left_column_weight, right_column_weight = build_niah_column_weights()
    with dpg.group(tag="section_test_tasks", show=show):
        with dpg.table(
            header_row=False,
            policy=getattr(dpg, "mvTable_SizingStretchProp", 0),
            borders_innerV=False,
            borders_outerV=False,
            borders_innerH=False,
            borders_outerH=False,
            no_host_extendX=True,
            no_pad_outerX=True,
            tag="niah_main_layout_table",
        ):
            dpg.add_table_column(init_width_or_weight=left_column_weight, width_stretch=True)
            dpg.add_table_column(init_width_or_weight=right_column_weight, width_stretch=True)
            with dpg.table_row():
                with dpg.child_window(tag="niah_left_panel", border=True, width=-1, autosize_y=True):
                    _add_card_heading(
                        dpg,
                        "CONTROL STACK",
                        "模型与参数控制",
                        "先锁定待测模型与裁判模型，再配置长上下文网格参数，最后启动批量执行。页面只保留一个纵向滚动区。",
                        help_tag_prefix="niah_left_panel",
                    )
                    dpg.add_spacer(height=6)
                    dpg.add_text(spec_map["niah_model_config_list"].label)
                    with dpg.child_window(tag="niah_model_config_list", border=True, height=180, autosize_x=True):
                        pass
                    dpg.add_text("已选 0 个模型", tag="niah_model_selection_summary", wrap=500)
                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label="全选",
                            tag="niah_select_all_models_button",
                            callback=_handle_select_all_niah_models,
                            user_data=runtime.store,
                        )
                        dpg.add_button(
                            label="清空",
                            tag="niah_clear_models_button",
                            callback=_handle_clear_niah_models,
                            user_data=runtime.store,
                        )
                    _add_niah_help_text(dpg, spec_map["niah_model_config_list"].help_text)

                    dpg.add_text(spec_map["niah_judge_model_config_list"].label)
                    dpg.add_listbox(
                        tag="niah_judge_model_config_list",
                        items=[],
                        width=-1,
                        num_items=5,
                        callback=_handle_niah_configuration_changed,
                        user_data=runtime.store,
                    )
                    _add_niah_help_text(dpg, spec_map["niah_judge_model_config_list"].help_text)
                    dpg.add_spacer(height=8)

                    dpg.add_text("基础参数")
                    dpg.add_text(spec_map["niah_retrieval_question"].label)
                    dpg.add_input_text(
                        tag="niah_retrieval_question",
                        width=-1,
                        default_value=state.retrieval_question,
                    )
                    _add_niah_help_text(dpg, spec_map["niah_retrieval_question"].help_text)

                    dpg.add_text("Needles（每行一个）")
                    dpg.add_input_text(
                        tag="niah_needles_text",
                        width=-1,
                        height=96,
                        multiline=True,
                        no_horizontal_scroll=True,
                        default_value=state.needles_text,
                    )
                    _add_niah_help_text(dpg, spec_map["niah_needles_text"].help_text)

                    dpg.add_text("Tokenizer Path")
                    dpg.add_input_text(
                        tag="niah_tokenizer_path",
                        width=-1,
                        default_value=state.tokenizer_path,
                    )
                    _add_niah_help_text(dpg, spec_map["niah_tokenizer_path"].help_text)

                    dpg.add_spacer(height=8)
                    dpg.add_text("维度控制")
                    _add_niah_help_text(dpg, spec_map["niah_context_lengths_num_intervals"].help_text)
                    _build_niah_numeric_group(
                        dpg,
                        fields=(
                            ("niah_context_lengths_min", "最小 Token 长度", state.context_lengths_min, 1, None),
                            ("niah_context_lengths_max", "最大 Token 长度", state.context_lengths_max, 1, None),
                            (
                                "niah_context_lengths_num_intervals",
                                "长度区间数",
                                state.context_lengths_num_intervals,
                                1,
                                None,
                            ),
                        ),
                        callback=_handle_niah_configuration_changed,
                        user_data=runtime.store,
                    )

                    _add_niah_help_text(dpg, spec_map["niah_document_depth_percent_intervals"].help_text)
                    _build_niah_numeric_group(
                        dpg,
                        fields=(
                            (
                                "niah_document_depth_percent_min",
                                "最小深度 %",
                                state.document_depth_percent_min,
                                0,
                                100,
                            ),
                            (
                                "niah_document_depth_percent_max",
                                "最大深度 %",
                                state.document_depth_percent_max,
                                0,
                                100,
                            ),
                            (
                                "niah_document_depth_percent_intervals",
                                "深度区间数",
                                state.document_depth_percent_intervals,
                                1,
                                None,
                            ),
                        ),
                        callback=_handle_niah_configuration_changed,
                        user_data=runtime.store,
                    )

                    dpg.add_spacer(height=8)
                    dpg.add_text("语料与显示")
                    with dpg.group(horizontal=True):
                        dpg.add_checkbox(
                            label="英文语料",
                            tag="niah_subset_english",
                            default_value=True,
                            callback=_handle_niah_configuration_changed,
                            user_data=runtime.store,
                        )
                        dpg.add_checkbox(
                            label="中文语料",
                            tag="niah_subset_chinese",
                            default_value=True,
                            callback=_handle_niah_configuration_changed,
                            user_data=runtime.store,
                        )
                        dpg.add_checkbox(
                            label="热力图显示数值",
                            tag="niah_show_score",
                            default_value=state.show_score,
                            callback=_handle_niah_configuration_changed,
                            user_data=runtime.store,
                        )
                    _add_niah_help_text(dpg, spec_map["niah_subset_english"].help_text)

                    dpg.add_spacer(height=8)
                    dpg.add_button(
                        label=state.run_button_label,
                        tag="niah_run_button",
                        callback=_handle_run_niah,
                        user_data=runtime,
                    )
                    dpg.add_text(state.status_text, tag="niah_panel_status", wrap=500)

                with dpg.child_window(tag="niah_right_panel", border=True, width=-1, autosize_y=True):
                    _add_card_heading(
                        dpg,
                        "LIVE RESULTS",
                        "执行与展示",
                        "先看任务概览，再读运行摘要与热力图；整个区域面向正在运行和刚完成的批量任务。",
                        help_tag_prefix="niah_right_panel",
                    )
                    dpg.add_spacer(height=6)
                    _build_niah_overview_metric_cards(dpg)
                    dpg.add_spacer(height=6)
                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label="打开 HTML 报告",
                            tag="niah_open_report_button",
                            callback=_open_niah_report,
                            enabled=False,
                        )
                        dpg.add_combo(
                            tag="niah_heatmap_model_selector",
                            items=(),
                            width=240,
                            label="",
                            callback=_handle_select_niah_heatmap_model,
                            user_data=runtime,
                            enabled=False,
                        )
                    dpg.add_separator()
                    dpg.add_input_text(
                        default_value="尚未运行捞针测试。",
                        tag="niah_result_summary",
                        multiline=True,
                        readonly=True,
                        width=-1,
                        height=180,
                        no_horizontal_scroll=True,
                    )
                    with dpg.plot(
                        label="检索热力图",
                        tag="niah_heatmap_plot",
                        height=320,
                        width=-1,
                        no_menus=True,
                        no_mouse_pos=True,
                    ):
                        dpg.add_plot_axis(dpg.mvXAxis, label="上下文长度", tag="niah_heatmap_x_axis")
                        dpg.add_plot_axis(dpg.mvYAxis, label="文档深度 (%)", tag="niah_heatmap_y_axis")
        _bind_theme_if_exists(dpg, "niah_right_panel", "app_card_theme")
        _bind_theme_if_exists(dpg, "niah_open_report_button", "app_nav_button_theme")

        _refresh_model_config_list(dpg, runtime.store)
        _refresh_niah_model_selection(dpg, runtime.store, state.selected_model_config_names)
        _set_niah_heatmap_model_selector(dpg, runtime, ())
        _set_niah_report_action(dpg, None)
        _update_niah_heatmap(dpg, None)
        _update_niah_overview_metrics(dpg, runtime.store)


def _build_placeholder_panel(dpg: object, tag: str, title: str, message: str, show: bool) -> None:
    with dpg.group(tag=tag, show=show):
        with dpg.child_window(tag=f"{tag}_card", border=True, autosize_x=True, autosize_y=True):
            _add_card_heading(dpg, "FUTURE SURFACE", title, message, help_tag_prefix=f"{tag}_card")
            dpg.add_text("为避免伪实现，该区域在真实结果数据模型接入前只保留信息架构与视觉占位。", wrap=_SECTION_HERO_WRAP)
        _bind_theme_if_exists(dpg, f"{tag}_card", "app_card_theme")


def _get_content_region_height(log_panel_height: int) -> int:
    return -(log_panel_height + _CONTENT_BOTTOM_PADDING)


def _set_log_panel_expanded(dpg: object, expanded: bool) -> None:
    state = build_log_panel_state(expanded=expanded)

    dpg.configure_item("bottom_panel", height=state.panel_height)
    dpg.configure_item(
        "content_scroll_region",
        height=_get_content_region_height(state.panel_height),
    )
    dpg.configure_item("log_output", show=state.show_log_output, height=state.log_height)
    dpg.configure_item("log_panel_separator", show=state.show_log_output)
    dpg.configure_item("log_panel_toggle_button", label=state.toggle_label)
    _apply_niah_panel_layout(dpg, expanded=expanded)


def _handle_toggle_log_panel(_sender: object, _app_data: object, _user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    current_label = dpg.get_item_configuration("log_panel_toggle_button")["label"]
    _set_log_panel_expanded(dpg, expanded=current_label == "展开日志")


def _build_sidebar(dpg: object, shell: AppShell) -> None:
    with dpg.child_window(tag="sidebar_panel", width=shell.navigation_width, border=True):
        dpg.add_text("CONTROL PLANE")
        dpg.add_text(shell.brand_title)
        dpg.add_text(shell.brand_subtitle, wrap=230)
        dpg.add_spacer(height=10)
        dpg.add_text("导航")
        dpg.add_text("围绕配置、执行与结果的三段式工作流组织桌面操作。", wrap=230)
        dpg.add_separator()

        for item in shell.navigation_items:
            dpg.add_button(
                label=item.label,
                tag=item.tag,
                width=-1,
                callback=_handle_navigation,
                user_data=item.tag,
            )
            _bind_theme_if_exists(dpg, item.tag, "app_nav_button_theme")

    _bind_theme_if_exists(dpg, "sidebar_panel", "app_card_theme")


def _build_bottom_panel(dpg: object, shell: AppShell) -> None:
    log_panel_state = build_log_panel_state()

    with dpg.child_window(
        tag="bottom_panel",
        border=True,
        autosize_x=True,
        height=log_panel_state.panel_height,
    ):
        with dpg.group(horizontal=True):
            dpg.add_text("SYSTEM CONSOLE")
            dpg.add_text("运行日志")
            dpg.add_button(
                label=log_panel_state.toggle_label,
                tag="log_panel_toggle_button",
                callback=_handle_toggle_log_panel,
            )

        add_log_output(
            default_value=shell.log_output,
            height=log_panel_state.log_height,
            show=log_panel_state.show_log_output,
        )
        _bind_theme_if_exists(dpg, "log_output", "app_console_theme")
        dpg.add_separator(tag="log_panel_separator", show=log_panel_state.show_log_output)
        with dpg.group(horizontal=True):
            add_status_bar(state=build_status_state(shell.status_text))
            add_progress_indicator(
                state=build_progress_state(
                    shell.progress_value,
                    shell.progress_overlay,
                )
            )

    _bind_theme_if_exists(dpg, "bottom_panel", "app_card_theme")
    _bind_theme_if_exists(dpg, "log_panel_toggle_button", "app_nav_button_theme")


def _build_content_panel(dpg: object, shell: AppShell, store: ModelConfigStore) -> None:
    runtime = AppRuntimeState(
        store=store,
        task_runner=TaskRunner(),
        update_queue=SimpleQueue(),
    )
    runtime.task_runner.register_callback(lambda update: runtime.update_queue.put(update))

    with dpg.child_window(tag="content_panel", border=False, autosize_x=True):
        with dpg.child_window(
            tag="content_scroll_region",
            border=False,
            autosize_x=True,
            height=_get_content_region_height(build_log_panel_state().panel_height),
        ):
            _build_section_hero(dpg, shell.default_section_tag)
            dpg.add_spacer(height=12)
            _build_model_config_panel(dpg, store)
            _build_niah_panel(dpg, runtime, show=False)
            _build_placeholder_panel(
                dpg,
                tag="section_results_overview",
                title="结果概览",
                message="结果概览视图将在接入评测结果数据模型后展示。",
                show=False,
            )

            _show_section(dpg, shell.default_section_tag)

        _build_bottom_panel(dpg, shell)

    return runtime


def refresh_log_output() -> None:
    import dearpygui.dearpygui as dpg

    if not dpg.does_item_exist("log_output"):
        return

    dpg.set_value("log_output", format_log_entries(get_shared_sink().snapshot()))


def launch_app() -> None:
    import dearpygui.dearpygui as dpg

    shell = build_app_shell()
    main_window = build_main_window_state(shell)
    logger = get_logger("ui")
    store = ModelConfigStore(storage_path=_resolve_model_config_store_path())
    runtime: AppRuntimeState | None = None

    dpg.create_context()
    _create_app_themes(dpg)
    attach_external_logger("evalscope")
    _bind_default_font(dpg, "ui")
    dpg.create_viewport(title="ai_test_tool", width=shell.width, height=shell.height)

    with dpg.window(
        label="main_window",
        tag="main_window",
        width=main_window.width,
        height=main_window.height,
        pos=main_window.pos,
        no_move=main_window.no_move,
        no_resize=main_window.no_resize,
        no_collapse=main_window.no_collapse,
        no_close=main_window.no_close,
        no_title_bar=main_window.no_title_bar,
    ):
        with dpg.group(horizontal=True):
            _build_sidebar(dpg, shell)
            runtime = _build_content_panel(dpg, shell, store)

    dpg.setup_dearpygui()
    dpg.bind_theme("app_global_theme")
    dpg.show_viewport()
    if hasattr(dpg, "maximize_viewport"):
        dpg.maximize_viewport()
    dpg.set_primary_window("main_window", True)
    apply_windows_viewport_title(
        getattr(dpg, "get_viewport_platform_handle", lambda: None)(),
        shell.title,
        fallback_window_title="ai_test_tool",
    )
    logger.info("UI initialized")

    frame_index = 0
    try:
        while dpg.is_dearpygui_running():
            if runtime is not None:
                _update_niah_drag_layout(dpg, runtime)
                _drain_task_updates(dpg, runtime)
                _update_niah_progress_from_tracker(dpg, runtime)
            if frame_index % 15 == 0:
                refresh_log_output()
            dpg.render_dearpygui_frame()
            if frame_index < 3:
                apply_windows_viewport_title(
                    getattr(dpg, "get_viewport_platform_handle", lambda: None)(),
                    shell.title,
                    fallback_window_title="ai_test_tool",
                )
            frame_index += 1
    finally:
        if runtime is not None:
            runtime.task_runner.shutdown()
        dpg.destroy_context()