# AI Agent Development Instructions

## 1. Project Positioning

你正在协助开发 ai_test_tool，一个基于 Python 的桌面化 LLM API 测试与评测工具。

- 目标用户是需要对接、测试和对比不同模型 API 的个人开发者。
- 当前前端使用 DearPyGui。
- 当前评测执行依赖 EvalScope。
- 当前已落地的核心能力是模型配置管理和 Needle-In-A-Haystack 捞针测试。

本文件面向 AI Agent，重点提供约束、架构边界、实现约定和修改策略。

## 2. Critical Constraints

- 严禁主动修改文档，除非用户明确要求。文档包括 README.md、ROADMAP.md 和本文件。
- 严禁引入未经用户批准的新依赖。只允许使用 Python 标准库和 pyproject.toml 中已声明的依赖。
- 包管理和运行工具只能使用 uv，禁止使用 pip、conda 或 poetry。
- 代码基底必须保持英文命名。变量名、函数名、类名、测试名、注释和提交信息都必须使用英文。DearPyGui 的界面展示文本可以使用中文。
- 不要将占位功能写成已实现功能。尤其是“结果概览”页面当前仍是占位视图。
- 修改时优先保持现有公开行为稳定，避免无关重构。

## 3. Current Tech Stack

- Python 3.12+
- DearPyGui 2.3+
- EvalScope 1.6+
- pytest 作为测试框架
- Windows 是主要开发与验证环境

## 4. Required Workflow

本项目遵循 TDD，默认流程必须是：

1. Red：先写或先改失败测试，明确目标行为。
2. Green：编写最小实现使测试通过。
3. Refactor：在测试保护下再整理结构。

如果任务本身是纯文档更新、纯说明梳理或纯调查，则不强行补测试；但只要涉及业务代码、UI 行为或策略逻辑，就必须优先遵守 TDD。

## 5. Command Rules

始终使用以下命令规范：

- 同步环境：`uv sync`
- 运行测试：`uv run pytest`
- 运行程序：`uv run src/main.py`
- 添加依赖：`uv add <package_name>`，但必须先获得用户批准

不要使用其他包管理命令替代以上流程。

## 6. Actual Project Structure

当前仓库结构以现状为准，新增功能时不得绕开既有分层：

```text
ai_test_tool/
├── src/
│   ├── main.py
│   ├── ai_test_tool/
│   │   └── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── logger.py
│   │   └── runner.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── base_strategy.py
│   │   └── niah_test.py
│   └── ui/
│       ├── __init__.py
│       ├── app.py
│       └── components.py
├── tests/
│   ├── conftest.py
│   ├── test_core/
│   ├── test_eval_strategies/
│   └── test_ui/
├── outputs/
├── pyproject.toml
├── README.md
└── ROADMAP.md
```

额外约定：

- `tests/conftest.py` 负责将 `src` 加入导入路径。
- 程序入口是 `src/main.py`。
- 包入口 `src/ai_test_tool/__init__.py` 当前仅转发 `main`。

## 7. Layer Responsibilities

### UI Layer

UI 相关代码放在 `src/ui/`：

- `app.py` 负责主窗口、页面切换、回调绑定、任务状态同步和结果展示。
- `components.py` 负责纯 UI 状态对象、表单字段规格、默认值和简单展示辅助函数。

约束：

- UI 主线程绝不能执行阻塞式模型调用。
- UI 层只负责采集参数、触发任务、展示状态，不直接承载复杂评测逻辑。
- UI 新增表单项时，必须同时考虑默认值、帮助文本、读取逻辑和测试覆盖。

### Core Layer

核心能力放在 `src/core/`：

- `config.py` 负责模型配置存储与本地密钥保护。
- `logger.py` 提供线程安全的共享内存日志 Sink。
- `runner.py` 提供后台任务调度与状态快照。

约束：

- 配置持久化逻辑不要散落到 UI 中。
- 新的后台任务机制应复用 `TaskRunner`，而不是各自启动不可控线程。
- 共享日志应继续通过 `get_logger` / `attach_external_logger` 进入统一日志面板。

### Eval Strategy Layer

评测策略放在 `src/tests/`：

- `base_strategy.py` 定义统一抽象 `BaseEvalStrategy` 和标准结果结构 `EvalResult`。
- `niah_test.py` 是当前已实现的捞针测试策略。

约束：

- 新增评测类型必须继承 `BaseEvalStrategy`。
- `prepare()` 负责配置构建与前置校验。
- `execute()` 负责实际评测调用。
- `get_results()` 返回的结果结构必须稳定，供 UI 和 Runner 消费。

## 8. Current Implemented Behavior

AI Agent 在修改代码时，必须以当前真实行为为准：

- 已支持模型配置的新增、回填、删除和持久化。
- 配置文件默认保存到 `%APPDATA%/ai_test_tool/model_configs.json`。
- Windows 下 API Key 默认使用 DPAPI 加密；非 Windows 下使用明文回退实现。
- 已支持 NIAH 面板参数输入、运行按钮、后台执行、进度轮询、结果摘要、热力图和 HTML 报告打开。
- 已支持通过 EvalScope `progress.json` 轮询运行进度。
- “结果概览”页面目前尚未接入真实数据模型，仅为占位提示。

## 9. Stable Contracts You Must Preserve

以下契约已经被 UI 或测试依赖，修改时必须谨慎：

### ModelConfigStore contract

- `ModelConfig` 包含 `display_name`、`base_url`、`api_key`、`model_name`。
- `ModelConfigStore` 提供 `upsert`、`remove`、`get`、`list_all`。

### TaskRunner contract

- `submit_strategy(task_id, strategy)` 用于提交评测任务。
- `TaskSnapshot` 至少包含 `task_id`、`strategy_name`、`status`、`result`、`error_message`。
- 状态流当前依赖 `queued -> preparing -> running -> completed/failed/cancelled`。

### EvalResult contract

- `EvalResult` 统一包含 `status`、`metrics`、`artifacts`、`error_message`。
- 不要随意改动字段名或返回类型。

### NIAH result contract

`NeedleInHaystackStrategy` 归一化后，UI 当前依赖以下字段：

- `metrics["acc"]`
- `metrics["sample_count"]`
- `artifacts["outputs_dir"]`
- `artifacts["heatmap_path"]`
- `artifacts["report_html_path"]`
- `artifacts["heatmap"]`
- `artifacts["summary"]`

如果改变这些字段，需要同步修改 UI 和测试。

## 10. Output And EvalScope Integration Rules

- 默认工作目录是 `./outputs`。
- NIAH 策略会依赖 EvalScope 输出目录中的 `progress.json`、`reports/report.html` 等文件。
- 如果修改 EvalScope 对接层，必须保证现有路径解析逻辑仍然可用，或同步更新 UI 展示和测试。
- 在图形环境中运行 EvalScope 时，必须继续保持非交互式 Matplotlib 后端配置，避免阻塞或弹窗。

## 11. Testing Expectations

已有测试按职责分布：

- `tests/test_core/`：配置存储、任务调度等核心逻辑。
- `tests/test_eval_strategies/`：NIAH 策略参数组装与结果归一化。
- `tests/test_ui/`：UI 默认状态、参数面板、帮助文本与部分应用层行为。

新增或修改功能时：

- Core 逻辑改动优先补 `tests/test_core/`。
- 策略行为改动优先补 `tests/test_eval_strategies/`。
- UI 状态、默认值、帮助文本、参数读取逻辑改动优先补 `tests/test_ui/`。

## 12. Implementation Guidance For Future Changes

### 新增评测类型时

- 在 `src/tests/` 中新增策略类，继承 `BaseEvalStrategy`。
- 在策略内部完成参数对象化、校验、EvalScope 或自定义执行逻辑封装。
- 在 UI 中增加独立面板或参数区域，但不要把策略执行细节写死在 UI 回调里。

### 修改模型配置功能时

- 保持存储格式兼容，避免无迁移地破坏已有本地配置文件。
- 涉及密钥处理时，优先沿用 `SecretCipher` 抽象。

### 修改日志或进度展示时

- 保持共享日志 Sink 的线程安全。
- 保持后台任务状态与 UI 展示的一致性。

## 13. Non-Goals For The Agent

以下内容不要擅自推进：

- 不要擅自新增复杂配置系统或数据库。
- 不要将现有 DearPyGui UI 重写为 Web UI。
- 不要把未完成的“结果概览”做成伪实现或假数据展示。
- 不要为了“更整洁”而大规模改动 import 路径、目录层级或模块命名。

## 14. Definition Of A Good Change

一个合格的改动应同时满足：

- 与当前架构一致。
- 不阻塞 UI 主线程。
- 不破坏现有策略、任务快照和结果数据契约。
- 有对应测试，或在纯文档任务中至少保证内容与当前实现一致。
- 不引入未经批准的依赖。