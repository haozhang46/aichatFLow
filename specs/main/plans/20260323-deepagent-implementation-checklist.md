# DeepAgent 接入 Implementation Checklist

## 1. 目标

将 `DeepAgent` 接入当前平台，但只替换 `agent 执行内核`，不替换平台底座。

本 checklist 用于指导实现阶段的落地顺序，直接对应现有代码位置。

## 2. 范围

### 2.1 保留

- `Agent Spec`
- `Tool Registry`
- `File Service + ACL`
- `Trace`
- `Draft / Register / Publish`

### 2.2 替换

- `OtieRuntime`
- planner / replan loop
- `POST /v1/agents/{agentId}/invoke` 的执行部分

## 3. 实施顺序

### Phase 0. 准备

- [ ] 确认 `DeepAgent` 接入方式：
  - 内部 Python package
  - 外部 service
  - adapter bridge
- [ ] 固定运行开关：
  - `runtime.engine = "otie" | "deepagent"`
- [ ] 确定首个试点 agent：
  - `story-agent`

### Phase 1. Adapter 骨架

- [ ] 新增 `app/runtime/deepagent_adapter.py`
- [ ] 定义 `DeepAgentRuntimeAdapter.invoke(...)`
- [ ] 定义 `DeepAgentInvokeRequest`
- [ ] 定义 `DeepAgentInvokeContext`
- [ ] 定义 `DeepAgentInvokeResult`

交付结果：

- 平台中存在可实例化的 adapter 骨架
- 但默认流量不切换

### Phase 2. Agent Spec 映射

- [ ] 新增 `Agent Spec -> DeepAgentConfig` 映射函数
- [ ] 映射以下字段：
  - `systemPrompt`
  - `availableTools`
  - `runtime.mode`
  - `runtime.maxSteps`
  - `memory.type`
  - `memory.root`
  - `policy.requiresUserContext`
  - `policy.allowFileAccess`
  - `policy.allowNetworkAccess`
- [ ] 对非法配置加 platform-side validation

建议位置：

- `app/services/agent_registry_service.py`
- 或新增 `app/runtime/deepagent_mapping.py`

### Phase 3. Tool Adapter

- [ ] 新增 `PlatformToolAdapter`
- [ ] 统一走 `ToolRegistry.execute`
- [ ] 自动注入：
  - `currentUserId`
  - `currentAgentId`
  - `allowedToolIds`
  - `traceId`
- [ ] 保证保留现有：
  - tool policy 校验
  - input schema 校验
  - output schema 校验

建议位置：

- `app/runtime/platform_tool_adapter.py`

### Phase 4. File Adapter

- [ ] 新增 `PlatformFileAdapter`
- [ ] 不直接暴露文件系统
- [ ] 仅包装以下平台 tool：
  - `file-list`
  - `file-read`
  - `file-write`
  - `file-delete`
  - `file-mkdir`
  - `file-patch`
- [ ] 确保沿用：
  - cookie user
  - ACL
  - `stories/` 根目录限制

建议位置：

- `app/runtime/platform_file_adapter.py`

### Phase 5. Trace Adapter

- [ ] 新增 `PlatformTraceAdapter`
- [ ] 保证事件对齐现有 trace contract
- [ ] 至少支持：
  - `run_started`
  - `step_started`
  - `step_completed`
  - `replanned`
  - `tool_call_started`
  - `tool_call_completed`
  - `tool_call_failed`
  - `run_completed`
- [ ] 额外字段统一写入 `metadata`

建议位置：

- `app/runtime/platform_trace_adapter.py`

### Phase 6. 路由接线

- [ ] 在 [unified.py](/Users/haochaoliang/Desktop/aiChatFLow/app/api/routes/unified.py) 中为 `POST /v1/agents/{agentId}/invoke` 增加 adapter 分支
- [ ] 分支条件建议为：
  - `Agent Spec.runtime.engine == "deepagent"`
- [ ] 未命中时继续 fallback 到旧实现
- [ ] 保持响应 contract 不变

### Phase 7. story-agent 试点

- [ ] 将 `story-agent` 对齐到统一 `Agent Spec`
- [ ] 为 `story-agent` 增加：
  - `runtime.engine = "deepagent"`
  - `availableTools`
  - `memory.root`
- [ ] 用 `story-agent` 验证：
  - 多步推理
  - 文件读写
  - trace 连通

### Phase 8. 兼容与回退

- [ ] 保留 `OtieRuntime` fallback
- [ ] 增加 runtime 选择日志
- [ ] 增加失败回退策略：
  - DeepAgent 失败时是否直接失败
  - 或 fallback 到 legacy runtime

## 4. 对应代码位置

### 当前主要入口

- [loop.py](/Users/haochaoliang/Desktop/aiChatFLow/app/runtime/loop.py)
- [unified.py](/Users/haochaoliang/Desktop/aiChatFLow/app/api/routes/unified.py)
- [registry.py](/Users/haochaoliang/Desktop/aiChatFLow/app/tools/registry.py)
- [files.py](/Users/haochaoliang/Desktop/aiChatFLow/app/api/routes/files.py)
- [platform_trace_service.py](/Users/haochaoliang/Desktop/aiChatFLow/app/services/platform_trace_service.py)

### 建议新增文件

- `app/runtime/deepagent_adapter.py`
- `app/runtime/deepagent_mapping.py`
- `app/runtime/platform_tool_adapter.py`
- `app/runtime/platform_file_adapter.py`
- `app/runtime/platform_trace_adapter.py`

## 5. 验收清单

### 5.1 Contract

- [ ] `AgentInvokeResponse` 不变
- [ ] trace contract 不变
- [ ] tool invoke contract 不变
- [ ] file contract 不变

### 5.2 权限

- [ ] `availableTools` 仍然生效
- [ ] tool policy 仍然生效
- [ ] 文件 ACL 仍然生效
- [ ] 用户身份仍然来自 cookie/session

### 5.3 观测

- [ ] trace 中能看到 `run_started`
- [ ] trace 中能看到 tool call
- [ ] trace 中能看到 replan
- [ ] trace 中能看到最终 `run_completed`

### 5.4 试点

- [ ] `story-agent` 能正常跑
- [ ] 文件工作区可持续使用
- [ ] 失败时可回退到旧 runtime

## 6. 风险优先级

### 高优先级

- [ ] tool 权限绕过
- [ ] 文件 ACL 绕过
- [ ] trace 不对齐
- [ ] 返回 contract 变化导致前端断裂

### 中优先级

- [ ] 双 runtime 并存增加维护成本
- [ ] `story-agent` 旧 spec 迁移成本

## 7. 建议第一个实现 PR

建议第一个 PR 只做这 4 件事：

1. 新增 `DeepAgentRuntimeAdapter` 抽象与空实现
2. 新增 `PlatformToolAdapter`
3. 新增 `PlatformTraceAdapter`
4. 在 `agent invoke` 路由增加 `deepagent` 分支开关，但默认不启用

这样可以先完成结构落点，不影响现有线上行为。

## 8. 结论

这份 checklist 的核心原则是：

- 平台继续做控制面
- DeepAgent 只替换执行面
- 所有外部能力必须通过平台 adapter 注入
- 先试点，再替换默认流量
