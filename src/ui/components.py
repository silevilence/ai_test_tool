from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import dearpygui.dearpygui as dpg

from core.config import ModelConfig
from core.logger import LogEntry


@dataclass(frozen=True, slots=True)
class NavigationItem:
    label: str
    tag: str


@dataclass(frozen=True, slots=True)
class StatusBarState:
    text: str


@dataclass(frozen=True, slots=True)
class ProgressState:
    value: float
    overlay: str


@dataclass(frozen=True, slots=True)
class LogPanelState:
    expanded: bool
    panel_height: int
    log_height: int
    status_row_height: int
    toggle_label: str
    show_log_output: bool


@dataclass(frozen=True, slots=True)
class ModelConfigFormState:
    display_name: str
    base_url: str
    api_key: str
    model_name: str


@dataclass(frozen=True, slots=True)
class ModelConfigFieldSpec:
    tag: str
    label: str
    hint: str
    help_text: str
    password: bool = False


def build_navigation_items() -> tuple[NavigationItem, ...]:
    return (
        NavigationItem(label="模型配置", tag="nav_model_config"),
        NavigationItem(label="测试任务", tag="nav_test_tasks"),
        NavigationItem(label="结果概览", tag="nav_results_overview"),
    )


def build_status_state(default_value: str = "Ready") -> StatusBarState:
    return StatusBarState(text=default_value)


def build_progress_state(
    default_value: float = 0.0,
    overlay: str = "0%",
) -> ProgressState:
    return ProgressState(value=default_value, overlay=overlay)


def build_log_panel_state(expanded: bool = True) -> LogPanelState:
    if expanded:
        return LogPanelState(
            expanded=True,
            panel_height=310,
            log_height=230,
            status_row_height=28,
            toggle_label="收起日志",
            show_log_output=True,
        )

    return LogPanelState(
        expanded=False,
        panel_height=74,
        log_height=0,
        status_row_height=28,
        toggle_label="展开日志",
        show_log_output=False,
    )


def build_model_config_form_state(
    display_name: str = "",
    base_url: str = "",
    api_key: str = "",
    model_name: str = "",
) -> ModelConfigFormState:
    return ModelConfigFormState(
        display_name=display_name,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
    )


def build_model_config_field_specs() -> tuple[ModelConfigFieldSpec, ...]:
    return (
        ModelConfigFieldSpec(
            tag="config_display_name",
            label="配置名称",
            hint="例如：OpenAI Production",
            help_text="用于在工具内部区分不同配置，建议填写你能一眼认出的名字。",
        ),
        ModelConfigFieldSpec(
            tag="config_base_url",
            label="Base URL",
            hint="例如：https://api.openai.com/v1",
            help_text="填写模型服务的接口根地址；本地模型可填 http://localhost:端口/v1。",
        ),
        ModelConfigFieldSpec(
            tag="config_api_key",
            label="API Key",
            hint="粘贴模型服务提供的密钥",
            help_text="用于访问模型服务，保存到本地时会按当前系统支持方式进行保护。",
            password=True,
        ),
        ModelConfigFieldSpec(
            tag="config_model_name",
            label="Model Name",
            hint="例如：gpt-4.1-mini",
            help_text="填写接口实际使用的模型名，必须与服务端可识别的 model 参数一致。",
        ),
    )


def build_model_config_usage_notes() -> tuple[str, ...]:
    return (
        "先填写左侧四个字段，再点击“保存配置”写入本地配置库。",
        "右侧列表可用于回填编辑，选中已有配置后可修改并再次保存。",
        "删除配置前请先在右侧列表中点选目标项。",
    )


def build_model_config_list_items(
    configs: Iterable[ModelConfig],
) -> tuple[str, ...]:
    return tuple(config.display_name for config in configs)


def format_log_entries(
    entries: Iterable[LogEntry],
    empty_message: str = "No logs yet.",
) -> str:
    lines = []
    for entry in entries:
        timestamp = entry.timestamp.astimezone().strftime("%H:%M:%S")
        lines.append(
            f"[{timestamp}] {entry.level:<7} {entry.logger_name}: {entry.message}"
        )

    if not lines:
        return empty_message

    return "\n".join(lines)


def add_status_bar(
    tag: str = "status_bar",
    state: StatusBarState | None = None,
) -> str:
    active_state = state or build_status_state()
    dpg.add_text(active_state.text, tag=tag)
    return tag


def add_progress_indicator(
    tag: str = "task_progress",
    state: ProgressState | None = None,
    width: int = 260,
) -> str:
    active_state = state or build_progress_state()
    dpg.add_progress_bar(
        default_value=active_state.value,
        overlay=active_state.overlay,
        tag=tag,
        width=width,
    )
    return tag


def add_log_output(
    tag: str = "log_output",
    default_value: str = "No logs yet.",
    height: int = 360,
    show: bool = True,
) -> str:
    dpg.add_input_text(
        default_value=default_value,
        tag=tag,
        multiline=True,
        readonly=True,
        width=-1,
        height=height,
        show=show,
    )
    return tag