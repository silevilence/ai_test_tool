from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import dearpygui.dearpygui as dpg

from core.config import ModelConfig
from core.logger import LogEntry
from tests.niah_test import DEFAULT_CONTEXT_LENGTHS_MAX
from tests.niah_test import DEFAULT_CONTEXT_LENGTHS_MIN
from tests.niah_test import DEFAULT_CONTEXT_LENGTHS_NUM_INTERVALS
from tests.niah_test import DEFAULT_DOCUMENT_DEPTH_PERCENT_INTERVALS
from tests.niah_test import DEFAULT_DOCUMENT_DEPTH_PERCENT_MAX
from tests.niah_test import DEFAULT_DOCUMENT_DEPTH_PERCENT_MIN
from tests.niah_test import DEFAULT_NEEDLES
from tests.niah_test import DEFAULT_RETRIEVAL_QUESTION
from tests.niah_test import DEFAULT_SUBSET_LIST
from tests.niah_test import DEFAULT_TOKENIZER_PATH


@dataclass(frozen=True, slots=True)
class NavigationItem:
    label: str
    tag: str


@dataclass(frozen=True, slots=True)
class AppDesignPalette:
    background: str
    sidebar: str
    surface: str
    surface_alt: str
    panel: str
    accent: str
    accent_alt: str
    accent_soft: str
    success: str
    warning: str
    border: str
    text_primary: str
    text_muted: str
    console: str


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


@dataclass(frozen=True, slots=True)
class NIAHParameterSpec:
    tag: str
    label: str
    help_text: str


@dataclass(frozen=True, slots=True)
class NIAHPanelState:
    model_config_name: str
    selected_model_config_names: tuple[str, ...]
    judge_model_config_name: str
    retrieval_question: str
    needles_text: str
    context_lengths_min: int
    context_lengths_max: int
    context_lengths_num_intervals: int
    document_depth_percent_min: int
    document_depth_percent_max: int
    document_depth_percent_intervals: int
    tokenizer_path: str
    show_score: bool
    selected_subsets: tuple[str, ...]
    run_button_label: str
    status_text: str


@dataclass(frozen=True, slots=True)
class NIAHHeatmapState:
    context_lengths: tuple[int, ...]
    depth_percents: tuple[int, ...]
    values: tuple[float, ...]
    rows: int
    cols: int


@dataclass(frozen=True, slots=True)
class NIAHLayoutState:
    left_panel_width: int
    result_summary_height: int


@dataclass(frozen=True, slots=True)
class NIAHLayoutDimensions:
    left_panel_width: int
    right_panel_width: int
    top_panel_height: int
    result_summary_height: int
    heatmap_height: int


@dataclass(frozen=True, slots=True)
class SectionHeroState:
    eyebrow: str
    title: str
    description: str
    supporting_text: str


@dataclass(frozen=True, slots=True)
class OverviewMetricState:
    label: str
    value: str
    detail: str


@dataclass(frozen=True, slots=True)
class HelpDisclosureState:
    label: str
    default_open: bool
    summary_max_chars: int


def build_navigation_items() -> tuple[NavigationItem, ...]:
    return (
        NavigationItem(label="模型配置", tag="nav_model_config"),
        NavigationItem(label="测试任务", tag="nav_test_tasks"),
        NavigationItem(label="结果概览", tag="nav_results_overview"),
    )


def build_app_design_palette() -> AppDesignPalette:
    return AppDesignPalette(
        background="#0F172A",
        sidebar="#111827",
        surface="#1E293B",
        surface_alt="#334155",
        panel="#162033",
        accent="#22C55E",
        accent_alt="#38BDF8",
        accent_soft="#12352A",
        success="#22C55E",
        warning="#F59E0B",
        border="#334155",
        text_primary="#F8FAFC",
        text_muted="#94A3B8",
        console="#020617",
    )


def build_section_hero_state(section_tag: str) -> SectionHeroState:
    hero_map = {
        "nav_model_config": SectionHeroState(
            eyebrow="MODEL REGISTRY",
            title="模型配置",
            description="集中管理本地模型资产、鉴权信息与接入端点，保证联调、评测与批量执行读取同一份可信配置。",
            supporting_text="Windows 环境默认使用系统凭据保护 API Key；这里更像接入控制面，而不是普通表单。",
        ),
        "nav_test_tasks": SectionHeroState(
            eyebrow="EVAL PIPELINE",
            title="测试任务",
            description="围绕长上下文检索评测搭建串行执行控制台，突出模型选择、参数编排、进度跟踪与结果回看。",
            supporting_text="当前主任务是长上下文检索与捞针测试，适合快速比较多个模型在相同输入网格上的表现。",
        ),
        "nav_results_overview": SectionHeroState(
            eyebrow="RESULTS HUB",
            title="结果概览",
            description="这里将承接后续横向汇总与全局结果浏览能力，目前仅保留信息架构与视觉占位，不伪造业务数据。",
            supporting_text="占位视图保留为真实数据模型接入前的导航落点，避免误导用户认为该能力已经完成。",
        ),
    }
    return hero_map.get(
        section_tag,
        SectionHeroState(
            eyebrow="CONTROL CENTER",
            title="LLM API 评测工具",
            description="统一的模型接入、评测执行与结果查看工作台。",
            supporting_text="",
        ),
    )


def build_help_disclosure_state(
    label: str = "?",
    default_open: bool = False,
    summary_max_chars: int = 24,
) -> HelpDisclosureState:
    return HelpDisclosureState(label=label, default_open=default_open, summary_max_chars=summary_max_chars)


def summarize_help_text(text: str, max_chars: int = 24) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars].rstrip()}..."


def build_status_state(default_value: str = "Ready") -> StatusBarState:
    return StatusBarState(text=default_value)


def build_progress_state(
    default_value: float = 0.0,
    overlay: str = "0%",
) -> ProgressState:
    return ProgressState(value=default_value, overlay=overlay)


def build_log_panel_state(expanded: bool = False) -> LogPanelState:
    if expanded:
        return LogPanelState(
            expanded=True,
            panel_height=236,
            log_height=156,
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


def build_niah_panel_state(
    model_config_name: str = "",
    selected_model_config_names: tuple[str, ...] = (),
    judge_model_config_name: str = "",
    retrieval_question: str = DEFAULT_RETRIEVAL_QUESTION,
    needles_text: str = "\n".join(DEFAULT_NEEDLES),
    context_lengths_min: int = DEFAULT_CONTEXT_LENGTHS_MIN,
    context_lengths_max: int = DEFAULT_CONTEXT_LENGTHS_MAX,
    context_lengths_num_intervals: int = DEFAULT_CONTEXT_LENGTHS_NUM_INTERVALS,
    document_depth_percent_min: int = DEFAULT_DOCUMENT_DEPTH_PERCENT_MIN,
    document_depth_percent_max: int = DEFAULT_DOCUMENT_DEPTH_PERCENT_MAX,
    document_depth_percent_intervals: int = DEFAULT_DOCUMENT_DEPTH_PERCENT_INTERVALS,
    tokenizer_path: str = DEFAULT_TOKENIZER_PATH,
    show_score: bool = False,
    selected_subsets: tuple[str, ...] = DEFAULT_SUBSET_LIST,
    run_button_label: str = "运行捞针测试",
    status_text: str = "配置完成后即可运行捞针测试。",
) -> NIAHPanelState:
    return NIAHPanelState(
        model_config_name=model_config_name,
        selected_model_config_names=selected_model_config_names,
        judge_model_config_name=judge_model_config_name,
        retrieval_question=retrieval_question,
        needles_text=needles_text,
        context_lengths_min=context_lengths_min,
        context_lengths_max=context_lengths_max,
        context_lengths_num_intervals=context_lengths_num_intervals,
        document_depth_percent_min=document_depth_percent_min,
        document_depth_percent_max=document_depth_percent_max,
        document_depth_percent_intervals=document_depth_percent_intervals,
        tokenizer_path=tokenizer_path,
        show_score=show_score,
        selected_subsets=selected_subsets,
        run_button_label=run_button_label,
        status_text=status_text,
    )


def build_niah_parameter_specs() -> tuple[NIAHParameterSpec, ...]:
    return (
        NIAHParameterSpec(
            tag="niah_model_config_list",
            label="待测模型配置（可多选）",
            help_text="勾选一个或多个需要接受 NIAH 评测的模型配置；批量任务会保持其他参数不变，仅替换这里选中的模型。",
        ),
        NIAHParameterSpec(
            tag="niah_judge_model_config_list",
            label="裁判模型配置",
            help_text="选择负责判定答案是否命中 needle 的裁判模型；它不会参与生成，只负责打分。",
        ),
        NIAHParameterSpec(
            tag="niah_retrieval_question",
            label="检索问题",
            help_text="最终会对长上下文提出的检索问题，模型是否能准确找回 needle 由这个问题决定。",
        ),
        NIAHParameterSpec(
            tag="niah_needles_text",
            label="Needles",
            help_text="每行一个待插入上下文的事实。评测时 EvalScope 会把这些事实埋到长文本不同深度位置。",
        ),
        NIAHParameterSpec(
            tag="niah_tokenizer_path",
            label="Tokenizer Path",
            help_text="用于计算上下文 token 长度的 tokenizer 名称或路径，必须和目标模型的分词行为尽量接近。",
        ),
        NIAHParameterSpec(
            tag="niah_context_lengths_num_intervals",
            label="上下文长度区间",
            help_text="最小、最大 Token 长度和区间数共同决定会生成多少档上下文长度样本。",
        ),
        NIAHParameterSpec(
            tag="niah_document_depth_percent_intervals",
            label="文档深度区间",
            help_text="最小、最大深度和区间数共同决定 needle 会被插入到文档哪些位置。",
        ),
        NIAHParameterSpec(
            tag="niah_subset_english",
            label="语料与显示选项",
            help_text="可分别评测英文和中文语料，并决定热力图是否直接显示数值分数。",
        ),
    )


def build_niah_heatmap_state(
    points: Iterable[tuple[int, int, float]] = (),
) -> NIAHHeatmapState:
    normalized_points = list(points)
    if not normalized_points:
        return NIAHHeatmapState(
            context_lengths=(0,),
            depth_percents=(0,),
            values=(0.0,),
            rows=1,
            cols=1,
        )

    context_lengths = tuple(sorted({context_length for context_length, _depth_percent, _value in normalized_points}))
    depth_percents = tuple(sorted({depth_percent for _context_length, depth_percent, _value in normalized_points}))
    point_lookup = {
        (context_length, depth_percent): value
        for context_length, depth_percent, value in normalized_points
    }

    values = tuple(
        float(point_lookup.get((context_length, depth_percent), 0.0))
        for context_length in context_lengths
        for depth_percent in depth_percents
    )
    return NIAHHeatmapState(
        context_lengths=context_lengths,
        depth_percents=depth_percents,
        values=values,
        rows=len(context_lengths),
        cols=len(depth_percents),
    )


def build_niah_layout_state(
    left_panel_width: int = 520,
    result_summary_height: int = 150,
) -> NIAHLayoutState:
    return NIAHLayoutState(
        left_panel_width=left_panel_width,
        result_summary_height=result_summary_height,
    )


def build_niah_column_weights() -> tuple[float, float]:
    return (1.55, 1.0)


def resolve_niah_layout_dimensions(
    layout_state: NIAHLayoutState,
    container_width: int,
    top_panel_height: int,
    horizontal_padding: int = 16,
    splitter_width: int = 10,
    result_splitter_height: int = 10,
    right_panel_chrome_height: int = 80,
    min_left_panel_width: int = 320,
    min_right_panel_width: int = 360,
    min_result_summary_height: int = 120,
    min_heatmap_height: int = 180,
) -> NIAHLayoutDimensions:
    available_width = max(
        min_left_panel_width + splitter_width + min_right_panel_width,
        container_width - horizontal_padding,
    )
    max_left_panel_width = max(
        min_left_panel_width,
        available_width - splitter_width - min_right_panel_width,
    )
    left_panel_width = min(max(layout_state.left_panel_width, min_left_panel_width), max_left_panel_width)
    right_panel_width = available_width - splitter_width - left_panel_width

    available_result_height = max(
        min_result_summary_height + result_splitter_height + min_heatmap_height,
        top_panel_height - right_panel_chrome_height,
    )
    max_result_summary_height = max(
        min_result_summary_height,
        available_result_height - result_splitter_height - min_heatmap_height,
    )
    result_summary_height = min(
        max(layout_state.result_summary_height, min_result_summary_height),
        max_result_summary_height,
    )
    heatmap_height = available_result_height - result_splitter_height - result_summary_height

    return NIAHLayoutDimensions(
        left_panel_width=left_panel_width,
        right_panel_width=right_panel_width,
        top_panel_height=top_panel_height,
        result_summary_height=result_summary_height,
        heatmap_height=heatmap_height,
    )


def build_niah_overview_metrics(
    selected_model_names: tuple[str, ...] = (),
    judge_model_name: str = "",
    expected_sample_count: int | None = None,
    show_score: bool = False,
) -> tuple[OverviewMetricState, ...]:
    selected_models_value = f"{len(selected_model_names)} 个"
    selected_models_detail = ", ".join(selected_model_names) if selected_model_names else "尚未选择待测模型"
    judge_value = judge_model_name or "未设置"
    judge_detail = "用于判定是否命中 needle 的裁判模型"
    samples_value = str(expected_sample_count) if expected_sample_count is not None else "--"
    samples_detail = "由上下文长度区间、深度区间与语料子集共同决定"
    heatmap_value = "显示分数" if show_score else "仅颜色"
    heatmap_detail = "切换热力图数值叠加，便于快速扫读或精确比较"

    return (
        OverviewMetricState(
            label="待测模型",
            value=selected_models_value,
            detail=selected_models_detail,
        ),
        OverviewMetricState(
            label="裁判模型",
            value=judge_value,
            detail=judge_detail,
        ),
        OverviewMetricState(
            label="预计样本",
            value=samples_value,
            detail=samples_detail,
        ),
        OverviewMetricState(
            label="热力图",
            value=heatmap_value,
            detail=heatmap_detail,
        ),
    )


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