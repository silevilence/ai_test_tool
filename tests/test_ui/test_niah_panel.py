from __future__ import annotations

from ui.app import read_evalscope_progress_state
from ui.components import build_niah_heatmap_state
from ui.components import build_niah_layout_state
from ui.components import build_niah_parameter_specs
from ui.components import build_niah_panel_state
from ui.components import resolve_niah_layout_dimensions


def test_build_niah_panel_state_exposes_expected_defaults() -> None:
    state = build_niah_panel_state()

    assert state.model_config_name == ""
    assert state.selected_model_config_names == ()
    assert state.judge_model_config_name == ""
    assert state.retrieval_question == "What is the best thing to do in San Francisco?"
    assert state.needles_text.startswith("The best thing to do in San Francisco")
    assert state.context_lengths_min == 1000
    assert state.context_lengths_max == 32000
    assert state.context_lengths_num_intervals == 10
    assert state.document_depth_percent_min == 0
    assert state.document_depth_percent_max == 100
    assert state.document_depth_percent_intervals == 10
    assert state.tokenizer_path == "Qwen/Qwen3-0.6B"
    assert state.show_score is False
    assert state.selected_subsets == ("english", "chinese")
    assert state.run_button_label == "运行捞针测试"
    assert state.status_text == "配置完成后即可运行捞针测试。"


def test_build_niah_heatmap_state_builds_dense_matrix_from_sparse_points() -> None:
    heatmap = build_niah_heatmap_state(
        points=[
            (1000, 0, 1.0),
            (1000, 50, 0.8),
            (4000, 50, 0.2),
        ]
    )

    assert heatmap.context_lengths == (1000, 4000)
    assert heatmap.depth_percents == (0, 50)
    assert heatmap.values == (1.0, 0.8, 0.0, 0.2)
    assert heatmap.rows == 2
    assert heatmap.cols == 2


def test_resolve_niah_layout_dimensions_clamps_width_and_height() -> None:
    layout_state = build_niah_layout_state(left_panel_width=900, result_summary_height=999)

    dimensions = resolve_niah_layout_dimensions(
        layout_state,
        container_width=1100,
        top_panel_height=430,
    )

    assert dimensions.left_panel_width == 714
    assert dimensions.right_panel_width == 360
    assert dimensions.result_summary_height == 160
    assert dimensions.heatmap_height == 180


def test_build_niah_parameter_specs_exposes_help_text() -> None:
    specs = build_niah_parameter_specs()
    spec_map = {spec.tag: spec for spec in specs}

    assert spec_map["niah_retrieval_question"].label == "检索问题"
    assert "最终会对长上下文提出的检索问题" in spec_map["niah_retrieval_question"].help_text
    assert "niah_context_lengths_num_intervals" in spec_map
    assert "裁判模型" in spec_map["niah_judge_model_config_list"].help_text


def test_read_evalscope_progress_state_reads_tracker_file(tmp_path) -> None:
    progress_path = tmp_path / "progress.json"
    progress_path.write_text(
        '{"status": "running", "pipeline": "eval", "total_count": 100, "processed_count": 10, "percent": 10.0}',
        encoding="utf-8",
    )

    progress_state = read_evalscope_progress_state(tmp_path)

    assert progress_state == {
        "status": "running",
        "pipeline": "eval",
        "total_count": 100,
        "processed_count": 10,
        "percent": 10.0,
    }
