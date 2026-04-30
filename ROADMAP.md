# LLM API 评测工具开发路线图

## 计划中 (Planned)

- [ ] **代码质量与架构治理**
    - [ ] 实施架构健康度评估：审查系统扩展性与可维护性，划定重构边界并输出技术改造蓝图
    - [ ] 执行性能基线审计：量化核心链路资源开销与运行效率，沉淀系统专项调优策略
    - [ ] 设置变更审批门禁：提交专项治理方案供用户/业务方评审，获准后启动实质性代码改造
    - [ ] 强化静态类型防御：补全全局 Type Hint 约束，清零 Pylance 诊断异常，提升运行鲁棒性
    - [ ] 推进工程代码规约：统一全局编码风格规范，优化代码语义表达，保障项目长效可读性

## 开发中 (In Progress)

- [ ] **UI 视觉重构与体验升级**
    - [ ] 制定视觉规范：确立科技主题设计语言，并全面应用深色模式（Dark Mode）
    - [ ] 优化视图呈现：提升全局 UI 组件的渲染表现力与视觉交互细节
    - [ ] 落实回归约束：确保视图层改造与存量业务逻辑完全解耦，保障核心功能无损升级

## 已完成 (Completed)

- [x] **建立项目框架**
    - [x] 初始化项目结构与环境
        - 使用 `uv init` 创建标准工程骨架
        - 配置 `pyproject.toml`
        - 添加基础依赖: `pytest`, `dearpygui`, `evalscope`
    - [x] 搭建 TDD 测试脚手架
        - 编写第一个连通性测试 (Sanity test)
        - 确保 `uv run pytest` 可以正常捕获并在 CI 环境/本地执行
    - [x] 设定统一日志模块
        - 实现线程安全的日志记录器
        - 为 UI 层和后台任务提供统一的 Log 接口

- [x] **实现基础 UI (DearPyGui)**
    - [x] 搭建主窗口骨架
        - 初始化 DPG 上下文，设置中文字体支持
        - 划分主界面布局 (左侧菜单导航，右侧内容区)
    - [x] 实现基础组件
        - 状态栏 (Status Bar) 与进度条指示器
        - 滚动日志输出框 (实时抓取后台日志并显示)
    - [x] 模型 API 配置面板
        - 支持添加、编辑、删除不同模型的 API 凭证 (Base URL, API Key, Model Name)
        - 确保证书在本地的安全存取机制

- [x] **为测试项目设计策略模式接口 (核心解耦)**
    - [x] 定义 `BaseEvalStrategy` 接口类
        - 规范输入参数 (Model config, Test parameters)
        - 规范生命周期方法 (`prepare()`, `execute()`, `get_results()`, `cancel()`)
    - [x] 实现任务调度器 (`TaskRunner`)
        - 利用 `threading` 实现后台队列执行
        - 实现任务状态回调机制 (通知 UI 更新进度)
    - [x] 实现评估结果标准数据模型
        - 统一各类测试输出的数据结构，方便 UI 进行表格或图表渲染

- [x] **实现捞针测试 (Needle-In-A-Haystack, NIAH)**
    - [x] 编写 EvalScope 捞针任务适配器 (`NIAHStrategy`)
        - 继承 `BaseEvalStrategy` 接口
        - 实现 `TaskConfig` 的参数组装逻辑，支持 `datasets=['needle_haystack']`
        - 封装 `dataset_args` 中特有参数 (`context_lengths_min/max`, `intervals`, `tokenizer_path` 等)
        - 功能文档参考： `https://evalscope.readthedocs.io/zh-cn/latest/third_party/needle_haystack.html`
    - [x] 设计裁判模型 (Judge Model) 配置模块
        - 为捞针测试配置独立的裁判模型凭证（如使用 Qwen-Max 或 GPT-4o 作为判定结果的裁判）
        - 封装 `judge_model_args` 参数逻辑
    - [x] 编写捞针测试适配器用例 (TDD)
        - 测试配置字典的生成是否符合 EvalScope 的标准 API 要求
        - 编写模拟返回结果解析的单元测试
    - [x] 实现捞针测试 UI 面板 (DearPyGui)
        - **基础参数区**: 提供输入框设置 `retrieval_question` (提问) 和多行文本设置 `needles` (插入的针)
        - **维度控制区**: 提供滑块或输入框设置 Token 长度区间 (Min/Max/Intervals) 和文档深度区间 (Depth %)
        - **执行与展示区**: 
            - 提供独立运行按钮与进度状态提示
            - 提取 EvalScope 跑完后的结果数据，利用 DearPyGui 绘制标准的捞针结果热力图 (Heatmap)

- [x] **多模型批量评测支持**
    - [x] 提供前置配置交互，支持批量勾选并加载多个目标评估模型
    - [x] 构建标准化串行调度队列，在锁定其他测试变量（仅替换模型配置）的前提下依次执行评测任务
    - [x] 集成 `evalscope` 汇总模块，于队列任务末端自动聚合产出多模型横向对比报告
