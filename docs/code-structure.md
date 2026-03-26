# 项目代码结构

这个项目可以按 4 层理解：API 层、执行层、基础服务层、前端展示层。

## 1. 根目录

- `app/`: 后端主代码
- `chatui-taiwild/`: 前端主代码
- `tests_py/`: Python 测试
- `data/`: 数据和注册表
- `docs/`: 文档
- `README.md`: 项目说明
- `OTIE_PRD_v1.md`: OTIE 设计文档

## 2. 后端 `app/`

### `app/api/routes`

HTTP 路由入口层。

- `unified.py`: 统一 chat 执行、plan、stream、agent invoke 的主入口
- `otie.py`: OTIE 专用接口
- `files.py`: 文件接口
- `file_acl.py`: 文件权限接口
- `rag.py`: RAG 检索接口
- `routes.py`: provider route 配置接口
- `health.py`: 健康检查

### `app/runtime`

执行时核心。

- `loop.py`: OTIE step loop，按 `tool / reason / respond` 顺序执行
- `deepagent_adapter.py`: DeepAgent tool loop，执行 `tool_call -> tool_result -> next round`
- `platform_tool_adapter.py`: 平台工具适配
- `platform_file_adapter.py`: 平台文件适配
- `platform_trace_adapter.py`: 平台 trace 适配

### `app/planner`

意图识别和计划生成。

- `intent_service.py`: 把请求归一化成 intent
- `planner_service.py`: 自动生成 execution plan，并补 weather、web-fetch、retrieval 等工具 step

### `app/orchestrator`

LLM 编排层。

- `graph.py`: `run_orchestrator()` 和 plan context 生成入口

### `app/tools`

工具定义和注册。

- `builtin.py`: 内置工具定义，如 `weather`、`find-skills`
- `registry.py`: 工具注册和执行入口
- `base.py`: 工具基类

### `app/services`

业务服务层。

- `execution_steps.py`: 归一化前端传来的 `executionPlan / confirmedPlan / stepExecutions`
- `capability_service.py`: capability 和 skill 推荐
- `skill_executor_service.py`: skill 执行
- `tool_executor_adapter_service.py`: tool 执行适配
- `tool_definition_registry_service.py`: tool 定义管理
- `tool_policy_service.py`: 工具白名单和黑名单
- `trace_store.py`: trace 存储和敏感字段脱敏
- `platform_trace_service.py`: 平台级 trace 事件
- `agent_registry_service.py`: 自定义 agent 注册
- `plan_record_service.py`: plan record 存储
- `rag_service.py`: 检索服务
- `routing.py`: provider 路由决策
- `executor.py`: workflow/provider 执行器

### 其他目录

- `contracts/`: OTIE 内部契约，如 `ExecutionPlan`、`PlanStep`
- `schemas/`: API schema
- `policy/`: 运行时策略控制
- `memory/`: plan store 等轻量存储
- `observability/`: OTIE trace 观测
- `core/`: 配置和基础设置

## 3. 前端 `chatui-taiwild/`

### `src/app`

- `page.tsx`: 主页面入口，请求调度、状态管理、执行流展示的核心文件
- `layout.tsx`: 应用布局
- `globals.css`: 全局样式

### `src/app/components`

页面级组件和弹窗。

- `TraceModal.tsx`: trace 查看
- `PlanDetailModal.tsx`: plan 详情
- `PlanRecordModal.tsx`: plan record 查看
- `CapabilityModal.tsx`: capability 弹窗
- `ToolPlaygroundModal.tsx`: tool playground
- `AgentPlaygroundModal.tsx`: agent playground
- `RagViewerModal.tsx`: RAG 查看
- `SettingsModal.tsx`: 设置弹窗
- `DeepseekModal.tsx`: LLM 配置弹窗
- `toolPlugins.tsx`: 工具结果渲染插件

### `src/components`

通用业务组件。

- `TaskFlowModal.tsx`: React Flow 任务流图
- `chat/ChatPanel.tsx`: 聊天面板
- `ui/`: 通用 UI 组件

## 4. 当前最关键的主链路

如果你主要关注 `chat -> tool -> stream`，优先看这几个文件：

1. `app/api/routes/unified.py`
2. `app/services/execution_steps.py`
3. `app/planner/planner_service.py`
4. `app/runtime/loop.py`
5. `app/runtime/deepagent_adapter.py`
6. `app/tools/builtin.py`
7. `chatui-taiwild/src/app/page.tsx`
8. `chatui-taiwild/src/components/TaskFlowModal.tsx`

## 5. 一句话总结

后端主链路是：

`unified route -> normalize steps -> plan/runtime -> tools/trace`

前端主链路是：

`page -> stream consume -> modal/panel render`
