from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path

from core.config import ModelConfig
from core.config import ModelConfigStore
from core.logger import get_logger
from core.logger import get_shared_sink
from ui.components import (
    NavigationItem,
    add_log_output,
    add_progress_indicator,
    add_status_bar,
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


@dataclass(frozen=True, slots=True)
class AppShell:
    title: str
    width: int
    height: int
    navigation_width: int
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


def build_app_shell() -> AppShell:
    return AppShell(
        title="LLM API 评测工具",
        width=1440,
        height=900,
        navigation_width=260,
        status_text="Ready",
        progress_value=0.0,
        progress_overlay="0%",
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


def apply_windows_viewport_title(
    platform_handle: int | None,
    title: str,
    platform_name: str | None = None,
    set_title_func: Callable[[int, str], None] | None = None,
) -> bool:
    active_platform_name = platform_name or os.name
    if active_platform_name != "nt" or not platform_handle:
        return False

    title_setter = set_title_func or _set_native_windows_title
    title_setter(int(platform_handle), title)
    return True


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
    dpg.configure_item("config_list", items=items)
    dpg.configure_item("config_list_hint", show=not items)

    if items and selected_display_name in items:
        dpg.set_value("config_list", selected_display_name)


def _show_section(dpg: object, section_tag: str) -> None:
    for navigation_tag, panel_tag in _SECTION_PANEL_TAGS.items():
        dpg.configure_item(panel_tag, show=navigation_tag == section_tag)

    dpg.set_value("active_section_title", _SECTION_TITLES[section_tag])


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


def _build_model_config_panel(dpg: object, store: ModelConfigStore) -> None:
    with dpg.child_window(tag="section_model_config", border=False, autosize_x=True):
        dpg.add_text("模型 API 配置")
        dpg.add_text("本地配置将保存在当前用户目录下，并在 Windows 上使用系统凭据保护。")
        for note in build_model_config_usage_notes():
            dpg.add_text(f"- {note}")
        dpg.add_separator()

        with dpg.group(horizontal=True):
            with dpg.child_window(width=460, border=False, autosize_y=True):
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

            with dpg.child_window(border=True, autosize_x=True, height=220):
                dpg.add_text("已保存配置")
                dpg.add_listbox(
                    tag="config_list",
                    items=[],
                    width=-1,
                    num_items=8,
                    callback=_handle_select_model_config,
                    user_data=store,
                )
                dpg.add_text("暂无已保存配置", tag="config_list_hint")
                dpg.add_text("点击某一项后，左侧会显示该配置的详细内容。")

        _refresh_model_config_list(dpg, store)
        _set_model_config_form_values(dpg)


def _build_placeholder_panel(dpg: object, tag: str, title: str, message: str, show: bool) -> None:
    with dpg.child_window(tag=tag, border=False, autosize_x=True, show=show):
        dpg.add_text(title)
        dpg.add_separator()
        dpg.add_text(message)


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


def _handle_toggle_log_panel(_sender: object, _app_data: object, _user_data: object) -> None:
    import dearpygui.dearpygui as dpg

    current_label = dpg.get_item_configuration("log_panel_toggle_button")["label"]
    _set_log_panel_expanded(dpg, expanded=current_label == "展开日志")


def _build_sidebar(dpg: object, shell: AppShell) -> None:
    with dpg.child_window(tag="sidebar_panel", width=shell.navigation_width, border=True):
        dpg.add_text("导航")
        dpg.add_separator()

        for item in shell.navigation_items:
            dpg.add_button(
                label=item.label,
                tag=item.tag,
                width=-1,
                callback=_handle_navigation,
                user_data=item.tag,
            )


def _build_bottom_panel(dpg: object, shell: AppShell) -> None:
    log_panel_state = build_log_panel_state()

    with dpg.child_window(
        tag="bottom_panel",
        border=True,
        autosize_x=True,
        height=log_panel_state.panel_height,
    ):
        with dpg.group(horizontal=True):
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
        dpg.add_separator(tag="log_panel_separator", show=log_panel_state.show_log_output)
        with dpg.group(horizontal=True):
            add_status_bar(state=build_status_state(shell.status_text))
            add_progress_indicator(
                state=build_progress_state(
                    shell.progress_value,
                    shell.progress_overlay,
                )
            )


def _build_content_panel(dpg: object, shell: AppShell, store: ModelConfigStore) -> None:
    with dpg.child_window(tag="content_panel", border=False, autosize_x=True):
        with dpg.child_window(
            tag="content_scroll_region",
            border=False,
            autosize_x=True,
            height=_get_content_region_height(build_log_panel_state().panel_height),
        ):
            dpg.add_text(_SECTION_TITLES[shell.default_section_tag], tag="active_section_title")
            dpg.add_separator()
            _build_model_config_panel(dpg, store)
            _build_placeholder_panel(
                dpg,
                tag="section_test_tasks",
                title="测试任务",
                message="测试任务视图将在下一阶段接入策略执行与后台调度。",
                show=False,
            )
            _build_placeholder_panel(
                dpg,
                tag="section_results_overview",
                title="结果概览",
                message="结果概览视图将在接入评测结果数据模型后展示。",
                show=False,
            )

            _show_section(dpg, shell.default_section_tag)

        _build_bottom_panel(dpg, shell)


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

    dpg.create_context()
    _bind_default_font(dpg, "ui")
    dpg.create_viewport(title=shell.title, width=shell.width, height=shell.height)

    with dpg.window(
        label=shell.title,
        tag="main_window",
        width=main_window.width,
        height=main_window.height,
        pos=main_window.pos,
        no_move=main_window.no_move,
        no_resize=main_window.no_resize,
        no_collapse=main_window.no_collapse,
        no_close=main_window.no_close,
    ):
        with dpg.group(horizontal=True):
            _build_sidebar(dpg, shell)
            _build_content_panel(dpg, shell, store)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    if hasattr(dpg, "maximize_viewport"):
        dpg.maximize_viewport()
    dpg.set_primary_window("main_window", True)
    apply_windows_viewport_title(
        getattr(dpg, "get_viewport_platform_handle", lambda: None)(),
        shell.title,
    )
    logger.info("UI initialized")

    frame_index = 0
    while dpg.is_dearpygui_running():
        if frame_index % 15 == 0:
            refresh_log_output()
        dpg.render_dearpygui_frame()
        frame_index += 1

    dpg.destroy_context()