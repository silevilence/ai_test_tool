# AI Agent Development Instructions

## 1. Project Overview
你正在协助开发一个基于 Python 的个人大模型接口（LLM API）测试与比对工具（ai_test_tool）。
- **核心功能**: 测试、评估和比对不同大模型 API（如本地部署、OpenAI、DeepSeek 等）的性能与能力。
- **前端框架**: `DearPyGui` (轻量级、高性能 GUI)
- **后端评估**: `EvalScope` (大模型评估框架) 及自定义测试脚本。

## 2. Core Constraints & Prohibitions (CRITICAL)
- **严禁主动修改文档**: 除非用户明确发出指令，否则你**绝对不可**主动修改或更新 `README.md`、`ROADMAP.md` 和本文件 `copilot-instructions.md`。
- **严禁引入未经批准的依赖**: 必须仅使用 Python 标准库和 `uv` 中指定的依赖。如需新包，必须先询问用户。
- **纯英文代码基底**: 所有变量名、函数名、类名、注释和提交信息 (Commit Message) 必须使用英文。UI 显示文字 (DearPyGui 标签) 可以使用中文。

## 3. Development Workflow (TDD)
本项目严格遵循测试驱动开发 (Test-Driven Development) 流程。你必须在编写功能代码前编写测试：
1. **Red**: 针对需求编写失败的 `pytest` 测试用例。
2. **Green**: 编写刚好能让测试通过的最小可行产品 (MVP) 业务代码。
3. **Refactor**: 在测试覆盖下重构代码，优化设计。

## 4. Package & Environment Management (uv)
本项目使用 `uv` 作为唯一且核心的 Python 包管理器和运行工具。你必须使用以下命令规范：
- **初始化项目**: `uv init`
- **安装依赖**: `uv add <package_name>` (例如: `uv add dearpygui evalscope pytest`)
- **运行测试**: `uv run pytest`
- **运行主程序**: `uv run src/main.py`
- **同步环境**: `uv sync`

*注意: 永远不要使用 `pip` 或 `conda`。*

## 5. Project Structure
严格保持以下项目结构，业务逻辑与 UI 层必须解耦：

```text
llm-eval-tool/
├── src/
│   ├── main.py              # 程序入口点
│   ├── ui/                  # DearPyGui 前端视图层
│   │   ├── __init__.py
│   │   ├── app.py           # GUI 主窗体逻辑
│   │   └── components.py    # 可复用的 UI 组件
│   ├── core/                # 核心业务逻辑 (API调用、EvalScope集成)
│   │   ├── __init__.py
│   │   ├── config.py        # 模型API配置管理
│   │   └── runner.py        # 异步任务调度 (多线程)
│   └── tests/               # 评测项目实现目录
│       ├── __init__.py
│       ├── base_strategy.py # 测试策略接口 (Strategy Pattern)
│       └── niah_test.py     # 捞针测试具体实现
├── tests/                   # 单元测试 (pytest)
│   ├── test_core/
│   ├── test_ui/
│   └── test_eval_strategies/
├── pyproject.toml           # uv 配置文件
└── ROADMAP.md               # 项目开发路线图
```

## 6. Design Patterns & Architecture
- **UI 非阻塞**: DearPyGui 主线程决不能被阻塞。所有 API 调用和 EvalScope 测试任务必须在 `threading` 后台线程中执行，通过队列 (`queue`) 或回调机制更新 UI 状态。
- **策略模式 (Strategy Pattern)**: 针对不同的测试任务（如基础跑分、捞针测试、API延迟测试），必须在 `src/tests/base_strategy.py` 中定义统一的基类/接口。所有新的测试类型必须继承该接口，以保证系统的高可扩展性。